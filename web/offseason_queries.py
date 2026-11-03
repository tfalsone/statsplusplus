"""
web/offseason_queries.py — data for the phase-aware Offseason page (Phase A).

This is a *view* over existing data and evaluation functions, organized around
the decisions a GM makes during the offseason. It intentionally reuses the
established query/eval machinery (arb model, upcoming-FA, payroll projection,
surplus) rather than introducing new models.

Panels (Phase A / proof-of-concept):
  - Arbitration    : arb-eligible own players, projected salary, tender rec
  - Free agency    : your expiring players (retain priority) + market board
  - Payroll outlook : next-year committed + projected vs current
  - Extensions     : high-surplus players 1-2 years from free agency

Phase B (Rule 5 / 40-man) is gated on storing the /players Rule-5 fields and is
not built here.
"""

from web_league_context import get_db, get_cfg, my_team_id
from statsplusplus.utils.positions import display_pos as _display_pos
from statsplusplus.data.db import ORG_ID_SQL


def _eval_date(conn):
    row = conn.execute("SELECT MAX(eval_date) FROM player_evaluation").fetchone()
    return row[0] if row and row[0] else None


# Chronological offseason phases (keys) — must match the OFFSEASON_PHASES list
# in api_routes. Kept here too so the panel-gating logic is a pure, testable
# function independent of the request layer.
PHASE_KEYS = ["season_review", "arbitration", "options", "free_agency", "rule5", "spring"]


def panels_for_phase(phase):
    """Which panels to surface for a given sub-phase. Empty phase = show all.

    Trades is always shown (handled by the template), so it's not in this dict.
    """
    show_all = not phase
    return {
        "season_review": show_all or phase == "season_review",
        "arbitration": show_all or phase == "arbitration",
        "options": show_all or phase == "options",
        "free_agency": show_all or phase == "free_agency",
        "extensions": show_all or phase in ("free_agency", "options"),
        "rule5": show_all or phase == "rule5",
    }


# ---------------------------------------------------------------------------
# Season in Review — a "wrapped"-style recap that opens the offseason: where the
# team stood, what went well / what to fix, standout players, farm development,
# and a focus handoff into the rest of the offseason panels.
#
# All from data already in the DB (season team/player stats, standings, farm
# FV + dev-speed). No new models. Degrades gracefully when a season hasn't been
# played yet (preseason / brand-new league).
# ---------------------------------------------------------------------------

# Offensive categories where HIGHER is better; pitching where LOWER is better.
# (col, label, direction, decimal places). Kept to meaningful, non-redundant
# facets — power, discipline, contact, run production — so multiple can surface.
_OFF_CATS = [("ops", "OPS", "hi", 3), ("woba", "wOBA", "hi", 3),
             ("r", "Runs", "hi", 0), ("hr", "Home Runs", "hi", 0),
             ("iso", "ISO (power)", "hi", 3), ("obp", "OBP", "hi", 3),
             ("bb_pct", "Walk rate", "hi", 1), ("k_pct", "Strikeout rate", "lo", 1),
             ("avg", "Batting avg", "hi", 3)]
_PIT_CATS = [("era", "ERA", "lo", 2), ("fip", "FIP", "lo", 2),
             ("k_pct", "K rate", "hi", 1), ("bb_pct", "Walk rate", "lo", 1),
             ("hra", "HR allowed", "lo", 0), ("avg", "Opp. AVG", "lo", 3)]


def _rank_categories(conn, tid, year, table, cats):
    """For each (col,label,dir) category, compute the team's value and its rank
    among all teams that played (1 = best). Returns a list of dicts.
    """
    cols = ",".join(c for c, _, _, _ in cats)
    rows = conn.execute(
        f"SELECT team_id, {cols} FROM {table} WHERE year=? AND split_id=1", (year,)
    ).fetchall()
    if not rows:
        return []
    out = []
    n = len(rows)
    for i, (col, label, direction, dp) in enumerate(cats):
        vals = [(r[0], r[col]) for r in rows if r[col] is not None]
        if not vals:
            continue
        # rank: best first. hi = descending, lo = ascending.
        vals.sort(key=lambda x: x[1], reverse=(direction == "hi"))
        rank = next((idx + 1 for idx, (t, _) in enumerate(vals) if t == tid), None)
        team_val = next((v for t, v in vals if t == tid), None)
        if rank is None or team_val is None:
            continue
        lg_avg = sum(v for _, v in vals) / len(vals)
        out.append({
            "label": label, "value": team_val, "dp": dp,
            "rank": rank, "n": len(vals),
            "lg_avg": lg_avg,
            "pctile": round(100 * (len(vals) - rank) / (len(vals) - 1)) if len(vals) > 1 else 50,
            "good": rank <= max(2, len(vals) // 3),
            "bad": rank > len(vals) - max(2, len(vals) // 3),
        })
    return out


def _season_players(conn, tid, year):
    """Top WAR performers (one hitter list, one pitcher list) from actual season
    stats, plus the biggest positive/negative surprise vs projection.
    """
    ed = _eval_date(conn)
    hitters = conn.execute("""
        SELECT b.player_id, p.name, b.war, b.hr, b.rbi, b.avg,
               (COALESCE(b.obp,0) + COALESCE(b.slg,0)) AS ops, b.pa
        FROM mlb_batting_stats b JOIN players p ON p.player_id = b.player_id
        WHERE b.year=? AND b.split_id=1 AND b.team_id=? AND b.pa >= 200
        ORDER BY b.war DESC LIMIT 3
    """, (year, tid)).fetchall()
    pitchers = conn.execute("""
        SELECT pt.player_id, p.name,
               (pt.war + COALESCE(pt.ra9war, pt.war)) / 2.0 AS war,
               pt.w, pt.l, pt.era, pt.k, pt.outs
        FROM mlb_pitching_stats pt JOIN players p ON p.player_id = pt.player_id
        WHERE pt.year=? AND pt.split_id=1 AND pt.team_id=? AND pt.outs >= 300
        ORDER BY war DESC LIMIT 3
    """, (year, tid)).fetchall()

    def _hit(r):
        return {"pid": r[0], "name": r[1], "war": round(r[2] or 0, 1),
                "line": f"{r[3]} HR, {r[4]} RBI, {r[6]:.3f} OPS" if r[6] is not None else f"{r[3]} HR"}

    def _pit(r):
        ip = (r[7] or 0) / 3.0
        return {"pid": r[0], "name": r[1], "war": round(r[2] or 0, 1),
                "line": f"{r[3]}-{r[4]}, {r[5]:.2f} ERA, {r[6]} K"}

    return {
        "hitters": [_hit(r) for r in hitters],
        "pitchers": [_pit(r) for r in pitchers],
    }


def _milb_level_map(cfg):
    """league_id -> {level:int, abbr:str} from the cumulative milb_league_map."""
    m = {}
    for lid, v in (cfg.settings.get("milb_league_map") or {}).items():
        try:
            m[int(lid)] = {"level": int(v.get("level")), "abbr": v.get("abbr")}
        except (TypeError, ValueError):
            continue
    return m


def _prospect_season_line(conn, pid, is_pitcher, year, level_map, team_names):
    """This season's performance, one stint per affiliate the player appeared
    at, ordered lowest level of play to highest (shows a climb). Each stint is
    labeled with the game level (AAA/AA/A/…) plus the affiliate team name — the
    concrete detail that disambiguates multiple stints at the same level (e.g.
    two Single-A stops the game both calls level 4). League abbr is included
    when available. Returns a list of {level, label, where, line} dicts.
    """
    from statsplusplus.utils.positions import LEVEL_DISPLAY_MAP, LEVEL_ORDER

    def _where(team_id, lid):
        """Affiliate label: team name, with league abbr as a hint when known."""
        tname = team_names.get(team_id)
        abbr = (level_map.get(lid) or {}).get("abbr") if lid is not None else None
        if tname and abbr:
            return f"{tname} ({abbr})"
        return tname or (abbr or "")

    stints = []
    if is_pitcher:
        rows = conn.execute("""
            SELECT team_id, league_id, outs, era, k, war, ra9war FROM pitching_stats
            WHERE player_id=? AND split_id=1 AND year=? AND ip > 0
        """, (pid, year)).fetchall()
        for r in rows:
            lvl = 1 if r[1] is None else (level_map.get(r[1]) or {}).get("level")
            if lvl is None:
                continue
            ip = (r[2] or 0) / 3.0
            if ip < 5:
                continue
            # Blended WAR to match how the app reports pitcher WAR elsewhere.
            war = ((r[5] or 0) + (r[6] if r[6] is not None else (r[5] or 0))) / 2.0
            stints.append((lvl, {
                "level": lvl, "label": LEVEL_DISPLAY_MAP.get(lvl, "?"),
                "where": _where(r[0], r[1]), "war": round(war, 1),
                "line": f"{ip:.0f} IP, {r[3]:.2f} ERA, {r[4]} K" if r[3] is not None
                        else f"{ip:.0f} IP"}))
    else:
        rows = conn.execute("""
            SELECT team_id, league_id, pa, hr, avg, obp, slg, war FROM batting_stats
            WHERE player_id=? AND split_id=1 AND year=? AND pa > 0
        """, (pid, year)).fetchall()
        for r in rows:
            lvl = 1 if r[1] is None else (level_map.get(r[1]) or {}).get("level")
            if lvl is None or (r[2] or 0) < 25:  # skip trivial cups of coffee
                continue
            stints.append((lvl, {
                "level": lvl, "label": LEVEL_DISPLAY_MAP.get(lvl, "?"),
                "where": _where(r[0], r[1]), "war": round(r[7] or 0, 1),
                "line": f"{r[2]} PA, {r[4]:.3f}/{r[5]:.3f}/{r[6]:.3f}, {r[3]} HR"
                        if r[4] is not None else f"{r[2]} PA"}))
    # order lowest level of play → highest (climb order = reverse of LEVEL_ORDER rank)
    order = {lvl: i for i, lvl in enumerate(LEVEL_ORDER)}
    stints.sort(key=lambda s: -order.get(s[0], 99))
    return [d for _, d in stints]


# Only prospects worth following — FV floor for the top-prospects summary and
# the risers list. 45+ is a real prospect; 35/40 org filler is intentionally out.
_FARM_MIN_FV = 45

# ETA (years to MLB) at or under this counts as a near-term contributor — i.e.
# realistically in the mix next season. AAA = 0.5, upper level pushes to 1.5.
_CONTRIB_MAX_ETA = 1.5


def _platoon_lean(row):
    """Detect a clear platoon lean from a hitter's L/R split ratings. The FV
    model's platoon penalty only fires on a severe *contact* split (weak side
    <= 25); that misses the common profile of an otherwise-average bat who is
    clearly better vs one hand across power/gap/eye (e.g. a LHH mashing RHP but
    exposed vs LHP). Such a player is a platoon/bench piece, not a regular, and
    won't get a full season of reps.

    Returns True when at least two offensive tools lean >= 10 points to the
    same side (i.e. a consistent, meaningful platoon split). Reads split columns
    off a latest_ratings row (may be None). Conservative: only flags a clear,
    same-direction lean.
    """
    if row is None:
        return False
    pairs = [(row["cntct_l"], row["cntct_r"]), (row["pow_l"], row["pow_r"]),
             (row["gap_l"], row["gap_r"]), (row["eye_l"], row["eye_r"])]
    lean_r = lean_l = 0
    for l, r in pairs:
        if l is None or r is None:
            continue
        if r - l >= 10:
            lean_r += 1
        elif l - r >= 10:
            lean_l += 1
    return lean_r >= 2 or lean_l >= 2


def _pitcher_role(peak_war, fv, stamina, bucket):
    """Project a pitcher's MLB role from stamina + quality, not WAR magnitude
    alone. Stamina is the honest starter/reliever discriminator (the SP/RP
    boundary sits ~stm 40; the composite already penalizes stm<40 and
    assign_bucket reroutes low-stamina "SP" to RP). A high-WAR-rate arm with a
    starter's build is a rotation piece; the same rate on a low-stamina arm is a
    bullpen/swing profile that won't hold a rotation spot.

    Returns (label, css_class, pt_fraction). Relievers/swing arms throw far
    fewer innings, so their fraction is lower regardless of rate.
    """
    st = stamina or 0
    # True relief prospect (bucket says RP, or stamina below the SP boundary).
    if bucket == "RP" or st < 40:
        if peak_war is not None and peak_war >= 1.5 and st >= 30:
            return "high-leverage reliever", "good", 0.55
        return "bullpen arm", "ok", 0.40
    # Fringe starter build (low-end stamina): more likely swing/long-man than
    # a rotation regular even if the rate looks starter-ish.
    if st < 48:
        return "swing / long reliever", "ok", 0.50
    # Real starter build.
    if peak_war is not None and peak_war >= 2.5:
        return "mid-rotation starter", "good", 0.85
    if peak_war is not None and peak_war >= 1.5:
        return "back-end starter", "good", 0.70
    return "depth starter", "ok", 0.50


def _contributor_role(peak_war, is_pitcher, fv=None, stamina=None, bucket=None):
    """Map a full-season peak-WAR *rate* to a projected role and the share of a
    full season's playing time that role realistically gets. The role — not the
    raw rate — is what a GM plans around: an "everyday contributor" gets ~full
    reps, a "role player" (platoon bat / swing arm / bench) gets far fewer, so
    his *accumulated* next-season WAR is well below his full-season rate.

    Pitchers route through _pitcher_role (stamina-aware). Hitters use WAR tier.
    Returns (label, css_class, pt_fraction).
    """
    if is_pitcher:
        return _pitcher_role(peak_war, fv, stamina, bucket)
    if peak_war is None:
        return "depth", "ok", 0.35
    if peak_war >= 3.5:
        return "impact talent", "good", 1.0     # everyday star — full reps
    if peak_war >= 2.5:
        return "everyday contributor", "good", 0.90
    if peak_war >= 1.5:
        return "regular", "good", 0.75
    if peak_war >= 0.8:
        return "platoon / bench bat", "ok", 0.50
    return "depth", "ok", 0.35


def _war_range(rate, frac):
    """Expected next-season WAR from a full-season rate and a role playing-time
    fraction, expressed as a small range to avoid false precision. Returns a
    display string like "0.8–1.1" (or "1.0" when the band is tight)."""
    if rate is None:
        return None
    mid = rate * frac
    lo = max(0.0, mid - 0.2)
    hi = mid + 0.2
    if round(lo, 1) == round(hi, 1):
        return f"{mid:.1f}"
    return f"{lo:.1f}–{hi:.1f}"


def _farm_contributors(conn, tid, ed):
    """Prospects realistically knocking on the MLB door — FV 45+, near-term ETA
    (AAA/upper level) — with a projected ROLE and a role-scaled expected WAR
    contribution for next season. This is the concrete answer to "what internal
    help is coming."

    Note on WAR: `peak_war` is a full-season *rate* (the calibrated tables are
    fit on regular-playing-time players). Showing it raw overstates a part-time
    player's actual contribution (a platoon bat won't get 600 PA). We surface
    the role's realistic playing-time-scaled expectation as the headline, with
    the full-season rate as secondary context.

    Sorted by ETA (soonest first) then full-season rate.
    """
    from statsplusplus.utils.positions import YEARS_TO_MLB
    rows = conn.execute(f"""
        SELECT p.player_id AS pid, p.name AS name, p.age AS age, p.role AS grole,
               pe.fv AS fv, pe.fv_str AS fv_str, pe.bucket AS bucket, pe.level AS level,
               pe.peak_war AS peak_war, pe.risk AS risk, lr.stm AS stm,
               lr.cntct_l, lr.cntct_r, lr.pow_l, lr.pow_r,
               lr.gap_l, lr.gap_r, lr.eye_l, lr.eye_r
        FROM player_evaluation pe JOIN players p ON pe.player_id = p.player_id
        LEFT JOIN latest_ratings lr ON lr.player_id = pe.player_id
        WHERE pe.eval_date=? AND {ORG_ID_SQL}=? AND pe.fv >= ?
          AND pe.level IN ('AAA', 'AA')
        ORDER BY pe.peak_war DESC
    """, (ed, tid, _FARM_MIN_FV)).fetchall()
    out = []
    for r in rows:
        lvlkey = (r["level"] or "").lower()
        eta = YEARS_TO_MLB.get(lvlkey)
        if eta is None or eta > _CONTRIB_MAX_ETA:
            continue
        is_pitcher = r["grole"] in (11, 12, 13)
        rate = r["peak_war"]
        role, role_class, frac = _contributor_role(
            rate, is_pitcher, fv=r["fv"], stamina=r["stm"], bucket=r["bucket"])
        # A clear platoon lean caps the bat at a platoon role (reduced reps),
        # even if his full-season rate reads like a regular's. Only demotes.
        if not is_pitcher and _platoon_lean(r) and frac > 0.50:
            role, role_class, frac = "platoon bat", "ok", 0.50
        out.append({
            "pid": r["pid"], "name": r["name"], "age": r["age"],
            "pos": _display_pos(r["bucket"]) if r["bucket"] else "?",
            "fv_str": r["fv_str"] or "", "level": r["level"] or "",
            "full_war": round(rate, 1) if rate is not None else None,
            "exp_war": _war_range(rate, frac),
            "exp_mid": round(rate * frac, 1) if rate is not None else None,
            "eta": "next season" if eta <= 0.5 else "1–2 years",
            "eta_sort": eta,
            "risk": r["risk"] or "",
            "role": role, "role_class": role_class,
        })
    out.sort(key=lambda x: (x["eta_sort"], -(x["full_war"] or 0)))
    return out[:8]


def _farm_development(conn, tid, year, cfg):
    """Development story for the org this season:
      - top_prospects : the system's best by FV (regardless of dev signal), each
                        with a cross-level performance line for the season.
      - risers        : dev-speed Rising, quality-gated to FV >= _FARM_MIN_FV,
                        sorted by FV then dev-speed z. (Empty pre-refresh.)
    """
    ed = _eval_date(conn)
    if ed is None:
        return {"top_prospects": [], "risers": [], "contributors": []}
    level_map = _milb_level_map(cfg)
    team_names = dict(conn.execute("SELECT team_id, name FROM teams").fetchall())

    top_prospects = []
    for r in conn.execute(f"""
        SELECT p.player_id AS pid, p.name AS name, p.age AS age, p.role AS role,
               pf.fv AS fv, pf.fv_str AS fv_str, pf.bucket AS bucket,
               pf.risk AS risk, pf.level AS level
        FROM prospect_fv pf JOIN players p ON pf.player_id = p.player_id
        WHERE pf.eval_date=? AND {ORG_ID_SQL}=? AND pf.fv >= ?
        ORDER BY pf.fv DESC, pf.prospect_surplus DESC, p.age ASC
        LIMIT 8
    """, (ed, tid, _FARM_MIN_FV)).fetchall():
        is_pitcher = r["role"] in (11, 12, 13)
        top_prospects.append({
            "pid": r["pid"], "name": r["name"], "age": r["age"],
            "pos": _display_pos(r["bucket"]) if r["bucket"] else "?",
            "fv": r["fv"] or 0, "fv_str": r["fv_str"] or str(r["fv"] or 0),
            "risk": r["risk"] or "", "level": r["level"] or "",
            "stints": _prospect_season_line(conn, r["pid"], is_pitcher, year,
                                            level_map, team_names),
        })

    # Risers: dev-speed Rising, quality-gated by FV, sorted by FV then z.
    risers = []
    has_dev = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='dev_speed'").fetchone()
    if has_dev:
        for r in conn.execute(f"""
            SELECT p.player_id AS pid, p.name AS name, ds.z AS z, ds.label AS label,
                   pf.fv AS fv, pf.fv_str AS fv_str, pf.bucket AS bucket, pf.level AS level
            FROM dev_speed ds
            JOIN players p ON p.player_id = ds.player_id
            JOIN prospect_fv pf ON pf.player_id = ds.player_id AND pf.eval_date=?
            WHERE {ORG_ID_SQL}=? AND ds.available=1 AND ds.css_class='rising'
              AND pf.fv >= ?
            ORDER BY pf.fv DESC, ds.z DESC
            LIMIT 6
        """, (ed, tid, _FARM_MIN_FV)).fetchall():
            risers.append({
                "pid": r["pid"], "name": r["name"],
                "z": round(r["z"], 1) if r["z"] is not None else None,
                "label": r["label"] or "Rising",
                "fv": r["fv"] or 0, "fv_str": r["fv_str"] or str(r["fv"] or 0),
                "pos": _display_pos(r["bucket"]) if r["bucket"] else "?",
                "level": r["level"] or "",
            })
    return {"top_prospects": top_prospects, "risers": risers,
            "contributors": _farm_contributors(conn, tid, ed)}


def get_season_review(team_id):
    """Assemble the Season in Review payload. See section comment above."""
    conn = get_db()
    cfg = get_cfg()
    import team_queries

    # Season year = latest year with team stats (handles offseason where the
    # just-completed season is the prior calendar year in some setups).
    yr = conn.execute(
        "SELECT MAX(year) FROM team_batting_stats WHERE split_id=1").fetchone()[0]
    if yr is None:
        return {"has_season": False}

    # Standings row for our team (record, pyth, run diff).
    standings = team_queries.get_standings()
    me = next((r for r in standings if r["tid"] == team_id), None)
    div = None
    if me:
        # division finish
        my_div = me.get("div")
        div_rows = [r for r in standings if r.get("div") == my_div]
        div_rows.sort(key=lambda x: -x["pct"])
        div = {"rank": next((i + 1 for i, r in enumerate(div_rows)
                             if r["tid"] == team_id), None),
               "n": len(div_rows), "name": my_div}

    # Pyth-vs-actual verdict.
    verdict = None
    if me and me.get("has_actual"):
        delta = round(me["w"] - me["pyth_w"])
        if delta >= 3:
            verdict = {"delta": delta, "text": f"Won {delta} more than run differential suggests — "
                       "outperformed the underlying numbers (regression risk, or a strong bullpen/clutch year).",
                       "tone": "warn"}
        elif delta <= -3:
            verdict = {"delta": delta, "text": f"Won {abs(delta)} fewer than run differential suggests — "
                       "the underlying performance was better than the record (bullpen or luck drag).",
                       "tone": "good"}
        else:
            verdict = {"delta": delta, "text": "Record closely matched the run differential — "
                       "the season played to its true talent.", "tone": "neutral"}

    strengths_off = _rank_categories(conn, team_id, yr, "team_batting_stats", _OFF_CATS)
    strengths_pit = _rank_categories(conn, team_id, yr, "team_pitching_stats", _PIT_CATS)
    all_cats = strengths_off + strengths_pit
    # Show every genuinely-good / genuinely-bad category (capped for layout),
    # never forcing a metric that isn't actually a strength or weakness.
    wins = sorted([c for c in all_cats if c["good"]], key=lambda x: x["rank"])[:5]
    fixes = sorted([c for c in all_cats if c["bad"]], key=lambda x: -x["rank"])[:5]

    players = _season_players(conn, team_id, yr)
    farm = _farm_development(conn, team_id, yr, cfg)

    # Focus handoff: short, directive takeaways — the weakest area to address
    # and whether the farm covers it, without restating the panels above.
    focus = []
    if fixes:
        labels = ", ".join(c["label"] for c in fixes[:2])
        focus.append(f"Address {labels} — {'this is' if len(fixes[:2]) == 1 else 'these are'} "
                     "your weakest area vs the league.")
    contributors = farm["contributors"]
    soon = [c for c in contributors if c["eta"] == "next season"]
    # Positions the near-term contributors can cover (dedup, keep order).
    covered = []
    for c in soon:
        if c["pos"] not in covered:
            covered.append(c["pos"])
    if soon:
        focus.append(f"Internal help is close: {len(soon)} MLB-ready prospect"
                     f"{'s' if len(soon) != 1 else ''} ({', '.join(covered[:4])}) — "
                     "don't overpay outside for what's already coming.")
    elif contributors:
        focus.append("Farm help is a year or two out — free agency and trades cover the short term.")
    else:
        focus.append("No near-term farm help — the roster must be built through free agency and trades.")

    return {
        "has_season": True,
        "year": yr,
        "team": me,
        "division": div,
        "verdict": verdict,
        "wins": wins,
        "fixes": fixes,
        "players": players,
        "farm": farm,
        "focus": focus,
    }


# ---------------------------------------------------------------------------
# Arbitration
# ---------------------------------------------------------------------------

def _load_perp_model(cfg):
    """Load the league's calibrated perpetual-arb salary model, or None.

    Without this, arb_salary_perpetual falls back to million-dollar-scaled
    defaults that floor to the minimum in low-salary-scale leagues.
    """
    import json
    mw_path = cfg.league_dir / "config" / "model_weights.json"
    if mw_path.exists():
        try:
            return json.load(open(mw_path)).get("ARB_SALARY_MODEL")
        except Exception:
            return None
    return None


def _career_war(conn, pid):
    """Cumulative career MLB WAR (batting + blended pitching) for the salary model."""
    bat = conn.execute(
        "SELECT COALESCE(SUM(war), 0) FROM mlb_batting_stats WHERE player_id=? AND split_id=1",
        (pid,)).fetchone()[0] or 0
    pit = conn.execute(
        "SELECT COALESCE(SUM((war + COALESCE(ra9war, war)) / 2.0), 0) "
        "FROM mlb_pitching_stats WHERE player_id=? AND split_id=1",
        (pid,)).fetchone()[0] or 0
    return bat + pit


def get_arbitration(team_id):
    """Arb-eligible players on this team, with projected salary and a
    tender / non-tender recommendation.

    Reuses arb.service_time (eligibility) + arb.arb_salary(_perpetual) using the
    league's calibrated model. All dollar thresholds scale with the league's
    $/WAR so this works at any salary scale (MLB millions or a retro league's
    thousands).
    """
    conn = get_db()
    ed = _eval_date(conn)
    if ed is None:
        return []
    cfg = get_cfg()
    min_sal = cfg.minimum_salary
    perp = cfg.perpetual_arb

    from statsplusplus.evaluation.arb import (
        service_time, arb_salary, arb_salary_perpetual,
    )
    from statsplusplus.config.league_config import dollars_per_war
    dpw = dollars_per_war(cfg.league_dir)
    perp_model = _load_perp_model(cfg) if perp else None

    # Tender tiers scaled to the league: a clear tender has surplus worth roughly
    # a win or more; anything positive is at least a marginal tender.
    strong_tender = 1.0 * dpw  # ~1 WAR of surplus

    # Attribute by the player's CURRENT org (ORG_ID_SQL), not c.contract_team_id:
    # the API retains the original signing team's ID in contract_team_id even
    # after a mid-season trade (documented unreliability — see system_overview.md),
    # so filtering on it mis-attributes traded players to their former team.
    rows = conn.execute(f"""
        SELECT c.player_id, p.name, p.age, c.salary_0, c.years, c.current_year,
               pe.surplus, pe.composite, pe.ceiling, pe.bucket,
               pe.peak_war, pe.stat_war
        FROM contracts c
        JOIN players p ON p.player_id = c.player_id
        JOIN player_evaluation pe ON pe.player_id = c.player_id AND pe.eval_date = ?
        WHERE {ORG_ID_SQL} = ? AND c.is_major = 1
          AND p.level IN ('1', 1)
          AND (c.years - c.current_year) <= 1
    """, (ed, team_id)).fetchall()

    out = []
    for r in rows:
        pid, name, age, sal = r[0], r[1], r[2], r[3] or 0
        bucket = r[9] or "?"
        st = service_time(conn, pid)

        # Eligibility is a SERVICE-TIME property, not a salary one — a player
        # can be arb-eligible while still paid the league minimum (e.g. svc
        # 3.029 on a $0.67M deal). The old `sal <= min_sal: continue` wrongly
        # skipped those.
        #
        # Perpetual/indefinite-arb leagues (PPL) have NO free agency and every
        # controlled player is perpetually in arb, so the standard 3-year / 6-year
        # service gates don't apply — the SQL's "contract expiring this year"
        # clause already scopes to the decisions that need making. For standard
        # arb, gate on completed service years (3 = eligible, 6 = graduated to FA).
        if not perp:
            if st.is_free_agent_eligible:
                continue                       # 6+ completed years → FA, not arb
            if st.completed_years < 3:
                continue                       # not yet arb-eligible

        # Projected next-year salary
        try:
            if perp:
                war = r[11] if r[11] is not None else (r[10] or 0)
                proj_sal = arb_salary_perpetual(
                    age, war or 0, dpw, min_sal,
                    career_war=_career_war(conn, pid), model=perp_model)
            else:
                # Derive the arb year from service (first arb at 3 completed
                # years) rather than hardcoding 1 — a 4th/5th-year player hits
                # the raise path, not the first-arb curve. (Super Two, which can
                # grant an early 4th arb year, is not yet modeled — see below.)
                arb_year = max(1, st.completed_years - 2)
                proj_sal = arb_salary(r[7] or 50, bucket, arb_year, sal, min_sal)
        except Exception:
            proj_sal = sal

        surplus = r[6] or 0
        # Tender recommendation from surplus (value net of cost over control),
        # scaled to the league's $/WAR.
        if surplus >= strong_tender:
            rec, rec_class = "Tender", "good"
        elif surplus >= 0:
            rec, rec_class = "Tender (marginal)", "ok"
        else:
            rec, rec_class = "Consider non-tender", "bad"

        out.append({
            "pid": pid, "name": name, "age": age,
            "pos": _display_pos(bucket) if bucket != "?" else "?",
            "cur_salary": sal,
            "proj_salary": proj_sal,
            "raise": proj_sal - sal,
            "surplus": surplus,  # raw dollars — template uses the money filter
            "service": st.display(),
            "rec": rec, "rec_class": rec_class,
        })
    out.sort(key=lambda x: -x["proj_salary"])
    return out


# ---------------------------------------------------------------------------
# Free agency — the actionable open-market pool (team_id = 0 = unsigned FA),
# driven by actual roster state, not inferred from lingering contract rows.
# Correct at any point in the offseason: an unsigned FA is available whether
# filing just happened or not.
# ---------------------------------------------------------------------------

# Composite floor for the market board — filter out replacement-level/roster
# filler so the board is a usable shortlist rather than the whole FA pool.
_MARKET_MIN_COMPOSITE = 48


def _team_need_positions(team_id):
    """Positions where this team is below league-average org depth (MLB+farm
    surplus), reusing the draft board's get_draft_org_depth signal. Returns a
    set of display-position keys (e.g. {"SS", "SP"}). Used to flag FAs that fill
    a need.
    """
    try:
        from team_queries import get_draft_org_depth
        depth = get_draft_org_depth(team_id)
    except Exception:
        return set()
    needs = set()
    for pos, d in (depth or {}).items():
        # get_draft_org_depth returns `ratio` = position depth vs league average.
        # < 1.0 means below-average depth at that position → a need. (Its own
        # scale treats < 0.6 as a clear gap, 0.6-1.2 as thin.)
        if (d.get("ratio") or 0) < 1.0:
            needs.add(pos)
    return needs


def _need_key(pos_disp):
    """Map a display position to the get_draft_org_depth key (collapses corner OF)."""
    if pos_disp in ("LF", "RF", "COF"):
        return "LF/RF"
    return pos_disp


# Game listed-position codes → display position (players.pos).
_LISTED_POS = {1: "P", 2: "C", 3: "1B", 4: "2B", 5: "3B", 6: "SS",
               7: "LF", 8: "CF", 9: "RF", 10: "DH"}


def _incumbent_by_pos(conn, team_id, ed):
    """Best MLB-roster composite per LISTED position for this team — the bar an
    FA must clear to be an upgrade. Keyed off the game position (players.pos),
    not the eval bucket, so a listed 1B is compared against the team's 1B even
    when his defensive bucket is 2B/COF. Pitchers keyed as SP/RP by role.
    """
    inc = {}
    for r in conn.execute("""
        SELECT p.pos, p.role, MAX(pe.composite)
        FROM player_evaluation pe JOIN players p ON p.player_id = pe.player_id
        WHERE pe.eval_date = ? AND pe.team_id = ? AND pe.level = 'MLB'
        GROUP BY p.pos, p.role
    """, (ed, team_id)).fetchall():
        pos, role, comp = r[0], r[1], r[2]
        key = "SP" if role in (11, 12) else ("RP" if role == 13 else _LISTED_POS.get(pos))
        if key is None:
            continue
        inc[key] = max(inc.get(key, 0), comp or 0)
    return inc


def _fa_pos(pos, role, bucket):
    """Display position for a free agent, preferring the game listed position
    (with SP/RP from role), falling back to the eval bucket."""
    if role in (11, 12):
        return "SP"
    if role == 13:
        return "RP"
    listed = _LISTED_POS.get(pos)
    if listed and listed != "P":
        return listed
    return _display_pos(bucket) if bucket else "?"


def _last_season(conn, pid, is_pitcher):
    """Prior-season line as a dict, or None. Includes sample size (PA/IP), the
    rate line, and ACTUAL WAR for that season (this is the number that matches
    the player page's season stats — distinct from the projected peak_war).
    """
    if is_pitcher:
        r = conn.execute("""
            SELECT year, w, l, era, k, outs, war, ra9war FROM mlb_pitching_stats
            WHERE player_id=? AND split_id=1 AND ip > 0 ORDER BY year DESC LIMIT 1
        """, (pid,)).fetchone()
        if not r:
            return None
        ip = (r[5] or 0) / 3.0
        # Blended WAR to match how the app reports pitcher WAR elsewhere
        war = ((r[6] or 0) + (r[7] if r[7] is not None else r[6] or 0)) / 2.0
        return {"line": f"{r[1]}-{r[2]}, {r[3]:.2f} ERA, {r[4]} K",
                "sample": f"{int(ip)}.{int(round((ip - int(ip)) * 3))} IP",
                "war": round(war, 1), "year": r[0]}
    r = conn.execute("""
        SELECT year, ab, h, hr, rbi, pa, war FROM mlb_batting_stats
        WHERE player_id=? AND split_id=1 AND ab > 0 ORDER BY year DESC LIMIT 1
    """, (pid,)).fetchone()
    if not r:
        return None
    avg = (r[2] / r[1]) if r[1] else 0
    return {"line": f".{int(round(avg * 1000)):03d}, {r[3]} HR, {r[4]} RBI",
            "sample": f"{r[5] or 0} PA",
            "war": round(r[6] or 0, 1), "year": r[0]}


def _proj_next_war(conn, pid, age, bucket, composite, ceiling, peak_war,
                   years_control, dpw, min_sal, weights):
    """Next-season projected WAR — the SAME number the player valuation page
    shows, by calling the shared compute_player_value and reading the first
    control-year of its breakdown. Single source of truth; do NOT re-derive
    (peak_war × aging_mult misses the development/confidence discount that
    dominates for unproven players).
    """
    from statsplusplus.evaluation.player_value import compute_player_value
    cpa = conn.execute(
        "SELECT COALESCE(SUM(ab + COALESCE(bb,0) + COALESCE(hbp,0) + COALESCE(sf,0)), 0) "
        "FROM mlb_batting_stats WHERE player_id=? AND split_id=1", (pid,)).fetchone()[0]
    cip = conn.execute(
        "SELECT COALESCE(SUM(ip), 0) FROM mlb_pitching_stats WHERE player_id=? AND split_id=1",
        (pid,)).fetchone()[0]
    try:
        res = compute_player_value(
            fv_continuous=0.0, bucket=bucket, age=age, level="MLB",
            composite=composite or 50, ceiling=ceiling or 50,
            career_pa=int(cpa), career_ip=float(cip), stat_war=peak_war,
            years_control=years_control or 1, salaries=None,
            dpw=dpw, min_sal=min_sal, weights=weights)
        bd = res.get("breakdown")
        if bd:
            return round(bd[0]["war"], 1)
    except Exception:
        pass
    return None


def get_market_board(team_id, limit=60):
    """The actual open-market free agent pool.

    Includes only genuinely signable players: currently unsigned
    (team_id = 0, free_agent = 1), above a composite floor, AND with prior stats
    in THIS league. Players from foreign leagues (e.g. NPB) appear in the API's
    global player dump with free_agent=1 but have never played here and can't be
    signed — the "has played in this league" check excludes them.

    "Fills a need" requires BOTH: the team is below league-average org depth at
    the player's position AND he is an actual upgrade over the team's current
    best there (or the team has no one). Position and incumbent are keyed off the
    game listed position, not the eval bucket, so a listed 1B is compared to the
    team's 1B.
    """
    conn = get_db()
    ed = _eval_date(conn)
    if ed is None:
        return []
    cfg = get_cfg()
    need_positions = _team_need_positions(team_id)
    incumbent = _incumbent_by_pos(conn, team_id, ed)
    from statsplusplus.evaluation.constants import load_model_weights
    from statsplusplus.config.league_config import dollars_per_war, league_minimum
    weights = load_model_weights(cfg.league_dir)
    dpw = dollars_per_war(cfg.league_dir)
    min_sal = league_minimum(cfg.league_dir)
    rows = conn.execute("""
        SELECT p.player_id, p.name, p.age, pe.composite, pe.ceiling, pe.peak_war,
               pe.bucket, lr.bats, lr.throws, p.pos, p.role, pe.years_control
        FROM players p
        JOIN player_evaluation pe ON pe.player_id = p.player_id AND pe.eval_date = ?
        LEFT JOIN latest_ratings lr ON lr.player_id = p.player_id
        WHERE p.free_agent = 1 AND p.team_id = 0
          AND pe.composite >= ?
          AND (EXISTS (SELECT 1 FROM mlb_batting_stats b WHERE b.player_id = p.player_id)
            OR EXISTS (SELECT 1 FROM mlb_pitching_stats pt WHERE pt.player_id = p.player_id))
        ORDER BY pe.composite DESC
        LIMIT ?
    """, (ed, _MARKET_MIN_COMPOSITE, limit)).fetchall()
    _hand = {1: "R", 2: "L", 3: "S", "R": "R", "L": "L", "S": "S"}
    out = []
    for r in rows:
        bucket = r[6] or "?"
        pos = _fa_pos(r[9], r[10], bucket)
        comp = r[3] or 0
        is_pitcher = pos in ("SP", "RP")
        inc = incumbent.get(pos)
        is_upgrade = inc is None or comp > inc
        fills_need = (_need_key(pos) in need_positions) and is_upgrade
        # Next-season projection — the SAME value the player valuation page shows
        # (shared compute_player_value; single source of truth).
        proj_war = _proj_next_war(conn, r[0], r[2], bucket, comp, r[4], r[5],
                                  r[11], dpw, min_sal, weights)
        # Recommended contract — a value-based cost estimate the FA cart draws
        # down against fa_budget (aav). Priced off average aged WAR across the
        # term (recommended_contract owns the aging), so pass peak_war + bucket
        # rather than the already-aged next-season figure. Not the real demand.
        from statsplusplus.config.finance_settings import recommended_contract
        rec = recommended_contract(r[5], dpw, r[2], min_sal, bucket=bucket, weights=weights)
        out.append({
            "pid": r[0], "name": r[1], "age": r[2],
            "pos": pos,
            "composite": comp,
            "ceiling": r[4] or 0,
            "proj_war": proj_war,
            "bats": _hand.get(r[7], "?"),
            "throws": _hand.get(r[8], "?"),
            "last": _last_season(conn, r[0], is_pitcher),
            "fills_need": fills_need,
            "rec_aav": rec["aav"],
            "rec_years": rec["years"],
            "rec_total": rec["total"],
        })
    return out


# ---------------------------------------------------------------------------
# Extension candidates
# ---------------------------------------------------------------------------

def get_extension_candidates(team_id):
    """High-surplus own players within ~2 years of free agency — locking in
    now can beat arb escalation / an open-market bid.
    """
    conn = get_db()
    ed = _eval_date(conn)
    if ed is None:
        return []
    from statsplusplus.config.league_config import dollars_per_war
    cfg = get_cfg()
    threshold = 0.75 * dollars_per_war(cfg.league_dir)  # ~0.75 WAR of surplus, league-scaled
    # Current-org attribution (not stale c.contract_team_id) — see get_arbitration.
    rows = conn.execute(f"""
        SELECT c.player_id, p.name, p.age, c.years, c.current_year,
               pe.surplus, pe.composite, pe.ceiling, pe.bucket
        FROM contracts c
        JOIN players p ON p.player_id = c.player_id
        JOIN player_evaluation pe ON pe.player_id = c.player_id AND pe.eval_date = ?
        WHERE {ORG_ID_SQL} = ? AND c.is_major = 1 AND p.level IN ('1', 1)
          AND (c.years - c.current_year) BETWEEN 1 AND 2
    """, (ed, team_id)).fetchall()

    out = []
    for r in rows:
        surplus = r[5] or 0
        if surplus < threshold:  # only meaningful-value players (league-scaled)
            continue
        out.append({
            "pid": r[0], "name": r[1], "age": r[2],
            "pos": _display_pos(r[8]) if r[8] else "?",
            "yrs_left": max(1, r[3] - r[4]),
            "surplus": surplus,  # raw dollars — template uses the money filter
            "composite": r[6] or 0,
        })
    out.sort(key=lambda x: -x["surplus"])
    return out


# ---------------------------------------------------------------------------
# Contract options — this-offseason team/player/vesting option decisions
# ---------------------------------------------------------------------------

def _proj_value_at_year(conn, pid, age, bucket, composite, ceiling, peak_war,
                        target_control_year, dpw, min_sal, weights):
    """Projected market VALUE (dollars) for a player at a given control year
    ahead, via the shared compute_player_value (single source of truth). Reads
    the matching row of its breakdown. Returns None on failure.
    """
    from statsplusplus.evaluation.player_value import compute_player_value
    cpa = conn.execute(
        "SELECT COALESCE(SUM(ab + COALESCE(bb,0) + COALESCE(hbp,0) + COALESCE(sf,0)), 0) "
        "FROM mlb_batting_stats WHERE player_id=? AND split_id=1", (pid,)).fetchone()[0]
    cip = conn.execute(
        "SELECT COALESCE(SUM(ip), 0) FROM mlb_pitching_stats WHERE player_id=? AND split_id=1",
        (pid,)).fetchone()[0]
    try:
        res = compute_player_value(
            fv_continuous=0.0, bucket=bucket, age=age, level="MLB",
            composite=composite or 50, ceiling=ceiling or 50,
            career_pa=int(cpa), career_ip=float(cip), stat_war=peak_war,
            years_control=max(target_control_year, 1), salaries=None,
            dpw=dpw, min_sal=min_sal, weights=weights)
        bd = res.get("breakdown") or []
        if not bd:
            return None
        idx = min(max(target_control_year - 1, 0), len(bd) - 1)
        return bd[idx].get("market_value")
    except Exception:
        return None


def get_option_decisions(team_id):
    """Own-team players with a contract option, grouped by decision timing.

    An option for year Y is decided in the offseason *before* Y. We can't
    reliably read from the API whether this offseason's window has already
    passed, so we relabel honestly rather than guess:

    - **this_offseason** : option year == game_year + 1 (the decision that
      belongs to the current offseason — may already be resolved in-game).
    - **upcoming**        : option year >= game_year + 2 (future offseasons).

    - **Team options**: recommend Exercise vs Decline via the shared valuation
      model — exercising costs the option salary, declining costs the buyout, so
      the breakeven is ``proj_value > option_salary - buyout``. Shown for
      upcoming options too, framed as advance planning.
    - **Player / vesting options**: informational (the team doesn't decide).

    The option year is derived from the contract (``season_year + offset``), NOT
    the game year — a last-year option resolves at ``season_year + years - 1``,
    a next-last-year option one year earlier.

    All dollar figures are raw league dollars (template uses the money filter).
    """
    conn = get_db()
    ed = _eval_date(conn)
    if ed is None:
        return {"this_offseason": [], "upcoming": []}
    cfg = get_cfg()
    from statsplusplus.evaluation.constants import load_model_weights
    from statsplusplus.config.league_config import dollars_per_war, league_minimum
    weights = load_model_weights(cfg.league_dir)
    dpw = dollars_per_war(cfg.league_dir)
    min_sal = league_minimum(cfg.league_dir)

    # Current-org attribution (not stale c.contract_team_id) — see get_arbitration.
    rows = conn.execute(f"""
        SELECT c.player_id, p.name, p.age, c.years, c.current_year, c.season_year,
               c.salary_0, c.salary_1, c.salary_2, c.salary_3, c.salary_4,
               c.salary_5, c.salary_6, c.salary_7, c.salary_8, c.salary_9,
               c.salary_10, c.salary_11, c.salary_12, c.salary_13, c.salary_14,
               c.last_year_team_option, c.last_year_player_option,
               c.last_year_vesting_option, c.last_year_option_buyout,
               c.next_last_year_team_option, c.next_last_year_player_option,
               c.next_last_year_vesting_option, c.next_last_year_option_buyout,
               pe.composite, pe.ceiling, pe.bucket, pe.peak_war
        FROM contracts c
        JOIN players p ON p.player_id = c.player_id
        JOIN player_evaluation pe ON pe.player_id = c.player_id AND pe.eval_date = ?
        WHERE {ORG_ID_SQL} = ? AND c.is_major = 1 AND p.level IN ('1', 1)
          AND (c.last_year_team_option = 1 OR c.last_year_player_option = 1
               OR c.last_year_vesting_option = 1
               OR c.next_last_year_team_option = 1 OR c.next_last_year_player_option = 1
               OR c.next_last_year_vesting_option = 1)
    """, (ed, team_id)).fetchall()

    game_year = int(cfg.year)
    entries = []
    for r in rows:
        pid, name, age = r[0], r[1], r[2]
        years, season_year = r[3] or 0, r[5] or game_year
        salaries = list(r[6:21])
        composite, ceiling, bucket, peak_war = r[29], r[30], r[31] or "?", r[32]
        pos = _display_pos(bucket) if bucket != "?" else "?"

        def _sal(idx):
            return (salaries[idx] or 0) if 0 <= idx < len(salaries) else 0

        # (salary index within the contract, option year, T/P/V flags, buyout)
        slots = [
            (years - 1, (r[21], r[22], r[23]), r[24] or 0),   # last-year option
            (years - 2, (r[25], r[26], r[27]), r[28] or 0),   # next-last-year option
        ]
        for opt_idx, (team_o, player_o, vesting_o), buyout in slots:
            if opt_idx < 0 or not (team_o or player_o or vesting_o):
                continue
            option_year = season_year + opt_idx
            opt_sal = _sal(opt_idx)
            if team_o:
                typ = "Team"
            elif player_o:
                typ = "Player"
            else:
                typ = "Vesting"
            entry = {
                "pid": pid, "name": name, "age": age, "pos": pos,
                "type": typ, "year": option_year,
                "option_salary": opt_sal, "buyout": buyout,
                "proj_value": None, "rec": None, "rec_class": "ok",
            }
            if typ == "Team":
                # control years from now (game_year) to the option year, 1-based
                ctrl = max(option_year - game_year, 1)
                pv = _proj_value_at_year(conn, pid, age, bucket, composite, ceiling,
                                         peak_war, ctrl, dpw, min_sal, weights)
                entry["proj_value"] = pv
                if pv is not None:
                    breakeven = opt_sal - buyout
                    if pv >= opt_sal:
                        entry["rec"], entry["rec_class"] = "Exercise", "good"
                    elif pv > breakeven:
                        entry["rec"], entry["rec_class"] = "Exercise (marginal)", "ok"
                    else:
                        entry["rec"], entry["rec_class"] = "Decline", "bad"
            elif typ == "Player":
                entry["rec"], entry["rec_class"] = "Player decides", "ok"
            else:
                entry["rec"], entry["rec_class"] = "Auto (performance)", "ok"
            entries.append(entry)

    # Split by decision timing: this offseason (option year == game_year + 1)
    # vs upcoming (game_year + 2 and beyond). Anything with an option year at or
    # before the current game year is a past/expiring edge case — group it with
    # "this offseason" so it isn't silently dropped.
    this_off = [e for e in entries if e["year"] <= game_year + 1]
    upcoming = [e for e in entries if e["year"] >= game_year + 2]
    this_off.sort(key=lambda x: (x["type"] != "Team", -(x["option_salary"] or 0)))
    upcoming.sort(key=lambda x: (x["year"], x["type"] != "Team", -(x["option_salary"] or 0)))
    return {"this_offseason": this_off, "upcoming": upcoming}


# ---------------------------------------------------------------------------
# Rule 5 — protect (your eligibles worth a 40-man spot) + targets (others')
# ---------------------------------------------------------------------------
#
# `years_protected_from_rule_5` (from /players) is the protection WINDOW length —
# how many pro seasons a player is shielded before exposure — NOT a countdown.
# Live vMLB /players (Session 98): the field holds only 5 (signed age ≤18) or 4
# (signed older), the two real Rule 5 thresholds; it does not tick down to 0.
# The large `ypr=0` population is the level-0 retired/FA pool, not eligibles.
# Eligibility is service-based and was pinned by diffing against OOTP's exported
# draft pool (1,919 players): a player is exposed once his accumulated
# `pro_service_years` reaches ONE SHORT of his `years_protected_from_rule_5`
# window (OOTP exposes a year earlier than the raw window). `draft_eligible` is
# amateur-draft eligibility (dormant outside the pre-draft window), NOT Rule 5.
#
# Eligible & exposed = pro_service_years >= years_protected_from_rule_5 - 1, not
# on the 40-man (is_on_secondary != 1), and not the level-0 historical/FA pool.
# MLB-level players (level '1') CAN be eligible — 31 pool members are on the
# active roster but off the 40-man — so only level '0' is excluded, not '1'.

# MLB-viable floor for the target side: a Rule 5 pick must stick on the active
# roster all year, so only players with real MLB projection are worth taking.
_RULE5_TARGET_MIN_FV = 45


def _rule5_readiness(level, age, mlb_service, bucket=None):
    """Classify how DRAFTABLE a Rule 5-eligible player is — i.e. how realistically
    a rival could carry him on their active 26-man roster all season (the Rule 5
    retention rule). This is the exposure-risk lens, orthogonal to raw talent.

    Hitters — must hold a bench/bat spot, so the bar is level + age:
      MLB-ready  : AAA / MLB, OR AA age ≥ 24, OR prior MLB service.
      Near-ready : AA (younger), or a young AAA bat.
      Distant    : A / Rookie and young.

    PITCHERS — RP-as-floor. A Rule 5 arm doesn't need to stick in the ROTATION;
    the classic Rule 5 move is to carry a live arm in the BULLPEN for the year.
    Relief needs less polish than starting, so the bar to "usable in relief" is
    lower than the hitter bar: any arm at AA+ (or with MLB service) is MLB-ready
    as a reliever; only A/Rookie arms are Near-ready/Distant. This is a stickiness
    (display/eligibility) judgement — it does NOT re-value the pitcher as an RP;
    the SP↔RP *valuation* (stuff-by-role) is a separate tracked model item.

    Returns one of "MLB-ready" / "Near-ready" / "Distant".
    """
    lvl = (level or "").upper()
    if (mlb_service or 0) > 0:
        return "MLB-ready"

    is_pitcher = bucket in _PITCHER_BUCKETS
    if is_pitcher:
        # Relief floor: AA+ arms can hold a bullpen spot now.
        if lvl in ("MLB", "AAA", "AA"):
            return "MLB-ready"
        if lvl in ("A", "A-SHORT", "A+"):
            return "Near-ready"
        return "Distant"

    # Hitters — need the bat to play, so hold the stiffer level/age bar.
    if lvl in ("MLB", "AAA"):
        return "MLB-ready"
    if lvl == "AA":
        return "MLB-ready" if (age or 0) >= 24 else "Near-ready"
    return "Distant"


def _rule5_role_label(bucket, listed_role):
    """Realistic Rule 5 role for the card/table. For arms, surface the bullpen
    path explicitly since that's how most Rule 5 pitchers actually stick:

      bucket RP                      -> "RP"
      bucket SP, listed as starter   -> "SP → RP"   (carry him in relief this year)
      bucket SP, listed as reliever  -> "RP"        (already a pen arm)

    Hitters just show their position bucket. `listed_role`: 11=SP, 12=RP, 13=CL.
    """
    if bucket == "RP":
        return "RP"
    if bucket == "SP":
        # listed_role 12/13 = already a reliever/closer in-game → just "RP".
        return "RP" if listed_role in (12, 13) else "SP → RP"
    return _display_pos(bucket) if bucket else "?"


# Protect recommendation matrix — value (FV) × draftability (readiness tier).
# Each cell is (rec_label, rec_class). "Expose" is styled "bad" only as a visual
# cue (red = letting him go), not a knock on the player. See the design note in
# get_rule5. The 40-man-crunch modifier (advisory) is applied separately.
_PROTECT_MATRIX = {
    # (value_tier, readiness) -> (rec, rec_class)
    ("high",   "MLB-ready"):  ("Protect",  "good"),
    ("high",   "Near-ready"): ("Protect",  "good"),
    ("high",   "Distant"):    ("Consider", "ok"),
    ("solid",  "MLB-ready"):  ("Protect",  "good"),
    ("solid",  "Near-ready"): ("Consider", "ok"),
    ("solid",  "Distant"):    ("Expose",   "bad"),
    ("fringe", "MLB-ready"):  ("Consider", "ok"),
    ("fringe", "Near-ready"): ("Expose",   "bad"),
    ("fringe", "Distant"):    ("Expose",   "bad"),
}


def _rule5_protect_rec(fv, readiness, roster_full):
    """Protect-vs-expose recommendation for one eligible player.

    value tier: FV ≥ 50 = high, 45–49 = solid, ≤ 44 = fringe.
    40-man modifier (advisory): when the roster is full, a Protect costs a
    corresponding move, so we FLAG that cost on the chip ("Protect (needs a
    40-man move)", styled ok) without demoting the call — the GM decides who
    they'd cut. Clear Expose/Consider calls are unaffected.

    Returns (rec, rec_class, readiness, why).
    """
    vt = "high" if fv >= 50 else "solid" if fv >= 45 else "fringe"
    rec, rec_class = _PROTECT_MATRIX[(vt, readiness)]

    why = {
        "MLB-ready": "a rival could carry him on their active roster now",
        "Near-ready": "a rebuilding team might stash him",
        "Distant": "too far from the majors for a rival to keep him all year",
    }[readiness]
    why = f"FV {fv}, {readiness} — {why}"

    if roster_full and rec == "Protect":
        rec = "Protect (needs a 40-man move)"
        rec_class = "ok"
        why += "; your 40-man is full, so protecting means a corresponding move"

    return rec, rec_class, readiness, why


# The 40-man (secondary) roster cap. Standard across OOTP leagues.
_FORTY_MAN_CAP = 40


def _forty_man_count(conn, team_id):
    """How many players this org currently has on its 40-man (secondary) roster.
    Uses the standard org attribution (ORG_ID_SQL) so minor-league affiliates
    count toward the parent club."""
    row = conn.execute(
        f"SELECT COUNT(*) n FROM players p "
        f"WHERE p.is_on_secondary = 1 AND {ORG_ID_SQL} = ?",
        (team_id,)
    ).fetchone()
    return row["n"] if row else 0


def _rule5_cut_candidates(conn, team_id, ed, lvl_by_league, level_names, limit=6):
    """"Low-hanging fruit" to clear a 40-man spot — players low on BOTH value axes.

    Neither metric works alone (verified against vMLB):
      • surplus alone  — the WAR projection reads off noisy small-sample reliever
        stats (stat_confidence ramp), so good RPs like Gaytan/Shackleton show
        near-zero surplus and look cuttable (tracked model item). A high-composite
        arm must NOT be flagged on broken surplus.
      • composite alone — flags premium young prospects (low current ability, huge
        FUTURE surplus) as cuttable. A high-surplus prospect must NOT be flagged.

    So a genuine cut candidate is low on BOTH: little current ability (composite)
    AND little projected value (surplus). That gate neutralizes each metric's blind
    spot — Gaytan survives on composite, a top prospect survives on surplus. Ranked
    by the combined normalized score (lowest first). Each carries comp/ceiling (the
    value axes shown), FV (for prospects), and a level-qualified stat line. Still
    advisory; the GM weighs contract/options/role.
    """
    rows = conn.execute(f"""
        SELECT p.player_id, p.name, p.age, pe.fv, pe.fv_str, pe.bucket,
               pe.composite, pe.ceiling, pe.surplus, pe.level
        FROM player_evaluation pe
        JOIN players p ON pe.player_id = p.player_id
        WHERE pe.eval_date = ? AND {ORG_ID_SQL} = ? AND p.is_on_secondary = 1
    """, (ed, team_id)).fetchall()

    _SURP_CAP = 5_000_000  # surplus above this is clearly a keeper on value alone

    def score(r):
        comp_n = (r["composite"] or 0) / 80.0
        surp_n = min(max(r["surplus"] or 0, 0), _SURP_CAP) / _SURP_CAP
        return comp_n + surp_n  # low on both → low score

    chosen = sorted(rows, key=score)[:limit]
    stat_lines = _rule5_stat_lines(conn, [r["player_id"] for r in chosen],
                                   lvl_by_league, level_names)
    out = []
    for r in chosen:
        fv = r["fv"]
        pos = _display_pos(r["bucket"]) if r["bucket"] else "?"
        sl = stat_lines.get(r["player_id"])
        out.append({
            "pid": r["player_id"], "name": r["name"], "age": r["age"],
            "pos": pos, "fv": fv or 0,
            # FV string only when it's a prospect (graduated MLBers have fv NULL).
            "fv_str": r["fv_str"] if fv else None,
            "level": r["level"] or "", "surplus": r["surplus"] or 0,
            "composite": r["composite"] or 0, "ceiling": r["ceiling"] or 0,
            "stat_line": sl["line"] if sl else None,
            "stat_level": sl["level"] if sl else None,
        })
    return out


def _rule5_draft_position(conn, team_id):
    """Projected Rule 5 pick slot: reverse regular-season standings (worst record
    picks first), scoped to the MLB clubs only (the standings table also carries
    minor-league affiliates, which must be excluded or the 0-0 affiliates sort to
    the top). Returns {"pick": int, "of": int} or None if standings unavailable.

    Approximate — OOTP's exact order can apply tie-breaks (prior-year record etc.)
    we don't model, so the UI should present it as "~Nth", not a hard slot.
    """
    try:
        mlb_ids = set(int(k) for k in get_cfg().team_abbr_map.keys())
    except Exception:
        return None
    if not mlb_ids:
        return None
    rows = conn.execute(
        f"SELECT team_id, w, l, pct FROM standings "
        f"WHERE team_id IN ({','.join('?' * len(mlb_ids))}) "
        f"ORDER BY pct ASC, l DESC",
        list(mlb_ids)
    ).fetchall()
    if not rows:
        return None
    for i, r in enumerate(rows, 1):
        if r["team_id"] == team_id:
            return {"pick": i, "of": len(rows)}
    return None


# Hitter buckets (anything not a pitcher role) — for stat-line selection.
_PITCHER_BUCKETS = {"SP", "RP"}


def _rule5_stat_lines(conn, pids, lvl_by_league, level_names):
    """Compact most-recent-season stat line per player, QUALIFIED BY the level the
    stats were accrued at (a .360 in AAA is worth more than in AA — and a player's
    current `level` isn't necessarily where he played last year). Picks the overall
    (split_id=1) row with the most PA (hitters) / IP (pitchers) in the player's
    latest year. Returns {pid: {kind, line, war, year, level}}.

      lvl_by_league : {league_id: level_int}  (from the milb_league_map)
      level_names   : {level_int: name}       (level_map; e.g. 2->"AAA")

    A NULL league_id = MLB. `level` is the resolved display label (AAA/AA/MLB/…).
    """
    if not pids:
        return {}

    def level_label(league_id):
        if league_id is None:
            return "MLB"
        lv = lvl_by_league.get(league_id)
        return level_names.get(lv, "MiLB") if lv is not None else "MiLB"

    def level_int(league_id):
        # 1=MLB … higher = lower level; None → treat as deep MiLB (6).
        if league_id is None:
            return 1
        return lvl_by_league.get(league_id, 6)

    out = {}
    ph = ",".join("?" * len(pids))
    # Hitters — latest year, overall split, most PA.
    for r in conn.execute(
        f"""SELECT b.player_id, b.year, b.league_id, b.pa, b.avg, b.obp, b.slg,
                   b.hr, b.sb, b.war
            FROM batting_stats b
            JOIN (SELECT player_id, MAX(year) y FROM batting_stats
                  WHERE split_id=1 AND player_id IN ({ph}) GROUP BY player_id) m
              ON b.player_id=m.player_id AND b.year=m.y
            WHERE b.split_id=1
            ORDER BY b.pa DESC""", list(pids)):
        if r["player_id"] in out or (r["pa"] or 0) < 1:
            continue
        obp = r["obp"] or 0
        slg = r["slg"] or 0
        out[r["player_id"]] = {
            "kind": "bat", "year": r["year"], "war": r["war"],
            "level": level_label(r["league_id"]), "level_int": level_int(r["league_id"]),
            "ops": obp + slg, "pa": r["pa"] or 0,
            "line": f"{_slash(r['avg'])}/{_slash(r['obp'])}/{_slash(r['slg'])}, "
                    f"{r['hr'] or 0} HR, {r['sb'] or 0} SB ({r['pa']} PA)",
        }
    # Pitchers — latest year, overall split, most IP.
    for r in conn.execute(
        f"""SELECT p.player_id, p.year, p.league_id, p.ip, p.era, p.k, p.bb,
                   p.gs, p.war
            FROM pitching_stats p
            JOIN (SELECT player_id, MAX(year) y FROM pitching_stats
                  WHERE split_id=1 AND player_id IN ({ph}) GROUP BY player_id) m
              ON p.player_id=m.player_id AND p.year=m.y
            WHERE p.split_id=1
            ORDER BY p.ip DESC""", list(pids)):
        if r["player_id"] in out or (r["ip"] or 0) < 1:
            continue
        ip = r["ip"] or 0
        era = r["era"] if r["era"] is not None else None
        k = r["k"] or 0
        bb = r["bb"] or 0
        out[r["player_id"]] = {
            "kind": "pit", "year": r["year"], "war": r["war"],
            "level": level_label(r["league_id"]), "level_int": level_int(r["league_id"]),
            "era": era, "ip": ip, "k9": (k * 9.0 / ip) if ip else 0,
            "k_bb": (k / bb) if bb else (k if k else 0),
            "line": f"{(era if era is not None else 0):.2f} ERA, "
                    f"{ip:.0f} IP, {k}/{bb} K/BB",
        }
    return out


def _slash(v):
    """Format a rate stat as a leading-dot slash number (.274)."""
    try:
        return f"{v:.3f}".lstrip("0") or ".000"
    except (TypeError, ValueError):
        return "—"


# Level credit — a dominant line at a lower level is worth much less (user: "that
# statline in AAA is worth more than in AA"). For a RULE 5 pick, who must jump
# STRAIGHT to the majors, A-ball and below are barely predictive, so the discount
# is steep: only AAA/AA/MLB production carries real weight.
# 1=MLB, 2=AAA, 3=AA, 4=A, 5=A-Short, 6=Rookie.
_LEVEL_CREDIT = {1: 1.0, 2: 1.0, 3: 0.80, 4: 0.40, 5: 0.30, 6: 0.25}

# The top-targets strip only headlines players whose readiness is backed by
# UPPER-level reps (the only realistic straight-to-MLB sticks). Lower-level
# players still appear in the full pool, just not in the headline strip.
_RULE5_STRIP_LEVELS = {"MLB", "AAA", "AA"}


def _rule5_perf_score(sl):
    """Level-adjusted recent-performance score in [0,1] from the attached stat
    line (`sl` from _rule5_stat_lines). This is the signal that separates a real
    Rule 5 pick from an FV mirage — a shiny FV with a 5.84 ERA shouldn't rank over
    a proven arm. Returns 0.5 (neutral) when there's no usable sample.

    Arms  : K/BB (the user's explicit signal) + ERA, each mapped to [0,1].
    Bats  : OPS vs a rough replacement baseline, PA-gated.
    All scaled by level credit so a lower-level line counts for less.
    """
    if not sl:
        return 0.5
    cred = _LEVEL_CREDIT.get(sl.get("level_int", 3), 0.7)

    if sl["kind"] == "pit":
        if (sl.get("ip") or 0) < 10:            # too few innings to read
            return 0.5
        # K/BB: 1.5→weak, 3.0→good, 5.0→elite. ERA: 5.0→weak, 3.5→good, 2.5→elite.
        kbb = sl.get("k_bb") or 0
        era = sl.get("era")
        kbb_s = _clamp01((kbb - 1.5) / (5.0 - 1.5))
        era_s = 0.5 if era is None else _clamp01((5.0 - era) / (5.0 - 2.5))
        raw = 0.6 * kbb_s + 0.4 * era_s        # K/BB leads (skill signal)
    else:
        if (sl.get("pa") or 0) < 60:            # tiny bat sample
            return 0.5
        ops = sl.get("ops") or 0
        # OPS: .650→weak, .780→good, .950→elite (level-agnostic baseline; the
        # level credit below handles the "where" discount).
        raw = _clamp01((ops - 0.650) / (0.950 - 0.650))

    # Apply level credit, but keep a neutral floor so a strong lower-level line
    # isn't crushed to zero — it's discounted, not disqualified.
    return 0.5 + (raw - 0.5) * (0.5 + 0.5 * cred) if raw >= 0.5 \
        else raw * (0.5 + 0.5 * cred) + 0.5 * (1 - (0.5 + 0.5 * cred))


def _clamp01(x):
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def _rule5_target_score(fv, age, perf):
    """Composite ranking score for a Rule 5 target (readiness already gates the
    pool to MLB-ready for the top strip). Blends:
      performance (recent, level-adjusted) — RESULTS-FIRST (user direction),
      upside (FV + youth)                  — the tiebreak among similar performers.
    Performance is weighted enough to reorder across a ~5-point FV gap so a
    proven FV-45 arm outranks an FV-50 arm with a poor line, while FV/age still
    tilt between comparable performers. Higher = better.
    """
    fv_s = _clamp01((fv - 40) / (65 - 40))          # FV 40→0, 65→1
    age_s = _clamp01((26 - (age or 26)) / (26 - 20))  # 26→0, 20→1 (youth = upside)
    upside = 0.75 * fv_s + 0.25 * age_s
    return 0.60 * perf + 0.40 * upside              # results-first blend


def get_rule5(team_id):
    """Rule 5 decisions for this offseason.

    Returns {"protect": [...], "targets": [...], "available": bool}:
      - protect  : your org's Rule 5-eligible players (service window elapsed,
                   off the 40-man), ranked by FV/surplus — add-to-40-man candidates.
      - targets  : other orgs' eligible + MLB-viable (FV >= 45) players you could
                   draft, ranked by FV.

    `available` is False when the field isn't populated yet (pre-refresh), so the
    template can show an informative message rather than empty tables.
    """
    conn = get_db()
    ed = _eval_date(conn)

    # Has the ypr field been populated at all? (NULL everywhere pre-refresh.)
    has_field = conn.execute(
        "SELECT 1 FROM players WHERE years_protected_from_rule_5 IS NOT NULL LIMIT 1"
    ).fetchone() is not None
    if ed is None or not has_field:
        return {"protect": [], "targets": [], "available": has_field}

    # Base eligibility predicate (shared by both sides).
    #
    # `years_protected_from_rule_5` is the player's protection WINDOW length — the
    # number of pro seasons he is shielded before exposure — NOT a live countdown.
    # Confirmed against the vMLB live /players feed (Session 98): the field only
    # ever holds 5 (signed young, age ≤18) or 4 (signed older), the two real Rule 5
    # thresholds; it does not decrement toward 0. (The large `ypr=0` population is
    # the level-0 retired/FA pool, not eligible players.) `pro_service_years` is a
    # well-populated accumulated-service count. A player is exposed once his
    # accumulated pro service reaches ONE SHORT OF his protection window:
    #       pro_service_years >= years_protected_from_rule_5 - 1
    #
    # The off-by-one and the level test below were both pinned by diffing against
    # OOTP's own exported draft pool (1,919 players): the strict `>= ypr` boundary
    # under-counted by 842 (OOTP exposes a year earlier than the raw window), and
    # 31 pool members sit at level '1' (on the active MLB roster but OFF the 40-man)
    # — so MLB-level players ARE eligible when off the 40-man; only the level-0
    # historical/retired/FA pool is excluded. Final rule reproduces the OOTP pool
    # at 1,919/1,919 recall with 3 boundary false positives.
    #
    # Eligible & exposed =
    #   pro_service_years >= years_protected_from_rule_5 - 1   (window all but elapsed)
    #   AND not on the 40-man (is_on_secondary != 1)           (40-man players are safe)
    #   AND not the level-0 historical/retired/FA pool
    #
    # NB: do NOT gate on is_active — in the /players feed is_active = 1 means
    # "on the active MLB roster", so every minor-leaguer (most of the Rule 5 pool)
    # is is_active = 0.
    eligible = (
        "p.pro_service_years IS NOT NULL "
        "AND p.years_protected_from_rule_5 IS NOT NULL "
        "AND p.pro_service_years >= p.years_protected_from_rule_5 - 1 "
        "AND (p.is_on_secondary IS NULL OR p.is_on_secondary != 1) "
        "AND p.level != '0'"
    )

    # 40-man roster state — gates and contextualizes every protect decision.
    forty_count = _forty_man_count(conn, team_id)
    spots_open = max(0, _FORTY_MAN_CAP - forty_count)
    roster_full = spots_open == 0

    # Protect side — your org's eligibles, ranked by FV then surplus.
    # Source FV from player_evaluation (the full table), NOT the prospect_fv view:
    # prospect_fv is age-gated at ≤ 25, but Rule 5 eligibility spans older org
    # depth too (a 27-yo AAA arm is still a real protect/expose decision).
    # The recommendation weighs FV against DRAFTABILITY (readiness tier) and the
    # 40-man crunch — see _rule5_protect_rec.
    protect = []
    for r in conn.execute(f"""
        SELECT p.player_id, p.name, p.age, p.mlb_service_years, p.role,
               pe.fv, pe.fv_str, pe.bucket, pe.risk, pe.surplus, pe.level
        FROM player_evaluation pe
        JOIN players p ON pe.player_id = p.player_id
        WHERE pe.eval_date = ? AND {ORG_ID_SQL} = ? AND {eligible}
        ORDER BY pe.fv DESC, pe.surplus DESC, p.age ASC
    """, (ed, team_id)).fetchall():
        fv = r["fv"] or 0
        readiness = _rule5_readiness(r["level"], r["age"], r["mlb_service_years"], r["bucket"])
        rec, rec_class, readiness, why = _rule5_protect_rec(fv, readiness, roster_full)
        protect.append({
            "pid": r["player_id"], "name": r["name"], "age": r["age"],
            "pos": _rule5_role_label(r["bucket"], r["role"]),
            "fv": fv, "fv_str": r["fv_str"] or str(fv), "risk": r["risk"] or "",
            "level": r["level"] or "",
            "surplus": r["surplus"] or 0,  # raw $ — template money filter
            "readiness": readiness,
            "rec": rec, "rec_class": rec_class, "rec_why": why,
        })

    # Attach a compact season stat line to each eligible — the evidence behind
    # the protect/expose call, qualified by the level it was accrued at (a strong
    # AAA line argues for protecting; the same line in AA is worth less).
    cfg = get_cfg()
    lvl_by_league = {lid: v["level"] for lid, v in _milb_level_map(cfg).items()}
    level_names = {int(k): v for k, v in (cfg.settings.get("level_map") or {}).items()}
    stat_lines = _rule5_stat_lines(conn, [p["pid"] for p in protect],
                                   lvl_by_league, level_names)
    for p in protect:
        sl = stat_lines.get(p["pid"])
        p["stat_line"] = sl["line"] if sl else None
        p["stat_war"] = sl["war"] if sl else None
        p["stat_year"] = sl["year"] if sl else None
        p["stat_level"] = sl["level"] if sl else None

    # Display tiers for the UI — triage the flat protect list into decision bands
    # so the template leads with real decisions and collapses the rest:
    #   protect  : rec Protect        — act now (prominent rows)
    #   consider : rec Consider, FV≥40 — genuine judgement calls (prominent rows)
    #   fringe   : rec Consider, FV≤39 — technically exposed but not real dilemmas
    #              (collapsed behind "show N more fringe")
    #   exposed  : rec starts with Expose — "do nothing"; collapsed to a count
    # (The flat `protect` list is kept too, for callers/tests that want everything.)
    protect_tiers = {
        "protect": [p for p in protect if p["rec"].startswith("Protect")],
        "consider": [p for p in protect if p["rec"] == "Consider" and p["fv"] >= 40],
        "fringe": [p for p in protect if p["rec"] == "Consider" and p["fv"] < 40],
        "exposed": [p for p in protect if p["rec"].startswith("Expose")],
    }

    # Target side — other orgs' eligible, MLB-viable players.
    # Each carries a readiness tier (a Rule 5 pick MUST stick on the active roster
    # all year, so MLB-ready targets are the only truly realistic picks) and a
    # need-fill flag against your org's positional holes (reused from the FA board).
    abbr = get_cfg().team_abbr_map
    need_positions = _team_need_positions(team_id)
    targets = []
    for r in conn.execute(f"""
        SELECT p.player_id, p.name, p.age, p.mlb_service_years, p.role,
               pe.fv, pe.fv_str, pe.bucket, pe.risk, pe.level, {ORG_ID_SQL} AS org_id
        FROM player_evaluation pe
        JOIN players p ON pe.player_id = p.player_id
        WHERE pe.eval_date = ? AND {ORG_ID_SQL} != ? AND {eligible}
          AND pe.fv >= ?
        ORDER BY pe.fv DESC, p.age ASC
    """, (ed, team_id, _RULE5_TARGET_MIN_FV)).fetchall():
        pos = _rule5_role_label(r["bucket"], r["role"])
        readiness = _rule5_readiness(r["level"], r["age"], r["mlb_service_years"], r["bucket"])
        targets.append({
            "pid": r["player_id"], "name": r["name"], "age": r["age"],
            "pos": pos,
            "fv": r["fv"] or 0, "fv_str": r["fv_str"] or str(r["fv"] or 0),
            "risk": r["risk"] or "", "level": r["level"] or "",
            "team": abbr.get(r["org_id"], "?"),
            "readiness": readiness,
            "fills_need": _need_key(_display_pos(r["bucket"]) if r["bucket"] else "?") in need_positions,
        })

    # Level-qualified season stat line for each target too — backs the "can he
    # stick?" read with his actual production and where he earned it. Reuses the
    # same helper + maps built for the protect side above.
    tgt_stats = _rule5_stat_lines(conn, [t["pid"] for t in targets],
                                  lvl_by_league, level_names)
    for t in targets:
        sl = tgt_stats.get(t["pid"])
        t["stat_line"] = sl["line"] if sl else None
        t["stat_war"] = sl["war"] if sl else None
        t["stat_level"] = sl["level"] if sl else None
        # Results-first ranking signal (level-adjusted recent performance) + the
        # composite target score that blends it with FV/age upside.
        t["perf"] = _rule5_perf_score(sl)
        t["score"] = _rule5_target_score(t["fv"], t["age"], t["perf"])

    # Rank the whole pool by the composite score (results-first), not raw FV —
    # so a proven arm outranks a shiny-FV mirage with a poor line.
    targets.sort(key=lambda t: -t["score"])

    return {
        "protect": protect,
        "protect_tiers": protect_tiers,
        "targets": targets,
        # Curated shortlist for the "top realistic targets" strip: MLB-ready AND
        # backed by UPPER-level reps (AAA/AA/MLB) — the only realistic straight-to-
        # majors sticks. Ranked by the composite results-first score. Lower-level
        # players stay in the full pool below, just not the headline. Need-fill is
        # a ★ flag only, not a ranking input (user decision).
        "top_targets": sorted(
            [t for t in targets
             if t["readiness"] == "MLB-ready"
             and (t.get("stat_level") in _RULE5_STRIP_LEVELS)],
            key=lambda t: -t["score"],
        )[:6],
        "available": True,
        # 40-man roster state — the headline constraint on both sides.
        "forty_man": {
            "count": forty_count,
            "cap": _FORTY_MAN_CAP,
            "open": spots_open,
            "full": roster_full,
            # "Low-hanging fruit" to clear a spot — fringe minor-league 40-man
            # depth only (never active-roster contributors). May be empty when
            # the 40-man is all on the active MLB roster (e.g. deep offseason).
            "cut_candidates": _rule5_cut_candidates(conn, team_id, ed,
                                                     lvl_by_league, level_names),
        },
        # Projected Rule 5 pick slot (reverse regular-season standings over the
        # MLB clubs). Approximate — ties/edge rules aren't modeled. None if the
        # standings aren't available.
        "draft_pos": _rule5_draft_position(conn, team_id),
        # Your positional holes — doubles as the draft-board quick-filter strip.
        "needs": sorted(need_positions),
    }


# ===========================================================================
# Spring Training — Opening Day projection
#
# Builds a configured 26-man and projects its season output as the
# record -> run-diff -> facet cascade, via the pure team_projection engine.
# See .kiro/specs/spring-training-page/design.md.
#
# The web layer here does the DB pull + roster/playing-time assembly (it may
# use scripts/projections.py, the established pattern); the pure projection math
# lives in statsplusplus.evaluation.team_projection.
# ===========================================================================

# Per-league team-projection calibration is derived from team-season history
# (calibrate.derive_projection_calibration). Cache it per request so repeated
# edits in one page load don't re-regress every time.
_SPRING_CALIB_CACHE: dict = {}


def _spring_calibration(conn, pyth_exp):
    key = id(conn)
    if key not in _SPRING_CALIB_CACHE:
        from statsplusplus.data.calibrate import derive_projection_calibration
        _SPRING_CALIB_CACHE[key] = derive_projection_calibration(conn, pyth_exp)
    return _SPRING_CALIB_CACHE[key]


# Fallback full-season staff IP split (generic MLB shape) when a league has no
# usable team pitching history to calibrate from. ~1444 team IP, ~57/43 SP/RP.
_SPRING_SP_TOTAL_IP_DEFAULT = 830.0
_SPRING_RP_TOTAL_IP_DEFAULT = 615.0


def _spring_staff_ip(conn):
    """Per-league SP and RP total-IP targets the OPENING-DAY staff covers, from
    the league's own MLB pitching history. Returns ``(sp_total_ip,
    rp_total_ip)`` — the innings the 5-man rotation and the 8-man bullpen each
    cover over a season.

    Measured as the TOP-N arms per team, NOT the whole staff: a team uses ~12
    relievers across a season (callups, DL churn), but the Opening-Day 8-man pen
    realistically covers only the top-8 share (~87% of RP innings in vMLB, ~536
    of ~614 IP). Attributing the full team RP total to just 8 rostered arms
    overstates each one's workload (a closer at 110+ IP). So we average the top-5
    starter and top-8 reliever IP across MLB teams — what a real Opening-Day
    staff actually throws (the remaining ~13% comes from the taxi squad, off the
    26). Falls back to the generic split for thin-history leagues. Cached.
    """
    key = (id(conn), "staff_ip")
    if key in _SPRING_CALIB_CACHE:
        return _SPRING_CALIB_CACHE[key]
    sp_total = rp_total = None
    try:
        yr = conn.execute(
            "SELECT MAX(year) y FROM pitching_stats WHERE league_id IS NULL"
        ).fetchone()["y"]
        if yr is not None:
            rows = conn.execute("""
                SELECT team_id, SUM(outs)/3.0 ip, MAX(gs) gs
                FROM pitching_stats
                WHERE year=? AND league_id IS NULL AND split_id=1
                GROUP BY team_id, player_id
            """, (yr,)).fetchall()
            from collections import defaultdict
            team_sp: dict = defaultdict(list)
            team_rp: dict = defaultdict(list)
            for r in rows:
                if not r["ip"]:
                    continue
                gs = r["gs"] or 0
                (team_sp if gs >= 10 else team_rp)[r["team_id"]].append(r["ip"])
            sp_vals, rp_vals = [], []
            for tid in set(team_sp) | set(team_rp):
                sps = sorted(team_sp.get(tid, []), reverse=True)
                rps = sorted(team_rp.get(tid, []), reverse=True)
                # MLB staffs only (a full season of innings).
                if sum(sps) + sum(rps) < 1000:
                    continue
                sp_vals.append(sum(sps[:_SPRING_SP_SLOTS]))
                rp_vals.append(sum(rps[:_SPRING_RP_SLOTS]))
            if len(sp_vals) >= 4 and len(rp_vals) >= 4:
                sp_total = sum(sp_vals) / len(sp_vals)
                rp_total = sum(rp_vals) / len(rp_vals)
    except Exception:
        sp_total = rp_total = None
    out = (sp_total if sp_total else _SPRING_SP_TOTAL_IP_DEFAULT,
           rp_total if rp_total else _SPRING_RP_TOTAL_IP_DEFAULT)
    _SPRING_CALIB_CACHE[key] = out
    return out


# Slot -> run-space defensive bucket (fielding_runs / def_curve keys). Field
# corners share the outfield "COF" curve; CF/IF/C key 1:1; 1B & DH carry no
# fielding runs (handled inside fielding_runs). Mirrors _SPRING_SLOT_ADJ_KEY
# but uses the run-space bucket names.
_SPRING_SLOT_DEF_BUCKET = {
    "C": "C", "1B": "1B", "2B": "2B", "3B": "3B", "SS": "SS",
    "LF": "COF", "RF": "COF", "CF": "CF", "DH": "DH",
}
# Full-season PA baseline the per-facet runs are expressed at (facet_runs.bat_runs
# defaults to 600; keep the two in sync).
_SPRING_FACET_PA = 600.0


def _spring_run_space(league_dir):
    """Load the per-league run-space facet calibration from tool_weights.json.

    Returns the `run_space` dict ({woba_scale, lg_woba, br_curve, def_curve,
    anchor, ...}) or None when the league hasn't been re-run on the run-space
    model (older calibration) — callers then fall back to the scalar war_proj.
    Cached per league_dir.
    """
    key = ("run_space", str(league_dir))
    if key in _SPRING_CALIB_CACHE:
        return _SPRING_CALIB_CACHE[key]
    import json as _json
    out = None
    try:
        tw = _json.loads((league_dir / "config" / "tool_weights.json").read_text())
        rs = tw.get("run_space") or {}
        # Require the pieces the facet math needs; else treat as unavailable.
        if rs.get("woba_scale") and rs.get("anchor"):
            out = rs
    except Exception:
        out = None
    _SPRING_CALIB_CACHE[key] = out
    return out


def _spring_bat_runs_for(_raw, hand, rs, lg_woba, weights):
    """Projected bat runs (wRAA) at 600 PA for a hitter facing ``hand`` ('R',
    'L', or None=overall), from the run-space tool->wOBA fit on that hand's
    split tools. Falls back to the overall proj_woba (then an OPS+-derived
    estimate is handled upstream) when a split is missing."""
    from statsplusplus.evaluation.composite import project_woba_hitter
    from statsplusplus.evaluation.facet_runs import bat_runs
    scale = rs.get("woba_scale")
    lgw = rs.get("lg_woba", lg_woba)
    if hand in ("R", "L"):
        sfx = "_" + hand.lower()
        tools = {
            "contact": _raw.get("cntct" + sfx), "gap": _raw.get("gap" + sfx),
            "power": _raw.get("pow" + sfx), "eye": _raw.get("eye" + sfx),
        }
    else:
        tools = {"contact": _raw.get("cntct"), "gap": _raw.get("gap"),
                 "power": _raw.get("pow"), "eye": _raw.get("eye")}
    woba = project_woba_hitter(tools, rs)
    if woba is None:
        # Overall path can still use the stored proj_woba if present.
        woba = _raw.get("proj_woba") if hand not in ("R", "L") else None
    if woba is None:
        return None
    return bat_runs(woba, lgw, scale, _SPRING_FACET_PA)


def _spring_facets(player, rs, lg_woba, weights):
    """Current-age per-facet RUNS at a full 600-PA season for a hitter.

    Returns a dict::

        {"bat": <overall wRAA>, "bat_R": <vs-RHP wRAA>, "bat_L": <vs-LHP wRAA>,
         "br": <baserunning runs>,
         "fld": {slot: <fielding runs AT slot>, ...},
         "pos": {slot: <positional-adj runs AT slot>, ...},
         "age_mult": <current-age aging multiplier applied to bat/br>}

    All runs are CURRENT-AGE (peak runs × the facet aging multiplier) and
    readiness-discounted to match war_proj's playing-level scaling, so facet WAR
    and the legacy scalar war_proj land on the same scale. Returns None when the
    run-space calibration is unavailable (caller falls back to the scalar path).
    """
    if not rs:
        return None
    from statsplusplus.evaluation.facet_runs import (
        baserunning_runs, fielding_runs, positional_adj_runs, facet_aging_mult,
    )
    _raw = player.get("_raw") or {}
    anchor = rs.get("anchor") or {}
    rpw = anchor.get("runs_per_win", 9.5)
    br_curve = rs.get("br_curve")
    def_curve = rs.get("def_curve")
    pos_models = weights.get("POSITIONAL_MODELS") if isinstance(weights, dict) else None

    # Peak (full-talent) facet runs.
    bat = _spring_bat_runs_for(_raw, None, rs, lg_woba, weights)
    if bat is None:
        # No usable wOBA projection — bat facet can't be built; bail to scalar.
        return None
    bat_r = _spring_bat_runs_for(_raw, "R", rs, lg_woba, weights)
    bat_l = _spring_bat_runs_for(_raw, "L", rs, lg_woba, weights)
    if bat_r is None:
        bat_r = bat
    if bat_l is None:
        bat_l = bat
    br = baserunning_runs({"speed": _raw.get("speed"), "steal": _raw.get("steal")}, br_curve)

    # Fielding runs AT each eligible slot (positional difficulty already encoded
    # in the per-position def_curve), plus the positional adjustment per slot.
    fld, pos = {}, {}
    for slot in player.get("eligible", []):
        dbucket = _SPRING_SLOT_DEF_BUCKET.get(slot, slot)
        fld[slot] = fielding_runs(_raw, dbucket, def_curve, pos_models)
        pos[slot] = positional_adj_runs(dbucket, rpw)

    # Current-age aging: age each facet by its own curve, run-weighted (same as
    # the evaluation engine's facet_aging_mult). Fielding is aged WITH defense;
    # use the player's best fielding slot as its weight proxy.
    best_fld = max(fld.values()) if fld else 0.0
    age = player.get("age") or 27
    age_mult = facet_aging_mult(age, bat, br, best_fld)
    readiness = _SPRING_READINESS.get(player.get("level"), 0.5)
    scale = age_mult * readiness
    return {
        "bat": bat * scale, "bat_R": bat_r * scale, "bat_L": bat_l * scale,
        "br": br * scale,
        "fld": {s: v * scale for s, v in fld.items()},
        "pos": pos,   # positional adj is age-invariant (not aged/readiness-scaled)
        "rpw": rpw, "anchor": anchor,
    }


_SPRING_LEVEL_NAME = {"1": "MLB", "2": "AAA", "3": "AA"}
# Readiness discount on a non-MLB player's current-season contribution (not yet
# MLB-proven). Distinct from projections.LEVEL_DISCOUNT (which discounts
# *playing-time likelihood*); this discounts the WAR *rate* for the Spring
# what-if, where the user has explicitly chosen to roster the player.
_SPRING_READINESS = {"MLB": 1.0, "AAA": 0.80, "AA": 0.65}


def _spring_pool(conn, team_id, ed):
    """Candidate pool: full 40-man + AA/AAA players with a WAR projection.

    Returns per-player dicts carrying the fields the allocator + engine need:
    current-age WAR (`war_proj`), level discount, split OPS+, positional ratings.
    Org membership via ORG_ID_SQL (contract_team_id is stale after trades).
    """
    from statsplusplus.evaluation.war import aging_mult
    from statsplusplus.evaluation.constants import load_model_weights
    import sys as _sys
    league_dir = get_cfg().league_dir
    _sys.path.insert(0, str(league_dir.parent.parent / "scripts"))
    from projections import (
        project_ops_plus, project_ops_plus_splits, project_era, project_fip,
        LEVEL_DISCOUNT, POS_THRESHOLDS,
    )

    weights = load_model_weights(league_dir)
    # Run-space facet calibration (woba_scale, lg_woba, br/def curves, WAR
    # anchor) — the SAME per-league calibration the evaluation engine uses. The
    # spring roster is valued facet-by-facet in RUNS from this, not off the
    # pre-bundled scalar war_proj. Missing (league not re-run on this model
    # version) → _spring_facets falls back to the scalar path gracefully.
    _rs = _spring_run_space(league_dir)
    # Per-league full-season SP/RP total IP — used for role-based pitcher WAR on
    # the pool rows (sp_war / rp_war): value an arm at the workload of the role
    # he'd fill, so the swap menu ranks relievers by relief value.
    _sp_total_ip, _rp_total_ip = _spring_staff_ip(conn)
    # League ERA/FIP anchors for the pitcher stat projections (display only).
    import json as _json
    _lg_era, _lg_fip = 4.5, 4.5
    try:
        _la = _json.loads((league_dir / "config" / "league_averages.json").read_text())
        _lg_era = _la.get("pitching", {}).get("era", 4.5)
        _lg_fip = _la.get("pitching", {}).get("fip", 4.5)
        _lg_woba = _la.get("batting", {}).get("woba", 0.320)
    except Exception:
        _lg_woba = 0.320

    rows = conn.execute(f"""
        SELECT pe.player_id, pe.name, pe.age, pe.bucket, pe.level, pe.peak_war,
               pe.composite, pe.fv, p.role, p.is_on_secondary,
               r.cntct, r.gap, r.pow, r.eye, r.speed, r.steal,
               r.cntct_l, r.cntct_r, r.gap_l, r.gap_r,
               r.pow_l, r.pow_r, r.eye_l, r.eye_r,
               r.c, r.ss, r.second_b, r.third_b, r.first_b, r.lf, r.cf, r.rf,
               r.ifr, r.ife, r.ifa, r.tdp, r.ofr, r.ofe, r.ofa,
               r.c_frm, r.c_blk, r.c_arm,
               r.defensive_value, r.baserunning_value, r.proj_woba
        FROM player_evaluation pe
        JOIN players p ON pe.player_id = p.player_id
        LEFT JOIN latest_ratings r ON pe.player_id = r.player_id
        WHERE pe.eval_date = ?
          AND {ORG_ID_SQL} = ?
          AND pe.peak_war IS NOT NULL
          AND (p.level = '1' OR (p.level IN ('2','3') AND p.is_on_secondary = 1)
               OR (p.level IN ('2','3') AND pe.peak_war >= 1.5))
    """, (ed, team_id)).fetchall()

    pool = []
    for r in rows:
        age = r["age"] or 27
        bucket = r["bucket"] or "COF"
        lvl = _SPRING_LEVEL_NAME.get(r["level"], r["level"])
        cur_war = (r["peak_war"] or 0) * aging_mult(age, bucket, weights)
        cur_war *= _SPRING_READINESS.get(lvl, 0.5)
        is_pitcher = bucket in ("SP", "RP")
        d = {
            "player_id": r["player_id"], "name": r["name"], "age": age,
            "bucket": bucket, "level": lvl, "role": r["role"],
            "on_40": bool(r["is_on_secondary"]), "is_pitcher": is_pitcher,
            "fv": r["fv"], "composite": r["composite"],
            "war_proj": round(cur_war, 2),
            "level_discount": LEVEL_DISCOUNT.get(lvl, 0.1),
            "speed": r["speed"] or 50,
        }
        if not is_pitcher:
            # Guard against players with no offensive ratings (LEFT JOIN NULLs /
            # incomplete rows) — fall back to neutral OPS+ (100) so the allocator
            # and splits don't crash on a None.
            if r["cntct"] is None or r["gap"] is None or r["pow"] is None or r["eye"] is None:
                d["ovr_ops_plus"] = 100
                d["split_ops_plus"] = 100
                d["ops_vs_l"] = 100
                d["ops_vs_r"] = 100
            else:
                d["ovr_ops_plus"] = project_ops_plus(r["cntct"], r["gap"], r["pow"], r["eye"])
                sp_ops, vl, vr = project_ops_plus_splits(dict(r))
                d["split_ops_plus"] = sp_ops
                d["ops_vs_l"] = vl
                d["ops_vs_r"] = vr
            for k in ("c", "ss", "second_b", "third_b", "first_b", "lf", "cf", "rf"):
                d[k] = r[k]
            # Eligible field positions (where the player is viable per the
            # positional rating thresholds) + DH (any hitter can DH). Drives
            # swap legality and the "utility" flexibility surfaced in the UI.
            elig = []
            for slot, (fld, thresh) in POS_THRESHOLDS.items():
                val = d.get(fld)
                if val is not None and val >= thresh:
                    elig.append(slot)
            # Fall back to the native bucket slot if ratings didn't qualify him
            # anywhere (incomplete ratings) so he's at least playable at home.
            if not elig:
                nat = _SPRING_BUCKET_POS.get(bucket)
                if nat:
                    elig.append(nat)
            elig.append("DH")
            d["eligible"] = sorted(set(elig))
            # Slot-adjusted WAR at EACH eligible position (what he's worth THERE,
            # positional adjustment swapped from his native bucket). The candidate
            # pool shows this so "what you see is what you get" on a swap — fixes
            # the native-vs-slot mismatch (e.g. a SS shown as 2.7 but worth 0.8
            # at 1B). _spring_slot_war is defined below; compute lazily per pos.
            # (slot_war filled after facets are computed below.)
            # Per-facet CURRENT-AGE runs at a full 600-PA season, computed in
            # run space from the model's own facets (proj_woba + splits, speed/
            # steal, raw defensive tools). These are the honest building blocks
            # the spring allocator values playing time with — bat (overall + vs
            # each hand), baserunning, and fielding AT each eligible slot — so a
            # platoon bat's offensive edge is never scaled by a defensive/
            # positional penalty (the old war_proj × hand_factor bug).
            d["_raw"] = {
                "cntct": r["cntct"], "gap": r["gap"], "pow": r["pow"], "eye": r["eye"],
                "cntct_l": r["cntct_l"], "gap_l": r["gap_l"], "pow_l": r["pow_l"], "eye_l": r["eye_l"],
                "cntct_r": r["cntct_r"], "gap_r": r["gap_r"], "pow_r": r["pow_r"], "eye_r": r["eye_r"],
                "speed": r["speed"], "steal": r["steal"],
                "ifr": r["ifr"], "ife": r["ife"], "ifa": r["ifa"], "tdp": r["tdp"],
                "ofr": r["ofr"], "ofe": r["ofe"], "ofa": r["ofa"],
                "c_frm": r["c_frm"], "c_blk": r["c_blk"], "c_arm": r["c_arm"],
                "proj_woba": r["proj_woba"],
            }
            d["facets"] = _spring_facets(d, _rs, _lg_woba, weights)
            # Slot-adjusted RATE WAR at each eligible slot — now facet-based
            # (falls back to the scalar swap when facets are unavailable) so the
            # candidate board, swap preview, and recommender all rank by the
            # same honest slot value.
            d["slot_war"] = {s: round(_spring_slot_rate_war(d, s), 1) for s in d["eligible"]}
            # Display stat selector values. OPS+ (legacy), plus the run-space
            # model's native facets: projected wOBA (the model's offensive
            # currency) and the model's defensive/baserunning run grades
            # (defensive_value / baserunning_value from latest_ratings — actual
            # eval outputs). wOBA prefers the EXACT stored model projection
            # (ratings.proj_woba, written by the evaluation engine from the
            # tool->wOBA fit); falls back to the OPS+ × league-wOBA display
            # estimate for leagues not yet re-run on this model version.
            opsp = d.get("ovr_ops_plus") or 100
            _pw = r["proj_woba"]
            woba = round(_pw, 3) if _pw is not None else round(_lg_woba * (opsp / 100.0), 3)
            d["stats"] = {
                "war": d["war_proj"],
                "ops_plus": opsp,
                "ops_vs_l": d.get("ops_vs_l"),
                "ops_vs_r": d.get("ops_vs_r"),
                "woba": woba,
                "def": r["defensive_value"],
                "bsr": r["baserunning_value"],
            }
            # Platoon profile (strong/weak hand + split) so the board can flag a
            # real platoon bat and the suggest-platoon action can use it.
            d["platoon"] = _spring_platoon_profile(d)
        else:
            # Pitchers: an SP can also work in relief; an RP is RP-only.
            d["eligible"] = ["SP", "RP"] if bucket == "SP" else ["RP"]
            # Role-based WAR (issue: swap menu should rank by the role a pitcher
            # would FILL, not his native-role full-season value). `war_proj` is
            # the native-role full-season projection; convert to a per-IP rate
            # over the native full-season workload and re-scale to the target
            # role's full-season IP, so an SP shown as a bullpen candidate is
            # valued on a reliever's innings (~65), not a starter's (~190).
            native_full_ip = (_sp_total_ip / 5.0) if bucket == "SP" else (_rp_total_ip / _SPRING_RP_SLOTS)
            native_full_ip = max(1.0, native_full_ip)
            _war_per_ip = (d["war_proj"] or 0.0) / native_full_ip
            d["sp_war"] = round(_war_per_ip * (_sp_total_ip / 5.0), 1)
            d["rp_war"] = round(_war_per_ip * (_rp_total_ip / _SPRING_RP_SLOTS), 1)
            # Projected ERA/FIP from the composite score (depth-chart parity).
            comp = r["composite"] or 50
            d["stats"] = {
                "war": d["war_proj"],
                "era": round(project_era(comp, comp, age, bucket, 0, _lg_era), 2),
                "fip": round(project_fip(comp, comp, age, bucket, 0, _lg_fip), 2),
            }
        pool.append(d)
    return pool


_SPRING_FIELD = ["C", "1B", "2B", "3B", "SS", "LF", "CF", "RF"]
_SPRING_BUCKET_POS = {"C": "C", "1B": "1B", "2B": "2B", "3B": "3B", "SS": "SS",
                      "LF": "LF", "CF": "CF", "RF": "RF", "COF": "LF", "IF": "2B"}


# Field positions ordered scarcest-first — fill the hard-to-cover spots before
# the easy ones so a premium-position player isn't wasted at a corner.
_SPRING_FILL_ORDER = ["C", "SS", "CF", "2B", "3B", "RF", "LF", "1B"]
# Default Opening Day structure (not rigid — bench/pen sizes derive from it).
_SPRING_BENCH_SLOTS = 4
_SPRING_SP_SLOTS = 5
_SPRING_RP_SLOTS = 8
# Replacement floor for auto-rostering a reliever. An arm projected at or below
# this adds nothing over a replacement-level call-up, so the recommender leaves
# the bullpen spot open rather than carrying a negative-WAR arm.
_SPRING_RP_MIN_WAR = 0.0
# A flagged out-of-options player must be at least this good (current-age WAR)
# for the recommender to carry him over a better alternative. Below this he's a
# genuine cut and gets surfaced as must-expose.
_SPRING_OOO_MIN_WAR = 0.3


def _spring_slot_val(p, slot):
    """Slot-adjusted RATE WAR for ranking in the recommender. Prefers the
    precomputed facet-based ``slot_war`` dict (from _spring_pool); falls back to
    the scalar positional-swap for dicts built outside the pool."""
    sw = p.get("slot_war")
    if sw and slot in sw:
        return sw[slot]
    return _spring_slot_war(p, slot)


def _spring_viable_at(p, pos):
    """Is hitter ``p`` viable at field position ``pos``?

    Prefers the precomputed ``eligible`` set (from _spring_pool); falls back to
    the positional rating thresholds / bucket map for player dicts that haven't
    been through the pool build."""
    if "eligible" in p:
        return pos in p["eligible"]
    import sys as _sys
    _sys.path.insert(0, str(get_cfg().league_dir.parent.parent / "scripts"))
    from projections import POS_THRESHOLDS
    fld, thresh = POS_THRESHOLDS.get(pos, (None, None))
    if fld and p.get(fld) is not None:
        return (p.get(fld) or 0) >= thresh
    return _SPRING_BUCKET_POS.get(p["bucket"]) == pos


def _spring_auto_config(pool, out_of_options=None):
    """Recommend an Opening Day 26-man.

    Phase 1 (coverage): fill the 8 field positions scarcest-first with the best
      VIABLE player at each (guarantees every position is actually covered, not
      left empty by a greedy best-WAR grab), then best remaining bat -> DH.
    Phase 2 (pitching): top 5 SP; bullpen anchored best-RP-first to 8.
    Phase 3 (bench): remaining position players by WAR + coverage bonus (backup
      C / multi-position flexibility) + platoon bonus (strong-side upgrade).
    Out-of-options: a flagged, credible player is kept; flagged players that
      can't be fit are returned as must-expose.

    Returns the config dict plus `_must_expose` (list of flagged pids cut).
    """
    ooo = set(out_of_options or ())
    hitters = sorted([p for p in pool if not p["is_pitcher"]], key=lambda x: -x["war_proj"])
    sps = sorted([p for p in pool if p["bucket"] == "SP"], key=lambda x: -x["war_proj"])
    rps = sorted([p for p in pool if p["bucket"] == "RP"], key=lambda x: -x["war_proj"])
    by_id = {p["player_id"]: p for p in pool}
    used, lineup = set(), {}

    # Phase 1 — coverage: best viable player per position, scarcest-first.
    # Rank candidates by SLOT-ADJUSTED WAR (not native war_proj): a 2B stretched
    # to 1B is worth far less THERE, so a true 1B should win the 1B slot even if
    # his native WAR is lower. (Same bug class as the DH fix.)
    for pos in _SPRING_FILL_ORDER:
        cands = [p for p in hitters if p["player_id"] not in used
                 and _spring_viable_at(p, pos)]
        if not cands:  # no viable body — take best remaining bat (stretched)
            cands = [p for p in hitters if p["player_id"] not in used]
        if cands:
            best = max(cands, key=lambda p: _spring_slot_val(p, pos))
            lineup[pos] = best["player_id"]
            used.add(best["player_id"])
    # DH — the best remaining BAT, ranked by DH-slot WAR (which strips the
    # defensive/positional value), so a bat-first player beats a glove-first one
    # whose native WAR was inflated by a premium-position adjustment.
    dh = sorted([p for p in hitters if p["player_id"] not in used],
                key=lambda p: -_spring_slot_val(p, "DH"))
    if dh:
        lineup["DH"] = dh[0]["player_id"]
        used.add(dh[0]["player_id"])

    # Phase 2 — pitchers. The rotation is a HARD 5 (you must field five starters
    # even if the fifth is weak — a 4-man rotation isn't an option). The bullpen
    # FLEXES: only carry arms projected above replacement — a below-replacement
    # reliever (negative WAR) is strictly worse than leaving the spot for a
    # replacement-level call-up (~0 WAR), so don't auto-roster him. The GM can
    # still add one manually if he has a reason to.
    rotation = [p["player_id"] for p in sps[:_SPRING_SP_SLOTS]]
    # Bullpen: prefer above-replacement arms, but always fill a full 8-man pen so
    # the roster totals 26 (the GM can drop the 8th for a 5th bench bat — the
    # 26th spot is an explicit field-vs-pen choice, surfaced via the "+ add arm"
    # / "+ add reserve" controls). Rank relievers by their RP-role value
    # (`rp_war`) rather than native `war_proj`, so a starter-ish arm isn't over-
    # rated by a starter's full-season projection.
    def _rp_val(p):
        return p.get("rp_war", p["war_proj"]) if p["bucket"] == "RP" else p.get("rp_war", p["war_proj"])
    rps_ranked = sorted(rps, key=_rp_val, reverse=True)
    bullpen = [p["player_id"] for p in rps_ranked[:_SPRING_RP_SLOTS]]
    used.update(rotation)
    used.update(bullpen)

    # Phase 3 — bench by marginal value (WAR + coverage + platoon bonus).
    starters = [by_id[pid] for pid in lineup.values()]
    starter_pos = {pos: by_id[pid] for pos, pid in lineup.items()}
    have_backup_c = False

    def _bench_score(p):
        s = p["war_proj"]
        # Coverage bonus: a backup catcher is scarce and valuable.
        if _spring_viable_at(p, "C") and not have_backup_c:
            s += 0.6
        # Multi-position flexibility: viable at 2+ non-trivial spots.
        nviable = sum(1 for pos in _SPRING_FIELD if _spring_viable_at(p, pos))
        if nviable >= 2:
            s += 0.2 * min(nviable - 1, 3)
        # Platoon bonus: strong-side bat that beats a starter by 5+ OPS+ on a hand.
        best_platoon = 0.0
        for pos, st in starter_pos.items():
            if pos == "DH":
                continue
            svl, svr = st.get("ops_vs_l", 0) or 0, st.get("ops_vs_r", 0) or 0
            pvl, pvr = p.get("ops_vs_l", 0) or 0, p.get("ops_vs_r", 0) or 0
            if svl and pvl > svl + 5:
                best_platoon = max(best_platoon, 0.3 * min((pvl - svl) / 30, 1.0))
            if svr and pvr > svr + 5:
                best_platoon = max(best_platoon, 0.2 * min((pvr - svr) / 30, 1.0))
        return s + best_platoon

    remaining = [p for p in hitters if p["player_id"] not in used]
    bench = []
    # HARD guarantee: a backup catcher. A C starts only ~67% of games, so every
    # team must carry a second catcher — reserve a bench slot for the best one.
    bc = [p for p in remaining if _spring_viable_at(p, "C")]
    if bc:
        best_c = max(bc, key=lambda p: p["war_proj"])
        bench.append(best_c["player_id"])
        used.add(best_c["player_id"])
        have_backup_c = True
    for p in sorted(remaining, key=_bench_score, reverse=True):
        if len(bench) >= _SPRING_BENCH_SLOTS:
            break
        if p["player_id"] in used:
            continue
        bench.append(p["player_id"])
        used.add(p["player_id"])
        if _spring_viable_at(p, "C"):
            have_backup_c = True

    # Out-of-options: pull in any flagged, credible player not already rostered,
    # bumping the weakest same-group bench/pen member. Surface the rest.
    must_expose = []
    for pid in ooo:
        p = by_id.get(pid)
        if p is None or pid in used:
            continue
        if p["war_proj"] < _SPRING_OOO_MIN_WAR:
            must_expose.append(pid)
            continue
        if p["is_pitcher"] and p["bucket"] == "SP" and len(rotation) >= _SPRING_SP_SLOTS:
            # Credible flagged SP — swap for the weakest rostered SP if better.
            weak = min(rotation, key=lambda x: by_id[x]["war_proj"])
            if p["war_proj"] > by_id[weak]["war_proj"]:
                rotation[rotation.index(weak)] = pid
            else:
                must_expose.append(pid)
        elif p["is_pitcher"]:
            if len(bullpen) < _SPRING_RP_SLOTS:
                bullpen.append(pid)            # open pen slot (we trim sub-repl arms)
            else:
                weak = min(bullpen, key=lambda x: by_id[x]["war_proj"]) if bullpen else None
                if weak and p["war_proj"] > by_id[weak]["war_proj"]:
                    bullpen[bullpen.index(weak)] = pid
                else:
                    must_expose.append(pid)
        else:
            weak = min(bench, key=lambda x: by_id[x]["war_proj"]) if bench else None
            if weak and p["war_proj"] > by_id[weak]["war_proj"]:
                bench[bench.index(weak)] = pid
            else:
                must_expose.append(pid)

    return {"lineup": lineup, "bench": bench, "rotation": rotation,
            "bullpen": bullpen, "_must_expose": must_expose}


# Map a lineup SLOT to its positional-adjustment key. Field corners (LF/RF)
# share the "COF" adjustment; DH is its own (worst) adjustment. Everything else
# keys 1:1. This lets us re-value a player for the slot he's ACTUALLY playing.
_SPRING_SLOT_ADJ_KEY = {
    "C": "C", "1B": "1B", "2B": "2B", "3B": "3B", "SS": "SS",
    "LF": "COF", "RF": "COF", "CF": "CF", "DH": "DH",
}


def _spring_slot_war(player, slot):
    """A hitter's WAR AT a given lineup slot.

    `war_proj` bakes in the positional adjustment for the player's NATIVE bucket.
    Playing a slot off his home position (or at DH, which carries no defensive
    value) must swap that adjustment: strip the native one, apply the slot's.
    e.g. a SS (+0.7) at DH (-1.7) loses 2.4 WAR of positional value.
    """
    from statsplusplus.utils.positions import POSITIONAL_WAR_ADJUSTMENTS as _PA
    native_key = _SPRING_SLOT_ADJ_KEY.get(player.get("bucket"), player.get("bucket"))
    slot_key = _SPRING_SLOT_ADJ_KEY.get(slot, slot)
    native_adj = _PA.get(native_key, 0.0)
    slot_adj = _PA.get(slot_key, 0.0)
    return player["war_proj"] - native_adj + slot_adj


def _spring_slot_rate_war(player, slot):
    """Full-season (600-PA) RATE WAR for a hitter AT ``slot``, built from the
    run-space facets (bat at the 71/29 hand mix + baserunning + fielding at the
    slot + positional adj → WAR via the league anchor). This is the facet-model
    analog of _spring_slot_war and is what the UI shows as a player's "value if
    he plays this spot every day". Falls back to _spring_slot_war when facets
    are unavailable."""
    f = player.get("facets")
    if not f:
        return _spring_slot_war(player, slot)
    bat = f["bat_R"] * _SPRING_VS_RHP_FREQ + f["bat_L"] * _SPRING_VS_LHP_FREQ
    runs = bat + f["br"] + f["fld"].get(slot, 0.0) + f["pos"].get(slot, 0.0)
    rpw = f["rpw"] or 9.5
    repl = (f["anchor"] or {}).get("replacement_runs", 20.0)
    return (runs + repl) / rpw if rpw else 0.0


# ── Platoon-assignment + start-share playing-time model ──
# PA is DERIVED from handedness deployment + realistic start-shares, NOT a flat
# tier. See spec §4. Opponent-handedness PA split (data: 71% vs RHP / 29% vs L).
_SPRING_VS_RHP_FREQ = 0.71
_SPRING_VS_LHP_FREQ = 0.29
# Realistic PRIMARY start-share by position (data: vMLB 2034 GS). The starter
# never plays 100%; the remainder flows to the backup. Catcher is lowest (a
# backup C is required — you can't cover 162 games with one catcher).
_SPRING_START_SHARE = {
    "C": 0.67, "1B": 0.79, "2B": 0.73, "3B": 0.73, "SS": 0.71,
    "LF": 0.76, "CF": 0.76, "RF": 0.81, "DH": 0.88,
}
_SPRING_DEFAULT_START_SHARE = 0.75
# PA budget per lineup slot over a season (data: team PA / 9 ≈ 658), split into
# handedness wedges by the 71/29 frequency. This is the "pie" each position
# must fill (vs-RHP wedge + vs-LHP wedge).
_SPRING_SLOT_PA = 658
_SPRING_PA_VS_RHP = round(_SPRING_SLOT_PA * _SPRING_VS_RHP_FREQ)   # ~467
_SPRING_PA_VS_LHP = round(_SPRING_SLOT_PA * _SPRING_VS_LHP_FREQ)   # ~191
# Realistic per-PLAYER PA ceiling across ALL positions in a season. A position's
# pie is balanced independently, so a multi-position utility man could be
# allocated (e.g.) 250 PA at 2B + 250 at SS + 250 at 3B = 750 — physically
# impossible for one body. When a player's total allocated PA exceeds this, his
# per-position contributions are scaled DOWN proportionally (he plays everywhere,
# just less) and an over-allocation warning names him + the positions. ~700 is a
# shade above the single-slot budget (658) — a true everyday+ workload.
_SPRING_PLAYER_PA_CAP = 700

# Pitcher role → IP share of a staff slot (rotation slot for SP, bullpen for RP).
_SPRING_PITCHER_ROLE_SHARE = {
    "sp1": 1.00, "sp2": 0.95, "sp3": 0.90, "sp4": 0.85, "sp5": 0.78,
    "closer": 0.70, "setup": 0.62, "middle": 0.50, "long": 0.42, "specialist": 0.30,
}
# Full-workload IP for a staff slot — the role share scales these to a projected
# innings load (SP: a full-season #1-starter workload; RP: a full bullpen role).
# Used to show each staff arm's projected IP alongside his contribution WAR.
_SPRING_SP_FULL_IP = 190.0
_SPRING_RP_FULL_IP = 65.0


def _spring_hand_factor(player, hand):
    """Multiplier on a hitter's overall value when facing a given hand, from his
    split OPS+ vs his overall OPS+. hand='R' uses vs-RHP, 'L' uses vs-LHP. A
    platoon bat who mashes LHP gets >1 vs L, <1 vs R; falls back to 1.0 when a
    split is missing. Clamped to a sane band."""
    ovr = player.get("ovr_ops_plus") or 100
    split = player.get("ops_vs_l" if hand == "L" else "ops_vs_r")
    if not ovr or not split:
        return 1.0
    return max(0.6, min(1.6, split / ovr))


# ── platoon intelligence ──
# A "real" platoon bat: the projected OPS+ gap between his strong and weak hand
# is at least this many points. ~15 OPS+ is a meaningful, exploitable split
# (roughly a .030 wOBA swing) without flagging ordinary noise.
_SPRING_PLATOON_SPLIT_PTS = 15
# ...and his STRONG side must clear this OPS+ (an exploitable strong side must
# actually be good — a bat that's 80 vs L / 60 vs R is not a platoon weapon).
_SPRING_PLATOON_STRONG_MIN = 105


def _spring_platoon_profile(player):
    """A hitter's platoon profile from his projected split OPS+ (ops_vs_l /
    ops_vs_r — already on every pool hitter). Returns::

        {"split": <abs OPS+ gap>, "strong": "L"|"R", "weak": "L"|"R",
         "strong_ops": <OPS+ vs strong hand>, "real": bool}

    ``real`` is True when the gap is meaningful AND the strong side is genuinely
    above average — i.e. a bat worth deploying ONLY against that hand. Returns
    None for pitchers or missing splits.
    """
    if player.get("is_pitcher"):
        return None
    vl = player.get("ops_vs_l")
    vr = player.get("ops_vs_r")
    if vl is None or vr is None:
        return None
    split = abs(vl - vr)
    strong = "L" if vl >= vr else "R"
    strong_ops = max(vl, vr)
    real = split >= _SPRING_PLATOON_SPLIT_PTS and strong_ops >= _SPRING_PLATOON_STRONG_MIN
    return {"split": round(split), "strong": strong, "weak": ("R" if strong == "L" else "L"),
            "strong_ops": round(strong_ops), "real": real}


def _spring_suggest_platoon(pool, config, pos):
    """Suggest the best platoon PAIR for a position: keep the stronger-overall
    bat as the primary (plays his strong hand + the open share), and pair a
    strong-side partner against the hand the primary is weak at.

    Returns a dict the UI can preview/apply::

        {"pos", "primary": pid, "partner": pid, "partner_hand": "L"|"R",
         "pa_alloc": {pid: {"r":PA,"l":PA}, ...}, "reason": str}

    or None when no worthwhile platoon exists (e.g. the starter has no real
    weak side, or no eligible partner is clearly better on that hand).
    """
    by_id = {p["player_id"]: p for p in pool}
    starter_pid = (config.get("lineup") or {}).get(pos)
    starter = by_id.get(starter_pid)
    if not starter:
        return None
    # DH platoons are valid (a strong-side/weak-side DH share, no defensive
    # cost). But every hitter is "eligible" at DH, so a DH partner must NOT be a
    # player already penciled in as an everyday FIELD starter — pairing him at
    # DH would double-roster him. Restrict DH partners to non-field-starters.
    field_starters = {pid for p_pos, pid in (config.get("lineup") or {}).items()
                      if p_pos != "DH"}
    # The primary's weaker hand — the one we want a partner to cover.
    sprof = _spring_platoon_profile(starter)
    if not sprof:
        return None
    weak_hand = sprof["weak"]   # hand the starter is WORSE against
    weak_key = "ops_vs_l" if weak_hand == "L" else "ops_vs_r"
    starter_weak_ops = starter.get(weak_key) or 100

    # Candidates: eligible-here bats (not the starter) who are meaningfully
    # better than the starter against his weak hand, ranked by that strength.
    cands = []
    for p in pool:
        if p["player_id"] == starter_pid or p.get("is_pitcher"):
            continue
        if not _spring_viable_at(p, pos):
            continue
        # At DH, skip players already starting in the field (no double-roster).
        if pos == "DH" and p["player_id"] in field_starters:
            continue
        cand_ops = p.get(weak_key)
        if cand_ops is None:
            continue
        edge = cand_ops - starter_weak_ops
        if edge >= _SPRING_PLATOON_SPLIT_PTS and cand_ops >= _SPRING_PLATOON_STRONG_MIN:
            cands.append((edge, cand_ops, p))
    if not cands:
        return None
    cands.sort(key=lambda t: (-t[0], -t[1], -t[2]["war_proj"]))
    _, _, partner = cands[0]

    # Build the pie: partner takes the weak-hand wedge; primary takes his strong
    # wedge fully + the leftover of the weak wedge (a strict platoon gives the
    # partner the whole weak wedge, but keep a realistic start-share for the
    # primary so he isn't benched entirely vs that hand).
    r_total, l_total = _SPRING_PA_VS_RHP, _SPRING_PA_VS_LHP
    alloc = {}
    if weak_hand == "L":
        alloc[starter_pid] = {"r": r_total, "l": round(l_total * 0.25)}
        alloc[partner["player_id"]] = {"r": 0, "l": l_total - round(l_total * 0.25)}
    else:
        alloc[starter_pid] = {"r": round(r_total * 0.25), "l": l_total}
        alloc[partner["player_id"]] = {"r": r_total - round(r_total * 0.25), "l": 0}

    return {
        "pos": pos,
        "primary": starter_pid,
        "partner": partner["player_id"],
        "partner_name": partner["name"],
        "partner_hand": weak_hand,
        "pa_alloc": alloc,
        "reason": (f"{partner['name']} projects {cands[0][1]:.0f} OPS+ vs {weak_hand}HP "
                   f"vs {starter['name']}'s {starter_weak_ops:.0f} "
                   f"(+{cands[0][0]:.0f}) — platoon the {weak_hand}HP wedge."),
    }


def _spring_contributions(pool, config, staff_ip=None):
    """Turn a config into playing-time-weighted PlayerContribution list.

    Playing time is modeled as PLATOON ASSIGNMENT × START-SHARE (spec §4), not a
    flat tier:
      - each position deploys a vs-RHP and a vs-LHP player (default: the same
        starter), plus a backup taking the remaining starts;
      - PA/value is the start-share-weighted blend of 71% vs-RHP + 29% vs-LHP,
        each valued with that player's split (vs-R / vs-L) effectiveness so
        platoon value actually shows;
      - WAR is re-valued for the slot actually played (see _spring_slot_war): DH
        strips defensive value, off-position play swaps the positional adj.

    `config` may carry a `platoon` map {pos: {"vsR": pid, "vsL": pid}} and a
    `start_share` map {pid: frac} overriding the position defaults; absent, the
    starter plays both hands at the position's realistic default start-share.
    """
    import sys as _sys
    _sys.path.insert(0, str(get_cfg().league_dir.parent.parent / "scripts"))
    from projections import allocate_playing_time, allocate_pitcher_time
    from statsplusplus.evaluation.team_projection import PlayerContribution

    by_id = {p["player_id"]: p for p in pool}
    platoon = config.get("platoon") or {}        # {pos: {"vsR": pid, "vsL": pid}}
    start_override = config.get("start_share") or {}  # {pid: frac}
    # Literal PA allocation {pos: {pid: {"r": PA, "l": PA}}}. When set for a
    # position, it is the source of truth for that pie (overrides the derived
    # platoon/start-share shares). Keys may be str (JSON) or int.
    pa_alloc = config.get("pa_alloc") or {}
    def _alloc_for(pos):
        a = pa_alloc.get(pos)
        if not a:
            return None
        out = {}
        for k, v in a.items():
            try:
                out[int(k)] = v
            except (TypeError, ValueError):
                pass
        return out or None

    def _ov(pid):
        return start_override.get(pid, start_override.get(str(pid)))

    # Bench bats available as backups, keyed by the position they can cover.
    bench_by_pos: dict = {}
    for pid in config.get("bench", []):
        p = by_id.get(pid)
        if not p:
            continue
        for e in p.get("eligible", []):
            bench_by_pos.setdefault(e, []).append(p)

    contribs = []
    constructed_lineup = {}
    used_backups: set = set()   # a bench bat backs up only ONE position

    def _slot_contrib(pid, pos, pa_r, pa_l):
        """Facet-based contribution for a hitter taking ``pa_r`` PA vs RHP and
        ``pa_l`` vs LHP at ``pos``. Returns (war, bat_share, br_share, fld_share,
        facet_runs_dict) — the REAL per-facet run split, so the engine's facet
        breakdown is honest and the platoon bat value is never scaled by the
        positional/defensive adjustment (the old war_proj × hand_factor bug).

        Runs scale linearly with PA off the 600-PA facet baselines. Bat uses the
        hand-specific wOBA per wedge; baserunning / fielding / positional adj
        scale by total PA (hand-independent). WAR-above-replacement is derived
        from total runs via the league anchor, pro-rated to the PA fraction so a
        partial-season slot isn't credited a full replacement cushion.
        Falls back to the scalar _spring_slot_war path when facets are absent.
        """
        p = by_id[pid]
        f = p.get("facets")
        pa = (pa_r or 0) + (pa_l or 0)
        if not f or pa <= 0:
            # Scalar fallback (older calibration): preserve prior behavior.
            share = pa / _SPRING_SLOT_PA if _SPRING_SLOT_PA else 0
            base = _spring_slot_war(p, pos)
            hf = (((pa_r or 0) * _spring_hand_factor(p, "R")
                   + (pa_l or 0) * _spring_hand_factor(p, "L")) / pa) if pa else 1.0
            war = base * share * hf
            contribs.append(PlayerContribution(
                pid, p["name"], war, is_pitcher=False,
                bat_share=0.72, br_share=0.08, fld_share=0.20))
            return war, 0.72, 0.08, 0.20, None
        # Bat runs: each wedge valued at that hand's wRAA, pro-rated by PA.
        bat = (f["bat_R"] * (pa_r or 0) + f["bat_L"] * (pa_l or 0)) / _SPRING_FACET_PA
        pa_frac = pa / _SPRING_FACET_PA
        br = f["br"] * pa_frac
        fld = (f["fld"].get(pos, 0.0)) * pa_frac
        posr = (f["pos"].get(pos, 0.0)) * pa_frac
        total_runs = bat + br + fld + posr
        anchor = f["anchor"]
        rpw = f["rpw"] or 9.5
        repl = anchor.get("replacement_runs", 20.0)
        # WAR above replacement for this slice: (runs_above_avg + pro-rated
        # replacement cushion) / runs_per_win.
        war = (total_runs + repl * pa_frac) / rpw if rpw else 0.0
        # Facet shares for the engine breakdown: fractions of the positive run
        # contribution (fielding folds in the positional adj as its "glove+spot"
        # value). Bat negative is still bat; shares are |run| proportions.
        a_bat, a_br, a_fld = abs(bat), abs(br), abs(fld + posr)
        tot = (a_bat + a_br + a_fld) or 1.0
        bsh, brs, fsh = a_bat / tot, a_br / tot, a_fld / tot
        contribs.append(PlayerContribution(
            pid, p["name"], war, is_pitcher=False,
            bat_share=bsh, br_share=brs, fld_share=fsh))
        return war, bsh, brs, fsh, {"bat": bat, "br": br, "fld": fld, "pos": posr}

    def _add_contrib(pid, pos, share, hand_mix):
        """Add a hitter's contribution for a given PA SHARE + handedness mix.
        Converts the share/mix to explicit per-wedge PA (matching _mkrow's PA
        accounting EXACTLY) and defers to the facet-based _slot_contrib. An
        everyday mix (both hands) fills ``share`` of BOTH wedges; a platoon
        single-hand mix fills ``share`` of that one wedge."""
        hands = {h for h, _w in hand_mix}
        pa_r = _SPRING_PA_VS_RHP * share if "R" in hands else 0.0
        pa_l = _SPRING_PA_VS_LHP * share if "L" in hands else 0.0
        war, *_ = _slot_contrib(pid, pos, pa_r, pa_l)
        return war

    def _mkrow(pid, pos, share, hand_mix, label):
        war = _add_contrib(pid, pos, share, hand_mix)
        _st = dict(by_id[pid].get("stats") or {})
        _st["war"] = round(_spring_slot_rate_war(by_id[pid], pos), 1)
        # PA this player fills in each handedness wedge (the pie): share of the
        # wedge PA for each hand he faces in his hand_mix.
        hands = {h: w for h, w in hand_mix}
        pa_r = round(_SPRING_PA_VS_RHP * share) if "R" in hands else 0
        pa_l = round(_SPRING_PA_VS_LHP * share) if "L" in hands else 0
        return {
            "pid": pid, "name": by_id[pid]["name"],
            "war": round(_spring_slot_rate_war(by_id[pid], pos), 1),
            "level": by_id[pid]["level"],
            "pt_pct": round(share * 100), "role": label,
            "pa_r": pa_r, "pa_l": pa_l, "pa": pa_r + pa_l,
            "stats": _st, "contrib_war": war,
        }

    def _mkrow_pa(pid, pos, pa_r, pa_l, label="Allocated"):
        """Build a row from EXPLICIT PA in each wedge (literal pie allocation).
        Value is the facet-based per-wedge contribution (see _slot_contrib): bat
        valued at each hand's wOBA, baserunning/fielding/positional scaled by PA.
        The displayed `war` is the player's full-season RATE at this slot (the
        600-PA facet WAR), with `contrib_war` the actual PA-scaled contribution."""
        war, *_ = _slot_contrib(pid, pos, pa_r or 0, pa_l or 0)
        rate = _spring_slot_rate_war(by_id[pid], pos)
        _st = dict(by_id[pid].get("stats") or {})
        _st["war"] = round(rate, 1)
        pa = (pa_r or 0) + (pa_l or 0)
        return {
            "pid": pid, "name": by_id[pid]["name"], "war": round(rate, 1),
            "level": by_id[pid]["level"],
            "pt_pct": round(pa / _SPRING_SLOT_PA * 100), "role": label,
            "pa_r": round(pa_r or 0), "pa_l": round(pa_l or 0), "pa": round(pa),
            "stats": _st, "contrib_war": war,
        }

    # Pass 1 — starters (+ platoon pairs). Record the backup SHARE still open.
    backup_need = {}  # pos -> remaining share to fill with a backup
    pa_alloc_positions = set()   # positions with literal allocation (skip backup pass)
    for pos in _SPRING_FIELD + ["DH"]:
        starter_pid = config["lineup"].get(pos)
        if not starter_pid or starter_pid not in by_id:
            continue
        # Literal PA allocation takes over this position's pie entirely.
        alloc = _alloc_for(pos)
        if alloc:
            rows = []
            for pid, pa in sorted(alloc.items(),
                                  key=lambda kv: -((kv[1].get("r", 0) or 0) + (kv[1].get("l", 0) or 0))):
                if pid not in by_id:
                    continue
                rows.append(_mkrow_pa(pid, pos, pa.get("r", 0) or 0, pa.get("l", 0) or 0))
            if rows:
                constructed_lineup[pos] = {"players": rows}
                pa_alloc_positions.add(pos)
                backup_need[pos] = 0.0
                continue
        pl = platoon.get(pos) or {}
        vsR = pl.get("vsR", starter_pid)
        vsL = pl.get("vsL", starter_pid)
        base_share = _SPRING_START_SHARE.get(pos, _SPRING_DEFAULT_START_SHARE)
        rows = []
        if vsR == vsL:
            share = _ov(vsR) if _ov(vsR) is not None else base_share
            rows.append(_mkrow(vsR, pos, share,
                        [("R", _SPRING_VS_RHP_FREQ), ("L", _SPRING_VS_LHP_FREQ)], "Everyday"))
            backup_need[pos] = max(0.0, 1.0 - share)
        else:
            rows.append(_mkrow(vsR, pos, _SPRING_VS_RHP_FREQ, [("R", 1.0)], "vs RHP"))
            if vsL in by_id:
                rows.append(_mkrow(vsL, pos, _SPRING_VS_LHP_FREQ, [("L", 1.0)], "vs LHP"))
            # a platoon pair already covers both hands → minimal backup need
            backup_need[pos] = 0.0
        constructed_lineup[pos] = {"players": rows}

    # Pass 2 — assign ONE bench bat as backup per position, SCARCEST-FIRST (C
    # most), each bench player used at most once (no PA double-counting).
    for pos in ["C", "SS", "CF", "2B", "3B", "RF", "LF", "1B", "DH"]:
        need = backup_need.get(pos, 0.0)
        if need <= 0.02 or pos not in constructed_lineup:
            continue
        starter_pid = constructed_lineup[pos]["players"][0]["pid"]
        cands = [b for b in bench_by_pos.get(pos, [])
                 if b["player_id"] != starter_pid and b["player_id"] not in used_backups]
        if not cands:
            continue
        bk = max(cands, key=lambda b: b["war_proj"])
        used_backups.add(bk["player_id"])
        constructed_lineup[pos]["players"].append(
            _mkrow(bk["player_id"], pos, need,
                   [("R", _SPRING_VS_RHP_FREQ), ("L", _SPRING_VS_LHP_FREQ)], "Backup"))

    # Finalize each position: starter top-level fields + pos_war total + the
    # PA "pie" (wedge budgets, filled PA by hand, and any unfilled remainder).
    for pos, entry in constructed_lineup.items():
        rows = entry["players"]
        starter_row = rows[0]
        for k, v in starter_row.items():
            entry[k] = v
        entry["players"] = rows
        entry["pos_war"] = round(sum(r["contrib_war"] for r in rows), 1)
        filled_r = sum(r.get("pa_r", 0) for r in rows)
        filled_l = sum(r.get("pa_l", 0) for r in rows)
        entry["pa_budget"] = {
            "r_total": _SPRING_PA_VS_RHP, "l_total": _SPRING_PA_VS_LHP,
            "r_filled": filled_r, "l_filled": filled_l,
            "r_open": max(0, _SPRING_PA_VS_RHP - filled_r),
            "l_open": max(0, _SPRING_PA_VS_LHP - filled_l),
        }

    # ── Per-player PA cap (prevents cross-position over-allocation) ──
    # Each position's pie is balanced independently, so one body could be
    # allocated > a full season of PA across multiple spots (e.g. a utility man
    # at 2B + SS + 3B). Sum each hitter's TOTAL allocated PA across all
    # positions; if it exceeds the realistic per-player ceiling, scale his
    # per-position reps (and the WAR they generate) DOWN proportionally — he
    # still plays everywhere, just less — so the projection stays physically
    # possible. Record each capped player for an over-allocation warning.
    pa_by_pid: dict = {}
    rows_by_pid: dict = {}
    for pos, entry in constructed_lineup.items():
        for r in entry["players"]:
            pid = r["pid"]
            pa_by_pid[pid] = pa_by_pid.get(pid, 0) + (r.get("pa", 0) or 0)
            rows_by_pid.setdefault(pid, []).append((pos, r))
    overalloc = []
    for pid, total_pa in pa_by_pid.items():
        if total_pa <= _SPRING_PLAYER_PA_CAP:
            continue
        f = _SPRING_PLAYER_PA_CAP / total_pa
        positions = [pos for pos, _r in rows_by_pid[pid]]
        # Scale each of this player's position rows + the PA-pie wedge totals.
        for pos, r in rows_by_pid[pid]:
            r["pa_r"] = round((r.get("pa_r", 0) or 0) * f)
            r["pa_l"] = round((r.get("pa_l", 0) or 0) * f)
            r["pa"] = r["pa_r"] + r["pa_l"]
            r["pt_pct"] = round(r["pa"] / _SPRING_SLOT_PA * 100)
            r["contrib_war"] = round((r.get("contrib_war", 0.0) or 0.0) * f, 3)
        # Scale every PlayerContribution for this pid by the same factor (WAR is
        # linear in PA, so this is exactly "played proportionally fewer reps").
        for c in contribs:
            if (not c.is_pitcher) and c.player_id == pid:
                c.war *= f
        overalloc.append({
            "pid": pid, "name": by_id[pid]["name"],
            "total_pa": round(total_pa), "capped_pa": _SPRING_PLAYER_PA_CAP,
            "positions": positions,
        })
    # Recompute each position's pos_war / pa_budget after any scaling.
    if overalloc:
        for pos, entry in constructed_lineup.items():
            rows = entry["players"]
            entry["pos_war"] = round(sum(r["contrib_war"] for r in rows), 1)
            filled_r = sum(r.get("pa_r", 0) for r in rows)
            filled_l = sum(r.get("pa_l", 0) for r in rows)
            entry["pa_budget"].update({
                "r_filled": filled_r, "l_filled": filled_l,
                "r_open": max(0, _SPRING_PA_VS_RHP - filled_r),
                "l_open": max(0, _SPRING_PA_VS_LHP - filled_l),
            })
            # Keep the starter top-level mirror fields in sync with row[0].
            for k, v in rows[0].items():
                entry[k] = v

    # Pitchers — IP share by role (rotation order 1-5, bullpen role). A per-pid
    # `roles` map in the config overrides the default position in the list.
    roles = config.get("roles") or {}

    def _role_of(pid):
        return roles.get(pid) or roles.get(str(pid))

    # ── Staff IP + role-based pitcher valuation (issues: season coverage +
    # role-appropriate WAR) ──
    # Full-season SP/RP total IP for THIS league (calibrated; generic fallback),
    # so the projected staff covers a real season (~1444 team IP, ~57/43 SP/RP
    # in vMLB) instead of the old flat 65-IP-per-arm (~225 RP IP total).
    sp_total_ip, rp_total_ip = staff_ip or (_SPRING_SP_TOTAL_IP_DEFAULT, _SPRING_RP_TOTAL_IP_DEFAULT)
    _RP_DEFAULT = ["closer", "setup", "setup", "middle", "middle", "middle", "long", "long"]

    rotation_ids = [pid for pid in config.get("rotation", []) if pid in by_id]
    bullpen_ids = [pid for pid in config.get("bullpen", []) if pid in by_id]

    # Resolve each arm's role + role-share weight, then DISTRIBUTE the group's
    # total IP across the rostered arms proportional to their weights — so the
    # staff sums to the real season regardless of how many arms are carried.
    rot_roles = [(_role_of(pid) or ("sp" + str(min(i + 1, 5)))) for i, pid in enumerate(rotation_ids)]
    pen_roles = [(_role_of(pid) or (_RP_DEFAULT[i] if i < len(_RP_DEFAULT) else "middle"))
                 for i, pid in enumerate(bullpen_ids)]
    rot_w = [_SPRING_PITCHER_ROLE_SHARE.get(r, 0.90) for r in rot_roles]
    pen_w = [_SPRING_PITCHER_ROLE_SHARE.get(r, 0.50) for r in pen_roles]
    # Normalize by a FULL staff's role-weight sum (5 SP / 8 RP default shares),
    # NOT the actual rostered count — so a SHORT staff UNDER-covers the season
    # (its innings aren't magically absorbed by the remaining arms; the gap is
    # the taxi-squad/callup innings a thin roster leans on) rather than inflating
    # each arm's IP. A full 8-man pen distributes the whole RP total; a 7-man pen
    # covers ~7/8 of it.
    _FULL_ROT_W = sum(_SPRING_PITCHER_ROLE_SHARE["sp" + str(i)] for i in range(1, _SPRING_SP_SLOTS + 1))
    _FULL_PEN_W = sum(_SPRING_PITCHER_ROLE_SHARE.get(r, 0.50)
                      for r in ["closer", "setup", "setup", "middle", "middle", "middle", "long", "long"][:_SPRING_RP_SLOTS])
    sum_rot_w = max(sum(rot_w), _FULL_ROT_W) if rot_w else _FULL_ROT_W
    sum_pen_w = max(sum(pen_w), _FULL_PEN_W) if pen_w else _FULL_PEN_W

    # Reference full-role workloads for the per-IP RATE (a stable "value per a
    # standard full season in this role" figure, independent of how the staff's
    # IP happens to split). SP ~ a full starter season; RP ~ a full bullpen
    # season. The CONTRIBUTION uses the calibrated role IP (which sums to the
    # real season); the RATE uses these references so it reads as talent, not
    # workload.
    _SP_REF_IP = sp_total_ip / 5.0          # a full rotation slot
    _RP_REF_IP = rp_total_ip / _SPRING_RP_SLOTS  # a full bullpen slot (8-man pen)

    def _war_per_ip(pid, native_bucket):
        """A pitcher's WAR per inning, from his NATIVE-role full-season
        projection. `war_proj` is a full season in his native role; divide by
        that native workload to get a rate that can be re-applied to ANY role's
        innings — so a starter considered for the pen is valued on relief
        innings, not starter innings (the role-based-valuation fix)."""
        native_full = _SP_REF_IP if native_bucket == "SP" else _RP_REF_IP
        return (by_id[pid]["war_proj"] or 0.0) / max(1.0, native_full)

    constructed_rotation, constructed_pen = [], []
    for i, pid in enumerate(rotation_ids):
        role = rot_roles[i]
        proj_ip = rot_w[i] / sum_rot_w * sp_total_ip
        wpi = _war_per_ip(pid, by_id[pid].get("bucket"))
        contrib = wpi * proj_ip            # value over his projected rotation IP
        rate = wpi * _SP_REF_IP            # value per a full rotation slot (talent)
        contribs.append(PlayerContribution(pid, by_id[pid]["name"], contrib, is_pitcher=True))
        constructed_rotation.append({"pid": pid, "name": by_id[pid]["name"],
                                     "war": round(rate, 1),            # per-full-slot rate (role-valued)
                                     "contrib_war": round(contrib, 1), # calibrated role-IP contribution
                                     "proj_ip": round(proj_ip),
                                     "role": role, "pt_pct": round(rot_w[i] / sum_rot_w * 100),
                                     "stats": by_id[pid].get("stats") or {}})
    for i, pid in enumerate(bullpen_ids):
        role = pen_roles[i]
        proj_ip = pen_w[i] / sum_pen_w * rp_total_ip
        wpi = _war_per_ip(pid, by_id[pid].get("bucket"))
        contrib = wpi * proj_ip            # value over his projected bullpen IP
        rate = wpi * _RP_REF_IP            # value per a full bullpen slot (talent)
        contribs.append(PlayerContribution(pid, by_id[pid]["name"], contrib, is_pitcher=True))
        constructed_pen.append({"pid": pid, "name": by_id[pid]["name"],
                                "war": round(rate, 1),             # per-full-slot rate (role-valued)
                                "contrib_war": round(contrib, 1),  # calibrated role-IP contribution
                                "proj_ip": round(proj_ip),
                                "role": role, "pt_pct": round(pen_w[i] / sum_pen_w * 100),
                                "stats": by_id[pid].get("stats") or {}})

    # Per-hitter aggregate across all pies: projected-contribution WAR (what the
    # projection actually credits) and total pie PA. Drives the derived active
    # roster + honest bench metrics.
    hitter_pie = {}   # pid -> {"contrib_war": float, "pa": int, "positions": [pos]}
    for pos, entry in constructed_lineup.items():
        for r in entry["players"]:
            if (r.get("pa", 0) or 0) <= 0:
                continue
            agg = hitter_pie.setdefault(r["pid"], {"contrib_war": 0.0, "pa": 0, "positions": []})
            agg["contrib_war"] += r.get("contrib_war", 0.0) or 0.0
            agg["pa"] += r.get("pa", 0) or 0
            agg["positions"].append(pos)

    # Bench = RESERVES: rostered hitters who are NOT filling a pie (or barely).
    # A platoon partner added via a pie is shown IN that pie, not on the bench
    # (no double-count). The explicit config["bench"] is the GM's reserve list;
    # a reserve who has since taken a pie share is surfaced with where he plays.
    # Metric: a reserve's projected CONTRIBUTION (what the projection credits —
    # ~0 for a pure, unused reserve) is misleading as a headline, so the bench
    # shows his full-season RATE as the primary number (his value if pressed
    # into duty) with contribution/PA as secondary context.
    bench_pids = [pid for pid in config.get("bench", []) if pid in by_id]
    bench_view = []
    for pid in bench_pids:
        agg = hitter_pie.get(pid)
        bench_view.append({
            "pid": pid, "name": by_id[pid]["name"],
            "war": round(by_id[pid]["war_proj"], 1),       # full-season RATE (primary)
            "contrib_war": round(agg["contrib_war"], 1) if agg else 0.0,
            "pie_pa": agg["pa"] if agg else 0,
            "in_pie": [agg_pos for agg_pos in (agg["positions"] if agg else [])],
            "stats": by_id[pid].get("stats") or {},
        })

    # Active position players = everyone actually taking PA in a pie PLUS the
    # explicit bench reserves (26-man accounting). A platoon partner who isn't
    # on config["bench"] is still active (he's in a pie) — this is the union the
    # UI needs so no rostered body is unaccounted-for.
    active_hitters = sorted(
        set(hitter_pie) | set(bench_pids),
        key=lambda p: -(hitter_pie.get(p, {}).get("contrib_war", 0.0)
                        or by_id[p]["war_proj"]))

    constructed = {
        "lineup": constructed_lineup, "rotation": constructed_rotation,
        "bullpen": constructed_pen, "bench": bench_view,
        "active_hitters": active_hitters,
        "hitter_pie": {str(k): v for k, v in hitter_pie.items()},
    }
    return contribs, constructed, overalloc


def _spring_league_mean_war(conn, ed, cfg, pyth_exp):
    """Mean auto-configured team WAR across all MLB orgs — the .500 anchor, plus
    the hitter/pitcher means that baseline the per-facet display.

    Removes the uniform optimism in the ratings-based WAR scale by centering an
    average roster at games/2 wins. Returns (total, hit, pit) means. Cached.
    """
    key = (id(conn), "lgwar")
    if key in _SPRING_CALIB_CACHE:
        return _SPRING_CALIB_CACHE[key]
    _staff_ip = _spring_staff_ip(conn)
    tids = [int(t) for t in cfg.team_abbr_map.keys()]
    totals, hits, pits = [], [], []
    for tid in tids:
        pool = _spring_pool(conn, tid, ed)
        if not pool:
            continue
        cfg_auto = _spring_auto_config(pool)
        contribs, _, _ = _spring_contributions(pool, cfg_auto, _staff_ip)
        totals.append(sum(c.war for c in contribs))
        hits.append(sum(c.war for c in contribs if not c.is_pitcher))
        pits.append(sum(c.war for c in contribs if c.is_pitcher))
    n = len(totals)
    out = (round(sum(totals) / n, 2), round(sum(hits) / n, 2), round(sum(pits) / n, 2)) if n else (None, None, None)
    _SPRING_CALIB_CACHE[key] = out
    return out


# ---------------------------------------------------------------------------
# Contested spots — Layer 1, the real decisions.
#
# A spot is contested when the OUTCOME IS IN DOUBT, not whenever a choice exists:
#   (1) starting-job competition — top candidate and runner-up within ~1 WAR
#       (a clear 4.0-vs-1.0 is a lock, not a decision);
#   (2) final-roster-spot bubble — the last bench bats / last bullpen arms,
#       where N vie for M<M+1 spots and the cut line is tight;
#   (3) forced by a hard constraint — an out-of-options player on the bubble
#       must make the 26 or clear waivers, so the spot is contested even with a
#       clear talent gap (the user-supplied out-of-options toggle feeds in here).
#
# Locks never appear here — they live in the Opening Day team view (Layer 2).
# ---------------------------------------------------------------------------

# How close the top-2 must be (in current-age WAR) to count as a competition.
_SPRING_CONTEST_WAR = 1.0
# Bubble width around a cut line: players within this of the last-in player.
_SPRING_BUBBLE_WAR = 0.8


def _spring_candidate(p, is_pick, forced=False):
    """A contested-spot candidate row for the UI."""
    return {
        "pid": p["player_id"], "name": p["name"], "age": p["age"],
        "level": p["level"], "war": round(p["war_proj"], 1),
        "fv": p.get("fv"), "composite": p.get("composite"),
        "bucket": p["bucket"], "is_pick": is_pick,
        "out_of_options": forced,
    }


def _spring_contested_spots(pool, config, out_of_options=None):
    """Detect the genuine competitions on the Opening Day roster.

    Args:
        pool: the candidate pool (from _spring_pool).
        config: the current 26-man config (auto or user).
        out_of_options: set of player_ids the user flagged as out of options.

    Returns a list of spot dicts:
        {kind, slot, candidates:[...], reason}
    sorted with forced/constraint spots first, then by how close the race is.
    """
    ooo = set(out_of_options or ())
    by_id = {p["player_id"]: p for p in pool}
    spots = []

    def _forced(cands):
        return any(c["player_id"] in ooo for c in cands)

    # --- (1) Field + DH starting jobs ---
    for pos in _SPRING_FIELD + ["DH"]:
        nat = pos  # DH handled as its own small pool below
        cands = sorted(
            [p for p in pool if not p["is_pitcher"]
             and _SPRING_BUCKET_POS.get(p["bucket"]) == (pos if pos != "DH" else p["bucket"])],
            key=lambda x: -x["war_proj"])
        if pos == "DH":
            # DH: best bats NOT already an everyday field starter in this config
            # (a locked field starter isn't also a DH decision).
            field_starters = {pid for pos_k, pid in config.get("lineup", {}).items()
                              if pos_k != "DH"}
            cands = sorted([p for p in pool if not p["is_pitcher"]
                            and p["player_id"] not in field_starters],
                           key=lambda x: -x["war_proj"])[:4]
        if len(cands) < 2:
            continue
        gap = cands[0]["war_proj"] - cands[1]["war_proj"]
        forced = _forced([{"player_id": c["player_id"]} for c in cands[:3]])
        if gap <= _SPRING_CONTEST_WAR or forced:
            rows = [_spring_candidate(c, i == 0, c["player_id"] in ooo)
                    for i, c in enumerate(cands[:3])]
            reason = ("out-of-options decision" if forced
                      else f"top two within {gap:.1f} WAR")
            spots.append({"kind": "field", "slot": pos, "candidates": rows,
                          "reason": reason, "gap": gap, "forced": forced})

    # --- (2) 5th starter ---
    sps = sorted([p for p in pool if p["bucket"] == "SP"], key=lambda x: -x["war_proj"])
    if len(sps) >= 6:
        gap = sps[4]["war_proj"] - sps[5]["war_proj"]
        bubble = [p for p in sps[3:7]]
        forced = any(p["player_id"] in ooo for p in bubble)
        if gap <= _SPRING_CONTEST_WAR or forced:
            pick_pid = sps[4]["player_id"]  # the 5th starter is the pick
            rows = [_spring_candidate(c, c["player_id"] == pick_pid, c["player_id"] in ooo)
                    for c in bubble]
            spots.append({"kind": "rotation", "slot": "5th Starter",
                          "candidates": rows,
                          "reason": ("out-of-options decision" if forced
                                     else f"5th vs 6th within {gap:.1f} WAR"),
                          "gap": gap, "forced": forced})

    # --- (3) Final bullpen spots (bubble around the 8-arm cut) ---
    rps = sorted([p for p in pool if p["bucket"] == "RP"], key=lambda x: -x["war_proj"])
    if len(rps) >= 9:
        cut_war = rps[7]["war_proj"]  # last man in (8th)
        bubble = [p for p in rps[6:] if cut_war - p["war_proj"] <= _SPRING_BUBBLE_WAR
                  or p["war_proj"] >= cut_war]
        forced = any(p["player_id"] in ooo for p in bubble)
        if len(bubble) >= 3 or forced:
            rows = [_spring_candidate(c, c["war_proj"] >= cut_war, c["player_id"] in ooo)
                    for c in bubble[:4]]
            spots.append({"kind": "bullpen", "slot": "Final bullpen spots",
                          "candidates": rows,
                          "reason": ("out-of-options decision" if forced
                                     else f"{len(bubble)} arms for the last spots"),
                          "gap": 0.0, "forced": forced})

    # --- (4) Last bench bat (bubble around the bench cut) ---
    hitters = sorted([p for p in pool if not p["is_pitcher"]], key=lambda x: -x["war_proj"])
    # Bench candidates = hitters beyond the 9 everyday slots.
    bench_pool = hitters[9:]
    if len(bench_pool) >= 2:
        # 4 bench bats assumed; bubble is around the 4th.
        cut_idx = min(3, len(bench_pool) - 1)
        cut_war = bench_pool[cut_idx]["war_proj"]
        pick_pid = bench_pool[cut_idx]["player_id"]  # last-in = the pick
        bubble = [p for p in bench_pool[max(0, cut_idx - 1):]
                  if abs(p["war_proj"] - cut_war) <= _SPRING_BUBBLE_WAR]
        forced = any(p["player_id"] in ooo for p in bubble)
        if len(bubble) >= 2 or forced:
            rows = [_spring_candidate(c, c["player_id"] == pick_pid, c["player_id"] in ooo)
                    for c in bubble[:3]]
            spots.append({"kind": "bench", "slot": "Last bench spot",
                          "candidates": rows,
                          "reason": ("out-of-options decision" if forced
                                     else "tight for the final bench spot"),
                          "gap": 0.0, "forced": forced})

    # Forced/constraint spots first; then closest races first.
    spots.sort(key=lambda s: (not s["forced"], s["gap"]))
    return spots


def get_spring_projection(team_id, config=None, out_of_options=None):
    """Project a configured Opening Day roster as the full cascade.

    Args:
        team_id: the org to project.
        config: optional roster configuration
            {lineup:{pos:pid}, bench:[pid], rotation:[pid], bullpen:[pid]}.
            None = the model's auto 26-man.
        out_of_options: optional iterable of player_ids the user flagged as out
            of options (a hard must-decide constraint — see contested spots).

    Returns a dict:
        projection: the TeamProjection cascade (record, run diff, facets, band),
        constructed: the per-slot roster view (lineup/rotation/bullpen/bench),
        contested: the Layer-1 decisions (competitions + constraint-forced),
        config: the config used (so the UI can seed its editable state),
        pool: the candidate pool (for contested-spot / swap menus).
    """
    from statsplusplus.evaluation.team_projection import project_team
    import dataclasses

    conn = get_db()
    cfg = get_cfg()
    ed = _eval_date(conn)
    pyth_exp = cfg.settings.get("pyth_exp", 1.83)

    pool = _spring_pool(conn, team_id, ed)
    if config is None:
        config = _spring_auto_config(pool, out_of_options)
    must_expose = config.get("_must_expose", [])

    staff_ip = _spring_staff_ip(conn)
    contribs, constructed, overalloc = _spring_contributions(pool, config, staff_ip)

    calib = _spring_calibration(conn, pyth_exp)
    mean_war, mean_hit, mean_pit = _spring_league_mean_war(conn, ed, cfg, pyth_exp)
    if mean_war is not None:
        calib = dataclasses.replace(calib, lg_mean_team_war=mean_war,
                                    lg_mean_hit_war=mean_hit, lg_mean_pit_war=mean_pit)

    proj = project_team(contribs, calib)
    contested = _spring_contested_spots(pool, config, out_of_options)

    by_id = {p["player_id"]: p for p in pool}

    # Platoon suggestions: for each field slot NOT already platooned (its pie has
    # a single hitter filling both wedges), propose the best strong-side partner
    # for the starter's weak hand, with the projected WIN delta of applying it.
    # Only surfaced when it actually helps (delta > 0). Lets the GM see
    # "platooning here is worth +0.4 wins" and apply it in one click.
    platoon_suggestions = []
    base_wins = proj.wins
    for pos in _SPRING_FIELD + ["DH"]:   # DH platoons too (no defensive cost)
        entry = constructed.get("lineup", {}).get(pos)
        if not entry:
            continue
        # Skip positions already deploying 2+ hitters (already a platoon/share).
        if len([r for r in entry.get("players", []) if (r.get("pa_r", 0) + r.get("pa_l", 0)) > 0]) >= 2:
            continue
        sug = _spring_suggest_platoon(pool, config, pos)
        if not sug:
            continue
        # Project the win delta of applying this platoon's pa_alloc.
        trial = dict(config)
        trial_alloc = dict(config.get("pa_alloc") or {})
        trial_alloc[pos] = sug["pa_alloc"]
        trial["pa_alloc"] = trial_alloc
        t_contribs, _, _ = _spring_contributions(pool, trial, staff_ip)
        t_proj = project_team(t_contribs, calib)
        dwins = round(t_proj.wins - base_wins, 2)
        if dwins > 0.05:   # only worthwhile suggestions
            sug["delta_wins"] = dwins
            sug["delta_run_diff"] = round(t_proj.run_diff - proj.run_diff, 1)
            platoon_suggestions.append(sug)
    platoon_suggestions.sort(key=lambda s: -s["delta_wins"])
    # Roster-validity warnings. A catcher starts only ~67% of games — a team
    # MUST carry a backup C (you can't cover 162 with one). Flag if the C slot
    # has no backup and there's no second catcher-eligible player rostered.
    warnings = []
    c_slot = constructed.get("lineup", {}).get("C")
    c_backup = c_slot and any(r.get("role") == "Backup" for r in c_slot.get("players", []))
    rostered = set(config.get("lineup", {}).values()) | set(config.get("bench", []))
    c_eligible = [pid for pid in rostered
                  if pid in by_id and "C" in (by_id[pid].get("eligible") or [])]
    if c_slot and not c_backup and len(c_eligible) < 2:
        warnings.append({
            "kind": "no_backup_catcher",
            "msg": "No backup catcher — a C starts only ~67% of games, so you "
                   "must carry a second catcher. Add one to your bench."})
    # Over-allocation: a player handed more than a full season of PA across
    # multiple positions. His contributions were scaled down proportionally
    # (the projection stays honest), but flag it so the GM can rebalance.
    for oa in overalloc:
        pos_list = "/".join(oa["positions"])
        warnings.append({
            "kind": "over_allocated",
            "msg": (f"{oa['name']} is allocated {oa['total_pa']} PA across "
                    f"{pos_list} — more than one player can take. Capped to "
                    f"{oa['capped_pa']} (reps scaled down proportionally). "
                    f"Trim his share at one of those spots.")})
    return {
        "projection": dataclasses.asdict(proj),
        "constructed": constructed,
        "contested": contested,
        "warnings": warnings,
        "config": config,
        "pool": pool,
        "platoon_suggestions": platoon_suggestions,
        # Flagged out-of-options players the recommender could NOT fit — the GM
        # must knowingly expose (waivers) or override.
        "must_expose": [{"pid": pid, "name": by_id[pid]["name"],
                         "war": round(by_id[pid]["war_proj"], 1)}
                        for pid in must_expose if pid in by_id],
    }


# ---------------------------------------------------------------------------
# Plan persistence — a saved Opening Day plan per team.
#
# A plan is just the user's chosen config (lineup/bench/rotation/bullpen) plus
# their out-of-options flags — the minimal state to reconstruct their decisions.
# Everything else (projection, contested spots, constructed roster) is DERIVED
# by re-running get_spring_projection against CURRENT data, so a plan stays
# meaningful across refreshes. Stored at config/spring_plans.json keyed by team.
# ---------------------------------------------------------------------------

def _spring_plans_path(league_dir):
    from pathlib import Path
    return Path(league_dir) / "config" / "spring_plans.json"


def _load_spring_plans(league_dir):
    import json
    path = _spring_plans_path(league_dir)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text()) or {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_spring_plan(team_id, config, out_of_options=None):
    """Persist a team's Opening Day plan. Stores player IDs + flags only (not
    derived projections). Returns the saved record."""
    import json
    from datetime import datetime, timezone
    cfg = get_cfg()
    league_dir = cfg.league_dir
    # Strip the internal _must_expose marker; store the roster selection + the
    # deployment decisions (platoon assignment, start-share, pitcher roles).
    clean = {k: config[k] for k in
             ("lineup", "bench", "rotation", "bullpen", "platoon", "start_share",
              "roles", "pa_alloc")
             if k in config}
    # Stamp with the current game date (from state.json, the authoritative
    # source) so the UI can warn if the plan predates a later data refresh.
    game_date = None
    try:
        import json
        from pathlib import Path
        sp = Path(league_dir) / "config" / "state.json"
        if sp.exists():
            game_date = json.loads(sp.read_text()).get("game_date")
    except Exception:
        game_date = None
    record = {
        "config": clean,
        "out_of_options": sorted(set(int(p) for p in (out_of_options or []))),
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "game_date": game_date,
    }
    plans = _load_spring_plans(league_dir)
    plans[str(team_id)] = record
    path = _spring_plans_path(league_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plans, indent=2) + "\n")
    return record


def load_spring_plan(team_id):
    """Load a team's saved plan, reconciled against the CURRENT pool.

    Players no longer in the pool (traded/released/retired since the plan was
    saved) are dropped from the config and reported in `dropped` so the UI can
    flag the staleness. Returns None if no plan is saved.
    """
    conn = get_db()
    cfg = get_cfg()
    ed = _eval_date(conn)
    plans = _load_spring_plans(cfg.league_dir)
    rec = plans.get(str(team_id))
    if not rec:
        return None

    pool_ids = {p["player_id"] for p in _spring_pool(conn, team_id, ed)}
    saved = rec.get("config", {})
    dropped = []

    def _keep_list(pids):
        kept = []
        for pid in pids or []:
            if pid in pool_ids:
                kept.append(pid)
            else:
                dropped.append(pid)
        return kept

    lineup = {}
    for pos, pid in (saved.get("lineup") or {}).items():
        if pid in pool_ids:
            lineup[pos] = pid
        else:
            dropped.append(pid)
    def _keep_pid_map(m):
        """Keep a {pid: val} map for pool players only; normalize int keys."""
        out = {}
        for k, v in (m or {}).items():
            try:
                pid_k = int(k)
            except (TypeError, ValueError):
                continue
            if pid_k in pool_ids:
                out[pid_k] = v
        return out

    # Platoon assignment {pos: {vsR, vsL}} — keep entries whose players survive.
    saved_platoon = saved.get("platoon") or {}
    platoon = {}
    for pos, pair in saved_platoon.items():
        kept = {h: pid for h, pid in (pair or {}).items() if pid in pool_ids}
        if kept:
            platoon[pos] = kept

    # Literal PA allocation {pos: {pid: {r,l}}} — drop players no longer rostered.
    saved_alloc = saved.get("pa_alloc") or {}
    pa_alloc = {}
    for pos, pmap in saved_alloc.items():
        kept = {}
        for k, v in (pmap or {}).items():
            try:
                pid_k = int(k)
            except (TypeError, ValueError):
                continue
            if pid_k in pool_ids:
                kept[pid_k] = v
        if kept:
            pa_alloc[pos] = kept

    config = {
        "lineup": lineup,
        "bench": _keep_list(saved.get("bench")),
        "rotation": _keep_list(saved.get("rotation")),
        "bullpen": _keep_list(saved.get("bullpen")),
        "platoon": platoon,
        "start_share": _keep_pid_map(saved.get("start_share")),
        "roles": _keep_pid_map(saved.get("roles")),
        "pa_alloc": pa_alloc,
    }
    ooo = [pid for pid in rec.get("out_of_options", []) if pid in pool_ids]
    return {
        "config": config,
        "out_of_options": ooo,
        "saved_at": rec.get("saved_at"),
        "game_date": rec.get("game_date"),
        "dropped": dropped,            # player_ids no longer in the pool
        "stale": bool(dropped),        # a saved player vanished since save
    }


def spring_projection_delta(team_id, config, baseline=None, out_of_options=None,
                            baseline_out_of_options=None):
    """Re-project a (possibly edited) config and return the cascade + the DELTA
    vs a baseline — the live decision signal.

    The delta is the precise part (season luck cancels between two configs), so
    the UI foregrounds it over the absolute band. Baseline defaults to the auto
    recommendation ("vs the model"); pass the pre-edit config to get the effect
    of a single edit ("vs before this change").

    Args:
        config: the edited roster configuration.
        baseline: config to diff against; None = the auto recommendation.
        out_of_options / baseline_out_of_options: flags for each side.

    Returns {projection, baseline, delta} where delta is per-metric after-minus-
    before (wins, run_diff, the four facet runs, team_war).
    """
    after = get_spring_projection(team_id, config, out_of_options)
    if baseline is None:
        base_res = get_spring_projection(team_id, None, baseline_out_of_options)
    else:
        base_res = get_spring_projection(team_id, baseline, baseline_out_of_options)
    a, b = after["projection"], base_res["projection"]
    metrics = ("wins", "run_diff", "team_war",
               "bat_runs", "br_runs", "fld_runs", "pit_runs",
               "runs_scored", "runs_allowed")
    delta = {m: round(a[m] - b[m], 2) for m in metrics}
    # Cumulative, itemized breakdown of the WHOLE plan vs the saved plan (or auto
    # 26 if none saved) — the header "Changes vs saved plan" panel. Independent
    # of `baseline` above (which the caller may set to the pre-edit config for a
    # single-edit delta); the breakdown always anchors on the persisted plan.
    breakdown = spring_change_breakdown(team_id, config, out_of_options=out_of_options)
    return {
        "projection": after["projection"],
        "constructed": after["constructed"],
        "contested": after["contested"],
        "config": after["config"],
        "must_expose": after["must_expose"],
        "warnings": after.get("warnings", []),
        "platoon_suggestions": after.get("platoon_suggestions", []),
        "baseline": base_res["projection"],
        "delta": delta,
        "breakdown": breakdown,
    }


# ---------------------------------------------------------------------------
# Change breakdown — cumulative impact of the whole plan vs a baseline, itemized
# into discrete roster MOVES each with its own win / run-diff / facet impact.
#
# Attribution is SEQUENTIAL along a canonical move order: start from the baseline
# config, apply the diffed moves one at a time, and credit each move the
# incremental projection change it produces GIVEN the prior moves. This sums
# EXACTLY to the headline total (unlike isolated-move attribution, which leaves
# an interaction remainder), is deterministic (canonical order, not edit order),
# and each line reads "applying this move changed wins by X".
# ---------------------------------------------------------------------------

# Canonical slot order for deterministic attribution (field, then DH, then staff).
_SPRING_MOVE_ORDER = _SPRING_FIELD + ["DH", "SP", "RP", "BENCH"]


def _spring_config_diff(base, cur, by_id):
    """Diff two configs into an ordered list of discrete MOVES. Each move is a
    dict {kind, slot, label, apply} where `apply(cfg)` mutates a config copy to
    carry JUST that move (so moves can be applied cumulatively for attribution).

    Move kinds: 'lineup' (starter swap at a field/DH slot), 'deploy' (platoon /
    pa_alloc change at a slot the starter kept), 'rotation'/'bullpen' (staff set
    change), 'bench' (reserve add/drop), 'role' (pitcher role / start_share).
    """
    import json as _json

    def _name(pid):
        p = by_id.get(pid)
        return (p["name"] if p else ("#" + str(pid)))

    moves = []

    # --- Field + DH starter changes (lineup) ---
    base_lineup = base.get("lineup", {}) or {}
    cur_lineup = cur.get("lineup", {}) or {}
    for pos in _SPRING_FIELD + ["DH"]:
        b_pid, c_pid = base_lineup.get(pos), cur_lineup.get(pos)
        if b_pid != c_pid:
            if c_pid is None:
                lab = f"Drop {pos} starter {_name(b_pid)}"
            elif b_pid is None:
                lab = f"Start {_name(c_pid)} at {pos}"
            else:
                lab = f"{pos}: {_name(b_pid)} → {_name(c_pid)}"
            moves.append({"kind": "lineup", "slot": pos, "label": lab,
                          "_set": ("lineup", pos, c_pid)})

    # --- Deployment changes at a slot the STARTER kept (platoon / pa_alloc) ---
    # Only surface where the lineup starter is unchanged (a starter swap already
    # subsumes the deployment reset). Compare the pa_alloc + platoon per slot.
    base_alloc = base.get("pa_alloc", {}) or {}
    cur_alloc = cur.get("pa_alloc", {}) or {}
    base_plat = base.get("platoon", {}) or {}
    cur_plat = cur.get("platoon", {}) or {}
    for pos in _SPRING_FIELD + ["DH"]:
        if base_lineup.get(pos) != cur_lineup.get(pos):
            continue  # subsumed by the starter swap above
        a_changed = _json.dumps(base_alloc.get(pos), sort_keys=True) != \
            _json.dumps(cur_alloc.get(pos), sort_keys=True)
        p_changed = _json.dumps(base_plat.get(pos), sort_keys=True) != \
            _json.dumps(cur_plat.get(pos), sort_keys=True)
        if a_changed or p_changed:
            moves.append({"kind": "deploy", "slot": pos,
                          "label": f"{pos}: platoon / playing-time change",
                          "_set_deploy": pos})

    # --- Staff set changes (rotation, bullpen) ---
    for key, slot, lbl in (("rotation", "SP", "Rotation"), ("bullpen", "RP", "Bullpen")):
        b_set = list(base.get(key, []) or [])
        c_set = list(cur.get(key, []) or [])
        added = [p for p in c_set if p not in b_set]
        removed = [p for p in b_set if p not in c_set]
        for pid in added:
            moves.append({"kind": key, "slot": slot,
                          "label": f"{lbl}: add {_name(pid)}", "_set_list": key})
        for pid in removed:
            moves.append({"kind": key, "slot": slot,
                          "label": f"{lbl}: drop {_name(pid)}", "_set_list": key})

    # --- Bench reserve add/drop ---
    b_bench = set(base.get("bench", []) or [])
    c_bench = set(cur.get("bench", []) or [])
    for pid in (c_bench - b_bench):
        moves.append({"kind": "bench", "slot": "BENCH",
                      "label": f"Bench: add {_name(pid)}", "_set_list": "bench"})
    for pid in (b_bench - c_bench):
        moves.append({"kind": "bench", "slot": "BENCH",
                      "label": f"Bench: drop {_name(pid)}", "_set_list": "bench"})

    # --- Pitcher role / start-share changes (grouped, low-level) ---
    if _json.dumps(base.get("roles"), sort_keys=True) != _json.dumps(cur.get("roles"), sort_keys=True) \
       or _json.dumps(base.get("start_share"), sort_keys=True) != _json.dumps(cur.get("start_share"), sort_keys=True):
        moves.append({"kind": "role", "slot": "ROLE",
                      "label": "Role / playing-time tweaks", "_set_roles": True})

    # Order moves canonically by slot for deterministic sequential attribution.
    order = {s: i for i, s in enumerate(_SPRING_MOVE_ORDER)}
    moves.sort(key=lambda m: order.get(m["slot"], 99))
    return moves


def _apply_move(cfg, move, cur):
    """Apply one diffed move's target state onto `cfg` (a working copy that
    starts at baseline), pulling the final value from the CURRENT config `cur`.
    Mutates and returns cfg."""
    import copy
    if "_set" in move:
        key, pos, pid = move["_set"]
        cfg.setdefault(key, {})
        if pid is None:
            cfg[key].pop(pos, None)
        else:
            cfg[key][pos] = pid
        # A starter swap also resets that slot's stale deployment (mirror the
        # client's clearSlotDeployment), then adopt the current one if present.
        for dk in ("pa_alloc", "platoon"):
            if cfg.get(dk):
                cfg[dk].pop(pos, None)
            if (cur.get(dk) or {}).get(pos) is not None:
                cfg.setdefault(dk, {})[pos] = copy.deepcopy(cur[dk][pos])
    elif "_set_deploy" in move:
        pos = move["_set_deploy"]
        for dk in ("pa_alloc", "platoon"):
            if (cur.get(dk) or {}).get(pos) is not None:
                cfg.setdefault(dk, {})[pos] = copy.deepcopy(cur[dk][pos])
            elif cfg.get(dk):
                cfg[dk].pop(pos, None)
    elif "_set_list" in move:
        key = move["_set_list"]
        cfg[key] = list(cur.get(key, []) or [])      # adopt the current set
    elif "_set_roles" in move:
        cfg["roles"] = copy.deepcopy(cur.get("roles") or {})
        cfg["start_share"] = copy.deepcopy(cur.get("start_share") or {})
    return cfg


def spring_change_breakdown(team_id, config, baseline=None, out_of_options=None,
                            baseline_out_of_options=None):
    """Cumulative impact of the whole plan vs a baseline, itemized by move.

    Returns {projection, baseline, delta (cumulative total), changes:[{label,
    kind, slot, wins, run_diff}], n_changes}. Each change's wins/run_diff is its
    SEQUENTIAL marginal contribution (applied in canonical order atop prior
    moves), so the change impacts sum exactly to the headline delta.

    `baseline=None` → the saved plan's config if one exists, else the auto 26.
    """
    from statsplusplus.evaluation.team_projection import project_team
    import copy, dataclasses

    conn = get_db()
    cfg_lc = get_cfg()
    ed = _eval_date(conn)
    pyth_exp = cfg_lc.settings.get("pyth_exp", 1.83)
    pool = _spring_pool(conn, team_id, ed)
    by_id = {p["player_id"]: p for p in pool}

    # Resolve the baseline config: explicit > saved plan > auto 26.
    base_ooo = baseline_out_of_options
    saved = None if baseline is not None else load_spring_plan(team_id)
    if baseline is None:
        if saved is not None:
            baseline = saved["config"]
            if base_ooo is None:
                base_ooo = saved.get("out_of_options")
        else:
            baseline = _spring_auto_config(pool, base_ooo)
    base_label = "saved plan" if saved is not None else "auto 26"

    # Calibration (shared across every incremental projection).
    calib = _spring_calibration(conn, pyth_exp)
    mean_war, mean_hit, mean_pit = _spring_league_mean_war(conn, ed, cfg_lc, pyth_exp)
    if mean_war is not None:
        calib = dataclasses.replace(calib, lg_mean_team_war=mean_war,
                                    lg_mean_hit_war=mean_hit, lg_mean_pit_war=mean_pit)

    staff_ip = _spring_staff_ip(conn)

    def _rec(cfg_in):
        contribs, _c, _o = _spring_contributions(pool, cfg_in, staff_ip)
        return project_team(contribs, calib)

    base_proj = _rec(baseline)
    cur_proj = _rec(config)

    # Walk the canonical move list, applying each atop the prior and crediting
    # it the incremental (wins, run_diff) change.
    moves = _spring_config_diff(baseline, config, by_id)
    changes = []
    work = copy.deepcopy(baseline)
    prev_w, prev_rd = base_proj.wins, base_proj.run_diff
    for mv in moves:
        _apply_move(work, mv, config)
        pr = _rec(work)
        changes.append({
            "label": mv["label"], "kind": mv["kind"], "slot": mv["slot"],
            "wins": round(pr.wins - prev_w, 2),
            "run_diff": round(pr.run_diff - prev_rd, 1),
        })
        prev_w, prev_rd = pr.wins, pr.run_diff

    return {
        "projection": dataclasses.asdict(cur_proj),
        "baseline": dataclasses.asdict(base_proj),
        "baseline_label": base_label,
        "delta": {
            "wins": round(cur_proj.wins - base_proj.wins, 2),
            "run_diff": round(cur_proj.run_diff - base_proj.run_diff, 1),
            "team_war": round(cur_proj.team_war - base_proj.team_war, 2),
            "bat_runs": round(cur_proj.bat_runs - base_proj.bat_runs, 1),
            "br_runs": round(cur_proj.br_runs - base_proj.br_runs, 1),
            "fld_runs": round(cur_proj.fld_runs - base_proj.fld_runs, 1),
            "pit_runs": round(cur_proj.pit_runs - base_proj.pit_runs, 1),
        },
        "changes": changes,
        "n_changes": len(changes),
    }


def delete_spring_plan(team_id):
    """Remove a team's saved plan. Returns True if one existed."""
    import json
    cfg = get_cfg()
    league_dir = cfg.league_dir
    plans = _load_spring_plans(league_dir)
    if str(team_id) in plans:
        del plans[str(team_id)]
        _spring_plans_path(league_dir).write_text(json.dumps(plans, indent=2) + "\n")
        return True
    return False
