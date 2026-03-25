"""
player_utils.py — Shared player evaluation utilities.
Used by farm_analysis.py, prospect_value.py, contract_value.py, trade_calculator.py, fv_calc.py.
"""

import os, json
from constants import PITCH_FIELDS  # noqa: F401 (re-exported)

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PITCH_NAMES  = {
    "Fst":"Fastball","Snk":"Sinker","Crv":"Curveball","Sld":"Slider",
    "Chg":"Changeup","Splt":"Splitter","Cutt":"Cutter","CirChg":"Circle Change",
    "Scr":"Screwball","Frk":"Forkball","Kncrv":"Knuckle Curve","Knbl":"Knuckleball"
}

# Positional WAR adjustments (runs/year ÷ 10 = WAR/year).
POSITIONAL_WAR_ADJUSTMENTS = {
    "C":   1.2, "SS":  0.7, "2B":  0.3, "CF":  0.25, "3B":  0.2,
    "COF": -0.7, "1B": -1.2, "DH": -1.7, "SP":  0.0,  "RP": -1.0,
}

# Positional defensive weights — position-specific importance of each tool.
# Used by defensive_score() for the anchor bonus.
# Keys match the aliased field names used in fv_calc.py and data.py.
DEFENSIVE_WEIGHTS = {
    "C":      {"CFrm": 0.45, "CBlk": 0.35, "CArm": 0.20},
    "SS":     {"IFR": 0.40, "IFE": 0.20, "IFA": 0.20, "TDP": 0.20},
    "2B":     {"IFR": 0.35, "TDP": 0.30, "IFE": 0.20, "IFA": 0.15},
    "3B":     {"IFA": 0.35, "IFE": 0.30, "IFR": 0.25, "TDP": 0.10},
    "CF":     {"OFR": 0.55, "OFE": 0.25, "OFA": 0.20},
    "COF_LF": {"OFR": 0.50, "OFE": 0.30, "OFA": 0.20},
    "COF_RF": {"OFR": 0.40, "OFA": 0.35, "OFE": 0.25},
}

# Level norm ages (used by calc_fv)
LEVEL_NORM_AGE = {
    "aaa": 26, "aa": 24, "a": 22, "a-short": 21,
    "usl": 19, "dsl": 18, "intl": 17,
}

# ---------------------------------------------------------------------------
# Rating normalization
# ---------------------------------------------------------------------------

_ratings_scale = None  # set by init_ratings_scale() or auto-detected

def init_ratings_scale(scale="1-100"):
    """Set the module-level ratings scale. Called once at startup."""
    global _ratings_scale
    _ratings_scale = scale

def _get_ratings_scale():
    global _ratings_scale
    if _ratings_scale is None:
        from league_config import config
        _ratings_scale = config.ratings_scale
    return _ratings_scale

def norm(raw):
    """Normalize a tool rating to 20-80 scouting scale, rounded to nearest 5.
    On 1-100 leagues: converts via linear mapping.
    On 20-80 leagues: clamps and rounds (values are already on the scouting scale)."""
    if raw is None:
        return None
    try:
        raw = int(raw)
    except (ValueError, TypeError):
        return None
    if raw <= 0:
        return None
    if _get_ratings_scale() == "20-80":
        return max(20, min(80, round(raw / 5) * 5))
    return round((20 + (min(raw, 100) / 100) * 60) / 5) * 5


def height_str(cm):
    """Convert height in cm to feet'inches" string."""
    if not cm:
        return None
    feet = int(cm / 30.48)
    inches = round((cm % 30.48) / 2.54)
    return f"{feet}'{inches}\""


def display_pos(bucket, listed_pos=None):
    """Convert internal bucket to display position. COF -> OF, keep CF distinct."""
    return "OF" if bucket == "COF" else bucket


def fmt_table(headers, values):
    """Format a single-row markdown table with header, separator, and value rows."""
    col_w = [max(len(h), len(v)) for h, v in zip(headers, values)]
    h_row = "| " + " | ".join(h.ljust(w) for h, w in zip(headers, col_w)) + " |"
    s_row = "| " + " | ".join("-" * w for w in col_w) + " |"
    v_row = "| " + " | ".join(v.ljust(w) for v, w in zip(values, col_w)) + " |"
    return "\n".join([h_row, s_row, v_row])


def defensive_score(p, bucket):
    """Weighted defensive score on 20-80 scale for a position bucket.
    Returns the position-weighted average of underlying defensive tools."""
    def _n(val):
        return norm(val) or 0
    if bucket == "COF":
        lf = sum(_n(p.get(f, 0) or 0) * w for f, w in DEFENSIVE_WEIGHTS["COF_LF"].items())
        rf = sum(_n(p.get(f, 0) or 0) * w for f, w in DEFENSIVE_WEIGHTS["COF_RF"].items())
        return max(lf, rf)
    weights = DEFENSIVE_WEIGHTS.get(bucket)
    if not weights:
        return 0
    return sum(_n(p.get(f, 0) or 0) * w for f, w in weights.items())


def _pos_composite(p, bucket, age):
    """Normalized positional composite for defensive bonus (uses Pot grades for age <= 23)."""
    if bucket == "COF":
        return norm(max(p.get("LF", 0), p.get("RF", 0)))
    pot_map = {"C": "PotC", "SS": "PotSS", "CF": "PotCF",
               "2B": "Pot2B", "3B": "Pot3B"}
    cur_map = {"C": "C", "SS": "SS", "CF": "CF", "2B": "2B", "3B": "3B"}
    field = pot_map.get(bucket) if age <= 23 else cur_map.get(bucket)
    if not field:
        return 0
    return norm(p.get(field, 0))

# ---------------------------------------------------------------------------
# Positional bucketing
# ---------------------------------------------------------------------------

def assign_bucket(p, use_pot=None):
    """Assign positional bucket per farm_analysis_guide.md."""
    age = p.get("Age", 99)
    if use_pot is None:
        use_pot = age <= 23

    def pgrade(field):
        key = ("Pot" + field) if use_pot else field
        return p.get(key, 0)

    pos_str  = str(p.get("Pos", ""))
    role_str = str(p.get("_role", ""))
    is_pitcher = (pos_str == "P" or role_str in ("starter", "reliever", "closer"))

    if is_pitcher:
        # For MLB players evaluated on current value (use_pot=False),
        # respect actual deployment role — a reliever is valued as RP
        # regardless of ratings that might suggest SP viability.
        if not use_pot and role_str in ("reliever", "closer"):
            return "RP"
        stm    = p.get("Stm", 0)
        # Knuckleball/knuckle-curve alone qualifies as SP if stamina is sufficient
        if stm >= 40 and (p.get("PotKnbl", 0) >= 45 or p.get("PotKncrv", 0) >= 45):
            return "SP"
        viable = sum(1 for f in PITCH_FIELDS if p.get("Pot" + f, 0) >= 45)
        return "RP" if (viable < 3 or stm < 40) else "SP"

    if pgrade("C")  >= 45:                          return "C"
    if pgrade("SS") >= 50:                          return "SS"
    if pgrade("2B") >= 50 or pgrade("SS") >= 50:   return "2B"
    if pgrade("CF") >= 55:                          return "CF"
    if pgrade("LF") >= 45 or pgrade("RF") >= 45:   return "COF"
    if pgrade("3B") >= 45:                          return "3B"
    if pgrade("1B") >= 45:                          return "1B"
    # Fallback: use listed position if no grade threshold met
    pos_map = {"2": "C", "3": "1B", "4": "2B", "5": "3B", "6": "SS",
               "7": "COF", "8": "CF", "9": "COF", "10": "COF"}
    if pos_str in pos_map:
        return pos_map[pos_str]
    return "COF"

# ---------------------------------------------------------------------------
# FV calculation
# ---------------------------------------------------------------------------

def dev_weight(age, norm_age, level=None):
    diff = norm_age - age
    if diff >= 3:  w = 0.55 if age <= 17 else 0.65
    elif diff >= 1:  w = 0.40 if age <= 17 else 0.50
    elif diff >= -1: w = 0.35
    elif diff >= -2: w = 0.20
    else:            w = 0.10
    # At lower levels, large Ovr-Pot gaps are expected — trust projection more
    low_level = level and level.lower().replace(" ", "-") in ("usl", "dsl", "intl", "rookie", "a-short")
    if low_level:
        w += 0.10
        # Cap weight for Rookie/DSL/Intl — can't be confident in players
        # who haven't faced real competition yet
        if level.lower().replace(" ", "-") in ("usl", "dsl", "intl", "rookie"):
            w = min(w, 0.50)
    return w

def effective_pot(p):
    """Pitcher arsenal ceiling override."""
    pot = p["Pot"]
    if not p.get("_is_pitcher"):
        return pot
    elite = sum(1 for f in PITCH_FIELDS if p.get("Pot" + f, 0) >= 80)
    if elite >= 3: return max(pot, 55)
    if elite >= 2: return max(pot, 50)
    return pot

def versatility_bonus(p):
    """+1 per additional viable position beyond primary, capped at +2. Requires Pot >= 45."""
    if p.get("_is_pitcher") or p["Pot"] < 45:
        return 0
    use_pot = p["Age"] <= 23
    def pgrade(f):
        return p.get(("Pot" + f) if use_pot else f, 0)
    primary = p["_bucket"]
    thresholds = {"C":45,"SS":50,"2B":50,"CF":55,"LF":45,"RF":45,"3B":45,"1B":45}
    bucket_map = {"C":"C","SS":"SS","2B":"2B","CF":"CF","LF":"COF","RF":"COF","3B":"3B","1B":"1B"}
    extra = sum(1 for pos, thr in thresholds.items()
                if bucket_map[pos] != primary and pgrade(pos) >= thr)
    return min(extra, 2)

def calc_fv(p):
    """
    Compute FV for a prospect. Player dict must have:
      Ovr, Pot, Age, _is_pitcher, _bucket, _norm_age
    Returns (fv_base: int, fv_plus: bool).
    """
    ovr  = p["Ovr"]
    pot  = effective_pot(p)
    age, norm_age = p["Age"], p["_norm_age"]
    bucket = p["_bucket"]

    # RP positional discount — RPs produce less WAR per FV grade than other
    # positions. Scale Pot down so only elite RPs earn high FV grades.
    # 0.80 factor calibrated to produce ~5% RP share in top prospect lists,
    # matching real-baseball norms. Elite RPs (Pot 70+) still reach FV 50.
    if bucket == "RP":
        pot = round(pot * 0.80)

    dw   = dev_weight(age, norm_age, level=p.get("_level"))
    fv   = ovr + (pot - ovr) * dw

    if pot >= 45:
        # Unified defensive bonus: composite-driven base + weighted score modifier
        comp = _pos_composite(p, bucket, age) or 0
        if comp >= 60:
            wt = defensive_score(p, bucket)
            if comp >= 70:
                db = 3 if wt >= 65 else 2 if wt >= 55 else 1
            else:
                db = 2 if wt >= 65 else 1 if wt >= 55 else 0
            fv = min(fv + db, pot)
        vb = versatility_bonus(p)
        if vb:
            fv = min(fv + vb, pot + 5)
        we = p.get("WrkEthic", "N")
        if we in ("H", "VH"): fv += 1
        elif we == "L":        fv -= 1

    if bucket == "RP":
        fv = min(fv, 50)

    if p.get("Acc") == "L":
        fv -= 2

    # Critical tool floor penalty — a prospect with a fatally weak key tool
    # cannot reach their ceiling regardless of other grades.
    # Pitchers: control (pot_ctrl). Hitters: contact (pot_cntct).
    # Threshold: normalized potential grade <= 35 (raw <= ~25).
    # Penalty scales: -3 FV at 35, -5 FV at 30 or below.
    if p.get("_is_pitcher"):
        for field in ("PotCtrl", "PotMov"):
            val = norm(p.get(field, 100))
            if val <= 30:
                fv -= 5
            elif val <= 35:
                fv -= 3
    else:
        crit = norm(p.get("PotCntct", 100))
        if crit <= 30:
            fv -= 5
        elif crit <= 35:
            fv -= 3

    # Platoon split penalty — a prospect with a severe weak side is a platoon
    # player (hitter) or gets exposed against one handedness (pitcher).
    # Only applies when split data exists and the weak side is exploitable.
    # Thresholds on 20-80 scale: weak <= 25, gap >= 10 (2 grades) or >= 15 (3 grades).
    if p.get("_is_pitcher"):
        sl, sr = norm(p.get("Stf_L", 0) or 0), norm(p.get("Stf_R", 0) or 0)
        if sl and sr:
            gap = abs(sl - sr)
            weak = min(sl, sr)
            if weak <= 25 and gap >= 15:
                fv -= 3
            elif weak <= 25 and gap >= 10:
                fv -= 2
    else:
        cl, cr = norm(p.get("Cntct_L", 0) or 0), norm(p.get("Cntct_R", 0) or 0)
        if cl and cr:
            gap = abs(cl - cr)
            weak = min(cl, cr)
            if weak <= 25 and gap >= 15:
                fv -= 3
            elif weak <= 25 and gap >= 10:
                fv -= 2

    base = round(fv / 5) * 5
    remainder = fv - base
    plus = remainder >= 2.0 or ((pot - base) >= 10 and age <= norm_age)
    return base, plus

# ---------------------------------------------------------------------------
# WAR estimation (used by contract_value.py and fv_calc.py)
# ---------------------------------------------------------------------------

from constants import OVR_TO_WAR, OVR_TO_WAR_CALIBRATED, AGING_HITTER, AGING_PITCHER  # noqa: F401 (re-exported)


def _interp(table_rows, value, col_idx):
    for i in range(len(table_rows) - 1):
        v0, v1 = table_rows[i][0], table_rows[i+1][0]
        if v1 <= value <= v0:
            t = (value - v1) / (v0 - v1)
            return table_rows[i+1][col_idx] + t * (table_rows[i][col_idx] - table_rows[i+1][col_idx])
    if value >= table_rows[0][0]: return table_rows[0][col_idx]
    return table_rows[-1][col_idx]


def _interp_dict(tbl, ovr):
    """Interpolate from a {ovr: war} dict (calibrated tables)."""
    pts = sorted(tbl.keys())
    if ovr >= pts[-1]:
        return tbl[pts[-1]]
    if ovr <= pts[0]:
        return tbl[pts[0]]
    for i in range(len(pts) - 1):
        if pts[i] <= ovr <= pts[i + 1]:
            t = (ovr - pts[i]) / (pts[i + 1] - pts[i])
            return tbl[pts[i]] + t * (tbl[pts[i + 1]] - tbl[pts[i]])
    return tbl[pts[0]]


def peak_war_from_ovr(ovr, bucket):
    # Use position-specific calibrated table when available
    if OVR_TO_WAR_CALIBRATED and bucket in OVR_TO_WAR_CALIBRATED:
        return _interp_dict(OVR_TO_WAR_CALIBRATED[bucket], ovr)
    # Fallback: generic 3-column table
    col = 2 if bucket == "SP" else (3 if bucket == "RP" else 1)
    return _interp(OVR_TO_WAR, ovr, col)


def aging_mult(age, bucket):
    table = AGING_PITCHER if bucket in ("SP", "RP") else AGING_HITTER
    ages  = sorted(table)
    if age <= ages[0]:  return 1.0
    if age >= ages[-1]: return table[ages[-1]]
    for i in range(len(ages) - 1):
        a0, a1 = ages[i], ages[i+1]
        if a0 <= age <= a1:
            t = (age - a0) / (a1 - a0)
            return table[a0] + t * (table[a1] - table[a0])
    return 0.35

# ---------------------------------------------------------------------------
# League settings
# ---------------------------------------------------------------------------

def load_league_settings():
    from league_config import config
    return config.settings

def league_minimum():
    from league_config import config
    return config.minimum_salary

def dollars_per_war():
    from league_context import get_league_dir
    path = get_league_dir() / "config" / "league_averages.json"
    if path.exists():
        with open(path) as f:
            data = json.load(f)
        if "dollar_per_war" in data:
            return data["dollar_per_war"]
    return 9_500_000


# ---------------------------------------------------------------------------
# Stat history helpers — shared by fv_calc.py and contract_value.py
# ---------------------------------------------------------------------------

def load_stat_history(conn, game_date):
    """Load completed-season stats into memory. Excludes current game year (partial season).
    Aggregates across teams for traded players. Uses stint to detect incomplete split seasons."""
    game_year = int(game_date[:4])

    bat_rows = conn.execute(
        """SELECT player_id, year, SUM(war) as war, SUM(ab) as ab,
                  MAX(stint) as max_stint, COUNT(team_id) as team_count
           FROM batting_stats WHERE split_id=1 AND year < ?
           GROUP BY player_id, year""",
        (game_year,)
    ).fetchall()
    pit_rows = conn.execute(
        """SELECT player_id, year,
                  SUM((war + COALESCE(ra9war, war)) / 2.0) as war,
                  SUM(gs) as gs, SUM(ip) as ip,
                  MAX(stint) as max_stint, COUNT(team_id) as team_count
           FROM pitching_stats WHERE split_id=1 AND year < ?
           GROUP BY player_id, year""",
        (game_year,)
    ).fetchall()

    bat_hist = {}
    for r in bat_rows:
        if (r["ab"] or 0) < 130:
            continue
        incomplete = (r["max_stint"] == 1 and r["team_count"] == 1)
        bat_hist.setdefault(r["player_id"], []).append({
            "year": r["year"], "war": r["war"] or 0, "incomplete": incomplete
        })

    pit_hist = {}
    for r in pit_rows:
        gs = r["gs"] or 0
        incomplete = (r["max_stint"] == 1 and r["team_count"] == 1)
        pit_hist.setdefault(r["player_id"], []).append({
            "year": r["year"], "war": r["war"] or 0, "is_sp": gs >= 10,
            "incomplete": incomplete
        })

    two_way = set()
    bat_by_year = {}
    for r in bat_rows:
        if (r["ab"] or 0) >= 130:
            bat_by_year.setdefault(r["player_id"], set()).add(r["year"])
    for r in pit_rows:
        if (r["gs"] or 0) >= 10:
            pid = r["player_id"]
            if pid in bat_by_year and r["year"] in bat_by_year[pid]:
                two_way.add(pid)

    for d in (bat_hist, pit_hist):
        for pid in d:
            d[pid].sort(key=lambda x: x["year"], reverse=True)

    return bat_hist, pit_hist, two_way


def stat_peak_war(pid, bucket, bat_hist, pit_hist, two_way=None):
    """3-year weighted WAR average for role-consistent seasons. Returns None if insufficient.
    Incomplete seasons (traded, only one team's data) are downweighted by 0.5.
    For two-way players, sums batting + pitching WAR per year."""
    if two_way and pid in two_way:
        return _two_way_peak_war(pid, bucket, bat_hist, pit_hist)

    role_changed = False
    if bucket in ("SP", "RP"):
        is_sp = bucket == "SP"
        seasons = [s for s in pit_hist.get(pid, []) if s["is_sp"] == is_sp]
        # Role-change fallback: if no qualifying seasons in current role,
        # use the other pitcher role's stats, scaled by IP ratio (SP~140ip, RP~65ip).
        if not seasons:
            seasons = [s for s in pit_hist.get(pid, []) if s["is_sp"] != is_sp]
            role_changed = bool(seasons)
    else:
        seasons = bat_hist.get(pid, [])

    if len(seasons) < 1:
        return None
    weights = [3, 2, 1][:len(seasons)]
    effective_wars = [s["war"] / (0.5 if s.get("incomplete") else 1.0) for s in seasons]
    result = sum(w * ew for w, ew in zip(weights, effective_wars)) / sum(weights)
    # Scale for role change: SP→RP reduces WAR (fewer IP), RP→SP increases it.
    if role_changed:
        result *= 0.46 if bucket == "RP" else 2.15  # ~65ip/140ip and inverse
    return result


def _two_way_peak_war(pid, bucket, bat_hist, pit_hist):
    """Combined batting + pitching WAR for two-way players, keyed by year.
    No incomplete adjustment — two-way players have full-season data on both sides."""
    bat_by_yr = {s["year"]: s["war"] for s in bat_hist.get(pid, [])}
    pit_by_yr = {s["year"]: s["war"] for s in pit_hist.get(pid, [])}
    years = sorted(set(bat_by_yr) | set(pit_by_yr), reverse=True)
    if len(years) < 1:
        return None
    combined = [bat_by_yr.get(y, 0) + pit_by_yr.get(y, 0) for y in years[:3]]
    weights = [3, 2, 1][:len(combined)]
    return sum(w * c for w, c in zip(weights, combined)) / sum(weights)


# ── PAP (Payroll Adjusted Performance) ──────────────────────────────────
from math import tanh
from constants import _w as _cw

def calc_pap(war, salary, team_games, dpw):
    """PAP from actual production. war=season WAR so far, salary=annual,
    team_games=team GP this season, dpw=$/WAR."""
    if war is None or team_games is None or team_games < 5:
        return None
    annualized = war * (162 / team_games)
    surplus = annualized * dpw - salary
    scale = _cw("PAP_SCALE", 25_000_000)
    return round(5 + 5 * tanh(surplus / scale), 2)
