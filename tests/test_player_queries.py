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
from player_queries import _build_evaluation_data

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


# ── _build_evaluation_data — component scores ────────────────────────────────

def test_build_evaluation_data_extracts_component_scores():
    """Component score fields are extracted from a ratings row dict."""
    rd = {
        "composite_score": 56, "ceiling_score": 62,
        "tool_only_score": 54, "secondary_composite": None,
        "ovr": 55, "pot": 60,
        "offensive_grade": 55, "baserunning_value": 50,
        "defensive_value": 45, "durability_score": None,
        "offensive_ceiling": 60,
    }
    result = _build_evaluation_data(rd, is_pitcher=False, norm_fn=lambda x: x)
    assert result["offensive_grade"] == 55
    assert result["baserunning_value"] == 50
    assert result["defensive_value"] == 45
    assert result["durability_score"] is None
    assert result["offensive_ceiling"] == 60


def test_build_evaluation_data_none_when_components_missing():
    """Legacy ratings row without component columns returns None for all component fields."""
    rd = {
        "composite_score": 56, "ceiling_score": 62,
        "tool_only_score": 54, "secondary_composite": None,
        "ovr": 55, "pot": 60,
    }
    result = _build_evaluation_data(rd, is_pitcher=False, norm_fn=lambda x: x)
    assert result["offensive_grade"] is None
    assert result["baserunning_value"] is None
    assert result["defensive_value"] is None
    assert result["durability_score"] is None
    assert result["offensive_ceiling"] is None


# ── _build_evaluation_data — positional context fields ────────────────────────

def test_build_evaluation_data_includes_positional_context_defaults():
    """Positional context fields default to zero/None when no data available."""
    rd = {
        "composite_score": 56, "ceiling_score": 62,
        "tool_only_score": 54, "secondary_composite": None,
        "ovr": 55, "pot": 60,
        "offensive_grade": 55, "baserunning_value": 50,
        "defensive_value": 45, "durability_score": None,
        "offensive_ceiling": 60,
    }
    result = _build_evaluation_data(rd, is_pitcher=False, norm_fn=lambda x: x)
    assert result["carrying_tool_bonus"] == 0.0
    assert result["carrying_tool_breakdown"] == []
    assert result["positional_percentile"] is None
    assert result["positional_median"] is None


def test_build_evaluation_data_reads_positional_percentile_from_rd():
    """Positional percentile and median are read from the ratings row dict."""
    rd = {
        "composite_score": 56, "ceiling_score": 62,
        "tool_only_score": 54, "secondary_composite": None,
        "ovr": 55, "pot": 60,
        "offensive_grade": 55, "baserunning_value": 50,
        "defensive_value": 45, "durability_score": None,
        "offensive_ceiling": 60,
        "positional_percentile": 72.5,
        "positional_median": 48,
    }
    result = _build_evaluation_data(rd, is_pitcher=False, norm_fn=lambda x: x)
    assert result["positional_percentile"] == 72.5
    assert result["positional_median"] == 48


def test_build_evaluation_data_empty_rd_returns_positional_defaults():
    """When rd is None, positional context fields are at defaults."""
    result = _build_evaluation_data(None, is_pitcher=False, norm_fn=lambda x: x)
    assert result["carrying_tool_bonus"] == 0.0
    assert result["carrying_tool_breakdown"] == []
    assert result["positional_percentile"] is None
    assert result["positional_median"] is None


def test_build_evaluation_data_pitcher_skips_carrying_tool_bonus():
    """Pitchers should not get carrying tool bonus even with position_bucket."""
    rd = {
        "composite_score": 56, "ceiling_score": 62,
        "tool_only_score": 54, "secondary_composite": None,
        "ovr": 55, "pot": 60,
        "offensive_grade": 55, "baserunning_value": None,
        "defensive_value": None, "durability_score": 50,
        "offensive_ceiling": 60,
        "cntct": 70, "gap": 65, "pow": 70, "eye": 65,
    }
    result = _build_evaluation_data(rd, is_pitcher=True, norm_fn=lambda x: x,
                                    position_bucket="SS")
    assert result["carrying_tool_bonus"] == 0.0
    assert result["carrying_tool_breakdown"] == []


# ── get_player_popup — stat line computation ─────────────────────────────────

def test_popup_hitter_has_valid_slashline():
    """Batting avg/obp/slg must be computed as floats, not integer division."""
    result = player_queries.get_player_popup(HITTER_ID)
    assert result is not None
    stats = result["stats"]
    assert stats is not None
    assert stats["avg"] is not None and stats["avg"] > 0, f"avg was {stats['avg']}"
    assert stats["obp"] is not None and stats["obp"] > 0
    assert stats["slg"] is not None and stats["slg"] > 0


def test_popup_pitcher_has_stats():
    result = player_queries.get_player_popup(PITCHER_ID)
    assert result is not None
    stats = result["stats"]
    assert stats is not None
    assert stats["era"] is not None
    assert stats["war"] is not None
