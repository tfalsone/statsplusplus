#!/usr/bin/env python3
"""Comp-based FV validation tool.

Finds MLB player-seasons matching a prospect's tool profile (current or ceiling)
and shows the actual WAR distribution. Used for model validation and calibration.

Usage:
    # By player name (uses current tools)
    python3 scripts/comp_validate.py "Zack Gelof"

    # By player name, ceiling profile
    python3 scripts/comp_validate.py "Eric Kiefer" --ceiling

    # Manual profile
    python3 scripts/comp_validate.py --bucket 2B --contact 50 --power 40 --eye 45 --gap 50

    # Adjust tolerance (default 10)
    python3 scripts/comp_validate.py "Zack Gelof" --tolerance 8
"""
import argparse
import sys
from math import sqrt
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import db
from league_context import get_league_dir
from ratings import norm_continuous as norm
from player_utils import assign_bucket


_POS_CLAUSE = {
    "C": "p.pos = 2",
    "1B": "p.pos = 3",
    "2B": "p.pos = 4",
    "3B": "p.pos = 5",
    "SS": "p.pos = 6",
    "CF": "p.pos IN (8)",
    "COF": "p.pos IN (3,7,8,9)",
    "LF": "p.pos IN (3,7,9)",
    "RF": "p.pos IN (3,7,9)",
}


def find_comps(conn, target_tools, bucket, tolerance=10, min_pa=200):
    """Find MLB player-seasons matching a tool profile.

    Args:
        conn: DB connection.
        target_tools: dict with keys from {contact, gap, power, eye} or
            {stuff, movement, control} on 20-80 scale.
        bucket: position bucket.
        tolerance: max average per-tool distance to qualify as a comp.
        min_pa: minimum PA (hitters) or IP (pitchers) for a season to count.

    Returns:
        List of comp dicts sorted by distance, each with name, age, war, pa,
        year, dist, tools.
    """
    is_pitcher = bucket in ("SP", "RP")

    if is_pitcher:
        if bucket == "SP":
            role_clause = "p.role IN (11,12,13) AND ps.ip >= ?"
        else:
            role_clause = "p.role IN (12,13) AND ps.ip >= ?"
        rows = conn.execute(f"""
            SELECT p.name, p.age, r.stf, r.mov, r.ctrl,
                   ps.war, ps.ip, ps.k, ps.bb, ps.year
            FROM latest_ratings r
            JOIN players p ON r.player_id = p.player_id
            JOIN pitching_stats ps ON ps.player_id = p.player_id
            WHERE p.level = 1 AND {role_clause}
              AND ps.split_id = 1
        """, (min_pa,)).fetchall()

        col_map = {"stuff": "stf", "movement": "mov", "control": "ctrl"}
        tool_keys = [k for k in ("stuff", "movement", "control") if k in target_tools]
    else:
        pos_clause = _POS_CLAUSE.get(bucket, "p.pos NOT IN (1,10)")
        rows = conn.execute(f"""
            SELECT p.name, p.age, r.cntct, r.pow, r.eye, r.gap, r.speed,
                   bs.war, bs.pa, bs.hr, bs.sb, bs.year
            FROM latest_ratings r
            JOIN players p ON r.player_id = p.player_id
            JOIN batting_stats bs ON bs.player_id = p.player_id
            WHERE p.level = 1 AND {pos_clause}
              AND bs.split_id = 1 AND bs.pa >= ?
        """, (min_pa,)).fetchall()

        col_map = {"contact": "cntct", "power": "pow", "eye": "eye", "gap": "gap"}
        tool_keys = [k for k in ("contact", "power", "eye", "gap") if k in target_tools]

    n_tools = len(tool_keys)
    if n_tools == 0:
        return []

    matches = []
    for r in rows:
        tools = {k: norm(r[col_map[k]]) for k in tool_keys}
        if any(v is None for v in tools.values()):
            continue

        dist = sqrt(sum((tools[k] - target_tools[k]) ** 2 for k in tool_keys))
        avg_dist = dist / sqrt(n_tools)

        if avg_dist <= tolerance:
            matches.append({
                "name": r["name"], "age": r["age"], "war": r["war"],
                "pa": r["ip"] if is_pitcher else r["pa"],
                "hr": None if is_pitcher else r["hr"],
                "sb": None if is_pitcher else r["sb"],
                "year": r["year"], "dist": round(avg_dist, 1),
                "tools": tools,
            })

    return sorted(matches, key=lambda x: x["dist"])


def summarize(comps):
    """Return summary statistics for a list of comps."""
    if not comps:
        return None
    wars = sorted(c["war"] for c in comps)
    n = len(wars)
    return {
        "n": n,
        "mean": sum(wars) / n,
        "median": wars[n // 2],
        "p25": wars[n // 4],
        "p75": wars[3 * n // 4],
        "min": wars[0],
        "max": wars[-1],
    }


def get_prospect_profile(conn, name, use_ceiling=False):
    """Look up a prospect's tool profile by name.

    Returns (target_tools, bucket, full_name) or (None, None, None) if not found.
    """
    row = conn.execute("""
        SELECT p.player_id, p.name, p.pos, p.role,
               r.cntct, r.pow, r.eye, r.gap,
               r.pot_cntct, r.pot_pow, r.pot_eye, r.pot_gap,
               r.stf, r.mov, r.ctrl,
               r.pot_stf, r.pot_mov, r.pot_ctrl,
               r.pot_c, r.pot_ss, r.pot_second_b, r.pot_third_b, r.pot_first_b,
               r.pot_lf, r.pot_cf, r.pot_rf
        FROM latest_ratings r
        JOIN players p ON r.player_id = p.player_id
        WHERE p.name LIKE ?
        ORDER BY r.snapshot_date DESC LIMIT 1
    """, (f"%{name}%",)).fetchone()

    if not row:
        return None, None, None

    # Use prospect_fv bucket if available, else assign
    pf_row = conn.execute(
        "SELECT bucket FROM prospect_fv WHERE player_id = ? ORDER BY eval_date DESC LIMIT 1",
        (row["player_id"],)
    ).fetchone()
    if pf_row:
        bucket = pf_row[0]
    else:
        try:
            bucket = assign_bucket(dict(row), use_pot=use_ceiling)
        except Exception:
            bucket = "SP" if row["role"] in (11, 12, 13) else "COF"

    is_pitcher = bucket in ("SP", "RP")

    if is_pitcher:
        if use_ceiling:
            tools = {
                "stuff": norm(row["pot_stf"]),
                "movement": norm(row["pot_mov"]),
                "control": norm(row["pot_ctrl"]),
            }
        else:
            tools = {
                "stuff": norm(row["stf"]),
                "movement": norm(row["mov"]),
                "control": norm(row["ctrl"]),
            }
    else:
        if use_ceiling:
            tools = {
                "contact": norm(row["pot_cntct"]),
                "power": norm(row["pot_pow"]),
                "eye": norm(row["pot_eye"]),
                "gap": norm(row["pot_gap"]),
            }
        else:
            tools = {
                "contact": norm(row["cntct"]),
                "power": norm(row["pow"]),
                "eye": norm(row["eye"]),
                "gap": norm(row["gap"]),
            }

    # Filter None values
    tools = {k: v for k, v in tools.items() if v is not None}
    return tools, bucket, row["name"]


def main():
    parser = argparse.ArgumentParser(description="Comp-based FV validation")
    parser.add_argument("name", nargs="?", help="Player name to look up")
    parser.add_argument("--ceiling", action="store_true", help="Use potential tools")
    parser.add_argument("--bucket", help="Position bucket (SS, 2B, COF, etc.)")
    parser.add_argument("--contact", type=float)
    parser.add_argument("--power", type=float)
    parser.add_argument("--eye", type=float)
    parser.add_argument("--gap", type=float)
    parser.add_argument("--stuff", type=float)
    parser.add_argument("--movement", type=float)
    parser.add_argument("--control", type=float)
    parser.add_argument("--tolerance", type=float, default=10)
    parser.add_argument("--min-pa", type=int, default=200)
    args = parser.parse_args()

    conn = db.get_conn(get_league_dir())

    if args.name:
        tools, bucket, full_name = get_prospect_profile(conn, args.name, args.ceiling)
        if not tools:
            print(f"Player not found: {args.name}")
            return
        if args.bucket:
            bucket = args.bucket
        mode = "ceiling" if args.ceiling else "current"
        print(f"\n{full_name} ({mode} tools, {bucket}):")
        print(f"  Profile: {', '.join(f'{k}={v:.0f}' for k, v in tools.items())}")
    else:
        if not args.bucket:
            print("--bucket required when specifying manual tools")
            return
        bucket = args.bucket
        tools = {}
        if args.contact is not None:
            tools["contact"] = args.contact
        if args.power is not None:
            tools["power"] = args.power
        if args.eye is not None:
            tools["eye"] = args.eye
        if args.gap is not None:
            tools["gap"] = args.gap
        if args.stuff is not None:
            tools["stuff"] = args.stuff
        if args.movement is not None:
            tools["movement"] = args.movement
        if args.control is not None:
            tools["control"] = args.control
        if not tools:
            print("Specify at least one tool (--contact, --power, --eye, --gap, --stuff, --movement, --control)")
            return
        print(f"\nManual profile ({bucket}):")
        print(f"  Profile: {', '.join(f'{k}={v:.0f}' for k, v in tools.items())}")

    comps = find_comps(conn, tools, bucket, args.tolerance, args.min_pa)
    stats = summarize(comps)

    if not stats:
        print(f"  No comps found (tolerance={args.tolerance})")
        conn.close()
        return

    print(f"\n  Comps found: {stats['n']} player-seasons (tolerance={args.tolerance})")
    print(f"  WAR: mean={stats['mean']:.1f}  median={stats['median']:.1f}  "
          f"P25={stats['p25']:.1f}  P75={stats['p75']:.1f}  "
          f"range=[{stats['min']:.1f}, {stats['max']:.1f}]")

    # Implied FV from median WAR
    if stats["median"] >= 4.0:
        implied = "60+"
    elif stats["median"] >= 3.0:
        implied = "55-60"
    elif stats["median"] >= 2.0:
        implied = "50-55"
    elif stats["median"] >= 1.0:
        implied = "45-50"
    else:
        implied = "40-45"
    print(f"  Implied FV: ~{implied}")

    # Show closest comps (deduplicated by name, show best season)
    print(f"\n  Closest comps:")
    seen = set()
    shown = 0
    for c in comps:
        if c["name"] in seen:
            continue
        seen.add(c["name"])
        print(f"    {c['name']:<22} WAR={c['war']:>4.1f}  "
              f"({c['year']}, age {c['age']})  dist={c['dist']}")
        shown += 1
        if shown >= 8:
            break

    conn.close()


if __name__ == "__main__":
    main()
