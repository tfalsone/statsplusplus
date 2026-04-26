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
# age-based decay). Source: VMLB + EMLB 2033 average, N=50+ per bucket.
# Separate tables for hitters and pitchers — pitchers develop later
# (stuff/movement can improve into mid-20s, control peaks even later).
_AGE_RUNWAY_HITTER = {
    17: 1.60, 18: 1.43, 19: 1.26, 20: 1.16, 21: 1.00,
    22: 0.73, 23: 0.55, 24: 0.43, 25: 0.33, 26: 0.19,
}
_AGE_RUNWAY_PITCHER = {
    17: 1.56, 18: 1.42, 19: 1.30, 20: 1.16, 21: 1.00,
    22: 0.79, 23: 0.62, 24: 0.48, 25: 0.35, 26: 0.20,
}
# Combined table kept for backward compatibility / external callers
_AGE_RUNWAY = {
    17: 1.58, 18: 1.42, 19: 1.28, 20: 1.16, 21: 1.00,
    22: 0.76, 23: 0.58, 24: 0.46, 25: 0.34, 26: 0.20,
}


def age_development_mult(age, is_pitcher=False):
    """Multiplier on dev_weight reflecting remaining development runway.

    Returns 1.0 for age ≤ 21 (full runway), decays based on empirical
    gap-closure rates for older prospects. Linearly interpolates between
    defined age points. Pitchers retain more runway at each age.
    """
    table = _AGE_RUNWAY_PITCHER if is_pitcher else _AGE_RUNWAY_HITTER
    if age <= 21:
        return table.get(age, 1.58)
    if age >= 26:
        return table[26]
    lo = int(age)
    hi = lo + 1
    frac = age - lo
    return table.get(lo, 0.20) * (1 - frac) + table.get(hi, 0.20) * frac


def dev_weight(age, norm_age, level=None, is_pitcher=False):
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
        w *= age_development_mult(age, is_pitcher=is_pitcher)
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
    return calc_fv_v2(p)


# ---------------------------------------------------------------------------
# Probability-based FV (v2)
# ---------------------------------------------------------------------------

# Forward-looking gap closure rates by age.
# "What fraction of the remaining composite-to-ceiling gap closes between
# age X and peak (26)?" Derived from cross-sectional mean realization at
# each age vs age 26 terminal. Source: VMLB 2033, N=200+ per age bucket.
_GAP_CLOSURE_HITTER = {
    17: 0.87, 18: 0.86, 19: 0.84, 20: 0.83, 21: 0.80,
    22: 0.68, 23: 0.48, 24: 0.38, 25: 0.38,
}
_GAP_CLOSURE_PITCHER = {
    17: 0.93, 18: 0.92, 19: 0.91, 20: 0.90, 21: 0.87,
    22: 0.83, 23: 0.72, 24: 0.59, 25: 0.49,
}

# Terminal (age 26) outcome distribution — what the final realization
# looks like at peak. Used to model variance around the expected closure.
# Buckets: (bust <75%, below 75-88%, meets 88-95%, exceeds 95-100%, full 100%)
_TERMINAL_DIST_HITTER = (0.01, 0.13, 0.24, 0.32, 0.29)
_TERMINAL_DIST_PITCHER = (0.00, 0.05, 0.14, 0.19, 0.62)

# Realization fractions for each terminal outcome bucket (midpoints).
_TERMINAL_REALIZATION = (0.65, 0.82, 0.92, 0.97, 1.00)

# Empirical outcome probabilities by age, from cross-sectional OVR/POT
# realization analysis (VMLB 2033). Each row: (bust, below, meets, exceeds, full).
# Bust: <60% realization. Below: 60-75%. Meets: 75-90%.
# Exceeds: 90-97%. Full: 97%+.
_OUTCOME_PROBS_HITTER = {
    17: (0.52, 0.45, 0.03, 0.00, 0.00),
    18: (0.46, 0.48, 0.06, 0.00, 0.00),
    19: (0.25, 0.57, 0.17, 0.00, 0.00),
    20: (0.25, 0.56, 0.19, 0.00, 0.00),
    21: (0.13, 0.43, 0.38, 0.06, 0.00),
    22: (0.03, 0.20, 0.50, 0.21, 0.06),
    23: (0.00, 0.07, 0.39, 0.33, 0.21),
    24: (0.00, 0.05, 0.28, 0.35, 0.31),
    25: (0.00, 0.07, 0.28, 0.29, 0.36),
}
_OUTCOME_PROBS_PITCHER = {
    17: (0.51, 0.45, 0.04, 0.00, 0.00),
    18: (0.31, 0.59, 0.10, 0.00, 0.00),
    19: (0.19, 0.61, 0.19, 0.01, 0.00),
    20: (0.07, 0.54, 0.35, 0.04, 0.00),
    21: (0.03, 0.37, 0.50, 0.08, 0.03),
    22: (0.00, 0.15, 0.61, 0.15, 0.08),
    23: (0.00, 0.06, 0.41, 0.23, 0.29),
    24: (0.00, 0.03, 0.24, 0.33, 0.39),
    25: (0.00, 0.02, 0.20, 0.31, 0.47),
}

# Realization fractions for each outcome bucket.
# These represent what fraction of the TRUE CEILING the player achieves
# as their peak OVR, not fraction of the gap. Derived from empirical
# OVR/POT ratios: bust median ~40% of POT, below ~68%, etc.
# Applied as: score_i = ceiling × realization_i, floored at 20.
_OUTCOME_REALIZATION = (0.40, 0.68, 0.83, 0.94, 1.00)


def _get_outcome_probs(age, is_pitcher):
    """Get outcome probabilities for a given age, with interpolation."""
    table = _OUTCOME_PROBS_PITCHER if is_pitcher else _OUTCOME_PROBS_HITTER
    if age <= 17:
        return table[17]
    if age >= 25:
        return table[25]
    lo = int(age)
    hi = lo + 1
    frac = age - lo
    lo_p = table.get(lo, table[25])
    hi_p = table.get(hi, table[25])
    return tuple(lo_p[i] * (1 - frac) + hi_p[i] * frac for i in range(5))


def calc_fv_v2(p):
    """Probability-informed FV using empirical gap closure rates.

    Uses forward-looking gap closure rates (what fraction of the remaining
    composite-to-ceiling gap closes by peak age) as the development weight.
    These rates are derived from cross-sectional OVR/POT analysis and
    inherently capture the probability distribution of outcomes — the mean
    closure rate IS the expected value across all outcome scenarios.

    Character traits and level context adjust the closure rate.
    """
    ovr = p["Ovr"]       # composite_score
    pot = p["Pot"]        # true_ceiling
    age = p["Age"]
    norm_age = p["_norm_age"]
    bucket = p["_bucket"]
    is_pitcher = bool(p.get("_is_pitcher"))

    if bucket == "RP":
        pot = round(pot * RP_POT_DISCOUNT)

    gap = max(0, pot - ovr)
    if gap == 0:
        base = round(ovr / 5) * 5
        return base, False

    # Get forward-looking gap closure rate for this age
    table = _GAP_CLOSURE_PITCHER if is_pitcher else _GAP_CLOSURE_HITTER
    if age <= 17:
        closure = table[17]
    elif age >= 25:
        closure = table[25]
    else:
        lo = int(age)
        hi = lo + 1
        frac = age - lo
        closure = table.get(lo, 0.38) * (1 - frac) + table.get(hi, 0.38) * frac

    # Level adjustment: young-for-level closes more gap, old-for-level less.
    level_diff = norm_age - age
    if level_diff >= 1:
        closure = min(0.98, closure + level_diff * 0.02)
    elif level_diff <= -1:
        closure = max(0.05, closure + level_diff * 0.02)

    # Character adjustments
    we = p.get("WrkEthic", "N")
    intel = p.get("Int", "N")
    if we in ("H", "VH"):
        closure = min(0.98, closure + 0.03)
    elif we == "L":
        closure = max(0.05, closure - 0.03)
    if intel in ("H", "VH"):
        closure = min(0.98, closure + 0.02)
    elif intel == "L":
        closure = max(0.05, closure - 0.02)

    # Scale closure rate to produce FV distributions closer to real baseball.
    # OOTP's development model is generous (median player realizes 97%+ of POT).
    # Real baseball has much higher bust rates. Apply a discount that reflects
    # the gap between game development and real-world outcomes.
    # Calibrated to produce ~1 FV55+/org, ~3 FV50+/org, ~8 FV45+/org.
    bust_discount = 0.45
    effective_closure = closure * bust_discount

    fv = ovr + gap * effective_closure

    # Accuracy penalty
    if p.get("Acc") == "L":
        fv -= 2

    # Platoon split penalty
    if is_pitcher:
        sl, sr = norm_floor(p.get("Stf_L", 0)), norm_floor(p.get("Stf_R", 0))
        if sl and sr:
            g, weak = abs(sl - sr), min(sl, sr)
            if weak <= 25 and g >= 15: fv -= 3
            elif weak <= 25 and g >= 10: fv -= 2
    else:
        cl, cr = norm_floor(p.get("Cntct_L", 0)), norm_floor(p.get("Cntct_R", 0))
        if cl and cr:
            g, weak = abs(cl - cr), min(cl, cr)
            if weak <= 25 and g >= 15: fv -= 3
            elif weak <= 25 and g >= 10: fv -= 2

    # RP ceiling
    if bucket == "RP":
        fv = min(fv, 57)

    base = round(fv / 5) * 5
    remainder = fv - base
    plus = remainder >= 2.5 and base < 80
    return base, plus
