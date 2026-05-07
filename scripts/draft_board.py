"""Draft board CLI tool.

Usage:
    python3 scripts/draft_board.py board [--top N]
    python3 scripts/draft_board.py available [--top N]
    python3 scripts/draft_board.py pick N
    python3 scripts/draft_board.py upload [--top N]
    python3 scripts/draft_board.py compare ID1 ID2 [ID3]

Modes:
    board      Full ranked draft board from uploaded pool
    available  Board minus already-taken players (mid-draft)
    pick N     Generate ranked list of exactly N players (pre-draft submission)
    upload     Write StatsPlus auto-draft file (data/<league>/tmp/draft_upload.txt)
    compare    Side-by-side comparison of 2-3 prospects by player_id or name
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from league_context import get_league_dir


def _connect():
    db = get_league_dir() / "league.db"
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    return conn


def _load_pool_ids():
    pool_path = get_league_dir() / "config" / "draft_pool.json"
    if not pool_path.exists():
        sys.exit("No draft pool uploaded. Upload via the web UI first.")
    return json.loads(pool_path.read_text())["player_ids"]


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


def _query_board(conn, pids):
    ph = ",".join("?" * len(pids))
    sql = _BOARD_SQL.format(placeholders=ph)
    return conn.execute(sql, pids).fetchall()


def _flags(r):
    flags = []
    if r["acc"] == "L":
        flags.append("Acc=L!")
    if r["risk"] == "Extreme":
        flags.append("EXTREME")
    if r["bucket"] in ("SP", "RP"):
        if (r["pot_ctrl"] or 0) < 45:
            flags.append("ctl<45")
    return " ".join(flags)


_ACC_ADJ = {"VH": 3, "A": 1, "H": 0, "L": -4, "N": 0}


def _compute_org_needs(conn):
    """Compute positional need scores based on MLB departures vs farm depth.

    Returns dict of bucket -> need_bonus (0, 1, or 2).
    """
    try:
        from league_config import LeagueConfig
        my_team = LeagueConfig().my_team_id
    except Exception:
        return {}

    pos_map = {2: "C", 3: "1B", 4: "2B", 5: "3B", 6: "SS",
               7: "COF", 8: "CF", 9: "COF"}

    # Count meaningful MLB players (composite >= 45) leaving within 2 years
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
        comp = r["composite_score"] or 0
        if yrs_left <= 2 and comp >= 45:
            leaving[bucket] = leaving.get(bucket, 0) + 1

    # Count FV 45+ farm prospects by bucket
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
            needs[bucket] = 2  # critical need
        elif n_leaving > 0 and n_farm <= 3:
            needs[bucket] = 1  # moderate need
    return needs


def _draft_value(r, needs=None, pick_round=None):
    """Compute draft value score: FV + ceiling bonus + RP discount + Acc penalty + risk + needs."""
    fv = r["fv"] or 0
    ceil = r["true_ceiling"] or 0
    val = fv + (ceil - 55) * 0.2
    # RP: lower positional value, don't draft early
    if r["bucket"] == "RP":
        val -= 5
    # Low scouting accuracy: tools may not be real
    acc = r["acc"] or ""
    if acc == "L":
        val -= 2
    elif acc == "VL":
        val -= 4
    # Development risk: extreme projection = lower expected value
    risk = r["risk"] or ""
    if risk == "Extreme":
        val -= 3
    elif risk == "High":
        val -= 1
    # Org needs bonus: only in rounds 3+ to avoid overriding BPA early
    if needs and pick_round and pick_round >= 3:
        val += needs.get(r["bucket"], 0)
    return val


def _compute_adp(rows, teams=None):
    """Compute Average Draft Position (ADP) based on POT rank.

    Other GMs primarily draft by POT. This estimates where each player
    would go if everyone drafted strictly by POT, then converts to a
    round number.

    Args:
        rows: Board rows (must have 'pot' and 'player_id' keys).
        teams: Number of teams in the league (picks per round). Auto-detected
               from league settings if None.

    Returns:
        Dict mapping player_id -> {"pot_rank": int, "exp_round": int, "value_gap": str}
    """
    if teams is None:
        try:
            from league_config import LeagueConfig
            cfg = LeagueConfig()
            teams = len(cfg.mlb_team_ids)
        except Exception:
            teams = 30

    # Rank by POT descending (ties broken by age ascending = younger first)
    ranked = sorted(rows, key=lambda r: (-(r["pot"] or 0), r["age"] or 99))
    pot_rank = {}
    for i, r in enumerate(ranked, 1):
        pot_rank[r["player_id"]] = i

    # Rank by our FV/draft_value
    fv_ranked = sorted(rows, key=lambda r: _draft_value(r), reverse=True)
    fv_rank = {}
    for i, r in enumerate(fv_ranked, 1):
        fv_rank[r["player_id"]] = i

    result = {}
    for r in rows:
        pid = r["player_id"]
        pr = pot_rank[pid]
        fr = fv_rank[pid]
        exp_rd = (pr - 1) // teams + 1
        gap = pr - fr  # positive = will fall (others undervalue), negative = will go early

        if gap >= teams:
            label = "Sleeper"
        elif gap >= teams // 2:
            label = "Value"
        elif gap <= -teams:
            label = "Reach"
        elif gap <= -(teams // 2):
            label = "Goes Early"
        else:
            label = ""

        result[pid] = {
            "pot_rank": pr,
            "fv_rank": fr,
            "exp_round": exp_rd,
            "gap": gap,
            "label": label,
        }
    return result


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
    # Tool comparison
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
        def_labels = []
        for r in rows:
            if r["bucket"] == "C":
                def_labels.append(f"C={r['c_frm']}")
            elif r["bucket"] in ("SS", "2B", "3B"):
                def_labels.append(f"IF={r['ifr']}")
            elif r["bucket"] in ("CF", "COF"):
                def_labels.append(f"OF={r['ofr']}")
            else:
                def_labels.append("-")
        _row("Defense", def_labels)
    else:
        # Mixed — show what's relevant per player
        for r in rows:
            print(f"\n  {r['name']}:")
            if r["bucket"] in ("SP", "RP"):
                print(f"    Stf {r['stf']}/{r['pot_stf']}  "
                      f"Mov {r['mov']}/{r['pot_mov']}  "
                      f"Ctl {r['ctrl']}/{r['pot_ctrl']}")
            else:
                print(f"    Cnt {r['cntct']}/{r['pot_cntct']}  "
                      f"Gap {r['gap']}/{r['pot_gap']}  "
                      f"Pow {r['pow']}/{r['pot_pow']}  "
                      f"Eye {r['eye']}/{r['pot_eye']}  Spd {r['speed']}")

    # Flags
    print()
    for r in rows:
        f = _flags(r)
        if f:
            print(f"  ⚠ {r['name']}: {f}")


def cmd_board(args):
    conn = _connect()
    pids = _load_pool_ids()
    rows = _query_board(conn, pids)
    adp = _compute_adp(rows)
    _print_board(rows, limit=args.top, adp=adp)
    _print_tools(rows, limit=args.top)


def cmd_available(args):
    conn = _connect()
    pids = _load_pool_ids()
    taken = _get_taken_pids()
    remaining = [p for p in pids if p not in taken]
    if not remaining:
        print("No players remaining (or could not fetch picks).")
        return
    rows = _query_board(conn, remaining)
    adp = _compute_adp(rows)
    print(f"({len(taken)} players already taken, {len(remaining)} remaining)\n")
    _print_board(rows, limit=args.top, adp=adp)
    _print_tools(rows, limit=args.top)


_GAME_POS = {1: "P", 2: "C", 3: "1B", 4: "2B", 5: "3B", 6: "SS",
             7: "LF", 8: "CF", 9: "RF", 10: "DH"}
_ROLE_TO_POS = {11: "SP", 12: "SP", 13: "RP"}


def _game_position(conn, player_id):
    """Get the game's listed position label for a player."""
    r = conn.execute(
        "SELECT pos, role FROM players WHERE player_id=?", (player_id,)
    ).fetchone()
    if not r:
        return "?"
    role_pos = _ROLE_TO_POS.get(r["role"])
    if role_pos:
        return role_pos
    return _GAME_POS.get(r["pos"], "?")


def _pick_value(r, adp, pick_round):
    """Draft value adjusted for availability.

    Players expected to be available in later rounds get penalized when
    picking in early rounds — save premium picks for players who won't last.
    """
    base = _draft_value(r)
    a = adp.get(r["player_id"])
    if not a:
        return base
    exp_rd = a["exp_round"]
    # If player's expected round is well beyond current pick round,
    # penalize proportionally. A Rd6 player picked in Rd1 wastes value.
    if exp_rd > pick_round:
        rounds_late = exp_rd - pick_round
        # -2 per round they'd still be available
        base -= rounds_late * 2
    # If player will go before our next pick, small boost (urgency)
    elif exp_rd < pick_round:
        base += 1
    return base


def cmd_pick(args):
    conn = _connect()
    pids = _load_pool_ids()
    rows = _query_board(conn, pids)
    adp = _compute_adp(rows)

    try:
        from league_config import LeagueConfig
        num_teams = len(LeagueConfig().mlb_team_ids)
    except Exception:
        num_teams = 30

    n = args.n

    # Sort by draft value (same logic as upload list)
    rows = sorted(rows, key=lambda r: _draft_value(r), reverse=True)
    rows = rows[:n]
    print(f"Pre-draft ranked list — Top {n}\n")
    _print_board(rows, limit=n, adp=adp)
    _print_tools(rows, limit=n)

    # Commissioner-ready list
    print(f"\n{'=' * 40}")
    print(f"Commissioner List (copy/paste ready):\n")
    for i, r in enumerate(rows, 1):
        gpos = _game_position(conn, r["player_id"])
        print(f"{i:2d}. {gpos:3s}  {r['name']}")


def cmd_upload(args):
    conn = _connect()
    pids = _load_pool_ids()
    rows = _query_board(conn, pids)
    adp = _compute_adp(rows)
    needs = _compute_org_needs(conn)
    limit = min(args.top or 500, 500)

    try:
        from league_config import LeagueConfig
        num_teams = len(LeagueConfig().mlb_team_ids)
    except Exception:
        num_teams = 30

    # Build the list greedily: at each position, pick the best player
    # we'd most regret missing. A player who'll be taken soon (low ExpRd)
    # ranks above an equal-value player who'll stick around.
    #
    # At list position P, the "round" context is ceil(P / num_teams).
    # We pick the player with the highest value who won't survive past
    # the next chunk of picks. If no one is urgent, take best available.
    available = list(rows)
    ordered = []

    for pos in range(1, limit + 1):
        if not available:
            break

        current_round = (pos - 1) // num_teams + 1
        next_chunk_end = pos + num_teams  # picks until our next turn

        # Split: players who'll be gone vs players who'll survive
        now_or_never = []
        can_wait = []
        for r in available:
            a = adp.get(r["player_id"], {})
            pot_rank = a.get("pot_rank", 9999)
            if pot_rank <= next_chunk_end:
                now_or_never.append(r)
            else:
                can_wait.append(r)

        # Pick best "now or never" if it's close in value to best overall.
        # If the best sleeper is significantly better, take the sleeper —
        # talent gap overrides urgency.
        # In later rounds, shrink the threshold — less value difference between
        # rounds means less reason to wait. By round 5+, just take BPA.
        best_urgent = max(now_or_never,
                          key=lambda r: _draft_value(r, needs, current_round)) if now_or_never else None
        best_wait = max(can_wait,
                        key=lambda r: _draft_value(r, needs, current_round)) if can_wait else None

        if best_urgent and best_wait:
            urgent_val = _draft_value(best_urgent, needs, current_round)
            wait_val = _draft_value(best_wait, needs, current_round)
            # Threshold shrinks as rounds progress: 3 in Rd1-2, 2 in Rd3-4, 0 in Rd5+
            if current_round <= 2:
                threshold = 3
            elif current_round <= 4:
                threshold = 2
            else:
                threshold = 0  # pure BPA in late rounds
            if wait_val >= urgent_val + threshold:
                chosen = best_wait
            else:
                chosen = best_urgent
        elif best_urgent:
            chosen = best_urgent
        else:
            chosen = best_wait

        ordered.append(chosen)
        available.remove(chosen)

    ranked_ids = [str(r["player_id"]) for r in ordered]
    out_path = get_league_dir() / "tmp" / "draft_upload.txt"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(ranked_ids) + "\n")
    print(f"Wrote {len(ranked_ids)} player IDs to {out_path}")
    print(f"Strategy: urgency-greedy ordering ({num_teams} teams)")

    if needs:
        need_strs = [f"{b}(+{v})" for b, v in sorted(needs.items(), key=lambda x: -x[1])]
        print(f"Org needs (Rd3+): {', '.join(need_strs)}")

    # Show top 30
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

    # Resolve IDs — accept player_id (int) or name (string)
    targets = []
    for val in args.players:
        if val.isdigit():
            targets.append(int(val))
        else:
            # Search by name in pool
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
    sql = _BOARD_SQL.format(placeholders=ph)
    rows = conn.execute(sql, targets).fetchall()
    if len(rows) < 2:
        sys.exit("Need at least 2 players to compare.")
    # Sort by the order requested
    by_id = {r["player_id"]: r for r in rows}
    ordered = [by_id[t] for t in targets if t in by_id]
    _print_compare(ordered)


def cmd_sim(args):
    """Simulate a draft: other teams pick by POT, we pick by our value list."""
    conn = _connect()
    pids = _load_pool_ids()
    rows = _query_board(conn, pids)
    adp = _compute_adp(rows)
    needs = _compute_org_needs(conn)

    try:
        from league_config import LeagueConfig
        num_teams = len(LeagueConfig().mlb_team_ids)
    except Exception:
        num_teams = 30

    pick_pos = args.pick  # our pick position (1-indexed)
    num_rounds = args.rounds

    if needs:
        need_strs = [f"{b}(+{v})" for b, v in sorted(needs.items(), key=lambda x: -x[1])]
        print(f"Org needs: {', '.join(need_strs)}\n")

    # Other teams' board: sorted by POT desc (how they draft)
    pot_board = sorted(rows, key=lambda r: (-(r["pot"] or 0), r["age"] or 99))

    import random
    rng = random.Random(args.seed if hasattr(args, 'seed') and args.seed else None)

    # Our pick positions across all rounds
    our_pick_positions = [pick_pos + (rd * num_teams) for rd in range(num_rounds)]
    # e.g. pick 30 in a 34-team league: [30, 64, 98, 132, 166]

    available = set(r["player_id"] for r in rows)
    our_picks = []
    other_picks_by_round = []

    for rd in range(1, num_rounds + 1):
        # Our next pick after this one (for "will they still be there?" logic)
        next_pick_overall = our_pick_positions[rd] if rd < num_rounds else 9999

        round_picks = []
        for slot in range(1, num_teams + 1):
            if not available:
                break
            if slot == pick_pos:
                # Our pick: best player who WON'T be available at our next pick.
                # Among available players, find those whose POT rank < next_pick
                # (they'll be taken before we pick again). Pick the best by value.
                avail_rows = [r for r in rows if r["player_id"] in available]
                # Split: "now or never" vs "can wait"
                now_or_never = []
                can_wait = []
                for r in avail_rows:
                    a = adp.get(r["player_id"], {})
                    pot_rank = a.get("pot_rank", 9999)
                    if pot_rank <= next_pick_overall:
                        now_or_never.append(r)
                    else:
                        can_wait.append(r)

                # Pick best "now or never" by value; fall back to best overall if none
                if now_or_never:
                    pick_from = sorted(now_or_never,
                                       key=lambda r: _draft_value(r, needs, rd), reverse=True)
                else:
                    pick_from = sorted(can_wait,
                                       key=lambda r: _draft_value(r, needs, rd), reverse=True)

                chosen = pick_from[0]
                our_picks.append((rd, slot, chosen))
                available.discard(chosen["player_id"])
                round_picks.append((slot, chosen, True))
            else:
                # Other team: pick from top available by POT with variance.
                candidates = [r for r in pot_board if r["player_id"] in available][:8]
                if candidates:
                    weights = [35, 25, 15, 10, 6, 4, 3, 2][:len(candidates)]
                    pick = rng.choices(candidates, weights=weights, k=1)[0]
                    available.discard(pick["player_id"])
                    round_picks.append((slot, pick, False))
        other_picks_by_round.append(round_picks)

    # Print results
    print(f"Draft Simulation — Pick #{pick_pos}, {num_rounds} rounds, {num_teams} teams\n")
    print(f"{'Rd':>2} {'Pick':>4} {'Name':24s} {'Pos':4s} {'FV':>4} {'Pot':>3} {'Ceil':>4} {'$M':>6}")
    print("-" * 60)
    for rd, slot, r in our_picks:
        overall = (rd - 1) * num_teams + slot
        surplus_m = r["prospect_surplus"] / 1e6
        print(f"{rd:2d} {overall:4d} {r['name']:24s} {r['bucket']:4s} "
              f"{r['fv_str']:>4} {r['pot']:3d} {r['true_ceiling']:4d} {surplus_m:6.1f}")

    # Show who went right before/after our picks
    print(f"\n{'─' * 60}")
    print("Context: picks around ours\n")
    for rd_idx, round_picks in enumerate(other_picks_by_round):
        rd = rd_idx + 1
        # Find our pick in this round
        our_idx = None
        for i, (slot, r, is_ours) in enumerate(round_picks):
            if is_ours:
                our_idx = i
                break
        if our_idx is None:
            continue
        # Show 3 before and 3 after
        start = max(0, our_idx - 3)
        end = min(len(round_picks), our_idx + 4)
        print(f"  Round {rd}:")
        for i in range(start, end):
            slot, r, is_ours = round_picks[i]
            overall = (rd - 1) * num_teams + slot
            marker = ">>>" if is_ours else "   "
            print(f"    {marker} #{overall:3d} {r['name']:24s} {r['bucket']:4s} "
                  f"FV {r['fv_str']:>3} Pot {r['pot']:2d}")
        print()


def main():
    parser = argparse.ArgumentParser(description="Draft board analysis tool")
    sub = parser.add_subparsers(dest="cmd")

    p_board = sub.add_parser("board", help="Full ranked draft board")
    p_board.add_argument("--top", type=int, default=30)

    p_avail = sub.add_parser("available", help="Best available (excludes taken)")
    p_avail.add_argument("--top", type=int, default=30)

    p_pick = sub.add_parser("pick", help="Ranked list for pre-draft submission")
    p_pick.add_argument("n", type=int, help="Number of picks (your draft position)")

    p_upload = sub.add_parser("upload", help="Generate StatsPlus auto-draft file")
    p_upload.add_argument("--top", type=int, default=500)

    p_cmp = sub.add_parser("compare", help="Head-to-head comparison")
    p_cmp.add_argument("players", nargs="+", help="Player IDs or names (2-3)")

    p_sim = sub.add_parser("sim", help="Simulate draft (other teams pick by POT)")
    p_sim.add_argument("pick", type=int, help="Your pick position (1-34)")
    p_sim.add_argument("--rounds", type=int, default=5, help="Number of rounds to simulate")
    p_sim.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility")

    args = parser.parse_args()
    if not args.cmd:
        parser.print_help()
        return

    {"board": cmd_board, "available": cmd_available, "pick": cmd_pick,
     "upload": cmd_upload, "compare": cmd_compare, "sim": cmd_sim}[args.cmd](args)


if __name__ == "__main__":
    main()
