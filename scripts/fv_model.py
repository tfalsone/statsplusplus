"""
fv_model.py — Prospect FV grade calculation.

Computes FV grades from player ratings dicts. Used by fv_calc.py and farm_analysis.py.
All functions are pure (no DB access).

Public API:
  calc_fv(p)            → (fv_base: int, fv_plus: bool)
  dev_weight(age, norm_age, level) → float
  effective_pot(p)      → int
  versatility_bonus(p)  → int
  defensive_score(p, bucket) → float
"""

from constants import PITCH_FIELDS, RP_POT_DISCOUNT
from ratings import norm, norm_floor

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Positional access premium parameters — premium positions where adequate
# defense enables a positional value premium that scales with offensive grade.
POSITIONAL_ACCESS = {
    "SS": {"access_threshold": 50, "base_premium": 2.0, "offense_scale": 0.06},
    "C":  {"access_threshold": 50, "base_premium": 1.5, "offense_scale": 0.05},
    "CF": {"access_threshold": 50, "base_premium": 1.5, "offense_scale": 0.05},
}

# Positional defensive weights — position-specific importance of each tool.
DEFENSIVE_WEIGHTS = {
    "C":      {"CFrm": 0.45, "CBlk": 0.35, "CArm": 0.20},
    "SS":     {"IFR": 0.40, "IFE": 0.20, "IFA": 0.20, "TDP": 0.20},
    "2B":     {"IFR": 0.35, "TDP": 0.30, "IFE": 0.20, "IFA": 0.15},
    "3B":     {"IFA": 0.35, "IFE": 0.30, "IFR": 0.25, "TDP": 0.10},
    "CF":     {"OFR": 0.55, "OFE": 0.25, "OFA": 0.20},
    "COF_LF": {"OFR": 0.50, "OFE": 0.30, "OFA": 0.20},
    "COF_RF": {"OFR": 0.40, "OFA": 0.35, "OFE": 0.25},
}

# Level norm ages — expected age at each level for an on-track prospect.
LEVEL_NORM_AGE = {
    "aaa": 26, "aa": 24, "a": 22, "a-short": 21,
    "usl": 19, "dsl": 18, "intl": 17,
}

# ---------------------------------------------------------------------------
# FV helpers
# ---------------------------------------------------------------------------

def dev_weight(age, norm_age, level=None):
    """Development weight: how much to blend Pot vs Ovr based on age vs level norm."""
    diff = norm_age - age
    if diff >= 3:    w = 0.55 if age <= 17 else 0.65
    elif diff >= 1:  w = 0.40 if age <= 17 else 0.50
    elif diff >= -1: w = 0.35
    elif diff >= -2: w = 0.20
    else:            w = 0.10
    low_level = level and level.lower().replace(" ", "-") in ("usl", "dsl", "intl", "rookie", "a-short")
    if low_level:
        w += 0.10
        if level.lower().replace(" ", "-") in ("usl", "dsl", "intl", "rookie"):
            w = min(w, 0.50)
    return w


def effective_pot(p):
    """Pitcher arsenal ceiling override — elite multi-pitch arsenal raises effective Pot."""
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


def defensive_score(p, bucket):
    """Weighted defensive score on 20-80 scale for a position bucket."""
    def _n(val): return norm(val) or 0
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
    pot_map = {"C": "PotC", "SS": "PotSS", "CF": "PotCF", "2B": "Pot2B", "3B": "Pot3B"}
    cur_map = {"C": "C", "SS": "SS", "CF": "CF", "2B": "2B", "3B": "3B"}
    field = pot_map.get(bucket) if age <= 23 else cur_map.get(bucket)
    if not field:
        return 0
    return norm(p.get(field, 0))


# ---------------------------------------------------------------------------
# Positional access premium
# ---------------------------------------------------------------------------

def positional_access_premium(bucket, offensive_grade, defensive_value, access_threshold=50):
    """Compute the positional value premium for premium positions.

    At premium positions (SS, C, CF), adequate defense (>= threshold) enables
    a positional value premium that scales with offensive grade. Higher offense
    at a premium position with adequate defense produces a larger premium.

    For non-premium positions, returns 0.

    Args:
        bucket: Position bucket.
        offensive_grade: The player's offensive grade (20-80).
        defensive_value: The player's defensive value (20-80).
        access_threshold: Minimum defensive value to qualify for positional access.

    Returns:
        Premium value as a float (added to FV before rounding).
    """
    params = POSITIONAL_ACCESS.get(bucket)
    if params is None:
        return 0.0
    if defensive_value < access_threshold:
        return 0.0
    base_premium = params["base_premium"]
    offense_scale = params["offense_scale"]
    return base_premium + (offensive_grade - 40) * offense_scale


# ---------------------------------------------------------------------------
# FV calculation
# ---------------------------------------------------------------------------

def calc_fv(p):
    """
    Compute FV for a prospect. Player dict must have:
      Ovr, Pot, Age, _is_pitcher, _bucket, _norm_age
    Returns (fv_base: int, fv_plus: bool).
    """
    ovr    = p["Ovr"]
    pot    = effective_pot(p)
    age, norm_age = p["Age"], p["_norm_age"]
    bucket = p["_bucket"]

    if bucket == "RP":
        pot = round(pot * RP_POT_DISCOUNT)

    dw = dev_weight(age, norm_age, level=p.get("_level"))
    fv = ovr + (pot - ovr) * dw

    if pot >= 45:
        comp = _pos_composite(p, bucket, age) or 0
        off_grade = p.get("_offensive_grade")
        # Premium positions with offensive grade available: use positional access
        if bucket in POSITIONAL_ACCESS and off_grade is not None:
            if p.get("_defensive_value") is not None:
                dv = p["_defensive_value"]
            else:
                dv = defensive_score(p, bucket)
            premium = positional_access_premium(bucket, off_grade, dv)
            if premium > 0:
                fv = min(fv + premium, pot)
        elif comp >= 60:
            # Non-premium positions or no offensive grade: existing defensive bonus
            if p.get("_defensive_value") is not None:
                wt = p["_defensive_value"]
            else:
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

    # Critical tool floor penalty
    if p.get("_is_pitcher"):
        for field in ("PotCtrl", "PotMov"):
            val = norm_floor(p.get(field, 100))
            if val <= 30:   fv -= 5
            elif val <= 35: fv -= 3
    else:
        crit = norm_floor(p.get("PotCntct", 100))
        if crit <= 30:   fv -= 5
        elif crit <= 35: fv -= 3

    # Platoon split penalty
    if p.get("_is_pitcher"):
        sl, sr = norm_floor(p.get("Stf_L", 0)), norm_floor(p.get("Stf_R", 0))
        if sl and sr:
            gap, weak = abs(sl - sr), min(sl, sr)
            if weak <= 25 and gap >= 15: fv -= 3
            elif weak <= 25 and gap >= 10: fv -= 2
    else:
        cl, cr = norm_floor(p.get("Cntct_L", 0)), norm_floor(p.get("Cntct_R", 0))
        if cl and cr:
            gap, weak = abs(cl - cr), min(cl, cr)
            if weak <= 25 and gap >= 15: fv -= 3
            elif weak <= 25 and gap >= 10: fv -= 2

    base = round(fv / 5) * 5
    remainder = fv - base
    plus = remainder >= 2.0 or ((pot - base) >= 10 and age <= norm_age)
    return base, plus
