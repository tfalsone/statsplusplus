"""Guard test: the per-request league is the single source of truth.

``get_league_dir()`` resolves the process-global active league (from
``STATSPP_LEAGUE`` or ``app_config.json``). Web code must read the *per-request*
league via ``g.league_dir`` (``web_league_context.get_cfg()``/``get_db()``) — a
no-slug call inside a Flask request bypasses that and would silently serve the
global league (the cross-league draft-pool leak). The guard turns that latent
bug into a loud error.

An explicit ``STATSPP_LEAGUE`` override is an unambiguous selection (single-
league deploys, blueprint-only tests) and is honored even inside a request.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "src"))

from statsplusplus.config.league_context import get_league_dir  # noqa: E402


def test_no_slug_outside_request_resolves_global(monkeypatch):
    """CLI / background path: no-arg resolution works (global default)."""
    monkeypatch.setenv("STATSPP_LEAGUE", "emlb")
    assert get_league_dir().name == "emlb"


def test_explicit_slug_always_works(monkeypatch):
    """An explicit slug is honored regardless of context."""
    monkeypatch.delenv("STATSPP_LEAGUE", raising=False)
    assert get_league_dir("vmlb").name == "vmlb"


def test_no_slug_inside_request_without_override_raises(monkeypatch):
    """No-slug call inside a Flask request, with no STATSPP_LEAGUE override,
    is a bug — it bypasses the per-request league — and must raise."""
    flask = pytest.importorskip("flask")
    monkeypatch.delenv("STATSPP_LEAGUE", raising=False)
    app = flask.Flask(__name__)
    with app.test_request_context("/"):
        with pytest.raises(RuntimeError, match="single source of truth"):
            get_league_dir()


def test_no_slug_inside_request_with_override_honored(monkeypatch):
    """An explicit STATSPP_LEAGUE override is honored even inside a request
    (single-league deploys, blueprint-only tests that skip before_request)."""
    flask = pytest.importorskip("flask")
    monkeypatch.setenv("STATSPP_LEAGUE", "emlb")
    app = flask.Flask(__name__)
    with app.test_request_context("/"):
        assert get_league_dir().name == "emlb"


def test_explicit_slug_inside_request_works(monkeypatch):
    """Passing the (session) slug explicitly inside a request is the correct
    pattern and must not raise."""
    flask = pytest.importorskip("flask")
    monkeypatch.delenv("STATSPP_LEAGUE", raising=False)
    app = flask.Flask(__name__)
    with app.test_request_context("/"):
        assert get_league_dir("ppl").name == "ppl"
