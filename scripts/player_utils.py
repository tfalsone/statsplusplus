"""
player_utils.py — Shared player evaluation utilities.

Rating normalization, positional bucketing, display helpers, league settings,
and PAP calculation. Imports and re-exports from fv_model and war_model for
backward compatibility.

Used by farm_analysis.py, prospect_value.py, contract_value.py, trade_calculator.py, fv_calc.py.
"""

import os, json
from constants import PITCH_FIELDS, RP_POT_DISCOUNT  # noqa: F401 (re-exported)

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---------------------------------------------------------------------------
# Constants (re-exported for backward compat)
# ---------------------------------------------------------------------------

PITCH_NAMES = {
    "Fst":"Fastball","Snk":"Sinker","Crv":"Curveball","Sld":"Slider",
    "Chg":"Changeup","Splt":"Splitter","Cutt":"Cutter","CirChg":"Circle Change",
    "Scr":"Screwball","Frk":"Forkball","Kncrv":"Knuckle Curve","Knbl":"Knuckleball"
}

POSITIONAL_WAR_ADJUSTMENTS = {
    "C":   1.2, "SS":  0.7, "2B":  0.3, "CF":  0.25, "3B":  0.2,
    "COF": -0.7, "1B": -1.2, "DH": -1.7, "SP":  0.0,  "RP": -1.0,
}

# ---------------------------------------------------------------------------
# Rating normalization — re-exported from ratings.py for backward compatibility
# ---------------------------------------------------------------------------
from ratings import (  # noqa: F401
    norm, norm_floor, get_ratings_scale, init_ratings_scale,
    _get_ratings_scale  # kept for any legacy internal callers
)


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

def assign_bucket(p, use_pot=None):
    """Assign positional bucket per farm_analysis_guide.md."""
    age = p.get("Age", 99)
    if use_pot is None:
        use_pot = age <= 23

    def pgrade(field):
        key = ("Pot" + field) if use_pot else field
        v = p.get(key, 0)
        if isinstance(v, (int, float)):
            return v
        try:
            return int(v)
        except (ValueError, TypeError):
            return 0

    pos_str  = str(p.get("Pos", ""))
    role_str = str(p.get("_role", ""))
    is_pitcher = (pos_str == "P" or role_str in ("starter", "reliever", "closer"))

    if is_pitcher:
        # For MLB players evaluated on current value (use_pot=False),
        # respect actual deployment role — a reliever is valued as RP
        # regardless of ratings that might suggest SP viability.
        if not use_pot and role_str in ("reliever", "closer"):
            return "RP"
        stm    = p.get("Stm") or 0
        # Knuckleball/knuckle-curve alone qualifies as SP if stamina is sufficient
        if stm >= 40 and ((p.get("PotKnbl") or 0) >= 45 or (p.get("PotKncrv") or 0) >= 45):
            return "SP"
        viable = sum(1 for f in PITCH_FIELDS if (p.get("Pot" + f) or 0) >= 45)
        return "RP" if (viable < 3 or stm < 40) else "SP"

    if pgrade("C")  >= 45:                          return "C"
    if pgrade("SS") >= 50:
        # Check if player would be more valuable at a less premium position.
        # A borderline SS (50-55) with much better 3B/2B defense will produce
        # more WAR at the alternative position despite the positional downgrade.
        ss_grade = pgrade("SS")
        if ss_grade <= 55:
            if pgrade("3B") >= ss_grade + 10:       return "3B"
            if pgrade("2B") >= ss_grade + 10:       return "2B"
        return "SS"
    if pgrade("2B") >= 50 or pgrade("SS") >= 50:   return "2B"
    if pgrade("CF") >= 55:
        # Same logic: borderline CF with much better corner OF defense
        cf_grade = pgrade("CF")
        if cf_grade <= 55:
            best_cof = max(pgrade("LF"), pgrade("RF"))
            if best_cof >= cf_grade + 10:           return "COF"
        return "CF"
    if pgrade("LF") >= 45 or pgrade("RF") >= 45:   return "COF"
    if pgrade("3B") >= 45:                          return "3B"
    if pgrade("1B") >= 45:                          return "1B"
    # Fallback: use listed position if no grade threshold met, but validate
    # that the player has the athleticism to actually play there.
    pos_map = {"2": "C", "3": "1B", "4": "2B", "5": "3B", "6": "SS",
               "7": "COF", "8": "CF", "9": "COF", "10": "COF"}
    fallback = pos_map.get(pos_str, "COF")
    # Downgrade to 1B if athleticism clearly doesn't support the listed position
    ifr = p.get("IFR") or 0
    spd = p.get("Speed") or 0
    ofr = p.get("OFR") or 0
    if fallback in ("SS", "2B") and ifr and ifr < 50:
        fallback = "1B"
    elif fallback == "3B" and ifr and ifr < 40:
        fallback = "1B"
    elif fallback in ("CF", "COF") and ofr and ofr < 40 and spd and spd < 40:
        fallback = "1B"
    return fallback

# ---------------------------------------------------------------------------
# FV calculation — re-exported from fv_model for backward compatibility
# ---------------------------------------------------------------------------
from fv_model import (  # noqa: F401
    calc_fv, dev_weight, age_development_mult,
    defensive_score, LEVEL_NORM_AGE, DEFENSIVE_WEIGHTS
)

# ---------------------------------------------------------------------------
# WAR estimation — re-exported from war_model for backward compatibility
# ---------------------------------------------------------------------------
from war_model import (  # noqa: F401
    peak_war_from_ovr, aging_mult, load_stat_history, stat_peak_war
)
from constants import OVR_TO_WAR, OVR_TO_WAR_CALIBRATED, AGING_HITTER, AGING_PITCHER, PEAK_AGE_PITCHER, PEAK_AGE_HITTER  # noqa: F401

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
    from constants import DEFAULT_DOLLARS_PER_WAR, DEFAULT_MINIMUM_SALARY
    path = get_league_dir() / "config" / "league_averages.json"
    if path.exists():
        with open(path) as f:
            data = json.load(f)
        if "dollar_per_war" in data:
            return data["dollar_per_war"]
    # Scale default by league salary level when no calibrated value exists
    min_sal = league_minimum()
    if min_sal and min_sal != DEFAULT_MINIMUM_SALARY:
        return round(DEFAULT_DOLLARS_PER_WAR * min_sal / DEFAULT_MINIMUM_SALARY)
    return DEFAULT_DOLLARS_PER_WAR


# ---------------------------------------------------------------------------
# Stat history helpers — re-exported from war_model for backward compatibility
# ---------------------------------------------------------------------------
# (already re-exported above via war_model import)

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
