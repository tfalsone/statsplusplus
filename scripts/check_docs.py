#!/usr/bin/env python3
"""Documentation staleness checker.

Flags living documents whose owned code changed more recently than the document
itself. Uses git commit timestamps as the mechanical signal and the doc status
header as the human-readable one.

This is a REPORT, not a gate. It lists candidates for review; a human decides
whether a doc actually drifted. Run from the project root:

    python3 scripts/check_docs.py            # report stale living docs
    python3 scripts/check_docs.py --all      # also list up-to-date docs
    python3 scripts/check_docs.py --strict   # exit 1 if any doc is stale

The doc-status convention and the human-facing ownership map live in
`docs/README.md`. The machine-readable ownership map is `DOC_OWNERSHIP` below —
keep the two in sync. The checker verifies that every Living doc in the registry
has an ownership entry and warns if one is missing.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

# ---------------------------------------------------------------------------
# Machine-readable ownership map: living doc -> code paths it describes.
# Mirror of the human-facing table in docs/README.md §2. Paths are relative to
# the repo root; a path may be a file or a directory (directory = any file under
# it). Keep in sync with the README.
# ---------------------------------------------------------------------------

DOC_OWNERSHIP: dict[str, list[str]] = {
    "evaluation_system_overview.md": [
        "src/statsplusplus/evaluation",
        "src/statsplusplus/data/evaluation_engine.py",
        "src/statsplusplus/data/fv_calc.py",
        "src/statsplusplus/data/calibrate.py",
    ],
    "valuation_model.md": [
        "src/statsplusplus/evaluation/surplus.py",
        "src/statsplusplus/evaluation/player_value.py",
        "src/statsplusplus/evaluation/constants.py",
    ],
    "evaluation_model_findings.md": [
        "src/statsplusplus/evaluation",
    ],
    "value_grade_research.md": [
        "src/statsplusplus/evaluation/surplus.py",
        "src/statsplusplus/evaluation/player_value.py",
        "src/statsplusplus/evaluation/fv.py",
    ],
    "system_overview.md": [
        "src/statsplusplus",
        "web",
    ],
    "client_reference.md": [
        "src/statsplusplus/client",
        "src/statsplusplus/data/refresh.py",
    ],
    "statsplus_api_analysis.md": [
        "src/statsplusplus/client",
        "src/statsplusplus/data/refresh.py",
    ],
    "tools_reference.md": [
        "scripts",
        "src/statsplusplus/cli",
        "web/queries.py",
        "web/team_queries.py",
        "web/player_queries.py",
    ],
    "testing_pipeline_design.md": [
        ".github/workflows",
    ],
}

STATUS_RE = re.compile(r"\*\*Status:\*\*\s*([A-Za-z]+)")
VERIFIED_RE = re.compile(r"\*\*Last verified against code:\*\*\s*(.+?)(?:$|\n)")
HISTORICAL_RE = re.compile(r"HISTORICAL", re.IGNORECASE)


def _git_last_commit_ts(path: Path) -> int | None:
    """Unix timestamp of the last commit that touched ``path`` (file or dir)."""
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%ct", "--", str(path)],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout.strip()
    except subprocess.CalledProcessError:
        return None
    return int(out) if out else None


def _git_last_commit_human(path: Path) -> str:
    try:
        return subprocess.run(
            ["git", "log", "-1", "--format=%ad (%h)", "--date=short", "--", str(path)],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout.strip() or "no commits"
    except subprocess.CalledProcessError:
        return "unknown"


def _parse_header(doc: Path) -> tuple[str | None, str | None]:
    """Return (status, last_verified) parsed from the doc's status header."""
    text = doc.read_text(errors="replace")[:1200]
    if HISTORICAL_RE.search(text):
        return "Historical", None
    status = STATUS_RE.search(text)
    verified = VERIFIED_RE.search(text)
    return (
        status.group(1) if status else None,
        verified.group(1).strip() if verified else None,
    )


def _newest_code_ts(paths: list[str]) -> tuple[int | None, str]:
    """Newest last-commit timestamp across the owned code paths + which path."""
    newest_ts: int | None = None
    newest_path = ""
    for rel in paths:
        p = ROOT / rel
        if not p.exists():
            continue
        ts = _git_last_commit_ts(p)
        if ts is not None and (newest_ts is None or ts > newest_ts):
            newest_ts = ts
            newest_path = rel
    return newest_ts, newest_path


def main() -> int:
    ap = argparse.ArgumentParser(description="Flag stale living documentation.")
    ap.add_argument("--all", action="store_true", help="Also list up-to-date docs.")
    ap.add_argument("--strict", action="store_true", help="Exit 1 if any doc is stale.")
    args = ap.parse_args()

    stale: list[str] = []
    unverified: list[str] = []
    ok: list[str] = []
    warnings: list[str] = []

    # Coverage check: every Living doc in the registry should have an owner entry.
    for doc_path in sorted(DOCS.glob("*.md")):
        name = doc_path.name
        status, verified = _parse_header(doc_path)
        if status != "Living":
            continue
        if name not in DOC_OWNERSHIP:
            warnings.append(
                f"{name}: marked Living but has no DOC_OWNERSHIP entry in check_docs.py"
            )

    for name, code_paths in DOC_OWNERSHIP.items():
        doc = DOCS / name
        if not doc.exists():
            warnings.append(f"{name}: in DOC_OWNERSHIP but file not found")
            continue

        status, verified = _parse_header(doc)
        doc_ts = _git_last_commit_ts(doc)
        code_ts, code_path = _newest_code_ts(code_paths)

        if verified and "NOT YET VERIFIED" in verified.upper():
            unverified.append(f"{name:40s} — header says NOT YET VERIFIED")
            continue

        if code_ts is None:
            warnings.append(f"{name}: no committed code found for owned paths")
            continue
        if doc_ts is None:
            stale.append(f"{name:40s} — doc not committed; code at {code_path}")
            continue

        if code_ts > doc_ts:
            stale.append(
                f"{name:40s} — code newer than doc "
                f"(code: {_git_last_commit_human(ROOT / code_path)} [{code_path}]  "
                f"doc: {_git_last_commit_human(doc)})"
            )
        else:
            ok.append(f"{name:40s} — current (verified: {verified or 'n/a'})")

    print("=" * 72)
    print("DOCUMENTATION STALENESS REPORT")
    print("=" * 72)

    if stale:
        print(f"\n⚠  STALE — owned code changed after the doc ({len(stale)}):\n")
        for line in stale:
            print(f"   {line}")

    if unverified:
        print(f"\n●  UNVERIFIED — never checked against code ({len(unverified)}):\n")
        for line in unverified:
            print(f"   {line}")

    if warnings:
        print(f"\n!  MAP WARNINGS ({len(warnings)}):\n")
        for line in warnings:
            print(f"   {line}")

    if args.all and ok:
        print(f"\n✓  CURRENT ({len(ok)}):\n")
        for line in ok:
            print(f"   {line}")

    if not stale and not unverified:
        print("\n✓ All living docs are current with their owned code.\n")
    else:
        print(
            f"\nReview the flagged docs. Verify against the code, fix drift, and bump "
            f"the 'Last verified against code' line.\n"
        )

    if args.strict and (stale or unverified):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
