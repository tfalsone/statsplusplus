#!/usr/bin/env python3
"""PROTOTYPE (read-only): a WAR-anchored VALUE GRADE for every player.

Explores adding one valuation number alongside composite/ceiling. The value
grade re-expresses the surplus model's `peak_war` (tool-based for prospects,
stat-dominated for established players) on the SAME 20-80 FV ladder the prospect
FV already uses — so prospects, veterans, hitters, and pitchers all land on one
comparable value scale.

    value_grade = fv_from_peak_war(peak_war, bucket)

For comparison it also expresses composite and ceiling on that ladder (via the
composite→WAR curve), so all three are directly comparable:

    comp_grade  = fv_from_peak_war(peak_war_from_score(composite, bucket), bucket)
    ceil_grade  = fv_from_peak_war(peak_war_from_score(ceiling,   bucket), bucket)

The point is NOT to change composite/ceiling. It is to see WHAT a value grade
tells the user that the high-level grades don't: where it aligns (value grade is
redundant) and where it diverges (value grade adds information — over/under
performers, overvalued ceilings, etc.).

Usage:
    python3 scripts/proto_value_grade.py [league ...]        # default: all
    python3 scripts/proto_value_grade.py emlb --examples     # verbose examples
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
ALIGN = 5.0        # within 1 tier → "aligned"
DIVERGE = 10.0     # ≥2 tiers → "notable divergence"


def career_pa_ip(conn):
    pa, ip = {}, {}
    for r in conn.execute(
        "SELECT player_id, SUM(ab+COALESCE(bb,0)+COALESCE(hbp,0)+COALESCE(sf,0)) "
        "FROM mlb_batting_stats WHERE split_id=1 GROUP BY player_id"):
        pa[r[0]] = int(r[1] or 0)
    for r in conn.execute(
        "SELECT player_id, SUM(ip) FROM mlb_pitching_stats WHERE split_id=1 GROUP BY player_id"):
        ip[r[0]] = float(r[1] or 0)
    return pa, ip


def classify(r, pa, ip):
    """prospect / established / graduate — for interpretation."""
    is_mlb = str(r["level"]) in ("MLB", "1")
    has_fv = (r["fv"] or 0) > 0
    p = pa.get(r["player_id"], 0)
    i = ip.get(r["player_id"], 0.0)
    if has_fv:
        return "prospect"
    if is_mlb and (p >= 500 or i >= 150):
        return "established"
    if is_mlb:
        return "graduate"
    return "other"


def build(slug):
    league_dir = ROOT / "data" / slug
    db = league_dir / "league.db"
    if not db.exists():
        return None
    weights = load_model_weights(league_dir)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    pa, ip = career_pa_ip(conn)
    ev = conn.execute("SELECT MAX(eval_date) FROM player_evaluation").fetchone()[0]
    rows = conn.execute("SELECT * FROM player_evaluation WHERE eval_date=?", (ev,)).fetchall()

    out = []
    for r in rows:
        b = r["bucket"]
        if not b:
            continue
        pw = r["peak_war"]
        if pw is None:
            continue
        value = fv_from_peak_war(float(pw), b, weights)
        comp_g = fv_from_peak_war(peak_war_from_score(float(r["composite"]), b, weights), b) if r["composite"] else None
        ceil_g = fv_from_peak_war(peak_war_from_score(float(r["ceiling"]), b, weights), b) if r["ceiling"] else None
        out.append({
            "pid": r["player_id"], "name": r["name"], "bucket": b, "age": r["age"],
            "level": r["level"], "cls": classify(r, pa, ip),
            "is_pitcher": b in ("SP", "RP"),
            "pa": pa.get(r["player_id"], 0), "ip": round(ip.get(r["player_id"], 0.0)),
            "comp": r["composite"], "ceil": r["ceiling"],
            "fv": r["fv"], "fvc": round(r["fv_continuous"], 1) if r["fv_continuous"] else None,
            "sc": round(r["stat_confidence"], 2) if r["stat_confidence"] is not None else None,
            "peak_war": round(pw, 2),
            "value": round(value, 1),
            "comp_g": round(comp_g, 1) if comp_g else None,
            "ceil_g": round(ceil_g, 1) if ceil_g else None,
            "v_vs_ceil": round(value - ceil_g, 1) if ceil_g else None,
            "v_vs_comp": round(value - comp_g, 1) if comp_g else None,
        })
    conn.close()
    return ev, out


def _dist(label, vals):
    if not vals:
        print(f"    {label}: (none)")
        return
    vals = sorted(vals)
    n = len(vals)
    med = vals[n // 2]
    p10, p90 = vals[max(0, n // 10)], vals[min(n - 1, 9 * n // 10)]
    print(f"    {label}: n={n}  p10={p10:+.1f}  median={med:+.1f}  p90={p90:+.1f}")


def report(slug, ev, data, examples=False):
    print(f"\n{'='*80}\nLEAGUE {slug}  (eval_date {ev})   —  VALUE GRADE PROTOTYPE\n{'='*80}")

    # 1. Does the value grade reproduce FV for prospects? (sanity — should align)
    pros = [d for d in data if d["cls"] == "prospect" and d["fvc"] is not None]
    diffs = [d["value"] - d["fvc"] for d in pros]
    print(f"\n[SANITY] Prospects: value grade vs their existing FV (should align — "
          f"both derive from peak_war)")
    _dist("value − FV", diffs)
    off = [d for d in pros if abs(d["value"] - d["fvc"]) > ALIGN]
    print(f"    off by >1 tier: {len(off)}/{len(pros)} ({100*len(off)//max(1,len(pros))}%)")

    # 2. Value vs ceiling, by player class — where does value ADD information?
    print(f"\n[A] VALUE vs CEILING grade, by class  (−ve = value BELOW ceiling = ceiling flatters)")
    for cls in ("prospect", "graduate", "established"):
        sub = [d for d in data if d["cls"] == cls and d["v_vs_ceil"] is not None]
        _dist(f"{cls:12s} value−ceil", [d["v_vs_ceil"] for d in sub])

    # 3. Per-bucket value vs ceiling for ESTABLISHED players (the target population)
    print(f"\n[B] ESTABLISHED players: median value−ceil gap by bucket")
    est = [d for d in data if d["cls"] == "established"]
    buckets = ["C", "1B", "2B", "3B", "SS", "CF", "COF", "SP", "RP"]
    for b in buckets:
        sub = [d["v_vs_ceil"] for d in est if d["bucket"] == b and d["v_vs_ceil"] is not None]
        if sub:
            sub.sort()
            flat = sum(1 for x in sub if x <= -DIVERGE)
            print(f"    {b:4s} n={len(sub):<4} median {sub[len(sub)//2]:+5.1f}   "
                  f"ceiling flatters ≥2 tiers: {flat} ({100*flat//len(sub)}%)")

    # 4. Hitter vs pitcher — does the value grade behave for pitchers too?
    print(f"\n[C] Value grade coverage hitters vs pitchers (established)")
    for grp, pred in (("hitters", lambda d: not d["is_pitcher"]),
                      ("pitchers", lambda d: d["is_pitcher"])):
        sub = [d for d in est if pred(d)]
        if sub:
            vg = sorted(d["value"] for d in sub)
            print(f"    {grp:9s} n={len(sub):<4} value grade  p10={vg[len(vg)//10]:.0f} "
                  f"median={vg[len(vg)//2]:.0f} p90={vg[9*len(vg)//10]:.0f}")

    if not examples:
        return

    # 5. Curated examples
    print(f"\n[EXAMPLES]")

    def show(d):
        tag = {"prospect": "PRO", "graduate": "GRAD", "established": "EST"}.get(d["cls"], "---")
        samp = f"PA{d['pa']}" if not d["is_pitcher"] else f"IP{d['ip']}"
        fv = f"FV{d['fv']}" if d["fv"] else "no-FV"
        print(f"      {d['name']:22s} {d['bucket']:3s} {tag:4s} age{d['age']} {samp:<7} sc{d['sc']}  "
              f"comp {d['comp']}(g{d['comp_g']})  ceil {d['ceil']}(g{d['ceil_g']})  "
              f"{fv}  peak_war {d['peak_war']}  →  VALUE {d['value']}")

    print("\n  — ALIGNED (value ≈ comp ≈ ceil: the grade adds little, player is what he looks like):")
    aligned = [d for d in data if d["cls"] == "established" and d["ceil_g"]
               and abs(d["v_vs_ceil"]) <= ALIGN and abs(d["v_vs_comp"] or 99) <= ALIGN]
    aligned.sort(key=lambda d: -d["value"])
    for d in aligned[:6]:
        show(d)

    print("\n  — CEILING FLATTERS (value well BELOW ceiling: overvaluation trap the grade catches):")
    flat = [d for d in data if d["v_vs_ceil"] is not None and d["v_vs_ceil"] <= -DIVERGE
            and d["cls"] in ("established", "graduate")]
    flat.sort(key=lambda d: d["v_vs_ceil"])
    for d in flat[:8]:
        show(d)

    print("\n  — VALUE ABOVE RATINGS (production exceeds tools: hidden performers):")
    over = [d for d in data if d["v_vs_comp"] is not None and d["v_vs_comp"] >= DIVERGE
            and d["cls"] in ("established", "graduate")]
    over.sort(key=lambda d: -d["v_vs_comp"])
    for d in over[:8]:
        show(d)

    print("\n  — PITCHERS (value grade for arms, established):")
    pit = [d for d in est if d["is_pitcher"]]
    pit.sort(key=lambda d: -d["value"])
    for d in pit[:6]:
        show(d)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    examples = "--examples" in sys.argv
    slugs = args or ["emlb", "vmlb", "ppl"]
    for s in slugs:
        res = build(s)
        if res is None:
            print(f"[{s}] no data")
            continue
        ev, data = res
        report(s, ev, data, examples=examples)


if __name__ == "__main__":
    main()
