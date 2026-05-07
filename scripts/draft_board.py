"""Draft board CLI tool.

Usage:
    python3 scripts/draft_board.py board [--top N]
    python3 scripts/draft_board.py available [--top N]
    python3 scripts/draft_board.py pick N
    python3 scripts/draft_board.py upload [--top N]
    python3 scripts/draft_board.py compare ID1 ID2 [ID3]
    python3 scripts/draft_board.py sim PICK [--rounds N] [--seed S]

Modes:
    board      Full ranked draft board from uploaded pool
    available  Board minus already-taken players (mid-draft)
    pick N     Generate ranked list of exactly N players (pre-draft submission)
    upload     Write StatsPlus auto-draft file (data/<league>/tmp/draft_upload.txt)
    compare    Side-by-side comparison of 2-3 prospects by player_id or name
    sim        Simulate draft (other teams pick by POT, we pick by value)
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from league_context import get_league_dir


# ═══════════════════════════════════════════════════════════════════════════
# Data Layer — loading and querying
# ═══════════════════════════════════════════════════════════════════════════

_BOARD_SQL = """
    SELECT pf.fv, pf.fv_str, pf.risk, pf.bucket, pf.prospect_surplus,
           p.name, p.age, p.player_id,
           r.composite_score, r.true_ceiling, r.offensive_grade,
           r.pot_cntct, r.pot_gap, r.pot_pow, r.pot_eye,
           r.cntct, r.gap, r.pow, r.eye, r.speed,
           r.pot_stf, r.pot_mov, r.pot_ctrl,
           r.stf, r.mov, r.ctrl,
           r.ofr, r.ifr, r.c_frm, r.acc, r.pot
    FROM prospect_fv pf
    JOIN players p ON pf.player_id = p.player_id
    JOIN latest_ratings r ON r.player_id = p.player_id
    WHERE pf.player_id IN ({placeholders})
    ORDER BY pf.fv DESC, pf.prospect_surplus DESC
"""


def _connect():
    db = get_league_dir() / "league.db"
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    return conn


def _get_num_teams():
    try:
        from league_config import LeagueConfig
        return len(LeagueConfig().mlb_team_ids)
    except Exception:
        return 30


def _load_pool_ids():
    pool_path = get_league_dir() / "config" / "draft_pool.json"
    if not pool_path.exists():
        sys.exit("No draft pool uploaded. Upload via the web UI first.")
    return json.loads(pool_path.read_text())["player_ids"]


def _query_board(conn, pids):
    ph = ",".join("?" * len(pids))
    sql = _BOARD_SQL.format(placeholders=ph)
    return conn.execute(sql, pids).fetchall()


def _get_taken_pids():
    """Fetch already-drafted player IDs from StatsPlus API."""
    try:
        from statsplus import client
        from league_context import get_statsplus_cookie
        from league_config import LeagueConfig
        cfg = LeagueConfig()
        slug = cfg.settings.get("statsplus_slug", "")
        cookie = get_statsplus_cookie()
        if slug and cookie:
            client.configure(slug, cookie)
        raw = client.get_draft()
        return {d["ID"] for d in raw if d.get("ID")}
    except Exception as e:
        print(f"Warning: could not fetch draft picks from API: {e}", file=sys.stderr)
        return set()


def load_board():
    """Load full draft board with ADP and needs. Returns (rows, adp, needs, num_teams, conn)."""
    conn = _connect()
    pids = _load_pool_ids()
    rows = _query_board(conn, pids)
    num_teams = _get_num_teams()
    adp = compute_adp(rows, num_teams)
    needs = compute_org_needs(conn)
    return rows, adp, needs, num_teams, conn


# ═══════════════════════════════════════════════════════════════════════════
# Valuation — scoring and ranking logic
# ═══════════════════════════════════════════════════════════════════════════

def draft_value(r, needs=None, pick_round=None):
    """Compute draft value score for a prospect row.

    Components: FV + ceiling bonus + RP discount + Acc penalty + risk + needs.
    """
    fv = r["fv"] or 0
    ceil = r["true_ceiling"] or 0
    val = fv + (ceil - 55) * 0.2
    if r["bucket"] == "RP":
        val -= 5
    acc = r["acc"] or ""
    if acc == "L":
        val -= 2
    elif acc == "VL":
        val -= 4
    risk = r["risk"] or ""
    if risk == "Extreme":
        val -= 3
    elif risk == "High":
        val -= 1
    if needs and pick_round and pick_round >= 3:
        val += needs.get(r["bucket"], 0)
    return val


def compute_adp(rows, num_teams=None):
    """Compute ADP: POT rank, expected round, and value gap label per player."""
    if num_teams is None:
        num_teams = _get_num_teams()

    ranked = sorted(rows, key=lambda r: (-(r["pot"] or 0), r["age"] or 99))
    pot_rank = {r["player_id"]: i + 1 for i, r in enumerate(ranked)}

    fv_ranked = sorted(rows, key=lambda r: draft_value(r), reverse=True)
    fv_rank = {r["player_id"]: i + 1 for i, r in enumerate(fv_ranked)}

    result = {}
    for r in rows:
        pid = r["player_id"]
        pr = pot_rank[pid]
        fr = fv_rank[pid]
        exp_rd = (pr - 1) // num_teams + 1
        gap = pr - fr

        if gap >= num_teams:
            label = "Sleeper"
        elif gap >= num_teams // 2:
            label = "Value"
        elif gap <= -num_teams:
            label = "Reach"
        elif gap <= -(num_teams // 2):
            label = "Goes Early"
        else:
            label = ""

        result[pid] = {
            "pot_rank": pr, "fv_rank": fr,
            "exp_round": exp_rd, "gap": gap, "label": label,
        }
    return result


def compute_org_needs(conn):
    """Positional need scores: MLB departures vs farm depth. Returns bucket -> bonus."""
    try:
        from league_config import LeagueConfig
        my_team = LeagueConfig().my_team_id
    except Exception:
        return {}

    pos_map = {2: "C", 3: "1B", 4: "2B", 5: "3B", 6: "SS", 7: "COF", 8: "CF", 9: "COF"}

    rows = conn.execute("""
        SELECT p.pos, p.role, c.years, c.current_year, r.composite_score
        FROM players p
        LEFT JOIN contracts c ON p.player_id = c.player_id
        LEFT JOIN latest_ratings r ON p.player_id = r.player_id
        WHERE p.team_id = ? AND p.level = '1'
    """, (my_team,)).fetchall()

    leaving = {}
    for r in rows:
        bucket = {11: "SP", 12: "RP", 13: "RP"}.get(r["role"]) or pos_map.get(r["pos"], "COF")
        yrs_left = (r["years"] or 0) - (r["current_year"] or 0) if r["years"] else 0
        if yrs_left <= 2 and (r["composite_score"] or 0) >= 45:
            leaving[bucket] = leaving.get(bucket, 0) + 1

    farm_rows = conn.execute("""
        SELECT pf.bucket, COUNT(*) as cnt
        FROM prospect_fv pf
        JOIN players p ON pf.player_id = p.player_id
        WHERE (p.parent_team_id = ? OR p.team_id = ?) AND pf.fv >= 45
        GROUP BY pf.bucket
    """, (my_team, my_team)).fetchall()
    farm = {r["bucket"]: r["cnt"] for r in farm_rows}

    needs = {}
    for bucket in ["C", "1B", "2B", "3B", "SS", "CF", "COF", "SP"]:
        n_leaving = leaving.get(bucket, 0)
        n_farm = farm.get(bucket, 0)
        if n_leaving > 0 and n_farm <= 1:
            needs[bucket] = 2
        elif n_leaving > 0 and n_farm <= 3:
            needs[bucket] = 1
    return needs


# ═══════════════════════════════════════════════════════════════════════════
# Strategy — list building and simulation
# ═══════════════════════════════════════════════════════════════════════════

def build_urgency_list(rows, adp, needs, num_teams, limit):
    """Build an urgency-greedy ordered list for auto-draft.

    At each position, prefer players who'll be gone soon unless a sleeper
    is significantly better. Threshold fades in later rounds.
    """
    available = list(rows)
    ordered = []

    for pos in range(1, limit + 1):
        if not available:
            break

        current_round = (pos - 1) // num_teams + 1
        next_chunk_end = pos + num_teams

        now_or_never = []
        can_wait = []
        for r in available:
            a = adp.get(r["player_id"], {})
            if a.get("pot_rank", 9999) <= next_chunk_end:
                now_or_never.append(r)
            else:
                can_wait.append(r)

        best_urgent = max(now_or_never,
                          key=lambda r: draft_value(r, needs, current_round)) if now_or_never else None
        best_wait = max(can_wait,
                        key=lambda r: draft_value(r, needs, current_round)) if can_wait else None

        if best_urgent and best_wait:
            urgent_val = draft_value(best_urgent, needs, current_round)
            wait_val = draft_value(best_wait, needs, current_round)
            if current_round <= 2:
                threshold = 10
            elif current_round <= 4:
                threshold = 5
            else:
                threshold = 0
            chosen = best_wait if wait_val >= urgent_val + threshold else best_urgent
        elif best_urgent:
            chosen = best_urgent
        else:
            chosen = best_wait

        ordered.append(chosen)
        available.remove(chosen)

    return ordered


def simulate_draft(rows, adp, needs, num_teams, pick_pos, num_rounds, seed=None):
    """Simulate a draft. Returns (our_picks, other_picks_by_round).

    our_picks: list of (round, slot, row)
    other_picks_by_round: list of lists of (slot, row, is_ours)
    """
    import random
    rng = random.Random(seed)

    pot_board = sorted(rows, key=lambda r: (-(r["pot"] or 0), r["age"] or 99))
    our_pick_positions = [pick_pos + (rd * num_teams) for rd in range(num_rounds)]

    available = set(r["player_id"] for r in rows)
    our_picks = []
    other_picks_by_round = []

    for rd in range(1, num_rounds + 1):
        next_pick_overall = our_pick_positions[rd] if rd < num_rounds else 9999
        round_picks = []

        for slot in range(1, num_teams + 1):
            if not available:
                break
            if slot == pick_pos:
                avail_rows = [r for r in rows if r["player_id"] in available]
                now_or_never = [r for r in avail_rows
                                if adp.get(r["player_id"], {}).get("pot_rank", 9999) <= next_pick_overall]
                can_wait = [r for r in avail_rows
                            if adp.get(r["player_id"], {}).get("pot_rank", 9999) > next_pick_overall]

                if now_or_never:
                    chosen = max(now_or_never, key=lambda r: draft_value(r, needs, rd))
                else:
                    chosen = max(can_wait, key=lambda r: draft_value(r, needs, rd))

                our_picks.append((rd, slot, chosen))
                available.discard(chosen["player_id"])
                round_picks.append((slot, chosen, True))
            else:
                candidates = [r for r in pot_board if r["player_id"] in available][:8]
                if candidates:
                    weights = [35, 25, 15, 10, 6, 4, 3, 2][:len(candidates)]
                    pick = rng.choices(candidates, weights=weights, k=1)[0]
                    available.discard(pick["player_id"])
                    round_picks.append((slot, pick, False))

        other_picks_by_round.append(round_picks)

    return our_picks, other_picks_by_round


# ═══════════════════════════════════════════════════════════════════════════
# Display — CLI output formatting
# ═══════════════════════════════════════════════════════════════════════════

def _flags(r):
    flags = []
    if r["acc"] == "L":
        flags.append("Acc=L!")
    if r["risk"] == "Extreme":
        flags.append("EXTREME")
    if r["bucket"] in ("SP", "RP") and (r["pot_ctrl"] or 0) < 45:
        flags.append("ctl<45")
    return " ".join(flags)


def _print_board(rows, limit=None, adp=None):
    if limit:
        rows = rows[:limit]
    print(f"{'#':>3} {'Name':24s} {'Age':>3} {'Pos':4s} {'FV':>3} {'Risk':>7} "
          f"{'Ceil':>4} {'$M':>6} {'ExpRd':>5} {'Flags'}")
    print("-" * 90)
    for i, r in enumerate(rows, 1):
        surplus_m = r["prospect_surplus"] / 1e6
        f = _flags(r)
        exp_rd = ""
        if adp and r["player_id"] in adp:
            a = adp[r["player_id"]]
            exp_rd = f"Rd{a['exp_round']}"
            if a["label"]:
                f = f"{a['label']} {f}".strip()
        print(f"{i:3d} {r['name']:24s} {r['age']:3d} {r['bucket']:4s} "
              f"{r['fv_str']:>3} {r['risk']:>7} {r['true_ceiling']:4d} "
              f"{surplus_m:6.1f} {exp_rd:>5} {f}")


def _print_tools(rows, limit=None):
    if limit:
        rows = rows[:limit]
    print()
    print(f"{'#':>3} {'Name':24s} {'Pos':4s} Tools (cur/pot)")
    print("-" * 82)
    for i, r in enumerate(rows, 1):
        if r["bucket"] in ("SP", "RP"):
            print(f"{i:3d} {r['name']:24s} {r['bucket']:4s} "
                  f"Stf {r['stf']:2d}/{r['pot_stf']:2d}  "
                  f"Mov {r['mov']:2d}/{r['pot_mov']:2d}  "
                  f"Ctl {r['ctrl']:2d}/{r['pot_ctrl']:2d}  Acc={r['acc']}")
        else:
            def_val = ""
            if r["bucket"] == "C":
                def_val = f" C={r['c_frm']}"
            elif r["bucket"] in ("SS", "2B", "3B"):
                def_val = f" IF={r['ifr']}"
            elif r["bucket"] in ("CF", "COF"):
                def_val = f" OF={r['ofr']}"
            print(f"{i:3d} {r['name']:24s} {r['bucket']:4s} "
                  f"Cnt {r['cntct']:2d}/{r['pot_cntct']:2d}  "
                  f"Gap {r['gap']:2d}/{r['pot_gap']:2d}  "
                  f"Pow {r['pow']:2d}/{r['pot_pow']:2d}  "
                  f"Eye {r['eye']:2d}/{r['pot_eye']:2d}  "
                  f"Spd {r['speed']:2d}{def_val}  Acc={r['acc']}")


def _print_compare(rows):
    """Side-by-side comparison of 2-3 prospects."""
    names = [r["name"] for r in rows]
    w = max(20, max(len(n) for n in names) + 2)

    def _row(label, values):
        print(f"  {label:12s}", end="")
        for v in values:
            print(f"{str(v):>{w}}", end="")
        print()

    print(f"\n{'':12s}", end="")
    for n in names:
        print(f"{n:>{w}}", end="")
    print("\n" + "-" * (12 + w * len(rows)))

    _row("FV", [f"{r['fv_str']} {r['risk']}" for r in rows])
    _row("Ceiling", [r["true_ceiling"] for r in rows])
    _row("Composite", [r["composite_score"] for r in rows])
    _row("Surplus", [f"${r['prospect_surplus']/1e6:.1f}M" for r in rows])
    _row("Age", [r["age"] for r in rows])
    _row("Position", [r["bucket"] for r in rows])
    _row("Acc", [r["acc"] for r in rows])
    print()

    all_pitchers = all(r["bucket"] in ("SP", "RP") for r in rows)
    all_hitters = all(r["bucket"] not in ("SP", "RP") for r in rows)

    if all_pitchers:
        _row("Stuff", [f"{r['stf']}/{r['pot_stf']}" for r in rows])
        _row("Movement", [f"{r['mov']}/{r['pot_mov']}" for r in rows])
        _row("Control", [f"{r['ctrl']}/{r['pot_ctrl']}" for r in rows])
    elif all_hitters:
        _row("Contact", [f"{r['cntct']}/{r['pot_cntct']}" for r in rows])
        _row("Gap", [f"{r['gap']}/{r['pot_gap']}" for r in rows])
        _row("Power", [f"{r['pow']}/{r['pot_pow']}" for r in rows])
        _row("Eye", [f"{r['eye']}/{r['pot_eye']}" for r in rows])
        _row("Speed", [r["speed"] for r in rows])
    else:
        for r in rows:
            print(f"\n  {r['name']}:")
            if r["bucket"] in ("SP", "RP"):
                print(f"    Stf {r['stf']}/{r['pot_stf']}  Mov {r['mov']}/{r['pot_mov']}  Ctl {r['ctrl']}/{r['pot_ctrl']}")
            else:
                print(f"    Cnt {r['cntct']}/{r['pot_cntct']}  Gap {r['gap']}/{r['pot_gap']}  "
                      f"Pow {r['pow']}/{r['pot_pow']}  Eye {r['eye']}/{r['pot_eye']}  Spd {r['speed']}")
    print()
    for r in rows:
        f = _flags(r)
        if f:
            print(f"  ⚠ {r['name']}: {f}")


_GAME_POS = {1: "P", 2: "C", 3: "1B", 4: "2B", 5: "3B", 6: "SS",
             7: "LF", 8: "CF", 9: "RF", 10: "DH"}
_ROLE_TO_POS = {11: "SP", 12: "SP", 13: "RP"}


def _game_position(conn, player_id):
    r = conn.execute("SELECT pos, role FROM players WHERE player_id=?", (player_id,)).fetchone()
    if not r:
        return "?"
    return _ROLE_TO_POS.get(r["role"]) or _GAME_POS.get(r["pos"], "?")


# ═══════════════════════════════════════════════════════════════════════════
# CLI Commands
# ═══════════════════════════════════════════════════════════════════════════

def cmd_board(args):
    rows, adp, needs, num_teams, conn = load_board()
    _print_board(rows, limit=args.top, adp=adp)
    _print_tools(rows, limit=args.top)


def cmd_available(args):
    rows, adp, needs, num_teams, conn = load_board()
    taken = _get_taken_pids()
    remaining_pids = [r["player_id"] for r in rows if r["player_id"] not in taken]
    if not remaining_pids:
        print("No players remaining (or could not fetch picks).")
        return
    remaining = [r for r in rows if r["player_id"] in set(remaining_pids)]
    adp = compute_adp(remaining, num_teams)
    print(f"({len(taken)} players already taken, {len(remaining)} remaining)\n")
    _print_board(remaining, limit=args.top, adp=adp)
    _print_tools(remaining, limit=args.top)


def cmd_pick(args):
    rows, adp, needs, num_teams, conn = load_board()
    ordered = build_urgency_list(rows, adp, needs, num_teams, args.n)

    print(f"Pre-draft ranked list — Top {args.n}\n")
    _print_board(ordered, limit=args.n, adp=adp)
    _print_tools(ordered, limit=args.n)

    print(f"\n{'=' * 40}")
    print(f"Commissioner List (copy/paste ready):\n")
    for i, r in enumerate(ordered, 1):
        gpos = _game_position(conn, r["player_id"])
        print(f"{i:2d}. {gpos:3s}  {r['name']}")


def cmd_upload(args):
    rows, adp, needs, num_teams, conn = load_board()
    limit = min(args.top or 500, 500)
    ordered = build_urgency_list(rows, adp, needs, num_teams, limit)

    ranked_ids = [str(r["player_id"]) for r in ordered]
    out_path = get_league_dir() / "tmp" / "draft_upload.txt"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(ranked_ids) + "\n")
    print(f"Wrote {len(ranked_ids)} player IDs to {out_path}")
    print(f"Strategy: urgency-greedy ordering ({num_teams} teams)")

    if needs:
        print(f"Org needs (Rd3+): {', '.join(f'{b}(+{v})' for b, v in sorted(needs.items(), key=lambda x: -x[1]))}")

    print(f"\nTop 30:")
    print(f"{'#':>3} {'Name':24s} {'Pos':4s} {'FV':>4} {'Risk':>7} {'ExpRd':>5}")
    print("-" * 55)
    for i, r in enumerate(ordered[:30], 1):
        a = adp.get(r["player_id"], {})
        print(f"{i:3d} {r['name']:24s} {r['bucket']:4s} {r['fv_str']:>4} "
              f"{r['risk']:>7} Rd{a.get('exp_round', '?'):>2}")


def cmd_compare(args):
    conn = _connect()
    pids = _load_pool_ids()

    targets = []
    for val in args.players:
        if val.isdigit():
            targets.append(int(val))
        else:
            ph = ",".join("?" * len(pids))
            match = conn.execute(
                f"SELECT player_id FROM players WHERE name LIKE ? AND player_id IN ({ph})",
                [f"%{val}%"] + pids
            ).fetchone()
            if match:
                targets.append(match[0])
            else:
                sys.exit(f"Player not found in draft pool: {val}")

    ph = ",".join("?" * len(targets))
    rows = conn.execute(_BOARD_SQL.format(placeholders=ph), targets).fetchall()
    if len(rows) < 2:
        sys.exit("Need at least 2 players to compare.")
    by_id = {r["player_id"]: r for r in rows}
    _print_compare([by_id[t] for t in targets if t in by_id])


def cmd_sim(args):
    rows, adp, needs, num_teams, conn = load_board()
    pick_pos = args.pick
    num_rounds = args.rounds

    if needs:
        print(f"Org needs: {', '.join(f'{b}(+{v})' for b, v in sorted(needs.items(), key=lambda x: -x[1]))}\n")

    our_picks, other_picks_by_round = simulate_draft(
        rows, adp, needs, num_teams, pick_pos, num_rounds, seed=args.seed)

    print(f"Draft Simulation — Pick #{pick_pos}, {num_rounds} rounds, {num_teams} teams\n")
    print(f"{'Rd':>2} {'Pick':>4} {'Name':24s} {'Pos':4s} {'FV':>4} {'Pot':>3} {'Ceil':>4} {'$M':>6}")
    print("-" * 60)
    for rd, slot, r in our_picks:
        overall = (rd - 1) * num_teams + slot
        print(f"{rd:2d} {overall:4d} {r['name']:24s} {r['bucket']:4s} "
              f"{r['fv_str']:>4} {r['pot']:3d} {r['true_ceiling']:4d} "
              f"{r['prospect_surplus'] / 1e6:6.1f}")

    print(f"\n{'─' * 60}")
    print("Context: picks around ours\n")
    for rd_idx, round_picks in enumerate(other_picks_by_round):
        our_idx = next((i for i, (s, r, ours) in enumerate(round_picks) if ours), None)
        if our_idx is None:
            continue
        start = max(0, our_idx - 3)
        end = min(len(round_picks), our_idx + 4)
        print(f"  Round {rd_idx + 1}:")
        for i in range(start, end):
            slot, r, is_ours = round_picks[i]
            overall = rd_idx * num_teams + slot
            marker = ">>>" if is_ours else "   "
            print(f"    {marker} #{overall:3d} {r['name']:24s} {r['bucket']:4s} "
                  f"FV {r['fv_str']:>3} Pot {r['pot']:2d}")
        print()


# ═══════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Draft board analysis tool")
    sub = parser.add_subparsers(dest="cmd")

    p_board = sub.add_parser("board", help="Full ranked draft board")
    p_board.add_argument("--top", type=int, default=30)

    p_avail = sub.add_parser("available", help="Best available (excludes taken)")
    p_avail.add_argument("--top", type=int, default=30)

    p_pick = sub.add_parser("pick", help="Ranked list for pre-draft submission")
    p_pick.add_argument("n", type=int, help="Number of players to list")

    p_upload = sub.add_parser("upload", help="Generate StatsPlus auto-draft file")
    p_upload.add_argument("--top", type=int, default=500)

    p_cmp = sub.add_parser("compare", help="Head-to-head comparison")
    p_cmp.add_argument("players", nargs="+", help="Player IDs or names (2-3)")

    p_sim = sub.add_parser("sim", help="Simulate draft (other teams pick by POT)")
    p_sim.add_argument("pick", type=int, help="Your pick position (1-N)")
    p_sim.add_argument("--rounds", type=int, default=5, help="Number of rounds")
    p_sim.add_argument("--seed", type=int, default=None, help="Random seed")

    args = parser.parse_args()
    if not args.cmd:
        parser.print_help()
        return

    {"board": cmd_board, "available": cmd_available, "pick": cmd_pick,
     "upload": cmd_upload, "compare": cmd_compare, "sim": cmd_sim}[args.cmd](args)


if __name__ == "__main__":
    main()
