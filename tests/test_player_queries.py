"""
tests/test_player_queries.py — integration tests for web/player_queries.py

Verifies get_player() returns without error and produces the expected shape
for hitters, pitchers, and prospects.
Uses the in-memory DB fixture from conftest.py.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "web"))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from unittest.mock import patch
import player_queries
from conftest import TEAM_ID, HITTER_ID, PITCHER_ID, PROSPECT_ID, YEAR

# Stub out heavy optional dependencies that aren't needed for shape tests
_STUB_PATCHES = [
    patch("player_queries.get_hitter_percentiles", return_value=None),
    patch("player_queries.get_pitcher_percentiles", return_value=None),
    patch("player_queries.get_fielding_percentiles", return_value=None),
]


def setup_module(_):
    for p in _STUB_PATCHES:
        p.start()


def teardown_module(_):
    for p in _STUB_PATCHES:
        p.stop()


# ── get_player — hitter ──────────────────────────────────────────────────────

def test_get_player_hitter_not_none():
    result = player_queries.get_player(HITTER_ID)
    assert result is not None

def test_get_player_hitter_top_level_keys():
    result = player_queries.get_player(HITTER_ID)
    for key in ("pid", "name", "age", "pos", "team", "level",
                "is_pitcher", "ratings", "bat_stats", "pit_stats",
                "valuation", "contract"):
        assert key in result, f"Missing key: {key}"

def test_get_player_hitter_is_not_pitcher():
    result = player_queries.get_player(HITTER_ID)
    assert result["is_pitcher"] is False

def test_get_player_hitter_has_ratings():
    result = player_queries.get_player(HITTER_ID)
    r = result["ratings"]
    assert r is not None
    for key in ("ovr", "pot", "hit", "gap", "power", "eye"):
        assert key in r, f"Missing ratings key: {key}"

def test_get_player_hitter_has_bat_stats():
    result = player_queries.get_player(HITTER_ID)
    assert len(result["bat_stats"]) >= 1
    row = result["bat_stats"][0]
    for key in ("year", "pa", "avg", "obp", "slg", "war"):
        assert key in row, f"Missing stat key: {key}"

def test_get_player_hitter_has_contract():
    result = player_queries.get_player(HITTER_ID)
    assert result["contract"] is not None
    assert "remaining" in result["contract"]

def test_get_player_hitter_has_valuation():
    result = player_queries.get_player(HITTER_ID)
    v = result["valuation"]
    assert v is not None
    assert v.get("type") == "MLB"
    assert "surplus" in v


# ── get_player — pitcher ─────────────────────────────────────────────────────

def test_get_player_pitcher_not_none():
    result = player_queries.get_player(PITCHER_ID)
    assert result is not None

def test_get_player_pitcher_is_pitcher():
    result = player_queries.get_player(PITCHER_ID)
    assert result["is_pitcher"] is True

def test_get_player_pitcher_has_ratings():
    result = player_queries.get_player(PITCHER_ID)
    r = result["ratings"]
    assert r is not None
    for key in ("ovr", "pot", "stuff", "movement", "control"):
        assert key in r, f"Missing pitcher ratings key: {key}"

def test_get_player_pitcher_has_pit_stats():
    result = player_queries.get_player(PITCHER_ID)
    assert len(result["pit_stats"]) >= 1
    row = result["pit_stats"][0]
    for key in ("year", "ip", "era", "k", "war"):
        assert key in row, f"Missing stat key: {key}"

def test_get_player_pitcher_has_valuation():
    result = player_queries.get_player(PITCHER_ID)
    v = result["valuation"]
    assert v is not None
    assert v.get("type") == "MLB"


# ── get_player — prospect ────────────────────────────────────────────────────

def test_get_player_prospect_not_none():
    result = player_queries.get_player(PROSPECT_ID)
    assert result is not None

def test_get_player_prospect_has_valuation():
    result = player_queries.get_player(PROSPECT_ID)
    v = result["valuation"]
    assert v is not None
    assert v.get("type") == "prospect"
    assert "fv" in v and "surplus" in v

def test_get_player_prospect_no_bat_stats():
    # Prospects have no MLB stats in our fixture
    result = player_queries.get_player(PROSPECT_ID)
    assert result["bat_stats"] == []


# ── get_player — missing player ──────────────────────────────────────────────

def test_get_player_missing_returns_none():
    result = player_queries.get_player(99999)
    assert result is None
