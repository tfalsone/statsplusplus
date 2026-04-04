"""
tests/test_prospect_value.py — Unit tests for scripts/prospect_value.py

Covers: prospect_surplus(), prospect_surplus_with_option()
All tests are pure math — no DB or API required.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


# ---------------------------------------------------------------------------
# prospect_surplus() — known output values
# ---------------------------------------------------------------------------

def test_surplus_sp_aa():
    from prospect_value import prospect_surplus
    result = prospect_surplus(55, 21, 'AA', 'SP', fv_plus=False, ovr=55, pot=70)
    assert result['total_surplus'] == 79_586_075

def test_surplus_ss_a():
    from prospect_value import prospect_surplus
    result = prospect_surplus(50, 20, 'A', 'SS', fv_plus=True, ovr=45, pot=65)
    assert result['total_surplus'] == 46_406_200

def test_surplus_rp_aaa():
    from prospect_value import prospect_surplus
    result = prospect_surplus(45, 23, 'AAA', 'RP', fv_plus=False, ovr=42, pot=55)
    assert result['total_surplus'] == 24_148_141

def test_surplus_cof_ashort():
    from prospect_value import prospect_surplus
    result = prospect_surplus(60, 19, 'A-Short', 'COF', fv_plus=False, ovr=50, pot=70)
    assert result['total_surplus'] == 73_518_397


# ---------------------------------------------------------------------------
# prospect_surplus_with_option() — option value >= base
# ---------------------------------------------------------------------------

def test_option_value_sp():
    from prospect_value import prospect_surplus, prospect_surplus_with_option
    base = prospect_surplus(55, 21, 'AA', 'SP', fv_plus=False, ovr=55, pot=70)['total_surplus']
    opt  = prospect_surplus_with_option(55, 21, 'AA', 'SP', fv_plus=False, ovr=55, pot=70)
    assert opt == 104_017_760
    assert opt >= base

def test_option_value_ss():
    from prospect_value import prospect_surplus_with_option
    assert prospect_surplus_with_option(50, 20, 'A', 'SS', fv_plus=True, ovr=45, pot=65) == 61_351_339

def test_option_value_rp():
    from prospect_value import prospect_surplus_with_option
    assert prospect_surplus_with_option(45, 23, 'AAA', 'RP', fv_plus=False, ovr=42, pot=55) == 29_953_560

def test_option_value_cof():
    from prospect_value import prospect_surplus_with_option
    assert prospect_surplus_with_option(60, 19, 'A-Short', 'COF', fv_plus=False, ovr=50, pot=70) == 77_327_844


# ---------------------------------------------------------------------------
# Structural / invariant tests
# ---------------------------------------------------------------------------

def test_surplus_non_negative():
    """Surplus should never be negative (floor at 0)."""
    from prospect_value import prospect_surplus
    result = prospect_surplus(40, 24, 'AAA', 'RP', ovr=35, pot=42)
    assert result['total_surplus'] >= 0

def test_higher_fv_higher_surplus():
    """FV 60 prospect should be worth more than FV 50 at same age/level/bucket."""
    from prospect_value import prospect_surplus
    s50 = prospect_surplus(50, 21, 'AA', 'SP', ovr=45, pot=60)['total_surplus']
    s60 = prospect_surplus(60, 21, 'AA', 'SP', ovr=55, pot=70)['total_surplus']
    assert s60 > s50

def test_younger_higher_surplus():
    """Younger prospect at same FV/level should be worth more."""
    from prospect_value import prospect_surplus
    s_young = prospect_surplus(55, 19, 'AA', 'SP', ovr=50, pot=65)['total_surplus']
    s_old   = prospect_surplus(55, 23, 'AA', 'SP', ovr=50, pot=65)['total_surplus']
    assert s_young > s_old

def test_option_gte_base():
    """Option value should always be >= base surplus."""
    from prospect_value import prospect_surplus, prospect_surplus_with_option
    for fv, age, level, bucket in [(50,21,'AA','SP'),(45,20,'A','SS'),(55,22,'AAA','RP')]:
        base = prospect_surplus(fv, age, level, bucket)['total_surplus']
        opt  = prospect_surplus_with_option(fv, age, level, bucket)
        assert opt >= base, f"Option < base for {bucket} FV{fv}"
