"""Release helper: version bump, whats_new entry, release commit, annotated tag, Discord post.

    python3 scripts/release.py prepare --bump minor --notes-file notes.md [--title T] [--dry-run]
    python3 scripts/release.py discord --title T --notes-file notes.md [--preview]
    python3 scripts/release.py verify-release [--tag vX.Y.Z] [--timeout SECS] [--poll SECS]

Notes file: optional first line "# Title", then "- bullet" lines (one per highlight).
`prepare` runs the same checks as the release `verify` job (pytest, mypy,
check_docs --strict) before it changes anything, and never pushes: it prints the
push/tag commands for you to run. `verify-release` is read-only: it uses `gh` to check
the Build Release run, the published release asset and `releases/latest` (exit 0 = pass,
1 = failed check, 2 = gh missing or not authenticated, 3 = timed out waiting for the run).
"""

import argparse
import datetime
import json
import re
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

VERSION_RE = re.compile(r'^version = "(\d+)\.(\d+)\.(\d+)"$', re.MULTILINE)


def git(root, *args, check=True):
    r = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    if check and r.returncode:
        sys.exit(f"✗ git {' '.join(args)}: {r.stderr.strip()}")
    return r


def bump_version(version, kind):
    major, minor, patch = map(int, version.split("."))
    if kind == "major":
        return f"{major + 1}.0.0"
    if kind == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def read_version(root):
    m = VERSION_RE.search((root / "pyproject.toml").read_text())
    if not m:
        sys.exit("✗ no `version = \"X.Y.Z\"` line in pyproject.toml")
    return ".".join(m.groups())


def parse_notes(text, title=None):
    """Return (title, [bullets]). Title: --title, else leading '# ' line."""
    lines = [ln.rstrip() for ln in text.strip().splitlines()]
    if lines and lines[0].startswith("# "):
        title = title or lines[0][2:].strip()
        lines = lines[1:]
    bullets = [ln[2:].strip() for ln in lines if ln.startswith(("- ", "* "))]
    if not title or not bullets:
        sys.exit("✗ need a title (--title or '# Title' line) and at least one '- ' bullet")
    return title, bullets


def add_whats_new(path, version, date, title, bullets):
    data = json.loads(path.read_text())
    if any(v["version"] == version for v in data["versions"]):
        sys.exit(f"✗ whats_new.json already has {version}")
    data["versions"].insert(0, {"version": version, "date": date, "title": title, "highlights": bullets})
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def preflight(root, tag, branch, fetch):
    """Return a list of problems (empty = good to go)."""
    problems = []
    if git(root, "branch", "--show-current").stdout.strip() != branch:
        problems.append(f"not on {branch}")
    dirty = [ln[3:] for ln in git(root, "status", "--porcelain").stdout.splitlines()]
    if dirty:
        problems.append(f"working tree not clean: {', '.join(dirty)}")
    if fetch:
        git(root, "fetch", "origin")
    remote = f"origin/{branch}"
    if git(root, "rev-parse", "--verify", "-q", remote, check=False).returncode:
        problems.append(f"{remote} not found")
    elif git(root, "merge-base", "--is-ancestor", remote, "HEAD", check=False).returncode:
        problems.append(f"{branch} is behind or diverged from {remote}")
    if git(root, "rev-parse", "--verify", "-q", f"refs/tags/{tag}", check=False).returncode == 0:
        problems.append(f"tag {tag} already exists")
    return problems


def checks(root):
    """The release gate, mirroring CI: (label, argv) pairs, run before any change."""
    py = sys.executable
    return [
        ("pytest -m 'not live_api' -q", [py, "-m", "pytest", "-m", "not live_api", "-q"]),
        ("mypy", [py, "-m", "mypy"]),
        ("scripts/check_docs.py --strict", [py, str(root / "scripts" / "check_docs.py"), "--strict"]),
    ]


def prepare(args, root=BASE):
    title, bullets = parse_notes(Path(args.notes_file).read_text(), args.title)
    old = read_version(root)
    new = bump_version(old, args.bump)
    tag = f"v{new}"
    date = datetime.date.today().isoformat()
    dry = args.dry_run
    say = (lambda m: print(f"[dry-run] would {m}")) if dry else (lambda m: print(f"→ {m}"))

    problems = preflight(root, tag, args.branch, fetch=not dry)
    for p in problems:
        print(f"{'⚠' if dry else '✗'} {p}")
    if problems and not dry:
        sys.exit(1)
    if dry:
        print("(dry-run: skipped `git fetch`, using local origin refs)")

    msg = f"Release {tag} — {title}"
    tag_msg = msg + "\n\n" + "\n".join(f"- {b}" for b in bullets)
    for label, _ in checks(root):
        say(f"run {label}" + (" (skipped by --skip-checks)" if args.skip_checks else ""))
    say(f"bump pyproject.toml {old} -> {new}")
    say(f"prepend docs/whats_new.json entry {new} ({date}): {title!r}, {len(bullets)} highlights")
    say(f"commit: {msg}")
    say(f"create annotated tag {tag}")
    if dry:
        return 0

    if not args.skip_checks:
        for label, cmd in checks(root):
            if subprocess.run(cmd, cwd=root).returncode:
                sys.exit(f"✗ {label} failed; nothing changed")
    pp = root / "pyproject.toml"
    pp.write_text(VERSION_RE.sub(f'version = "{new}"', pp.read_text(), count=1))
    add_whats_new(root / "docs" / "whats_new.json", new, date, title, bullets)
    git(root, "add", "pyproject.toml", "docs/whats_new.json")
    git(root, "commit", "-m", msg)
    git(root, "tag", "-a", tag, "-m", tag_msg)
    print(f"\n✓ Committed and tagged {tag}. Review, then push (not run for you):\n")
    print(f"  git push origin {args.branch}\n  git push origin {tag}\n")
    print(f"Then: python3 scripts/release.py discord --title {title!r} --notes-file {args.notes_file}")
    print("After the tag push, and again after `discord`, confirm the release shipped:\n"
          "  python3 scripts/release.py verify-release")
    return 0


def discord(args, root=BASE, posts_path=None):
    import discord_post

    title, bullets = parse_notes(Path(args.notes_file).read_text(), args.title)
    version = read_version(root)
    full_title = f"Stats++ v{version} — {title}"
    embed = discord_post.build_embed(full_title, "\n".join(f"• {b}" for b in bullets))
    if args.preview:
        print(f"Title: {embed['title']}\n---\n{embed['description']}")
        return 0
    discord_post._post_webhook(discord_post._load_config(), embed)
    posts_path = posts_path or root / "data" / "discord_posts.json"
    posts_path.write_text(json.dumps({
        "last_posted_commit": git(root, "rev-parse", "--short", "HEAD").stdout.strip(),
        "date": datetime.date.today().isoformat(),
        "title": full_title,
    }, indent=4, ensure_ascii=False) + "\n")
    print(f"✓ Updated {posts_path}")
    return 0


def _gh(*args):
    """Run read-only `gh`; return CompletedProcess, or None if gh is not installed."""
    try:
        return subprocess.run(["gh", *args], capture_output=True, text=True)
    except FileNotFoundError:
        return None


def _gh_json(*args):
    r = _gh(*args)
    if r is None or r.returncode:
        return None
    try:
        return json.loads(r.stdout)
    except ValueError:
        return None


def verify_release(args, root=BASE, sleep=time.sleep):
    """Read-only post-push check via gh: CI run, release asset, zip contents, releases/latest."""
    tag = args.tag or f"v{read_version(root)}"
    version = tag.lstrip("v")
    asset = f"statsplusplus-{tag}.zip"
    rows = []  # (ok, label, detail)

    def finish():
        print(f"\nverify-release {tag}")
        for ok, label, detail in rows:
            print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f": {detail}" if detail else ""))
        good = all(ok for ok, _, _ in rows)
        print(f"\n{'PASS' if good else 'FAIL'}: {tag}")
        return 0 if good else 1

    auth = _gh("auth", "status")
    if auth is None:
        print("✗ gh is not installed; verify manually: Actions run 'Build Release' is green and "
              f"the release has {asset} containing MANIFEST.txt")
        return 2
    if auth.returncode:
        print("✗ gh is not authenticated (run `gh auth login`); verify manually on GitHub")
        return 2

    # (b) Build Release run for the tag
    waited, run = 0, None
    while True:
        if run is None:
            runs = _gh_json("run", "list", "--workflow", "release.yml", "--branch", tag,
                            "--limit", "1", "--json", "databaseId,status,conclusion")
            run = runs[0]["databaseId"] if runs else None
        detail = _gh_json("run", "view", str(run), "--json", "status,conclusion,jobs") if run else None
        if detail and detail.get("status") == "completed":
            break
        if waited >= args.timeout:
            print(f"✗ timed out after {args.timeout}s waiting for the Build Release run for {tag}"
                  + (f" (run {run}, status {detail.get('status') if detail else '?'})" if run else " (no run found)"))
            return 3
        sleep(args.poll)
        waited += args.poll
    jobs = detail.get("jobs", [])
    failed = [j["name"] for j in jobs if j.get("conclusion") not in ("success", "skipped")]
    for j in jobs:
        rows.append((j.get("conclusion") in ("success", "skipped"), f"job {j['name']}", j.get("conclusion") or ""))
    ok_run = detail.get("conclusion") == "success" and not failed
    rows.append((ok_run, "Build Release run", f"{run} {detail.get('conclusion')}"))
    if not ok_run:
        rows.append((False, "failed jobs", ", ".join(failed) or "none reported"))
        code = finish()
        print(f"  See: gh run view {run} --log-failed")
        return code

    # (c) release, asset, zip contents
    rel = _gh_json("release", "view", tag, "--json", "tagName,isDraft,isPrerelease,assets")
    if rel is None:
        rows.append((False, "GitHub Release exists", "not found"))
        return finish()
    rows.append((not rel["isDraft"] and not rel["isPrerelease"], "release published",
                 "draft" if rel["isDraft"] else "prerelease" if rel["isPrerelease"] else ""))
    has_asset = asset in [a["name"] for a in rel.get("assets", [])]
    rows.append((has_asset, f"asset {asset}", "" if has_asset else "missing"))
    if has_asset:
        with tempfile.TemporaryDirectory() as tmp:
            d = _gh("release", "download", tag, "--pattern", asset, "--dir", tmp)
            zp = Path(tmp) / asset
            if d is None or d.returncode or not zp.exists():
                rows.append((False, "download asset", (d.stderr.strip() if d else "") or "failed"))
            else:
                try:
                    with zipfile.ZipFile(zp) as z:
                        names = z.namelist()
                        rows.append(("MANIFEST.txt" in names, "zip has MANIFEST.txt", ""))
                        m = VERSION_RE.search(z.read("pyproject.toml").decode()) if "pyproject.toml" in names else None
                        got = ".".join(m.groups()) if m else None
                        rows.append((got == version, "zip pyproject version", f"{got} (want {version})"))
                except zipfile.BadZipFile:
                    rows.append((False, "zip readable", "bad zip file"))

    # releases/latest is what the in-app updater reads
    latest = _gh_json("release", "view", "--json", "tagName")
    got = latest.get("tagName") if latest else None
    rows.append((got == tag, "releases/latest", f"{got} (want {tag})"))
    return finish()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare", help="bump, update whats_new, commit, tag (no push)")
    p.add_argument("--bump", choices=["patch", "minor", "major"], required=True)
    p.add_argument("--notes-file", required=True)
    p.add_argument("--title", help="release title (default: '# ' line of notes file)")
    p.add_argument("--branch", default="main")
    p.add_argument("--skip-checks", "--skip-tests", dest="skip_checks", action="store_true",
                   help="skip ALL pre-release checks (pytest, mypy, check_docs); CI's verify job still gates the tag")
    p.add_argument("--dry-run", action="store_true")
    d = sub.add_parser("discord", help="post release embed and update discord_posts.json")
    d.add_argument("--notes-file", required=True)
    d.add_argument("--title")
    d.add_argument("--preview", action="store_true")
    v = sub.add_parser("verify-release", help="read-only gh check of CI run, release asset and releases/latest")
    v.add_argument("--tag", help="default: v<pyproject version>")
    v.add_argument("--timeout", type=int, default=1200, help="seconds to wait for the run (default 1200)")
    v.add_argument("--poll", type=int, default=20, help="seconds between polls (default 20)")
    args = ap.parse_args(argv)
    return {"prepare": prepare, "discord": discord, "verify-release": verify_release}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
