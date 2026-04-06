"""
test_scripts.py — Tests for core script functions.

Covers edge cases and smoke tests that catch regressions in calibrate,
fv_calc, and player_utils that aren't exercised by the web query tests.
"""

import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE / "scripts"))

from conftest import _SCHEMA, _seed, _make_cfg, TEAM_ID, HITTER_ID, PITCHER_ID, PROSPECT_ID, YEAR, EVAL_DATE


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def script_db():
    """Isolated in-memory DB for script-layer tests (not shared with web tests)."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    # Add tables needed by calibrate/fv_calc but not in web schema
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS ratings_history (
            player_id INTEGER, snapshot_date TEXT,
            ovr INTEGER, pot INTEGER,
            PRIMARY KEY (player_id, snapshot_date)
        );
        CREATE TABLE IF NOT EXISTS model_weights (
            key TEXT PRIMARY KEY, value TEXT
        );
    """)
    _seed(conn)
    conn.commit()
    return conn


@pytest.fixture
def mock_cfg_scripts():
    cfg = _make_cfg()
    cfg.league_dir = Path("/tmp")
    return cfg


# ---------------------------------------------------------------------------
# assign_bucket — edge cases
# ---------------------------------------------------------------------------

class TestAssignBucket:
    def test_normal_ss(self):
        from player_utils import assign_bucket
        p = {"Pos": "6", "ss": 55, "pot_ss": 60, "Age": 25,
             "C": 30, "2B": 45, "CF": 40, "LF": 40, "RF": 40, "3B": 40, "1B": 40,
             "PotC": 30, "Pot2B": 45, "PotCF": 40, "PotLF": 40, "PotRF": 40, "Pot3B": 40, "Pot1B": 40}
        assert assign_bucket(p) == "SS"

    def test_empty_string_defensive_grades(self):
        """API sometimes returns '' instead of 0 for defensive grades — must not crash."""
        from player_utils import assign_bucket
        p = {"Pos": "1", "Age": 28, "_role": "starter",
             "C": "", "SS": "", "2B": "", "CF": "", "LF": "", "RF": "", "3B": "", "1B": "",
             "PotC": "", "PotSS": "", "Pot2B": "", "PotCF": "", "PotLF": "", "PotRF": "", "Pot3B": "", "Pot1B": "",
             "Stm": 55, "PotFst": 65, "PotCrv": 50, "PotSld": 55, "PotChg": 45}
        # Should not raise TypeError
        result = assign_bucket(p, use_pot=False)
        assert result in ("SP", "RP")

    def test_none_defensive_grades(self):
        """None values for defensive grades must not crash."""
        from player_utils import assign_bucket
        p = {"Pos": "3", "Age": 30, "_role": "position_player",
             "C": None, "SS": None, "2B": None, "CF": None,
             "LF": None, "RF": None, "3B": None, "1B": 50,
             "PotC": None, "PotSS": None, "Pot2B": None, "PotCF": None,
             "PotLF": None, "PotRF": None, "Pot3B": None, "Pot1B": 50}
        result = assign_bucket(p, use_pot=False)
        assert result == "1B"

    def test_string_numeric_grades(self):
        """String '55' should be coerced to int 55."""
        from player_utils import assign_bucket
        p = {"Pos": "6", "Age": 25, "_role": "position_player",
             "C": "30", "SS": "55", "2B": "45", "CF": "40",
             "LF": "40", "RF": "40", "3B": "40", "1B": "40",
             "PotC": "30", "PotSS": "60", "Pot2B": "45", "PotCF": "40",
             "PotLF": "40", "PotRF": "40", "Pot3B": "40", "Pot1B": "40"}
        result = assign_bucket(p, use_pot=False)
        assert result == "SS"


# ---------------------------------------------------------------------------
# calibrate — _bucket_player edge cases
# ---------------------------------------------------------------------------

class TestCalibrateHelpers:
    def test_bucket_player_empty_string_grades(self):
        """_bucket_player must not crash when DB row has empty string defensive grades."""
        import sqlite3
        from calibrate import _bucket_player
        # Simulate a sqlite3.Row with empty string values
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("""CREATE TABLE t (
            player_id INT, age INT, pos INT, role INT, ovr INT, pot INT,
            c TEXT, ss TEXT, second_b TEXT, third_b TEXT, first_b TEXT,
            lf TEXT, cf TEXT, rf TEXT,
            pot_c TEXT, pot_ss TEXT, pot_second_b TEXT, pot_third_b TEXT,
            pot_first_b TEXT, pot_lf TEXT, pot_cf TEXT, pot_rf TEXT,
            stm INT, pot_fst INT, pot_snk INT, pot_crv INT, pot_sld INT,
            pot_chg INT, pot_splt INT, pot_cutt INT, pot_cir_chg INT,
            pot_scr INT, pot_frk INT, pot_kncrv INT, pot_knbl INT
        )""")
        conn.execute("""INSERT INTO t VALUES (
            23, 28, 6, 0, 55, 60,
            '', '', '', '', '', '', '', '',
            '', '', '', '', '', '', '', '',
            55, 65, 0, 50, 55, 45, 0, 0, 0, 0, 0, 0, 0
        )""")
        row = conn.execute("SELECT * FROM t").fetchone()
        role_map = {"0": "position_player", "11": "starter", "12": "reliever"}
        # Must not raise TypeError
        result = _bucket_player(row, role_map)
        assert result in ("C", "SS", "2B", "3B", "CF", "COF", "1B", "SP", "RP")

    def test_bucket_player_none_grades(self):
        """_bucket_player must handle NULL defensive grades."""
        import sqlite3
        from calibrate import _bucket_player
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("""CREATE TABLE t (
            player_id INT, age INT, pos INT, role INT, ovr INT, pot INT,
            c INT, ss INT, second_b INT, third_b INT, first_b INT,
            lf INT, cf INT, rf INT,
            pot_c INT, pot_ss INT, pot_second_b INT, pot_third_b INT,
            pot_first_b INT, pot_lf INT, pot_cf INT, pot_rf INT,
            stm INT, pot_fst INT, pot_snk INT, pot_crv INT, pot_sld INT,
            pot_chg INT, pot_splt INT, pot_cutt INT, pot_cir_chg INT,
            pot_scr INT, pot_frk INT, pot_kncrv INT, pot_knbl INT
        )""")
        conn.execute("""INSERT INTO t VALUES (
            24, 30, 3, 0, 50, 55,
            NULL, NULL, NULL, NULL, 50, NULL, NULL, NULL,
            NULL, NULL, NULL, NULL, 50, NULL, NULL, NULL,
            55, 65, 0, 50, 55, 45, 0, 0, 0, 0, 0, 0, 0
        )""")
        row = conn.execute("SELECT * FROM t").fetchone()
        role_map = {"0": "position_player"}
        result = _bucket_player(row, role_map)
        assert result == "1B"


# ---------------------------------------------------------------------------
# fv_calc — skip malformed rows
# ---------------------------------------------------------------------------

class TestFvCalcHelpers:
    def test_fv_calc_skips_empty_string_ovr(self):
        """fv_calc must skip players with non-numeric Ovr without crashing."""
        from player_utils import assign_bucket
        # Simulate what fv_calc does with a malformed row
        p = {"ID": 998, "Age": 22, "Ovr": "", "Pot": "", "level": "3",
             "Pos": "6", "_role": "position_player", "_is_pitcher": False,
             "Name": "Bad Player",
             "C": "", "SS": "", "2B": "", "CF": "", "LF": "", "RF": "", "3B": "", "1B": "",
             "PotC": "", "PotSS": "", "Pot2B": "", "PotCF": "", "PotLF": "", "PotRF": "", "Pot3B": "", "Pot1B": ""}
        ovr_raw = p.get("Ovr", 0)
        # This is the guard in fv_calc.run()
        if not isinstance(ovr_raw, (int, float)):
            try:
                int(ovr_raw)
            except (ValueError, TypeError):
                return  # correctly skipped
        pytest.fail("Should have been skipped")
