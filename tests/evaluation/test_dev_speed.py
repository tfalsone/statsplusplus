"""Tests for statsplusplus.evaluation.dev_speed — pure development-speed metric.

Covers the validated design decisions (Session 88):
  - component split (offensive grade for hitters, composite for pitchers)
  - dev_group pooling (SP/RP/C/HIT — hitters not sliced by fielding position)
  - gap + ΔOVR/ΔPOT decomposition from OUR composite/ceiling (not game OVR/POT)
  - history/reporting gate and confidence tier
  - thin-cell all-ages fallback
"""

from statsplusplus.evaluation import dev_speed as ds


def _snap(date, comp, ceil, off=None, deff=None):
    return {"snapshot_date": date, "composite_score": comp, "ceiling_score": ceil,
            "ovr": None, "pot": None, "offensive_grade": off, "defensive_value": deff}


def _win(pairs, off=None, deff=None):
    """Build a window from (date, comp, ceil) tuples; optional parallel off/def lists."""
    out = []
    for i, (d, c, ce) in enumerate(pairs):
        out.append(_snap(d, c, ce,
                         off[i] if off else None,
                         deff[i] if deff else None))
    return out


def test_dev_group_pools_hitters_keeps_catcher_and_pitchers():
    assert ds.dev_group("SS") == "HIT"
    assert ds.dev_group("1B") == "HIT"
    assert ds.dev_group("COF") == "HIT"
    assert ds.dev_group("C") == "C"       # catcher separate
    assert ds.dev_group("SP") == "SP"
    assert ds.dev_group("RP") == "RP"


def test_primary_signal_offense_for_hitters_composite_for_pitchers():
    assert ds.primary_signal("SS", has_off=True) == "off"
    assert ds.primary_signal("SS", has_off=False) == "comp"   # no off data -> composite
    assert ds.primary_signal("SP", has_off=True) == "comp"


def test_component_delta_annualizes_over_populated_subwindow():
    win = _win([("2033-01-01", 40, 50), ("2034-01-01", 44, 52)], off=[40, 48])
    d, f, l = ds.component_delta(win, "offensive_grade")
    assert f == 40 and l == 48
    assert round(d, 1) == 8.0  # +8 over ~1yr


def test_gap_and_trajectory_use_composite_ceiling_not_ovr_pot():
    # OVR/POT are None (OVR-less league); metric must still compute from comp/ceil.
    baseline = {"off": {("HIT", "22-23"): (2.0, 3.0, 100)}}
    win = _win([("2033-06-01", 46, 58), ("2033-12-01", 46, 57), ("2034-06-01", 46, 56)],
               off=[46, 46, 46])
    r = ds.compute_dev_speed(bucket="CF", age=22, window=win, baseline=baseline,
                             acc="H", playing_time=400)
    assert r is not None and r["available"]
    assert r["gap"] == 10          # 56 - 46 (from ceiling/composite, not NULL ovr/pot)
    assert r["d_pot"] == -2        # ceiling 58 -> 56 (eroding)
    assert r["d_ovr"] == 0         # composite flat


def test_stalled_with_eroding_ceiling_and_wide_gap():
    baseline = {"off": {("HIT", "22-23"): (3.0, 2.0, 100)}}
    win = _win([("2033-06-01", 45, 60), ("2033-12-01", 45, 59), ("2034-06-01", 45, 58)],
               off=[45, 45, 45])
    r = ds.compute_dev_speed(bucket="COF", age=22, window=win, baseline=baseline,
                             acc="H", playing_time=400)
    # flat bat (0/yr) vs +3 mean, sd 2 -> z=-1.5; wide gap -> stalled
    assert r["z"] == -1.5
    assert r["css_class"] == "stalled"


def test_reporting_gate_young_or_low_composite():
    baseline = {"off": {("HIT", "16-17"): (1.0, 2.0, 100)}}
    win = _win([("2033-06-01", 30, 55), ("2033-12-01", 31, 55), ("2034-06-01", 33, 55)],
               off=[30, 31, 33])
    r = ds.compute_dev_speed(bucket="SS", age=17, window=win, baseline=baseline,
                             acc="VH", playing_time=400)
    # age 17 < MIN_AGE_REPORT and composite 33 < MIN_COMPOSITE_REPORT -> not available
    assert r is not None and r["available"] is False


def test_too_short_window_returns_none():
    baseline = {"off": {}}
    win = _win([("2034-01-01", 50, 55), ("2034-02-01", 50, 55), ("2034-03-01", 50, 55)],
               off=[50, 50, 50])
    r = ds.compute_dev_speed(bucket="SS", age=23, window=win, baseline=baseline)
    assert r is None  # < MIN_WINDOW_DAYS span


def test_all_ages_fallback_when_fine_cell_thin():
    # No (HIT, 24-25) cell, but a (HIT, ALL) fallback exists.
    baseline = {"off": {("HIT", "ALL"): (2.0, 3.0, 500)}}
    z, grp = ds.dev_speed_z(5.0, "CF", "24-25", "off", baseline)
    assert z is not None and grp[2] == 500  # used the ALL fallback


def test_confidence_tier_scales_with_window_acc_playing_time():
    high = ds.confidence_tier(1.0, 7, "VH", 500, is_pitcher=False)
    low = ds.confidence_tier(0.6, 4, "L", 20, is_pitcher=False)
    assert high == "High"
    assert low == "Low"
