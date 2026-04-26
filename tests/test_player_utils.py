"""
tests/test_player_utils.py — Unit tests for scripts/player_utils.py

Covers: norm(), calc_fv(), peak_war_from_ovr(), aging_mult()
All tests are pure math — no DB or API required.

Note: peak_war_from_ovr() results depend on calibrated model weights loaded
from model_weights.json. Tests use invariant/structural assertions rather than
exact values to remain stable across recalibrations.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _sp():
    return {'Ovr':55,'Pot':70,'Age':21,'_is_pitcher':True,'_bucket':'SP','_norm_age':26,'_level':'aa',
            'PotFst':65,'PotSnk':0,'PotCrv':60,'PotSld':55,'PotChg':50,'PotSplt':0,'PotCutt':0,
            'PotCirChg':0,'PotScr':0,'PotFrk':0,'PotKncrv':0,'PotKnbl':0,
            'PotStf':65,'PotMov':60,'PotCtrl':55,'Stm':55,'WrkEthic':'N','Acc':'A','_mlb_median':50}

def _ss():
    return {'Ovr':50,'Pot':65,'Age':20,'_is_pitcher':False,'_bucket':'SS','_norm_age':24,'_level':'a',
            'PotCntct':60,'PotGap':55,'PotPow':50,'PotEye':55,'PotKs':50,
            'PotSS':60,'SS':45,'WrkEthic':'H','Acc':'A','_mlb_median':48}

def _rp():
    return {'Ovr':48,'Pot':60,'Age':24,'_is_pitcher':True,'_bucket':'RP','_norm_age':26,'_level':'aaa',
            'PotFst':65,'PotSnk':0,'PotCrv':55,'PotSld':60,'PotChg':0,'PotSplt':0,'PotCutt':0,
            'PotCirChg':0,'PotScr':0,'PotFrk':0,'PotKncrv':0,'PotKnbl':0,
            'PotStf':60,'PotMov':55,'PotCtrl':50,'Stm':30,'WrkEthic':'N','Acc':'A','_mlb_median':50}


# ---------------------------------------------------------------------------
# norm()
# ---------------------------------------------------------------------------

def test_norm_100scale_high():
    from player_utils import norm, init_ratings_scale
    init_ratings_scale('1-100')
    assert norm(75) == 65

def test_norm_100scale_mid():
    from player_utils import norm, init_ratings_scale
    init_ratings_scale('1-100')
    assert norm(50) == 50

def test_norm_80scale_exact():
    from player_utils import norm, init_ratings_scale
    init_ratings_scale('20-80')
    assert norm(65) == 65

def test_norm_80scale_rounds():
    from player_utils import norm, init_ratings_scale
    init_ratings_scale('20-80')
    assert norm(43) == 45

def test_norm_none_returns_none():
    from player_utils import norm, init_ratings_scale
    init_ratings_scale('1-100')
    assert norm(None) is None

def test_norm_zero_returns_none():
    from player_utils import norm, init_ratings_scale
    init_ratings_scale('1-100')
    assert norm(0) is None


# ---------------------------------------------------------------------------
# calc_fv()
# ---------------------------------------------------------------------------

def test_calc_fv_sp():
    from player_utils import calc_fv
    fv, risk = calc_fv(_sp())
    assert fv == 60
    assert risk in ("Low", "Medium", "High", "Extreme")

def test_calc_fv_ss():
    from player_utils import calc_fv
    fv, risk = calc_fv(_ss())
    assert fv == 55
    assert risk in ("Low", "Medium", "High", "Extreme")

def test_calc_fv_rp():
    from player_utils import calc_fv
    fv, risk = calc_fv(_rp())
    assert fv == 45
    assert risk in ("Low", "Medium", "High", "Extreme")

def test_calc_fv_rp_capped_at_55():
    """RPs should never exceed FV 55 regardless of ratings."""
    from player_utils import calc_fv
    p = _rp()
    p['Pot'] = 80
    p['Ovr'] = 70
    fv, _ = calc_fv(p)
    assert fv <= 55


# ---------------------------------------------------------------------------
# peak_war_from_ovr()
# ---------------------------------------------------------------------------

def test_peak_war_sp():
    """SP at OVR 60 should produce reasonable WAR (2-4 range)."""
    from player_utils import peak_war_from_ovr
    war = peak_war_from_ovr(60, 'SP')
    assert 2.0 <= war <= 4.0

def test_peak_war_rp():
    """RP at OVR 55 should produce lower WAR than SP (RP cap)."""
    from player_utils import peak_war_from_ovr
    war = peak_war_from_ovr(55, 'RP')
    assert 0.5 <= war <= 1.5

def test_peak_war_ss():
    """SS at OVR 65 should produce premium-position WAR."""
    from player_utils import peak_war_from_ovr
    war = peak_war_from_ovr(65, 'SS')
    assert 4.0 <= war <= 6.0

def test_peak_war_cof():
    """COF at OVR 55 should produce moderate WAR."""
    from player_utils import peak_war_from_ovr
    war = peak_war_from_ovr(55, 'COF')
    assert 2.0 <= war <= 4.0

def test_peak_war_monotonic():
    """Higher Ovr should always produce higher WAR for the same bucket."""
    from player_utils import peak_war_from_ovr
    for bucket in ('SP', 'RP', 'SS', 'COF'):
        wars = [peak_war_from_ovr(ovr, bucket) for ovr in range(40, 85, 5)]
        assert wars == sorted(wars), f"{bucket} WAR not monotonic: {wars}"


# ---------------------------------------------------------------------------
# aging_mult()
# ---------------------------------------------------------------------------

def test_aging_sp_at_peak():
    from player_utils import aging_mult
    assert aging_mult(28, 'SP') == 1.0

def test_aging_hitter_at_peak():
    from player_utils import aging_mult
    assert aging_mult(28, 'SS') == 1.0

def test_aging_sp_decline():
    from player_utils import aging_mult
    assert round(aging_mult(33, 'SP'), 4) == 0.6600

def test_aging_hitter_decline():
    from player_utils import aging_mult
    assert round(aging_mult(30, 'SS'), 4) == 0.9200

def test_aging_rp_late():
    from player_utils import aging_mult
    assert round(aging_mult(35, 'RP'), 4) == 0.4300

def test_aging_monotonic_decline():
    """Aging multiplier should be non-increasing from peak age onward."""
    from player_utils import aging_mult
    for bucket in ('SP', 'SS'):
        mults = [aging_mult(age, bucket) for age in range(28, 41)]
        assert mults == sorted(mults, reverse=True), f"{bucket} aging not monotonic"
