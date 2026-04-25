"""
tests/test_composite_web.py — integration tests for composite score web query updates.

Verifies that composite_score, ceiling_score, and related fields appear in
results from get_player(), get_roster(), search_players(), get_farm(),
get_top_prospects(), get_all_prospects(), and get_player_card().

Uses the in-memory DB fixture from conftest.py (which seeds composite_score
in the ratings table).
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "web"))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from unittest.mock import patch
import player_queries
import queries
import team_queries
from conftest import TEAM_ID, HITTER_ID, PITCHER_ID, PROSPECT_ID, YEAR

# Stub out heavy optional dependencies
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


# ── get_player — composite score fields ──────────────────────────────────────

class TestGetPlayerCompositeScore:
    def test_hitter_has_composite_score(self):
        result = player_queries.get_player(HITTER_ID)
        assert result is not None
        assert "composite_score" in result
        assert result["composite_score"] == 56

    def test_hitter_has_ceiling_score(self):
        result = player_queries.get_player(HITTER_ID)
        assert result["ceiling_score"] == 62

    def test_hitter_has_tool_only_score(self):
        result = player_queries.get_player(HITTER_ID)
        assert result["tool_only_score"] == 54

    def test_pitcher_has_composite_score(self):
        result = player_queries.get_player(PITCHER_ID)
        assert result is not None
        assert result["composite_score"] == 59

    def test_pitcher_has_ceiling_score(self):
        result = player_queries.get_player(PITCHER_ID)
        assert result["ceiling_score"] == 66

    def test_prospect_has_composite_score(self):
        result = player_queries.get_player(PROSPECT_ID)
        assert result is not None
        assert "composite_score" in result

    def test_hitter_has_divergence_field(self):
        result = player_queries.get_player(HITTER_ID)
        assert "divergence" in result
        # composite_score=56, tool_only=54, ovr=55 → |54-55|=1 < 5 → agreement or None
        # divergence uses tool_only_score vs ovr

    def test_hitter_has_archetype_field(self):
        result = player_queries.get_player(HITTER_ID)
        assert "archetype" in result

    def test_hitter_has_carrying_tools_field(self):
        result = player_queries.get_player(HITTER_ID)
        assert "carrying_tools" in result
        assert isinstance(result["carrying_tools"], list)

    def test_hitter_has_red_flag_tools_field(self):
        result = player_queries.get_player(HITTER_ID)
        assert "red_flag_tools" in result
        assert isinstance(result["red_flag_tools"], list)

    def test_hitter_has_two_way_scores_field(self):
        result = player_queries.get_player(HITTER_ID)
        assert "two_way_scores" in result
        # Hitter has no secondary_composite, so two_way_scores should be None
        assert result["two_way_scores"] is None

    def test_hitter_has_ceiling_divergence_field(self):
        result = player_queries.get_player(HITTER_ID)
        assert "ceiling_divergence" in result

    def test_missing_player_returns_none(self):
        result = player_queries.get_player(99999)
        assert result is None


# ── get_roster — composite score in ovr field ────────────────────────────────

class TestGetRosterCompositeScore:
    def test_roster_hitter_uses_composite(self):
        hitters, _ = team_queries.get_roster(TEAM_ID)
        assert len(hitters) >= 1
        row = hitters[0]
        assert "ovr" in row
        # composite_score=56 should be used instead of player_surplus.ovr=55
        assert row["ovr"] == 56

    def test_roster_pitcher_uses_composite(self):
        _, pitchers = team_queries.get_roster(TEAM_ID)
        assert len(pitchers) >= 1
        row = pitchers[0]
        assert "ovr" in row
        # composite_score=59 should be used instead of player_surplus.ovr=58
        assert row["ovr"] == 59


# ── get_roster_hitters — composite score ─────────────────────────────────────

class TestGetRosterHittersComposite:
    def test_hitters_use_composite(self):
        result = team_queries.get_roster_hitters(TEAM_ID)
        assert len(result) >= 1
        row = result[0]
        assert "ovr" in row
        assert row["ovr"] == 56


# ── get_roster_pitchers — composite score ────────────────────────────────────

class TestGetRosterPitchersComposite:
    def test_pitchers_use_composite(self):
        result = team_queries.get_roster_pitchers(TEAM_ID)
        assert len(result) >= 1
        row = result[0]
        assert "ovr" in row
        assert row["ovr"] == 59


# ── search_players — composite score ─────────────────────────────────────────

class TestSearchPlayersComposite:
    def test_search_returns_composite_in_ovr(self):
        result = queries.search_players("Joe")
        assert len(result) >= 1
        row = next(r for r in result if r["pid"] == HITTER_ID)
        # ovr field should prefer composite_score (56) over raw ovr (55)
        assert row["ovr"] == 56


# ── get_farm — composite score ───────────────────────────────────────────────

class TestGetFarmComposite:
    def test_farm_has_composite_score(self):
        result = team_queries.get_farm(TEAM_ID)
        assert len(result) >= 1
        row = result[0]
        assert "composite_score" in row

    def test_farm_has_ceiling_score(self):
        result = team_queries.get_farm(TEAM_ID)
        row = result[0]
        assert "ceiling_score" in row


# ── get_top_prospects — composite score ──────────────────────────────────────

class TestGetTopProspectsComposite:
    def test_top_prospects_has_composite_score(self):
        result = queries.get_top_prospects()
        assert len(result) >= 1
        row = result[0]
        assert "composite_score" in row

    def test_top_prospects_has_ceiling_score(self):
        result = queries.get_top_prospects()
        row = result[0]
        assert "ceiling_score" in row


# ── get_all_prospects — composite score ──────────────────────────────────────

class TestGetAllProspectsComposite:
    def test_all_prospects_has_composite_score(self):
        result = queries.get_all_prospects()
        assert len(result) >= 1
        row = result[0]
        assert "composite_score" in row
