"""Prospect development-speed metric — pure computation.

Measures how fast the developmentally-relevant component (offensive grade for
hitters, composite for pitchers) is moving over a trailing window, relative to
same-bucket / same-age-band / same-league peers, as a z-score. Qualified by the
POT gap and its ΔOVR-vs-ΔPOT decomposition, and gated / graded by a confidence
tier (history length, scouting accuracy, playing time).

Design + validation: `.kiro/specs/development-speed-metric/design.md`.

This module is pure: it operates on pre-loaded snapshot rows and a pre-built
baseline. The DB loading, bucketing (via ``assign_bucket``), and persistence live
in the data pipeline (``fv_calc``).

Public API:
    component_delta(snaps, key) -> (annual_delta|None, first, last)
    build_baseline(records) -> {(bucket, band): (mean, sd, n)}
    dev_speed_z(annual_move, bucket, band, baseline) -> (z|None, group|None)
    classify(z, gap, signal) -> (label, css_class, note)
    confidence_tier(window_years, n_snaps, acc, playing_time, is_pitcher) -> str
    age_band(age) -> str
    compute_dev_speed(...) -> dict   # the top-level per-player result
"""

from __future__ import annotations

import statistics as _st
from datetime import date
from typing import Any, Optional

# --- Tunable parameters (validated defaults; may move to model_weights later) ---
WINDOW_MONTHS = 12          # trailing window for "current" dev pace
MIN_SNAPSHOTS = 3           # minimum points in the window to compute
MIN_WINDOW_DAYS = 150       # ~5 months minimum span (also the reporting gate)
MIN_GROUP_N = 20            # minimum peers to form a baseline cell
AGE_BAND_WIDTH = 2
MAX_BASELINE_AGE = 25       # prospect age ceiling for the baseline population
WIDE_GAP = 12               # POT-gap threshold for the "upside" qualifier

# Reporting floor (below this the signal is too noisy to show a verdict).
MIN_AGE_REPORT = 18
MIN_COMPOSITE_REPORT = 38

# Confidence-tier thresholds.
_CONF_PA_FULL = 250         # PA (hitter) for full playing-time credit in the window
_CONF_IP_FULL = 60          # IP (pitcher)


def age_band(age: int) -> str:
    lo = (int(age) // AGE_BAND_WIDTH) * AGE_BAND_WIDTH
    return f"{lo}-{lo + AGE_BAND_WIDTH - 1}"


def _years_between(d1: str, d2: str) -> float:
    y1, m1, day1 = map(int, d1.split("-"))
    y2, m2, day2 = map(int, d2.split("-"))
    return (date(y2, m2, day2) - date(y1, m1, day1)).days / 365.25


def component_delta(snaps: list[dict], key: str) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """Annualized delta of a component over the sub-window where it's populated.

    Components (offensive_grade, defensive_value) are only written on snapshots
    where the eval engine ran, which can start later than the composite history.
    Returns (annual_delta or None, first_val, last_val).
    """
    pts = [s for s in snaps if s.get(key) is not None and s[key] > 0]
    if len(pts) < 2:
        return None, (pts[0][key] if pts else None), (pts[-1][key] if pts else None)
    f, l = pts[0], pts[-1]
    yrs = _years_between(f["snapshot_date"], l["snapshot_date"])
    if yrs * 365.25 < MIN_WINDOW_DAYS:
        return None, f[key], l[key]
    return (l[key] - f[key]) / yrs, f[key], l[key]


def dev_group(bucket: str) -> str:
    """Coarser grouping for the dev-speed *baseline*.

    Offensive development rate is essentially position-independent for hitters
    (validated: 1B/2B/3B/SS/CF/COF offensive-dev means cluster within ~0.5/yr),
    so we do NOT slice hitters by fielding position — that only thins the sample.
    The one meaningful exception is catcher, whose bat develops slower (workload/
    defensive-demand drag). Pitchers keep the SP/RP split (real, validated).

    Groups: "SP", "RP", "C", "HIT" (all non-catcher hitters).
    The player's true position bucket is still used for display, not the baseline.
    """
    if bucket in ("SP", "RP"):
        return bucket
    if bucket == "C":
        return "C"
    return "HIT"


def build_baseline(records: list[dict]) -> dict[str, dict[tuple, tuple]]:
    """Per (dev_group, age-band) mean/SD for each dev signal.

    Returns {signal: {(group, band): (mean, sd, n)}} for signal in {"comp","off"}
    — annualized movement of composite / offensive grade. `group` is the coarse
    dev_group (SP/RP/C/HIT), not the fine fielding bucket — see dev_group().
    A (group, "ALL") all-ages fallback cell is also emitted for tiny leagues.
    """
    field = {"comp": "annual_comp", "off": "annual_off"}
    out: dict[str, dict[tuple, tuple]] = {}
    from collections import defaultdict
    for sig, fld in field.items():
        fine: dict[tuple, list] = defaultdict(list)
        grp_all: dict[str, list] = defaultdict(list)
        for r in records:
            if r["age"] <= MAX_BASELINE_AGE and r.get(fld) is not None:
                g = dev_group(r["bucket"])
                fine[(g, r["band"])].append(r[fld])
                grp_all[g].append(r[fld])
        b = {}
        for key, vals in fine.items():
            if len(vals) >= MIN_GROUP_N:
                b[key] = (round(_st.mean(vals), 3), round(_st.pstdev(vals) or 1.0, 3), len(vals))
        for g, vals in grp_all.items():
            if len(vals) >= MIN_GROUP_N:
                b[(g, "ALL")] = (round(_st.mean(vals), 3), round(_st.pstdev(vals) or 1.0, 3), len(vals))
        out[sig] = b
    return out


def primary_signal(bucket: str, has_off: bool) -> str:
    """Which dev signal headlines this player: offensive for hitters (defense is
    experience-inflated and often maxed), composite for pitchers."""
    is_hitter = bucket not in ("SP", "RP")
    return "off" if (is_hitter and has_off) else "comp"


def dev_speed_z(annual_move: Optional[float], bucket: str, band: str,
                sig: str, baseline: dict) -> tuple[Optional[float], Optional[tuple]]:
    if annual_move is None:
        return None, None
    b = baseline.get(sig, {})
    g = dev_group(bucket)
    # (group, band) → (group, all ages) fallback for tiny leagues
    for key in ((g, band), (g, "ALL")):
        if key in b:
            mean, sd, n = b[key]
            if sd <= 0:
                return None, (mean, sd, n)
            return round((annual_move - mean) / sd, 2), (mean, sd, n)
    return None, None


def classify(z: Optional[float], gap: int, sig: str) -> tuple[str, str, str]:
    """(label, css_class, note) from z (pace vs peers) qualified by POT gap.

    css_class in {rising, onpace, watch, stalled, regressing, none}.
    Labels are descriptive (observation, not verdict).
    """
    if z is None:
        return "—", "none", ""
    what = "bat" if sig == "off" else "overall"
    wide = (gap or 0) >= WIDE_GAP
    if z >= 1.0:
        if wide:
            return "Rising (room)", "rising", f"{what} developing, ceiling room remains"
        return "Rising (realizing)", "rising", f"{what} developing, near ceiling"
    if z <= -1.0:
        if wide:
            return "Stalled — upside at risk", "stalled", f"{what} not tracking a wide ceiling gap"
        return "Regressing/plateaued", "regressing", f"{what} flat/declining, near his level"
    if z <= -0.5 and wide:
        return "Watch — slow vs upside", "watch", f"{what} slow vs a wide ceiling gap"
    return "On pace", "onpace", f"{what} developing about as expected"


def confidence_tier(window_years: float, n_snaps: int, acc: Optional[str],
                    playing_time: float, is_pitcher: bool) -> str:
    """High / Medium / Low confidence in the reading, from the factors validation
    showed matter: window length + snapshot count, scouting accuracy, playing time.
    """
    score = 0
    # window length / density
    if window_years >= 1.0 and n_snaps >= 6:
        score += 2
    elif window_years >= 0.6 and n_snaps >= 4:
        score += 1
    # scouting accuracy
    a = (acc or "").upper()
    if a in ("VH", "H"):
        score += 1
    elif a in ("L", "VL"):
        score -= 1
    # playing time in the window
    full = _CONF_IP_FULL if is_pitcher else _CONF_PA_FULL
    if playing_time >= full:
        score += 1
    elif playing_time < full * 0.4:
        score -= 1
    if score >= 3:
        return "High"
    if score >= 1:
        return "Medium"
    return "Low"


def compute_dev_speed(
    *,
    bucket: str,
    age: int,
    window: list[dict],
    baseline: dict,
    acc: Optional[str] = None,
    playing_time: float = 0.0,
) -> Optional[dict[str, Any]]:
    """Top-level per-player dev-speed result, or None if the window is too short.

    `window` is the player's trailing-window snapshot rows (each a dict with
    snapshot_date, composite_score, ovr, pot, offensive_grade, defensive_value),
    already filtered/selected by the caller. `baseline` is from build_baseline.

    Returns a dict shaped for storage + display (see the spec / query layer):
        {z, signal, label, css_class, note, gap, d_ovr, d_pot,
         confidence, available, comp_first, comp_last, off_first, off_last, ...}
    Returns None when there is not enough history to compute at all.
    """
    if len(window) < MIN_SNAPSHOTS:
        return None
    first, last = window[0], window[-1]
    yrs = _years_between(first["snapshot_date"], last["snapshot_date"])
    if yrs * 365.25 < MIN_WINDOW_DAYS:
        return None

    d_comp = (last["composite_score"] - first["composite_score"]) / yrs
    d_off, off_f, off_l = component_delta(window, "offensive_grade")
    d_def, def_f, def_l = component_delta(window, "defensive_value")
    # Gap + trajectory use OUR model's composite/ceiling (not the game's OVR/POT),
    # consistent with the rest of the app. OVR/POT are NULL in OVR-less leagues
    # (e.g. PPL); composite/ceiling are always populated. d_ovr/d_pot are stored
    # under legacy names but represent current-composite / ceiling deltas.
    def _cur(s):
        return s.get("composite_score") if s.get("composite_score") else (s.get("ovr") or 0)
    def _ceil(s):
        return s.get("ceiling_score") if s.get("ceiling_score") else (s.get("pot") or 0)
    cur_last, cur_first = _cur(last), _cur(first)
    ceil_last, ceil_first = _ceil(last), _ceil(first)
    gap = max(0, ceil_last - cur_last)
    d_ovr = cur_last - cur_first       # Δ current ability (composite)
    d_pot = ceil_last - ceil_first     # Δ ceiling
    band = age_band(age)
    is_pitcher = bucket in ("SP", "RP")

    sig = primary_signal(bucket, has_off=d_off is not None)
    annual_move = d_off if sig == "off" else d_comp
    z, grp = dev_speed_z(annual_move, bucket, band, sig, baseline)

    comp_last = last["composite_score"]
    reportable = age >= MIN_AGE_REPORT and (comp_last or 0) >= MIN_COMPOSITE_REPORT
    available = reportable and z is not None

    conf = confidence_tier(yrs, len(window), acc, playing_time, is_pitcher)
    label, css, note = classify(z, gap, sig) if available else ("—", "none", "")

    return {
        "available": available,
        "z": z,
        "signal": sig,
        "label": label,
        "css_class": css,
        "note": note,
        "gap": gap,
        "d_ovr": d_ovr,
        "d_pot": d_pot,
        "confidence": conf,
        "annual_move": round(annual_move, 2) if annual_move is not None else None,
        "peer_mean": grp[0] if grp else None,
        "peer_sd": grp[1] if grp else None,
        "peer_n": grp[2] if grp else None,
        "comp_first": first["composite_score"], "comp_last": comp_last,
        "off_first": off_f, "off_last": off_l,
        "def_first": def_f, "def_last": def_l,
        "window_years": round(yrs, 2), "n_snaps": len(window),
        "band": band,
    }
