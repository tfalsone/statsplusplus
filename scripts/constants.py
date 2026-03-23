# constants.py — shared constants across all scripts

PITCH_FIELDS = ["Fst","Snk","Crv","Sld","Chg","Splt","Cutt","CirChg","Scr","Frk","Kncrv","Knbl"]

# Reliever WAR ceiling — elite closers peak here; FV hard cap for RP is 50
RP_WAR_CAP = 2.0

# Arbitration salary as % of market value by arb year.
# Calibrated to OOTP arb outcomes: 86 arb-eligible players with WAR > 0.5.
# OOTP arb pays ~20-33% of FA market rate (vs ~45-80% in real MLB).
ARB_PCT = {1: 0.20, 2: 0.22, 3: 0.33}

# Below this WAR threshold, a player's market value is league minimum —
# production at this level is freely available (waiver claims, call-ups).
# Prevents the linear $/WAR model from generating phantom surplus for
# replacement-level players in pre-arb years.
REPLACEMENT_WAR = 1.0

# Prospect surplus model
# ---------------------------------------------------------------------------

# FV → expected peak WAR/year (midpoint of each FV band per farm_analysis_guide.md)
# Interpolate linearly between defined points. RP WAR is capped at RP_WAR_CAP regardless of FV.
FV_TO_PEAK_WAR = {
    80: 10.0, 70: 7.0, 65: 5.5, 60: 4.2, 55: 2.9, 50: 2.0, 45: 1.2, 40: 0.5
}

# Development discount — bust probability only (P(reaches projected FV)).
# Time value of money is handled separately by PROSPECT_DISCOUNT_RATE.
DEVELOPMENT_DISCOUNT = {
    "MLB": 1.00, "AAA": 0.90, "AA": 0.75, "A": 0.60,
    "A-Short": 0.50, "USL": 0.38, "DSL": 0.38, "Intl": 0.25,
}

# Estimated years until MLB debut by current level
YEARS_TO_MLB = {
    "MLB": 0, "AAA": 0.5, "AA": 1.5, "A": 2.5,
    "A-Short": 3.5, "USL": 4.5, "DSL": 4.5, "Intl": 5.0,
}

# Annual discount rate for time value + residual development risk
PROSPECT_DISCOUNT_RATE = 0.05

# ---------------------------------------------------------------------------
# WAR projection tables
# ---------------------------------------------------------------------------

# OVR → peak WAR/year by bucket (hitter, SP, RP)
# Used for MLB players without sufficient stat history.
# Calibrated 2033-04-25 to align with FV_TO_PEAK_WAR scale.
OVR_TO_WAR = [
    # (Ovr, hitter_WAR, SP_WAR, RP_WAR)
    (80, 9.0, 8.0, 2.5),
    (75, 7.5, 6.5, 2.0),
    (70, 6.0, 5.5, 1.5),
    (65, 4.5, 4.0, 1.2),
    (60, 3.2, 2.8, 1.0),
    (55, 2.2, 1.9, 0.7),
    (50, 2.0, 1.7, 0.5),
    (45, 1.0, 0.8, 0.3),
    (40, 0.2, 0.2, 0.1),
]

# ---------------------------------------------------------------------------
# Aging curves
# ---------------------------------------------------------------------------

# Multiplier on peak WAR by age. Interpolated for intermediate ages.
# Calibrated 2033-04-25 from Marcel/BP/FanGraphs consensus aging research.
# Decline rates: ~3%/yr 29-31, ~6%/yr 32-34, ~9%/yr 35-37, ~12%/yr 38+.

AGING_HITTER = {
    27: 1.00, 28: 1.00, 29: 0.97, 30: 0.94, 31: 0.91,
    32: 0.85, 33: 0.79, 34: 0.76, 35: 0.67, 36: 0.58,
    37: 0.49, 38: 0.37, 39: 0.26, 40: 0.16, 42: 0.08
}

# Pitchers slightly steeper from 32+ (injury/velocity risk).
AGING_PITCHER = {
    27: 1.00, 28: 1.00, 29: 0.97, 30: 0.94, 31: 0.91,
    32: 0.84, 33: 0.77, 34: 0.65, 35: 0.55, 36: 0.45,
    37: 0.35, 38: 0.25, 39: 0.16, 40: 0.09
}
