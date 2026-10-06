#!/usr/bin/env python3
"""Read-only research: where do composite/ceiling and the WAR-anchored value grade
tell different stories?

Motivation: once a hitter crosses the rookie threshold he loses his FV grade and
is judged by composite/ceiling alone. Ceiling is a pure tool projection with no
reality check against production, so a weak-bat player can show a flattering
ceiling. This script quantifies that gap across three cohorts:

  1. ESTABLISHED  — MLB hitters, no FV (stat_confidence high). ceiling-grade vs
                    peak_war-grade (peak_war is stat-dominated for these players).
  2. NEAR-READY   — prospects (have FV) with a small comp→ceiling gap ("maxed").
                    FV vs ceiling-grade.
  3. GRADUATES    — crossed the threshold recently (low career PA just over 130,
                    or MLB level with modest sample). ceiling-grade vs peak_war-grade.

"Grade" everywhere is the WAR-anchored FV grade (surplus.fv_from_peak_war),
so composite/ceiling/peak_war are all expressed on the SAME 20-80 value ladder
and are directly comparable. Hitters only (pitchers are a separate model).

Usage:
    python3 scripts/analyze_grade_divergence.py [league_slug ...]   # default: all
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from statsplusplus.evaluation.war import peak_war_from_score
from statsplusplus.evaluation.surplus import fv_from_peak_war
from statsplusplus.evaluation.constants import load_model_weights

HITTER_BUCKETS = {"C", "1B", "2B", "3B", "SS", "CF", "COF", "LF", "RF", "DH"}
DIVERGENCE = 7.5   # grade points — ~1.5 FV tiers; a "meaningful" disagreement


def grade_from_score(score, bucket, weights):
    """Composite/ceiling 20-80 score → WAR → WAR-anchored value grade."""
    if not score:
        return None
    war = peak_war_from_score(float(score), bucket, weights)
    return fv_from_peak_war(war, bucket, weights)


def grade_from_war(war, bucket, weights):
    if war is None:
        return None
    return fv_from_peak_war(float(war), bucket, weights)


def career_pa_map(conn):
    m = {}
    for r in conn.execute(
        "SELECT player_id, SUM(ab + COALESCE(bb,0) + COALESCE(hbp,0) + COALESCE(sf,0)) "
        "FROM mlb_batting_stats WHERE split_id=1 GROUP BY player_id"
    ):
        m[r[0]] = int(r[1] or 0)
    return m


def analyze(slug):
    league_dir = ROOT / "data" / slug
    db = league_dir / "league.db"
    if not db.exists():
        print(f"  [{slug}] no league.db, skipping")
        return
    weights = load_model_weights(league_dir)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    pa = career_pa_map(conn)

    ev = conn.execute("SELECT MAX(eval_date) FROM player_evaluation").fetchone()[0]
    rows = conn.execute(
        "SELECT * FROM player_evaluation WHERE eval_date=?", (ev,)
    ).fetchall()

    hitters = [r for r in rows if r["bucket"] in HITTER_BUCKETS]

    established, near_ready, graduates = [], [], []
    for r in hitters:
        pid = r["player_id"]
        comp, ceil = r["composite"], r["ceiling"]
        fv, fvc = r["fv"], r["fv_continuous"]
        pw, sc = r["peak_war"], r["stat_confidence"]
        bucket = r["bucket"]
        p = pa.get(pid, 0)
        is_mlb = str(r["level"]) in ("MLB", "1")

        ceil_grade = grade_from_score(ceil, bucket, weights)
        comp_grade = grade_from_score(comp, bucket, weights)
        pw_grade = grade_from_war(pw, bucket, weights)

        rec = {
            "pid": pid, "name": r["name"], "bucket": bucket, "age": r["age"],
            "level": r["level"], "pa": p, "comp": comp, "ceil": ceil,
            "fv": fv, "fvc": round(fvc, 1) if fvc else None,
            "peak_war": round(pw, 2) if pw is not None else None,
            "sc": round(sc, 2) if sc is not None else None,
            "comp_grade": round(comp_grade, 1) if comp_grade else None,
            "ceil_grade": round(ceil_grade, 1) if ceil_grade else None,
            "pw_grade": round(pw_grade, 1) if pw_grade else None,
        }

        has_fv = fv and fv > 0
        sc_val = sc if sc is not None else 0.0
        # Cohort 1: ESTABLISHED MLB hitters — isolate the genuinely-proven by
        # requiring high stat_confidence (peak_war is truly stat-anchored, not
        # still tool-blended). This removes early-graduates whose high ceiling
        # vs low current production is EXPECTED (they just haven't developed).
        if is_mlb and not has_fv and p >= 130 and sc_val >= 0.8:
            if ceil_grade is not None and pw_grade is not None:
                rec["gap"] = round(ceil_grade - pw_grade, 1)   # +ve = ceiling flatters
                established.append(rec)
        # Cohort 2: near-ready prospects (have FV, small comp→ceiling gap).
        # Exclude the FV-20 / ceiling-grade-35 FLOOR MISMATCH (FV floors at 20,
        # the WAR ladder bottoms at 35) — that's a scale artifact, not a real
        # disagreement. Only count prospects graded as actual prospects (FV ≥ 40).
        if has_fv and comp and ceil and (ceil - comp) <= 3 and (fv or 0) >= 40:
            if ceil_grade is not None:
                rec["gap"] = round(ceil_grade - fvc, 1)   # +ve = ceiling above FV
                near_ready.append(rec)
        # Cohort 3: recent graduates (MLB, just over threshold, modest sample)
        if is_mlb and not has_fv and 130 <= p <= 500:
            if ceil_grade is not None and pw_grade is not None:
                rec["grad_gap"] = round(ceil_grade - pw_grade, 1)
                graduates.append(rec)

    _report(slug, ev, established, near_ready, graduates)
    conn.close()


def _pct(n, d):
    return f"{100*n/d:.0f}%" if d else "—"


def _report(slug, ev, established, near_ready, graduates):
    print(f"\n{'='*78}\nLEAGUE: {slug}   (eval_date {ev})\n{'='*78}")

    # Cohort 1
    print(f"\n[1] ESTABLISHED MLB HITTERS (no FV, ≥130 PA, stat_confidence ≥ 0.8) — n={len(established)}")
    print("    Genuinely proven players. Does the CEILING grade overstate the")
    print("    stat-anchored (peak_war) grade? +ve = ceiling flatters.")
    flatter = [r for r in established if r["gap"] >= DIVERGENCE]
    under = [r for r in established if r["gap"] <= -DIVERGENCE]
    if established:
        gaps = sorted(r["gap"] for r in established)
        median_gap = gaps[len(gaps) // 2]
        print(f"    median ceiling−peak_war gap: {median_gap:+.1f} pts (n={len(established)})")
    print(f"    ceiling flatters by ≥{DIVERGENCE} pts: {len(flatter)} ({_pct(len(flatter), len(established))})")
    print(f"    ceiling understates by ≥{DIVERGENCE} pts: {len(under)} ({_pct(len(under), len(established))})")
    for r in sorted(flatter, key=lambda x: -x["gap"])[:10]:
        print(f"      {r['name']:22s} {r['bucket']:3s} age{r['age']} PA{r['pa']:<5} sc{r['sc']}  "
              f"comp {r['comp']}→g{r['comp_grade']}  ceil {r['ceil']}→g{r['ceil_grade']}  "
              f"peak_war {r['peak_war']}→g{r['pw_grade']}  (ceil +{r['gap']})")

    # Cohort 2
    print(f"\n[2] NEAR-READY / MAXED PROSPECTS (FV ≥ 40, ceiling−comp ≤ 3) — n={len(near_ready)}")
    print("    Real prospects (FV-20 floor artifacts excluded). Does the CEILING")
    print("    grade disagree with the player's own FV?")
    cflat = [r for r in near_ready if r["gap"] >= DIVERGENCE]
    print(f"    ceiling grade above FV by ≥{DIVERGENCE} pts: {len(cflat)} ({_pct(len(cflat), len(near_ready))})")
    for r in sorted(cflat, key=lambda x: -x["gap"])[:10]:
        print(f"      {r['name']:22s} {r['bucket']:3s} age{r['age']} FV{r['fv']} "
              f"comp {r['comp']} ceil {r['ceil']}→g{r['ceil_grade']}  (FV {r['fvc']}, ceil +{r['gap']})")

    # Cohort 3
    print(f"\n[3] RECENT GRADUATES (MLB, 130–500 career PA) — n={len(graduates)}")
    print("    comp vs ceiling vs stat-anchored grade for freshly-graduated players")
    gflat = [r for r in graduates if r["grad_gap"] >= DIVERGENCE]
    print(f"    ceiling flatters stat-grade by ≥{DIVERGENCE} pts: {len(gflat)} ({_pct(len(gflat), len(graduates))})")
    for r in sorted(gflat, key=lambda x: -x["grad_gap"])[:8]:
        print(f"      {r['name']:22s} {r['bucket']:3s} age{r['age']} PA{r['pa']:<4} "
              f"comp {r['comp']}→g{r['comp_grade']}  ceil {r['ceil']}→g{r['ceil_grade']}  "
              f"peak_war {r['peak_war']}→g{r['pw_grade']} sc{r['sc']}  (ceil +{r['grad_gap']})")


def main():
    slugs = sys.argv[1:] or ["emlb", "vmlb", "ppl"]
    print("Grade divergence analysis — composite/ceiling vs WAR-anchored value grade")
    print("(all grades on the same fv_from_peak_war ladder; hitters only)")
    for s in slugs:
        analyze(s)


if __name__ == "__main__":
    main()
