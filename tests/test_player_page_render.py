"""
tests/test_player_page_render.py — template rendering tests for the player page.

Verifies that player.html renders without Jinja2 errors for all player types:
MLB hitters, MLB pitchers, and prospects (no stats). This catches macro scoping
issues where a macro defined inside a conditional block is called from another branch.

Uses the Flask test client with the in-memory DB fixture from conftest.py.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "web"))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import pytest
from unittest.mock import patch, MagicMock
from conftest import TEAM_ID, HITTER_ID, PITCHER_ID, PROSPECT_ID


@pytest.fixture(scope="module")
def client():
    """Create a Flask test client with the before_request handler patched out."""
    from app import app
    app.config["TESTING"] = True

    # Patch the before_request to skip league context setup (already mocked by conftest)
    original_before = app.before_request_funcs.get(None, [])[:]

    def _noop_league_context():
        from flask import g
        g.league_slug = "test"
        g.league_dir = Path("/tmp")
        g.league_ready = True
        g.league_config = MagicMock()

    app.before_request_funcs[None] = [_noop_league_context]

    with app.test_client() as c:
        yield c

    # Restore
    app.before_request_funcs[None] = original_before


class TestPlayerPageRender:
    """Verify player.html renders without template errors for all player types."""

    def test_hitter_page_renders(self, client):
        """MLB hitter page (has_stats=True) should render without error."""
        resp = client.get(f"/player/{HITTER_ID}")
        assert resp.status_code == 200
        assert b"Joe Hitter" in resp.data

    def test_pitcher_page_renders(self, client):
        """MLB pitcher page (has_stats=True) should render without error."""
        resp = client.get(f"/player/{PITCHER_ID}")
        assert resp.status_code == 200
        assert b"Sam Pitcher" in resp.data

    def test_prospect_page_renders(self, client):
        """Prospect page (has_stats=False) should render without error.

        This is the critical test — it catches macros defined inside the
        has_stats block that are called from the else (prospect) branch.
        """
        resp = client.get(f"/player/{PROSPECT_ID}")
        assert resp.status_code == 200
        assert b"Bob Prospect" in resp.data

    def test_missing_player_returns_404(self, client):
        resp = client.get("/player/99999")
        assert resp.status_code == 404


    def test_player_page_renders_component_scores(self, client):
        """Player page shows component score labels when component scores are present."""
        resp = client.get(f"/player/{HITTER_ID}")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "Component Scores" in html
        assert "Offense" in html
        assert "Baserunning" in html
        assert "Def" in html

    def test_player_page_falls_back_when_no_components(self, client):
        """Player page shows Comp / Ceil fallback when component scores are absent."""
        resp = client.get(f"/player/{PROSPECT_ID}")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "Comp / Ceil" in html
