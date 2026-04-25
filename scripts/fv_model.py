"""
fv_model.py — Prospect FV grade calculation.

Computes FV grades from player ratings dicts. Used by fv_calc.py and farm_analysis.py.
All functions are pure (no DB access).

Public API:
  calc_fv(p)            → (fv_base: int, fv_plus: bool)
  dev_weight(age, norm_age, level) → float
  age_development_mult(age) → float
  defensive_score(p, bucket) → float
"""

from constants import RP_POT_DISCOUNT
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

# Age-based development runway multiplier.
# Derived from cross-sectional OVR/POT gap analysis: at each age, what
# fraction of the ceiling-current gap remains unrealized? Normalized to
# age 21 = 1.0 (the inflection where level-based context gives way to
# age-based decay). Source: VMLB 2033, N=50+ per age bucket.
_AGE_RUNWAY = {
    17: 1.42, 18: 1.42, 19: 1.29, 20: 1.18, 21: 1.00,
    22: 0.69, 23: 0.40, 24: 0.28, 25: 0.22, 26: 0.12,
}


def age_development_mult(age):
    """Multiplier on dev_weight reflecting remaining development runway.

    Returns 1.0 for age ≤ 21 (full runway), decays based on empirical
    gap-closure rates for older prospects. Linearly interpolates between
    defined age points.
    """
    if age <= 21:
        return _AGE_RUNWAY.get(age, 1.42)
    if age >= 26:
        return _AGE_RUNWAY[26]
    lo = int(age)
    hi = lo + 1
    frac = age - lo
    return _AGE_RUNWAY.get(lo, 0.12) * (1 - frac) + _AGE_RUNWAY.get(hi, 0.12) * frac


def dev_weight(age, norm_age, level=None):
    """Development weight: how much to blend Pot vs Ovr based on age vs level norm."""
    diff = norm_age - age
    if diff >= 3:    w = 0.55 if age <= 17 else 0.65
    elif diff >= 2:  w = 0.45 if age <= 17 else 0.60
    elif diff >= 1:  w = 0.40 if age <= 17 else 0.50
    elif diff >= -1: w = 0.35
    elif diff >= -2: w = 0.20
    else:            w = 0.10
    low_level = level and level.lower().replace(" ", "-") in ("usl", "dsl", "intl", "rookie", "a-short")
    if low_level:
        w += 0.10
        if level.lower().replace(" ", "-") in ("usl", "dsl", "intl", "rookie"):
            w = min(w, 0.55)
    # Apply empirical age decay for prospects past peak development age
    if age > 21:
        w *= age_development_mult(age)
    return w


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

    Simplified formula (Session 48): the composite already incorporates
    positional tool weights, defensive value, and carrying tool bonuses.
    The ceiling already incorporates peak tool bonus and age-weighted blend.
    FV is now just: composite + dev_weight × (ceiling - composite), plus
    character modifiers and platoon penalty.

    Removed (now in composite/ceiling): defensive bonus, versatility bonus,
    positional access premium, critical tool floor penalty.
    """
    ovr    = p["Ovr"]
    pot    = p["Pot"]
    age, norm_age = p["Age"], p["_norm_age"]
    bucket = p["_bucket"]

    if bucket == "RP":
        pot = round(pot * RP_POT_DISCOUNT)

    dw = dev_weight(age, norm_age, level=p.get("_level"))
    fv = ovr + (pot - ovr) * dw

    # Character modifiers
    we = p.get("WrkEthic", "N")
    if we in ("H", "VH"): fv += 1
    elif we == "L":        fv -= 1

    if p.get("Acc") == "L":
        fv -= 2

    # Platoon split penalty (not captured by composite)
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

    # RP ceiling: cap FV at 55. RP value is heavily discounted due to
    # fewer innings; even elite closers rarely justify FV above 55.
    if bucket == "RP":
        fv = min(fv, 57)  # 57 rounds to 55+

    base = round(fv / 5) * 5
    remainder = fv - base
    plus = remainder >= 2.0 or ((pot - base) >= 10 and age <= norm_age)
    return base, plus
