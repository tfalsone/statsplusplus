"""Hermetic tests for scripts/release.py and the discord_post embed path."""

import json
import subprocess
import sys
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import discord_post
import release

NOTES = "# Shiny thing\n- First highlight.\n- Second highlight.\n"


def _git(cwd, *a):
    subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    """Temp repo on main with a bare origin, pyproject and whats_new.json."""
    origin = tmp_path / "origin.git"
    work = tmp_path / "work"
    work.mkdir()
    _git(tmp_path, "init", "--bare", "-b", "main", str(origin))
    _git(work, "init", "-b", "main")
    _git(work, "config", "user.email", "t@t")
    _git(work, "config", "user.name", "t")
    (work / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "1.2.3"\n')
    (work / "docs").mkdir()
    (work / "docs" / "whats_new.json").write_text(json.dumps({"_comment": "c", "versions": [
        {"version": "1.2.3", "date": "2026-01-01", "title": "old", "highlights": ["a"]}]}, indent=2))
    (work / "notes.md").write_text(NOTES)
    (work / ".gitignore").write_text("/data/\n")
    _git(work, "add", ".")
    _git(work, "commit", "-m", "init")
    _git(work, "remote", "add", "origin", str(origin))
    _git(work, "push", "-u", "origin", "main")
    return work


def _args(repo, **kw):
    ns = dict(bump="minor", notes_file=str(repo / "notes.md"), title=None, branch="main",
              skip_checks=True, dry_run=False)
    ns.update(kw)
    return MagicMock(**ns)


@pytest.mark.parametrize("kind,expected", [("patch", "1.2.4"), ("minor", "1.3.0"), ("major", "2.0.0")])
def test_bump_version(kind, expected):
    assert release.bump_version("1.2.3", kind) == expected


def test_parse_notes_title_and_bullets():
    assert release.parse_notes(NOTES) == ("Shiny thing", ["First highlight.", "Second highlight."])
    assert release.parse_notes("- x", title="T") == ("T", ["x"])
    with pytest.raises(SystemExit):
        release.parse_notes("- no title")


def test_dry_run_changes_nothing(repo, capsys):
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True)
    release.prepare(_args(repo, dry_run=True), root=repo)
    out = capsys.readouterr().out
    assert "bump pyproject.toml 1.2.3 -> 1.3.0" in out and "annotated tag v1.3.0" in out
    assert 'version = "1.2.3"' in (repo / "pyproject.toml").read_text()
    assert subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True) == head
    assert subprocess.check_output(["git", "tag"], cwd=repo, text=True) == ""


def test_prepare_commits_tags_and_does_not_push(repo, capsys):
    release.prepare(_args(repo), root=repo)
    assert 'version = "1.3.0"' in (repo / "pyproject.toml").read_text()
    top = json.loads((repo / "docs" / "whats_new.json").read_text())["versions"][0]
    assert top["version"] == "1.3.0" and top["title"] == "Shiny thing" and len(top["highlights"]) == 2
    tag_msg = subprocess.check_output(["git", "tag", "-n99", "v1.3.0"], cwd=repo, text=True)
    assert "First highlight." in tag_msg
    assert subprocess.check_output(["git", "status", "--porcelain"], cwd=repo, text=True) == ""
    assert subprocess.run(["git", "rev-parse", "origin/main"], cwd=repo, capture_output=True,
                          text=True).stdout != subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True)
    assert "git push origin v1.3.0" in capsys.readouterr().out


def test_prepare_refuses_dirty_tree_and_wrong_branch(repo):
    (repo / "junk.txt").write_text("x")
    _git(repo, "add", "junk.txt")
    with pytest.raises(SystemExit):
        release.prepare(_args(repo), root=repo)
    with pytest.raises(SystemExit):
        release.prepare(_args(repo, branch="nope"), root=repo)
    assert subprocess.check_output(["git", "tag"], cwd=repo, text=True) == ""


def test_untracked_ignored_posts_file_does_not_block(repo, capsys):
    (repo / "data").mkdir()
    (repo / "data" / "discord_posts.json").write_text("{}")
    release.prepare(_args(repo, dry_run=True), root=repo)
    assert "not clean" not in capsys.readouterr().out


def test_discord_posts_embed_and_records_state(repo):
    (repo / "data").mkdir()
    posts = repo / "data" / "discord_posts.json"
    args = MagicMock(notes_file=str(repo / "notes.md"), title=None, preview=False)
    with patch.object(discord_post, "_load_config", return_value={"webhook_url": "u"}), \
         patch.object(discord_post, "_post_webhook") as post:
        release.discord(args, root=repo)
    embed = post.call_args[0][1]
    assert embed["title"] == "Stats++ v1.2.3 — Shiny thing"
    assert "• First highlight." in embed["description"]
    saved = json.loads(posts.read_text())
    assert saved["title"] == embed["title"] and saved["last_posted_commit"]
    out = subprocess.check_output(["git", "status", "--porcelain"], cwd=repo, text=True)
    assert out == ""  # untracked + ignored: never dirties the tree


def test_build_embed_limits():
    with pytest.raises(ValueError):
        discord_post.build_embed("t", "x" * 4097)
    assert discord_post.build_embed(" t ", " b ")["description"] == "b"


def test_send_uses_user_agent_and_exits_on_http_error():
    resp = MagicMock(status=204)
    with patch("urllib.request.urlopen", return_value=resp) as uo:
        discord_post._post_webhook({"webhook_url": "https://x"}, {"title": "t"})
    req = uo.call_args[0][0]
    assert req.get_header("User-agent").startswith("Stats++ Bot")
    assert json.loads(req.data) == {"embeds": [{"title": "t"}]}
    err = urllib.error.HTTPError("https://x", 403, "no", {}, None)
    with patch("urllib.request.urlopen", side_effect=err), pytest.raises(SystemExit):
        discord_post._send({"webhook_url": "https://x"}, {"content": "hi"})


def test_dry_run_lists_all_three_checks(repo, capsys):
    release.prepare(_args(repo, dry_run=True, skip_checks=False), root=repo)
    out = capsys.readouterr().out
    assert "run pytest" in out and "run mypy" in out and "run scripts/check_docs.py --strict" in out


@pytest.mark.parametrize("failing", ["pytest", "mypy", "check_docs"])
def test_failing_check_aborts_before_commit_and_tag(repo, failing):
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True)
    ran = []
    real_run = subprocess.run

    def fake_run(cmd, **kw):
        if cmd[0] != sys.executable:
            return real_run(cmd, **kw)
        ran.append(cmd)
        return MagicMock(returncode=1 if failing in " ".join(map(str, cmd)) else 0)

    with patch.object(release.subprocess, "run", side_effect=fake_run), pytest.raises(SystemExit):
        release.prepare(_args(repo, skip_checks=False), root=repo)
    assert any(failing in " ".join(map(str, c)) for c in ran)
    assert 'version = "1.2.3"' in (repo / "pyproject.toml").read_text()
    assert subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True) == head
    assert subprocess.check_output(["git", "tag"], cwd=repo, text=True) == ""


def test_all_checks_pass_then_commit(repo):
    real_run = subprocess.run
    seen = []

    def fake_run(cmd, **kw):
        if cmd[0] == sys.executable:
            seen.append(cmd)
            return MagicMock(returncode=0)
        return real_run(cmd, **kw)

    with patch.object(release.subprocess, "run", side_effect=fake_run):
        release.prepare(_args(repo, skip_checks=False), root=repo)
    assert len(seen) == 3
    assert subprocess.check_output(["git", "tag"], cwd=repo, text=True).strip() == "v1.3.0"


# ---- verify-release (gh mocked) ---------------------------------------------

import io
import zipfile


def _zip_bytes(manifest=True, version="1.3.0"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("pyproject.toml", f'[project]\nversion = "{version}"\n')
        if manifest:
            z.writestr("MANIFEST.txt", "pyproject.toml\n")
    return buf.getvalue()


class FakeGh:
    """Stand-in for subprocess.run that answers `gh` calls; records every call."""

    def __init__(self, run_states=None, conclusion="success", assets=("statsplusplus-v1.3.0.zip",),
                 zip_data=None, latest="v1.3.0", auth_rc=0, draft=False):
        self.states = list(run_states or ["completed"])
        self.conclusion, self.assets, self.latest = conclusion, list(assets), latest
        self.zip_data = zip_data if zip_data is not None else _zip_bytes()
        self.auth_rc, self.draft, self.calls = auth_rc, draft, []

    def __call__(self, cmd, **kw):
        self.calls.append(cmd)
        out = lambda o="", rc=0: subprocess.CompletedProcess(cmd, rc, json.dumps(o) if not isinstance(o, str) else o, "err")
        a = cmd[1:]
        if a[:2] == ["auth", "status"]:
            return out("", self.auth_rc)
        if a[:2] == ["run", "list"]:
            return out([{"databaseId": 42}])
        if a[:2] == ["run", "view"]:
            st = self.states.pop(0) if len(self.states) > 1 else self.states[0]
            return out({"status": st, "conclusion": self.conclusion if st == "completed" else None,
                        "jobs": [{"name": "verify", "conclusion": "success"},
                                 {"name": "build", "conclusion": self.conclusion}]})
        if a[:2] == ["release", "view"] and "--json" in a and len(a) == 4:  # latest
            return out({"tagName": self.latest})
        if a[:2] == ["release", "view"]:
            return out({"tagName": a[2], "isDraft": self.draft, "isPrerelease": False,
                        "assets": [{"name": n} for n in self.assets]})
        if a[:2] == ["release", "download"]:
            (Path(a[a.index("--dir") + 1]) / a[a.index("--pattern") + 1]).write_bytes(self.zip_data)
            return out("")
        raise AssertionError(cmd)


def _verify(fake, tmp_path, **kw):
    (tmp_path / "pyproject.toml").write_text('version = "1.3.0"\n')
    ns = dict(tag=None, timeout=100, poll=10)
    ns.update(kw)
    sleeps = []
    with patch.object(release.subprocess, "run", fake):
        rc = release.verify_release(MagicMock(**ns), root=tmp_path, sleep=sleeps.append)
    return rc, sleeps


def test_verify_gh_missing(tmp_path, capsys):
    def boom(*a, **k):
        raise FileNotFoundError
    (tmp_path / "pyproject.toml").write_text('version = "1.3.0"\n')
    with patch.object(release.subprocess, "run", boom):
        assert release.verify_release(MagicMock(tag=None, timeout=1, poll=1), root=tmp_path) == 2
    assert "not installed" in capsys.readouterr().out


def test_verify_gh_not_authenticated(tmp_path, capsys):
    rc, _ = _verify(FakeGh(auth_rc=1), tmp_path)
    assert rc == 2 and "not authenticated" in capsys.readouterr().out


def test_verify_full_pass_defaults_tag_and_waits(tmp_path, capsys):
    fake = FakeGh(run_states=["queued", "in_progress", "completed"])
    rc, sleeps = _verify(fake, tmp_path)
    assert rc == 0 and sleeps == [10, 10]
    assert "PASS: v1.3.0" in capsys.readouterr().out
    assert all(c[1:3] not in (["release", "delete"], ["release", "edit"]) for c in fake.calls)


def test_verify_run_failed(tmp_path, capsys):
    rc, _ = _verify(FakeGh(conclusion="failure"), tmp_path)
    out = capsys.readouterr().out
    assert rc == 1 and "FAIL" in out and "build" in out and "gh run view 42 --log-failed" in out


def test_verify_asset_missing(tmp_path, capsys):
    rc, _ = _verify(FakeGh(assets=[]), tmp_path)
    assert rc == 1 and "missing" in capsys.readouterr().out


def test_verify_zip_missing_manifest(tmp_path, capsys):
    rc, _ = _verify(FakeGh(zip_data=_zip_bytes(manifest=False)), tmp_path)
    assert rc == 1 and "FAIL  zip has MANIFEST.txt" in capsys.readouterr().out


def test_verify_zip_wrong_version_and_not_latest(tmp_path, capsys):
    rc, _ = _verify(FakeGh(zip_data=_zip_bytes(version="1.2.0"), latest="v1.2.0"), tmp_path)
    out = capsys.readouterr().out
    assert rc == 1 and "FAIL  zip pyproject version" in out and "FAIL  releases/latest" in out


def test_verify_timeout(tmp_path, capsys):
    rc, sleeps = _verify(FakeGh(run_states=["in_progress"]), tmp_path, timeout=30)
    assert rc == 3 and sleeps == [10, 10, 10] and "timed out" in capsys.readouterr().out
