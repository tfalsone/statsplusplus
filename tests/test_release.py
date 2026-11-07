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
    _git(work, "add", ".")
    _git(work, "commit", "-m", "init")
    _git(work, "remote", "add", "origin", str(origin))
    _git(work, "push", "-u", "origin", "main")
    return work


def _args(repo, **kw):
    ns = dict(bump="minor", notes_file=str(repo / "notes.md"), title=None, branch="main",
              skip_tests=True, dry_run=False)
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


def test_discord_posts_embed_and_records_state(repo, tmp_path):
    posts = tmp_path / "posts.json"
    args = MagicMock(notes_file=str(repo / "notes.md"), title=None, preview=False)
    with patch.object(discord_post, "_load_config", return_value={"webhook_url": "u"}), \
         patch.object(discord_post, "_post_webhook") as post:
        release.discord(args, root=repo, posts_path=posts)
    embed = post.call_args[0][1]
    assert embed["title"] == "Stats++ v1.2.3 — Shiny thing"
    assert "• First highlight." in embed["description"]
    saved = json.loads(posts.read_text())
    assert saved["title"] == embed["title"] and saved["last_posted_commit"]


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
