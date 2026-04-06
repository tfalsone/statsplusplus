#!/usr/bin/env python3
"""
standings.py — League-wide standings via pythagorean expectation.
Usage: python3 scripts/standings.py [--year 2033] [--refresh]

Derives W/L from team RS/RA using pythagorean formula (exponent 1.83).
Games estimated from pitching outs / 27.
Reads from DB (team_batting_stats + team_pitching_stats).
Use --refresh to pull fresh data from the API first.
"""

import argparse, json, os, sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "scripts"))
import db as _db
from league_config import config as _cfg

PYTH_EXP = _cfg.pyth_exp


def _standings_from_db(year):
    conn = _db.get_conn()
    conn.row_factory = None

    bat = conn.execute(
        "SELECT team_id, name, r FROM team_batting_stats WHERE year=? AND split_id=1",
        (year,),
    ).fetchall()
    pit = conn.execute(
        "SELECT team_id, r, ip FROM team_pitching_stats WHERE year=? AND split_id=1",
        (year,),
    ).fetchall()
    conn.close()
    if not bat or not pit:
        return None

    rs_map = {r[0]: (r[1], r[2]) for r in bat}   # tid -> (name, RS)
    ra_map = {r[0]: (r[1], r[2]) for r in pit}    # tid -> (RA, IP)
    return _build_rows(rs_map, ra_map)


def _standings_from_api(year):
    sys.path.insert(0, BASE)
    from statsplus import client

    tb = client.get_team_batting_stats(year=year, split=1)
    tp = client.get_team_pitching_stats(year=year, split=1)
    if not tb or not tp:
        return None

    rs_map = {t["tid"]: (t["name"], t["r"]) for t in tb if t.get("split_id") == 1}
    ra_map = {t["tid"]: (t["r"], t["ip"]) for t in tp if t.get("split_id") == 1}
    return _build_rows(rs_map, ra_map)


def _build_rows(rs_map, ra_map):
    rows = []
    for tid, (name, rs) in rs_map.items():
        if tid not in ra_map:
            continue
        ra, ip = ra_map[tid]
        g = round(ip / 9)
        if g == 0 or rs + ra == 0:
            continue
        pyth = rs**PYTH_EXP / (rs**PYTH_EXP + ra**PYTH_EXP)
        w = round(pyth * g, 1)
        l = round(g - w, 1)
        rows.append({
            "tid": tid, "name": name, "g": g,
            "w": w, "l": l, "pct": pyth,
            "rs": rs, "ra": ra, "diff": rs - ra,
        })
    rows.sort(key=lambda x: x["pct"], reverse=True)
    return rows


def actual_record(team_id, year):
    """Return actual W-L from games table for a team in a given season."""
    conn = _db.get_conn()
    conn.row_factory = None
    row = conn.execute("""
        SELECT
            SUM(CASE WHEN (home_team=? AND runs0>runs1) OR (away_team=? AND runs1>runs0) THEN 1 ELSE 0 END) as w,
            SUM(CASE WHEN (home_team=? AND runs0<runs1) OR (away_team=? AND runs1<runs0) THEN 1 ELSE 0 END) as l
        FROM games
        WHERE played=1 AND date >= ? AND (home_team=? OR away_team=?)
    """, (team_id, team_id, team_id, team_id, f"{year}-01-01", team_id, team_id)).fetchone()
    conn.close()
    w, l = (row[0] or 0), (row[1] or 0)
    return w, l


def print_standings(rows, my_tid=None):
    if my_tid is None:
        my_tid = _cfg.my_team_id
    leader_pct = rows[0]["pct"] if rows else 0.5

    hdr = f"{'#':>2}  {'Team':<28} {'W':>5} {'L':>5} {'Pct':>6} {'GB':>5} {'RS':>4} {'RA':>4} {'Diff':>5}"
    print(hdr)
    print("-" * len(hdr))
    leader_w = rows[0]["w"] if rows else 0
    leader_l = rows[0]["l"] if rows else 0
    for i, r in enumerate(rows, 1):
        gb = ((leader_w - leader_l) - (r["w"] - r["l"])) / 2
        gb_str = "-" if gb < 0.25 else f"{gb:.1f}"
        diff_str = f"+{r['diff']}" if r["diff"] > 0 else str(r["diff"])
        marker = " ◄" if r["tid"] == my_tid else ""
        print(f"{i:>2}  {r['name']:<28} {r['w']:>5} {r['l']:>5} {r['pct']:>6.3f} {gb_str:>5} {r['rs']:>4} {r['ra']:>4} {diff_str:>5}{marker}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=None)
    ap.add_argument("--refresh", action="store_true", help="Pull fresh from API")
    ap.add_argument("--actual", action="store_true",
                    help="Show actual W-L for my team alongside pythagorean")
    args = ap.parse_args()

    if args.year is None:
        args.year = _cfg.year

    rows = None
    if not args.refresh:
        rows = _standings_from_db(args.year)
    if rows is None:
        rows = _standings_from_api(args.year)

    if not rows:
        print("No data available.")
        sys.exit(1)

    print(f"\n{args.year} Standings — Pythagorean ({len(rows)} teams)\n")
    print_standings(rows)
    print()

    if args.actual:
        w, l = actual_record(_cfg.my_team_id, args.year)
        pyth = next((r for r in rows if r["tid"] == _cfg.my_team_id), None)
        if pyth:
            delta_w = w - pyth["w"]
            print(f"Actual record: {w}-{l}  |  Pythagorean: {pyth['w']}-{pyth['l']}  |  Delta: {delta_w:+.1f}W")
            if delta_w < -2:
                print("  → Underperforming pythagorean — likely bullpen/luck drag")
            elif delta_w > 2:
                print("  → Overperforming pythagorean — regression risk")
        print()
