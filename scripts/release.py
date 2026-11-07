"""Release helper: version bump, whats_new entry, release commit, annotated tag, Discord post.

    python3 scripts/release.py prepare --bump minor --notes-file notes.md [--title T] [--dry-run]
    python3 scripts/release.py discord --title T --notes-file notes.md [--preview]

Notes file: optional first line "# Title", then "- bullet" lines (one per highlight).
`prepare` never pushes: it prints the push/tag commands for you to run.
"""

import argparse
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

VERSION_RE = re.compile(r'^version = "(\d+)\.(\d+)\.(\d+)"$', re.MULTILINE)
# Local Discord bookkeeping file (tracked despite /data/ being ignored); never blocks a release.
IGNORED_DIRTY = {"data/discord_posts.json"}


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
    dirty = [f for f in dirty if f not in IGNORED_DIRTY]
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
    say(f"run pytest -m 'not live_api' -q" + (" (skipped by --skip-tests)" if args.skip_tests else ""))
    say(f"bump pyproject.toml {old} -> {new}")
    say(f"prepend docs/whats_new.json entry {new} ({date}): {title!r}, {len(bullets)} highlights")
    say(f"commit: {msg}")
    say(f"create annotated tag {tag}")
    if dry:
        return 0

    if not args.skip_tests:
        r = subprocess.run([sys.executable, "-m", "pytest", "-m", "not live_api", "-q"], cwd=root)
        if r.returncode:
            sys.exit("✗ tests failed; nothing changed")
    pp = root / "pyproject.toml"
    pp.write_text(VERSION_RE.sub(f'version = "{new}"', pp.read_text(), count=1))
    add_whats_new(root / "docs" / "whats_new.json", new, date, title, bullets)
    git(root, "add", "pyproject.toml", "docs/whats_new.json")
    git(root, "commit", "-m", msg)
    git(root, "tag", "-a", tag, "-m", tag_msg)
    print(f"\n✓ Committed and tagged {tag}. Review, then push (not run for you):\n")
    print(f"  git push origin {args.branch}\n  git push origin {tag}\n")
    print(f"Then: python3 scripts/release.py discord --title {title!r} --notes-file {args.notes_file}")
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


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare", help="bump, update whats_new, commit, tag (no push)")
    p.add_argument("--bump", choices=["patch", "minor", "major"], required=True)
    p.add_argument("--notes-file", required=True)
    p.add_argument("--title", help="release title (default: '# ' line of notes file)")
    p.add_argument("--branch", default="main")
    p.add_argument("--skip-tests", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    d = sub.add_parser("discord", help="post release embed and update discord_posts.json")
    d.add_argument("--notes-file", required=True)
    d.add_argument("--title")
    d.add_argument("--preview", action="store_true")
    args = ap.parse_args(argv)
    return prepare(args) if args.cmd == "prepare" else discord(args)


if __name__ == "__main__":
    sys.exit(main())
