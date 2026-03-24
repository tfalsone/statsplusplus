"""DB queries for the web dashboard — state helpers and league-level queries.

Team queries: web/team_queries.py
Player queries: web/player_queries.py
Percentiles: web/percentiles.py
"""

import os, sys, json

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "scripts"))
from player_utils import display_pos as _display_pos
from web_league_context import get_db, get_cfg, team_abbr_map, team_names_map, pos_order, year, mlb_team_ids

ROLE_MAP = {11: "SP", 12: "RP", 13: "CL"}

# Legacy module-level aliases — used by app.py and re-export consumers.
# These are properties that re-evaluate each access via get_cfg().
class _DynMap:
    """Lazy proxy so `queries.TEAM_NAMES[tid]` still works in request context."""
    def __init__(self, fn): self._fn = fn
    def get(self, k, d=None): return self._fn().get(k, d)
    def __getitem__(self, k): return self._fn()[k]
    def __contains__(self, k): return k in self._fn()
    def keys(self): return self._fn().keys()
    def values(self): return self._fn().values()
    def items(self): return self._fn().items()

TEAM_ABBR = _DynMap(team_abbr_map)
TEAM_NAMES = _DynMap(team_names_map)


# ── state helpers ────────────────────────────────────────────────────────

def get_state(force=False):
    cfg = get_cfg()
    if force:
        cfg.reload()
    with open(cfg.state_path) as f:
        return json.load(f)


def get_my_team_id():
    return get_cfg().my_team_id


def get_my_team_abbr():
    cfg = get_cfg()
    return cfg.team_abbr(cfg.my_team_id)


def set_my_team(team_id):
    cfg = get_cfg()
    state = get_state()
    state["my_team_id"] = team_id
    with open(cfg.state_path, "w") as f:
        json.dump(state, f, indent=2)
        f.write("\n")
    cfg.reload()


# ── league-level queries ────────────────────────────────────────────────

_ETA_BASE = {"MLB": 0, "AAA": 1, "AA": 2, "A": 3,
             "A-Short": 4, "Rookie": 4, "USL": 5, "DSL": 5, "Intl": 5}

def _calc_eta(level, ovr, pot):
    """ETA in calendar year. Pull forward if Ovr already MLB-viable (≥45)."""
    base = _ETA_BASE.get(level, 3)
    if ovr and ovr >= 45 and base > 0:
        base = max(base - 1, 0)
    return year() + base

def get_top_prospects(n=100):
    conn = get_db()
    conn.row_factory = None
    ed = conn.execute("SELECT MAX(eval_date) FROM prospect_fv").fetchone()[0]

    _abbr = team_abbr_map()
    _names = team_names_map()
    _po = pos_order()
    mlb_tids = mlb_team_ids()
    rows = conn.execute("""
        SELECT p.name, p.age, p.parent_team_id, pf.fv, pf.fv_str, pf.bucket,
               pf.level, pf.prospect_surplus, p.pos, p.player_id,
               r.height, r.bats, r.throws, r.ovr, r.pot
        FROM prospect_fv pf
        JOIN players p ON pf.player_id=p.player_id
        LEFT JOIN latest_ratings r ON pf.player_id=r.player_id
        WHERE pf.eval_date=? AND pf.level != 'MLB'
    """, (ed,)).fetchall()

    rows = [r for r in rows if r[2] in mlb_tids]

    def sort_key(r):
        fv_val = r[3] + (0.1 if r[4].endswith("+") else 0)
        return (-fv_val, -(r[7] or 0))

    rows = sorted(rows, key=sort_key)[:n]

    def fmt_ht(cm):
        if not cm: return ""
        ft = int(cm / 30.48)
        inch = round((cm % 30.48) / 2.54)
        return f"{ft}'{inch}\""

    return [{"rank": i + 1, "name": r[0], "age": r[1],
             "team": _abbr.get(r[2], "FA"), "tid": r[2],
             "team_name": _names.get(r[2], ""),
             "fv": r[3], "fv_str": r[4],
             "bucket": _display_pos(r[5], r[8]), "level": r[6],
             "pos_order": _po.get(_display_pos(r[5], r[8]), 99),
             "surplus": round(r[7] / 1e6, 1) if r[7] else 0,
             "pid": r[9],
             "eta": _calc_eta(r[6], r[13], r[14]),
             "height": fmt_ht(r[10]),
             "bats": r[11] or "", "throws": r[12] or ""}
            for i, r in enumerate(rows)]


def _build_league_team_sets():
    """Build team sets per league dynamically from config.leagues."""
    cfg = get_cfg()
    result = {}
    for lg in cfg.leagues:
        tids = set()
        for div_tids in lg["divisions"].values():
            tids.update(div_tids)
        result[lg["short"]] = tids
    return result


def _build_batting_leaders(rows, pa_qual, n=5):
    """Build stat leader panels from a list of batting rows."""
    _abbr = team_abbr_map()
    def top(rows, key, fmt, n=n, low=False, qual=False):
        pool = [(r, key(r)) for r in rows if key(r) is not None and (not qual or (r[12] or 0) >= pa_qual)]
        pool.sort(key=lambda x: x[1], reverse=not low)
        return [{"pid": r[0], "name": r[1], "team": _abbr.get(r[2], "?"),
                 "tid": r[2], "val": fmt(v)} for r, v in pool[:n]]
    return {
        "AVG": top(rows, lambda r: r[4]/r[3] if r[3] else None, lambda v: f"{v:.3f}", qual=True),
        "HR":  top(rows, lambda r: r[7], str),
        "RBI": top(rows, lambda r: r[8], str),
        "SB":  top(rows, lambda r: r[11], str),
        "OPS": top(rows, lambda r: ((r[4]+r[9]+(r[15] or 0))/r[12] + (r[4]+r[5]+2*r[6]+3*r[7])/r[3]) if r[3] and r[12] and (r[12] or 0) >= pa_qual else None,
                    lambda v: f"{v:.3f}", qual=True),
        "WAR": top(rows, lambda r: r[13], lambda v: f"{v:.1f}"),
    }


def get_batting_leaders(yr=None, min_pa=50):
    """Top 5 per stat, keyed by 'All' + each league short name."""
    yr = yr or year()
    conn = get_db()
    conn.row_factory = None
    tip = conn.execute("SELECT AVG(ip) FROM team_pitching_stats WHERE year=? AND split_id=1",
                       (yr,)).fetchone()
    team_g = round(tip[0] / 9) if tip and tip[0] else 0
    pa_qual = round(3.1 * team_g)
    rows = conn.execute("""
        SELECT p.player_id, p.name, p.team_id,
               b.ab, b.h, b.d, b.t, b.hr, b.rbi, b.bb, b.k, b.sb, b.pa, b.war, b.r, b.hbp
        FROM batting_stats b JOIN players p ON b.player_id=p.player_id
        WHERE b.year=? AND b.split_id=1 AND b.pa >= ?
        ORDER BY b.war DESC
    """, (yr, min_pa)).fetchall()
    league_sets = _build_league_team_sets()
    result = {"All": _build_batting_leaders(rows, pa_qual)}
    for lg_short, tids in league_sets.items():
        result[lg_short] = _build_batting_leaders([r for r in rows if r[2] in tids], pa_qual)
    return result


def _build_pitching_leaders(rows, ip_qual, n=5):
    """Build stat leader panels from a list of pitching rows."""
    _abbr = team_abbr_map()
    ip_ok = lambda r: (r[3] or 0) >= ip_qual
    def top(rows, key, fmt, n=n, low=False, qual=False):
        pool = [(r, key(r)) for r in rows if key(r) is not None and (not qual or ip_ok(r))]
        pool.sort(key=lambda x: x[1], reverse=not low)
        return [{"pid": r[0], "name": r[1], "team": _abbr.get(r[2], "?"),
                 "tid": r[2], "val": fmt(v)} for r, v in pool[:n]]
    return {
        "ERA":  top(rows, lambda r: r[4] if ip_ok(r) else None, lambda v: f"{v:.2f}", low=True, qual=True),
        "W":    top(rows, lambda r: r[7], str),
        "K":    top(rows, lambda r: r[5], str),
        "SV":   top(rows, lambda r: r[9] if r[9] else None, str),
        "WHIP": top(rows, lambda r: (r[6]+r[11])/r[3] if ip_ok(r) and r[3] else None,
                     lambda v: f"{v:.2f}", low=True, qual=True),
        "WAR":  top(rows, lambda r: r[10], lambda v: f"{v:.1f}"),
    }


def get_pitching_leaders(yr=None, min_ip=10):
    """Top 5 per stat, keyed by 'All' + each league short name."""
    yr = yr or year()
    conn = get_db()
    conn.row_factory = None
    tip = conn.execute("SELECT AVG(ip) FROM team_pitching_stats WHERE year=? AND split_id=1",
                       (yr,)).fetchone()
    team_g = round(tip[0] / 9) if tip and tip[0] else 0
    ip_qual = round(1.0 * team_g)
    rows = conn.execute("""
        SELECT p.player_id, p.name, p.team_id,
               ps.ip, ps.era, ps.k, ps.bb, ps.w, ps.l, ps.sv, ps.war, ps.ha, ps.hld
        FROM pitching_stats ps JOIN players p ON ps.player_id=p.player_id
        WHERE ps.year=? AND ps.split_id=1 AND ps.ip >= ?
        ORDER BY ps.war DESC
    """, (yr, min_ip)).fetchall()
    league_sets = _build_league_team_sets()
    result = {"All": _build_pitching_leaders(rows, ip_qual)}
    for lg_short, tids in league_sets.items():
        result[lg_short] = _build_pitching_leaders([r for r in rows if r[2] in tids], ip_qual)
    return result


def get_all_prospects():
    """All FV≥40 prospects for by-team/by-position views."""
    conn = get_db()
    conn.row_factory = None
    ed = conn.execute("SELECT MAX(eval_date) FROM prospect_fv").fetchone()[0]

    _abbr = team_abbr_map()
    _names = team_names_map()
    _po = pos_order()
    mlb_tids = mlb_team_ids()
    rows = conn.execute("""
        SELECT p.name, p.age, p.parent_team_id, pf.fv, pf.fv_str, pf.bucket,
               pf.level, pf.prospect_surplus, p.pos, p.player_id,
               r.height, r.bats, r.throws, r.ovr, r.pot
        FROM prospect_fv pf
        JOIN players p ON pf.player_id=p.player_id
        LEFT JOIN latest_ratings r ON pf.player_id=r.player_id
        WHERE pf.eval_date=? AND pf.level != 'MLB' AND pf.fv >= 40
    """, (ed,)).fetchall()

    rows = [r for r in rows if r[2] in mlb_tids]

    def sort_key(r):
        fv_val = r[3] + (0.1 if r[4].endswith("+") else 0)
        return (-fv_val, -(r[7] or 0))

    rows = sorted(rows, key=sort_key)

    def fmt_ht(cm):
        if not cm: return ""
        ft = int(cm / 30.48)
        inch = round((cm % 30.48) / 2.54)
        return f"{ft}'{inch}\""

    return [{"name": r[0], "age": r[1],
             "team": _abbr.get(r[2], "FA"), "tid": r[2],
             "team_name": _names.get(r[2], ""),
             "fv": r[3], "fv_str": r[4],
             "bucket": _display_pos(r[5], r[8]), "level": r[6],
             "pos_order": _po.get(_display_pos(r[5], r[8]), 99),
             "surplus": round(r[7] / 1e6, 1) if r[7] else 0,
             "pid": r[9],
             "eta": _calc_eta(r[6], r[13], r[14]),
             "height": fmt_ht(r[10]),
             "bats": r[11] or "", "throws": r[12] or ""}
            for r in rows]


def get_prospect_summary(pid):
    """Prospect side-panel data: ratings, FV, surplus, scouting summary."""
    conn = get_db()
    conn.row_factory = None
    ed = conn.execute("SELECT MAX(eval_date) FROM prospect_fv").fetchone()[0]

    pf = conn.execute("""
        SELECT pf.fv, pf.fv_str, pf.bucket, pf.level, pf.prospect_surplus,
               p.name, p.age, p.parent_team_id, p.role
        FROM prospect_fv pf JOIN players p ON pf.player_id=p.player_id
        WHERE pf.eval_date=? AND pf.player_id=?
    """, (ed, pid)).fetchone()
    if not pf:
        return None

    fv, fv_str, bucket, level, surplus, name, age, tid, role = pf

    r = conn.execute("SELECT * FROM latest_ratings WHERE player_id=?", (pid,)).fetchone()
    if not r:
        return None
    cols = [d[0] for d in conn.execute("SELECT * FROM latest_ratings LIMIT 0").description]
    rd = dict(zip(cols, r))

    def n80(v):
        if not v: return 20
        return round((20 + (v / 100) * 60) / 5) * 5

    is_pitcher = bucket in ('SP', 'RP')

    ovr_val = rd.get("ovr")
    pot_val = rd.get("pot")

    out = {
        "pid": pid, "name": name, "age": age, "bucket": bucket, "level": level,
        "team": TEAM_ABBR.get(tid, "FA"), "team_name": TEAM_NAMES.get(tid, ""),
        "fv": fv, "fv_str": fv_str,
        "surplus": round(surplus / 1e6, 1) if surplus else 0,
        "eta": _calc_eta(level, ovr_val, pot_val),
        "ovr": ovr_val, "pot": pot_val,
        "height": _fmt_ht(rd.get("height")),
        "bats": rd.get("bats", ""), "throws": rd.get("throws", ""),
    }

    if is_pitcher:
        ctrl_r, ctrl_l = rd.get("ctrl_r", 0) or 0, rd.get("ctrl_l", 0) or 0
        ctrl = rd.get("ctrl") or (round((ctrl_r + ctrl_l) / 2) if ctrl_r and ctrl_l else ctrl_r or ctrl_l)
        out["tools"] = [
            {"name": "Stuff", "cur": n80(rd.get("stf")), "fut": n80(rd.get("pot_stf"))},
            {"name": "Movement", "cur": n80(rd.get("mov")), "fut": n80(rd.get("pot_mov"))},
            {"name": "Control", "cur": n80(ctrl), "fut": n80(rd.get("pot_ctrl"))},
        ]
        if rd.get("hra") is not None:
            out["tools"].insert(2, {"name": "HR Allow", "cur": n80(rd["hra"]), "fut": n80(rd.get("pot_hra"))})
        if rd.get("pbabip") is not None:
            out["tools"].insert(3 if rd.get("hra") is not None else 2,
                                {"name": "BABIP Allow", "cur": n80(rd["pbabip"]), "fut": n80(rd.get("pot_pbabip"))})
        if rd.get("stm"):
            out["tools"].append({"name": "Stamina", "cur": n80(rd["stm"]), "fut": None})
        if rd.get("vel"):
            out["velocity"] = rd["vel"]
        # Top pitches (up to 4, sorted by current grade)
        pitch_map = [
            ("fst", "Fastball"), ("snk", "Sinker"), ("crv", "Curveball"),
            ("sld", "Slider"), ("chg", "Changeup"), ("splt", "Splitter"),
            ("cutt", "Cutter"), ("cir_chg", "Circle Change"), ("scr", "Screwball"),
            ("frk", "Forkball"), ("kncrv", "Knuckle Curve"), ("knbl", "Knuckleball"),
        ]
        pitches = []
        for col, label in pitch_map:
            cur, fut = rd.get(col), rd.get(f"pot_{col}")
            if cur or fut:
                pitches.append({"name": label, "cur": n80(cur), "fut": n80(fut)})
        pitches.sort(key=lambda x: -(x["cur"] or 0))
        out["pitches"] = pitches[:5]
    else:
        out["tools"] = [
            {"name": "Hit", "cur": n80(rd.get("cntct")), "fut": n80(rd.get("pot_cntct"))},
            {"name": "Gap", "cur": n80(rd.get("gap")), "fut": n80(rd.get("pot_gap"))},
            {"name": "Power", "cur": n80(rd.get("pow")), "fut": n80(rd.get("pot_pow"))},
            {"name": "Eye", "cur": n80(rd.get("eye")), "fut": n80(rd.get("pot_eye"))},
            {"name": "K-Rate", "cur": n80(rd.get("ks")), "fut": n80(rd.get("pot_ks"))},
        ]
        if rd.get("babip") is not None:
            out["tools"].insert(5, {"name": "BABIP", "cur": n80(rd["babip"]), "fut": n80(rd.get("pot_babip"))})
        out["tools"].append({"name": "Speed", "cur": n80(rd.get("speed")), "fut": None})
        # Primary defense grade for bucket
        def_map = {"C": "c", "1B": "first_b", "2B": "second_b", "3B": "third_b",
                    "SS": "ss", "LF": "lf", "CF": "cf", "RF": "rf"}
        # Show all viable positions
        defense = []
        for pos_lbl, col in def_map.items():
            cur = rd.get(col)
            fut = rd.get(f"pot_{col}")
            if cur and cur >= 20:
                defense.append({"pos": pos_lbl, "cur": n80(cur), "fut": n80(fut)})
        defense.sort(key=lambda x: -(x["cur"] or 0))
        out["defense"] = defense

    # Scouting summary
    import json as _json
    try:
        league_dir = get_cfg().league_dir
        with open(os.path.join(str(league_dir), "history", "prospects.json")) as f:
            pros = _json.load(f)
        entry = pros.get(str(pid))
        if entry and entry.get("summary"):
            out["summary"] = entry["summary"]
    except (FileNotFoundError, _json.JSONDecodeError):
        pass

    return out


def _fmt_ht(cm):
    if not cm: return ""
    ft = int(cm / 30.48)
    inch = round((cm % 30.48) / 2.54)
    return f"{ft}'{inch}\""


# ── re-exports from extracted modules ───────────────────────────────────

from team_queries import (get_summary, get_standings, get_division_standings,
                          get_roster, get_farm, get_team_stats, get_contracts,
                          get_roster_summary, get_upcoming_fa, get_surplus_leaders,
                          get_age_distribution, get_farm_depth, get_stat_leaders,
                          get_power_rankings, get_recent_games, get_payroll_summary,
                          get_record_breakdown, get_depth_chart,
                          get_roster_hitters, get_roster_pitchers,
                          get_org_overview)
from player_queries import get_player
from percentiles import get_hitter_percentiles, get_pitcher_percentiles
