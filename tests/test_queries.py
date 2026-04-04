"""
tests/test_queries.py — integration tests for web/queries.py

Verifies each query function returns without error and produces the expected shape.
Uses the in-memory DB fixture from conftest.py.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "web"))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import queries
from conftest import TEAM_ID, HITTER_ID, PITCHER_ID, PROSPECT_ID, YEAR


# ── get_top_prospects ────────────────────────────────────────────────────────

def test_get_top_prospects_returns_list():
    result = queries.get_top_prospects()
    assert isinstance(result, list)

def test_get_top_prospects_shape():
    result = queries.get_top_prospects()
    assert len(result) >= 1
    row = result[0]
    for key in ("rank", "name", "fv", "fv_str", "bucket", "level", "surplus", "pid"):
        assert key in row, f"Missing key: {key}"

def test_get_top_prospects_ranked():
    result = queries.get_top_prospects()
    assert result[0]["rank"] == 1


# ── get_all_prospects ────────────────────────────────────────────────────────

def test_get_all_prospects_returns_list():
    result = queries.get_all_prospects()
    assert isinstance(result, list)

def test_get_all_prospects_fv_filter():
    result = queries.get_all_prospects()
    assert all(r["fv"] >= 40 for r in result)


# ── get_batting_leaders ──────────────────────────────────────────────────────

def test_get_batting_leaders_returns_dict():
    result = queries.get_batting_leaders(yr=YEAR)
    assert isinstance(result, dict)
    assert "All" in result

def test_get_batting_leaders_has_categories():
    result = queries.get_batting_leaders(yr=YEAR)
    for cat in ("HR", "RBI", "AVG", "OPS", "SB", "WAR"):
        assert cat in result["All"], f"Missing batting category: {cat}"

def test_get_batting_leaders_entries_have_shape():
    result = queries.get_batting_leaders(yr=YEAR)
    for cat, entries in result["All"].items():
        for e in entries:
            assert "pid" in e and "name" in e and "val" in e


# ── get_pitching_leaders ─────────────────────────────────────────────────────

def test_get_pitching_leaders_returns_dict():
    result = queries.get_pitching_leaders(yr=YEAR)
    assert isinstance(result, dict)
    assert "All" in result

def test_get_pitching_leaders_has_categories():
    result = queries.get_pitching_leaders(yr=YEAR)
    for cat in ("ERA", "W", "K", "SV", "WHIP", "WAR"):
        assert cat in result["All"], f"Missing pitching category: {cat}"


# ── search_players ───────────────────────────────────────────────────────────

def test_search_players_returns_list():
    result = queries.search_players("Joe")
    assert isinstance(result, list)

def test_search_players_finds_hitter():
    result = queries.search_players("Joe")
    assert any(r["pid"] == HITTER_ID for r in result)

def test_search_players_shape():
    result = queries.search_players("Joe")
    assert len(result) >= 1
    row = result[0]
    for key in ("pid", "name", "age", "level", "team", "pos"):
        assert key in row, f"Missing key: {key}"

def test_search_players_short_query_returns_empty():
    result = queries.search_players("J")
    assert result == []

def test_search_players_no_match_returns_empty():
    result = queries.search_players("zzznomatch")
    assert result == []
