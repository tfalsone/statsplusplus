"""
tests/test_player_utils.py — Unit tests for scripts/player_utils.py

Covers: norm(), calc_fv(), peak_war_from_ovr(), aging_mult()
All tests are pure math — no DB or API required.
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
            'PotStf':65,'PotMov':60,'PotCtrl':55,'Stm':55,'WrkEthic':'N','Acc':'A'}

def _ss():
    return {'Ovr':50,'Pot':65,'Age':20,'_is_pitcher':False,'_bucket':'SS','_norm_age':24,'_level':'a',
            'PotCntct':60,'PotGap':55,'PotPow':50,'PotEye':55,'PotKs':50,
            'PotSS':60,'SS':45,'WrkEthic':'H','Acc':'A'}

def _rp():
    return {'Ovr':48,'Pot':60,'Age':24,'_is_pitcher':True,'_bucket':'RP','_norm_age':26,'_level':'aaa',
            'PotFst':65,'PotSnk':0,'PotCrv':55,'PotSld':60,'PotChg':0,'PotSplt':0,'PotCutt':0,
            'PotCirChg':0,'PotScr':0,'PotFrk':0,'PotKncrv':0,'PotKnbl':0,
            'PotStf':60,'PotMov':55,'PotCtrl':50,'Stm':30,'WrkEthic':'N','Acc':'A'}


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
    assert calc_fv(_sp()) == (65, False)

def test_calc_fv_ss():
    from player_utils import calc_fv
    assert calc_fv(_ss()) == (60, False)

def test_calc_fv_rp():
    from player_utils import calc_fv
    assert calc_fv(_rp()) == (50, False)

def test_calc_fv_rp_capped_at_50():
    """RPs should never exceed FV 50 regardless of ratings."""
    from player_utils import calc_fv
    p = _rp()
    p['Pot'] = 80
    p['Ovr'] = 70
    fv, _ = calc_fv(p)
    assert fv <= 50


# ---------------------------------------------------------------------------
# peak_war_from_ovr()
# ---------------------------------------------------------------------------

def test_peak_war_sp():
    from player_utils import peak_war_from_ovr
    assert round(peak_war_from_ovr(60, 'SP'), 3) == 2.800

def test_peak_war_rp():
    from player_utils import peak_war_from_ovr
    assert round(peak_war_from_ovr(55, 'RP'), 3) == 0.700

def test_peak_war_ss():
    from player_utils import peak_war_from_ovr
    assert round(peak_war_from_ovr(65, 'SS'), 3) == 4.500

def test_peak_war_cof():
    from player_utils import peak_war_from_ovr
    assert round(peak_war_from_ovr(55, 'COF'), 3) == 2.200

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
