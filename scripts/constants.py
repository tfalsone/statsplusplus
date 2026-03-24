# constants.py — shared constants across all scripts

import json
from pathlib import Path

PITCH_FIELDS = ["Fst","Snk","Crv","Sld","Chg","Splt","Cutt","CirChg","Scr","Frk","Kncrv","Knbl"]

# ---------------------------------------------------------------------------
# Calibrated model weights (loaded from config/model_weights.json if present)
# ---------------------------------------------------------------------------

_weights = None

def _load_weights():
    """Load league-calibrated model weights. Returns dict or None."""
    global _weights
    if _weights is not None:
        return _weights
    try:
        from league_context import get_league_dir
        path = get_league_dir() / "config" / "model_weights.json"
        if path.exists():
            with open(path) as f:
                _weights = json.load(f)
            return _weights
    except Exception:
        pass
    _weights = {}
    return _weights

def _w(key, default):
    """Get a calibrated value, falling back to default."""
    w = _load_weights()
    if not w or key not in w:
        return default
    raw = w[key]
    # Convert string keys to int
    if isinstance(raw, dict):
        return {int(k): v for k, v in raw.items()}
    return raw

# ---------------------------------------------------------------------------
# Defaults (used when model_weights.json is absent)
# ---------------------------------------------------------------------------

# Arbitration salary as % of market value by arb year.
# Calibrated to OOTP arb outcomes: 86 arb-eligible players with WAR > 0.5.
# OOTP arb pays ~20-33% of FA market rate (vs ~45-80% in real MLB).
_ARB_PCT_DEFAULT = {1: 0.20, 2: 0.22, 3: 0.33}
ARB_PCT = _w("ARB_PCT", _ARB_PCT_DEFAULT)

# Prospect surplus model
# ---------------------------------------------------------------------------

# FV → expected peak WAR/year (midpoint of each FV band per farm_analysis_guide.md)
# Interpolate linearly between defined points.
_FV_TO_PEAK_WAR_DEFAULT = {
    80: 10.0, 70: 7.0, 65: 5.5, 60: 4.2, 55: 2.9, 50: 2.0, 45: 1.2, 40: 0.5
}
FV_TO_PEAK_WAR = _w("FV_TO_PEAK_WAR", _FV_TO_PEAK_WAR_DEFAULT)

# SP-specific FV → peak WAR table. When calibrated, SP and hitter tables diverge
# because pitchers produce less WAR per OVR point than hitters in most leagues.
# Falls back to the generic hitter table when uncalibrated.
FV_TO_PEAK_WAR_SP = _w("FV_TO_PEAK_WAR_SP", _FV_TO_PEAK_WAR_DEFAULT)

# Per-position hitter FV → peak WAR tables. When calibrated, each hitter bucket
# gets its own table (COF produces less WAR per FV grade than SS). Falls back to
# the generic hitter table when uncalibrated.
def _load_fv_by_pos():
    w = _load_weights()
    raw = w.get("FV_TO_PEAK_WAR_BY_POS")
    if not raw or not isinstance(raw, dict):
        return None
    return {bucket: {int(k): v for k, v in tbl.items()}
            for bucket, tbl in raw.items() if isinstance(tbl, dict)}

FV_TO_PEAK_WAR_BY_POS = _load_fv_by_pos()

# RP-specific FV → peak WAR table. Calibrated from regression on 1582 qualifying
# RP seasons (IP>=20, GS<=3): WAR = -1.37 + 0.040 * Ovr, cross-referenced with
# peak-season WAR by Pot bucket. Replaces the old flat RP_WAR_CAP=2.0 which
# collapsed FV 50-80 RPs to identical surplus values.
_FV_TO_PEAK_WAR_RP_DEFAULT = {
    80: 3.2, 70: 2.6, 65: 2.3, 60: 2.0, 55: 1.6, 50: 1.2, 45: 0.8, 40: 0.5
}
FV_TO_PEAK_WAR_RP = _w("FV_TO_PEAK_WAR_RP", _FV_TO_PEAK_WAR_RP_DEFAULT)

# Development discount — bust probability only (P(reaches projected FV)).
# Time value of money is handled separately by PROSPECT_DISCOUNT_RATE.
# Flattened curve (Session 33): old values dropped too steeply below AAA,
# causing 81/100 top prospects to be AAA. A high-ceiling A-ball arm is still
# very valuable — the old 0.60 discount was too harsh.
DEVELOPMENT_DISCOUNT = {
    "MLB": 1.00, "AAA": 0.88, "AA": 0.78, "A": 0.68,
    "A-Short": 0.55, "USL": 0.45, "DSL": 0.45, "Intl": 0.35,
}

# Estimated years until MLB debut by current level
YEARS_TO_MLB = {
    "MLB": 0, "AAA": 0.5, "AA": 1.5, "A": 2.5,
    "A-Short": 3.5, "USL": 4.5, "DSL": 4.5, "Intl": 5.0,
}

# Annual discount rate for time value + residual development risk
PROSPECT_DISCOUNT_RATE = 0.05

# Scarcity multiplier by talent tier. Low-ceiling players are freely available (waivers,
# minor league FA) so their theoretical surplus has no trade value. Applied using Pot
# (ceiling) rather than FV so developing players are valued for what they'll become.
# Smooth S-curve shape — no single-point cliffs. Reaches 1.0 at Pot 49 to reflect
# scouting fog of war (1-2 point Pot differences are within noise).
_SCARCITY_MULT_DEFAULT = {40: 0.0, 42: 0.05, 44: 0.20, 45: 0.35, 46: 0.55, 47: 0.75, 48: 0.92, 49: 1.0, 80: 1.0}
SCARCITY_MULT = _w("SCARCITY_MULT", _SCARCITY_MULT_DEFAULT)

# ---------------------------------------------------------------------------
# WAR projection tables
# ---------------------------------------------------------------------------

# OVR → peak WAR/year by bucket.
# Used for MLB players without sufficient stat history.
# When model_weights.json exists, OVR_TO_WAR_CALIBRATED provides position-specific
# tables (per bucket). Otherwise, falls back to the generic 3-column table below.
OVR_TO_WAR = [
    # (Ovr, hitter_WAR, SP_WAR, RP_WAR) — default fallback
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

def _load_calibrated_ovr():
    """Load position-specific OVR_TO_WAR from model_weights.json."""
    w = _load_weights()
    raw = w.get("OVR_TO_WAR")
    if not raw or not isinstance(raw, dict):
        return None
    # Convert: {"SS": {"80": 7.83, ...}} -> {"SS": {80: 7.83, ...}}
    return {bucket: {int(k): v for k, v in tbl.items()}
            for bucket, tbl in raw.items() if isinstance(tbl, dict)}

OVR_TO_WAR_CALIBRATED = _load_calibrated_ovr()

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
