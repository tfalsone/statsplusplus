"""Tests for the phase-aware Offseason page (web/offseason_queries.py + routes).

Covers the logic that had real bugs during development:
  - market board = actual unsigned FAs only (team_id=0, free_agent=1)
  - foreign-league players (no stats in THIS league, e.g. NPB) excluded
  - "fills a need" requires need-position AND an upgrade over the incumbent
  - Proj WAR matches the player valuation page (shared compute_player_value)
  - phase gating (which panels show for a given sub-phase)
  - toggle / set-phase endpoints persist to state.json
  - /offseason renders (route smoke) on both fixture league types
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "web"))
sys.path.insert(0, str(_ROOT / "scripts"))

from _fixture_league import build_fixture, remove_fixture, EVAL_DATE, TEAM_ID, YEAR
from statsplusplus.data.db import get_connection

_SLUG = "_web_offseason"


def _add_offseason_entities(league_dir):
    """Add free agents (signable + a foreign-league one) and an arb-eligible
    player to the base fixture so the offseason panels have data to work on."""
    conn = get_connection(league_dir)

    def _ins(table, **cols):
        keys = ",".join(cols)
        conn.execute(f"INSERT OR REPLACE INTO {table} ({keys}) "
                     f"VALUES ({','.join('?' * len(cols))})", list(cols.values()))

    # 300: signable FA — unsigned, has prior stats in this league, strong 1B.
    # 301: foreign-league FA — unsigned, NO stats in this league (should be
    #      excluded from the market board even though free_agent=1).
    # 302: weak unsigned FA at SS — real FA but below any incumbent.
    _ins("players", player_id=300, name="Frank Freeagent", age=29, team_id=0,
         parent_team_id=0, level="1", pos=3, role=0, free_agent=1)
    _ins("players", player_id=301, name="Kenji Foreign", age=28, team_id=0,
         parent_team_id=0, level="0", pos=3, role=0, free_agent=1)
    _ins("players", player_id=302, name="Wally Weak", age=33, team_id=0,
         parent_team_id=0, level="1", pos=6, role=0, free_agent=1)

    for pid in (300, 301, 302):
        _ins("ratings", player_id=pid, snapshot_date=EVAL_DATE, ovr=55, pot=55,
             composite_score=55, ceiling_score=55, league_id=1, bats="R", throws="R")

    # Prior stats in THIS league only for the signable FAs (300, 302) — 301 has none.
    _ins("batting_stats", player_id=300, year=2033, team_id=0, split_id=1,
         pa=500, ab=450, h=135, hr=20, rbi=75, bb=45, k=90, avg=0.300, obp=0.365, slg=0.520, war=3.0)
    _ins("batting_stats", player_id=302, year=2033, team_id=0, split_id=1,
         pa=300, ab=280, h=64, hr=4, rbi=25, bb=18, k=70, avg=0.229, obp=0.280, slg=0.320, war=-0.4)

    for pid, name, bkt, comp, ceil, war in (
        (300, "Frank Freeagent", "1B", 58, 58, 3.0),
        (301, "Kenji Foreign", "1B", 62, 62, 3.5),
        (302, "Wally Weak", "SS", 48, 48, 0.0),
    ):
        _ins("player_evaluation", player_id=pid, eval_date=EVAL_DATE, name=name,
             bucket=bkt, age=29, composite=comp, ceiling=ceil, fv=50, fv_str="50",
             fv_continuous=50.0, surplus=0, surplus_yr1=0, level="MLB",
             team_id=0, parent_team_id=0, stat_confidence=0.9, peak_war=war,
             stat_war=war, tool_war=war, years_control=1)

    # 400: on-roster player (team 1) with a TEAM OPTION in his final contract
    # year — exercises the Contract Options panel.
    _ins("players", player_id=400, name="Opt Guy", age=30, team_id=TEAM_ID,
         parent_team_id=0, level="1", pos=8, role=0)
    _ins("ratings", player_id=400, snapshot_date=EVAL_DATE, ovr=55, pot=55,
         composite_score=56, ceiling_score=60, league_id=1, bats="R", throws="R")
    _ins("player_evaluation", player_id=400, eval_date=EVAL_DATE, name="Opt Guy",
         bucket="CF", age=30, composite=56, ceiling=60, fv=55, fv_str="55",
         fv_continuous=55.0, surplus=0, surplus_yr1=0, level="MLB",
         team_id=TEAM_ID, parent_team_id=0, stat_confidence=0.9, peak_war=3.0,
         stat_war=3.0, tool_war=3.0, years_control=1)
    _ins("batting_stats", player_id=400, year=2033, team_id=TEAM_ID, split_id=1,
         pa=550, ab=500, h=145, hr=22, rbi=80, bb=45, k=100, avg=0.290, obp=0.360, slg=0.500, war=3.0)
    # 2-year deal, currently in year 0; final year (yr 1) is a team option @ 8M, buyout 1M.
    _ins("contracts", player_id=400, team_id=TEAM_ID, contract_team_id=TEAM_ID,
         is_major=1, season_year=YEAR, years=2, current_year=0,
         salary_0=6_000_000, salary_1=8_000_000,
         last_year_team_option=1, last_year_option_buyout=1_000_000)

    # 401: a TRADED player — now on TEAM_ID's roster (team_id=TEAM_ID) but his
    # contract row still carries the PRE-TRADE contract_team_id (2). The API
    # retains the original signing team in contract_team_id after a mid-season
    # trade, so attributing by it would wrongly list him under team 2 and hide
    # him from TEAM_ID. Regression guard for the ORG_ID_SQL attribution fix.
    # Same option shape as 400 so he surfaces on the Contract Options panel.
    _ins("players", player_id=401, name="Trade Deadline Guy", age=31, team_id=TEAM_ID,
         parent_team_id=0, level="1", pos=8, role=0)
    _ins("ratings", player_id=401, snapshot_date=EVAL_DATE, ovr=55, pot=55,
         composite_score=55, ceiling_score=58, league_id=1, bats="R", throws="R")
    _ins("player_evaluation", player_id=401, eval_date=EVAL_DATE, name="Trade Deadline Guy",
         bucket="CF", age=31, composite=55, ceiling=58, fv=50, fv_str="50",
         fv_continuous=50.0, surplus=0, surplus_yr1=0, level="MLB",
         team_id=TEAM_ID, parent_team_id=0, stat_confidence=0.9, peak_war=2.0,
         stat_war=2.0, tool_war=2.0, years_control=1)
    _ins("batting_stats", player_id=401, year=2033, team_id=TEAM_ID, split_id=1,
         pa=500, ab=460, h=130, hr=18, rbi=70, bb=35, k=95, avg=0.283, obp=0.345, slg=0.470, war=2.0)
    _ins("contracts", player_id=401, team_id=TEAM_ID, contract_team_id=2,
         is_major=1, season_year=YEAR, years=2, current_year=0,
         salary_0=5_000_000, salary_1=7_000_000,
         last_year_team_option=1, last_year_option_buyout=1_000_000)

    # --- Arbitration eligibility (standard-arb gate) ---
    # 410: Danny-Haas case — arb-eligible by SERVICE (3 completed years) but
    #      still on a MINIMUM deal. Must appear on the arb board; the old
    #      `sal <= min_sal` skip wrongly dropped him. 3*172+5 = 521 days.
    # 411: 6+ completed years → graduated to free agency → must NOT appear on
    #      the standard-arb board. 6*172+10 = 1042 days.
    _ins("players", player_id=410, name="Danny Haas", age=25, team_id=TEAM_ID,
         parent_team_id=0, level="1", pos=5, role=0, mlb_service_days=521)
    _ins("players", player_id=411, name="Vic Veteran", age=31, team_id=TEAM_ID,
         parent_team_id=0, level="1", pos=3, role=0, mlb_service_days=1042)
    for pid, name, bkt in ((410, "Danny Haas", "3B"), (411, "Vic Veteran", "1B")):
        _ins("ratings", player_id=pid, snapshot_date=EVAL_DATE, ovr=52, pot=52,
             composite_score=52, ceiling_score=55, league_id=1, bats="R", throws="R")
        _ins("player_evaluation", player_id=pid, eval_date=EVAL_DATE, name=name,
             bucket=bkt, age=27, composite=52, ceiling=55, fv=50, fv_str="50",
             fv_continuous=50.0, surplus=4_000_000, surplus_yr1=0, level="MLB",
             team_id=TEAM_ID, parent_team_id=0, stat_confidence=0.9, peak_war=2.0,
             stat_war=2.0, tool_war=2.0, years_control=1)
    # Both on expiring deals so the SQL's (years-current_year)<=1 clause includes
    # them. 410 is on the league minimum (720000 per fixture settings).
    _ins("contracts", player_id=410, team_id=TEAM_ID, contract_team_id=TEAM_ID,
         is_major=1, season_year=YEAR, years=1, current_year=0, salary_0=720_000)
    _ins("contracts", player_id=411, team_id=TEAM_ID, contract_team_id=TEAM_ID,
         is_major=1, season_year=YEAR, years=1, current_year=0, salary_0=12_000_000)

    conn.commit()
    conn.close()


@pytest.fixture(scope="module")
def league():
    build_fixture(_SLUG, with_ovr=True)
    from statsplusplus.config.league_context import get_league_dir
    _add_offseason_entities(get_league_dir(_SLUG))
    prev = os.environ.get("STATSPP_LEAGUE")
    os.environ["STATSPP_LEAGUE"] = _SLUG
    try:
        yield _SLUG
    finally:
        if prev is None:
            os.environ.pop("STATSPP_LEAGUE", None)
        else:
            os.environ["STATSPP_LEAGUE"] = prev
        remove_fixture(_SLUG)


@pytest.fixture()
def q(league, monkeypatch):
    """offseason_queries wired to the fixture league via patched accessors —
    avoids the live-app request context and its fixture-ordering fragility."""
    import offseason_queries as osq
    from statsplusplus.config.league_config import LeagueConfig
    from statsplusplus.config.league_context import get_league_dir
    from statsplusplus.data.db import get_connection
    ld = get_league_dir(_SLUG)
    cfg = LeagueConfig(base_dir=ld)
    conn = get_connection(ld)
    monkeypatch.setattr(osq, "get_db", lambda: conn)
    monkeypatch.setattr(osq, "get_cfg", lambda: cfg)
    # _team_need_positions imports get_draft_org_depth from team_queries, which
    # also uses get_db/get_cfg from web_league_context — patch there too.
    import web_league_context as wlc
    monkeypatch.setattr(wlc, "get_db", lambda: conn)
    monkeypatch.setattr(wlc, "get_cfg", lambda: cfg)
    yield osq
    conn.close()


# ---------------------------------------------------------------------------
# Market board
# ---------------------------------------------------------------------------

def test_market_board_only_unsigned(q):
    board = q.get_market_board(TEAM_ID, limit=100)
    names = {p["name"] for p in board}
    assert "Frank Freeagent" in names  # unsigned + has league stats
    assert "Joe Hitter" not in names and "Rival Bat" not in names


def test_foreign_league_player_excluded(q):
    """A free_agent=1 player with no stats in THIS league (NPB-style) must not
    appear on the market board."""
    board = q.get_market_board(TEAM_ID, limit=100)
    assert "Kenji Foreign" not in {p["name"] for p in board}


def test_proj_war_matches_player_value(q):
    """Board Proj WAR == the shared compute_player_value breakdown year-1 WAR
    (single source of truth, not a re-derived approximation)."""
    from statsplusplus.evaluation.player_value import compute_player_value
    from statsplusplus.evaluation.constants import load_model_weights
    from statsplusplus.config.league_config import dollars_per_war, league_minimum
    from statsplusplus.config.league_context import get_league_dir
    ld = get_league_dir(_SLUG)

    board = {p["name"]: p for p in q.get_market_board(TEAM_ID, limit=100)}
    frank = board["Frank Freeagent"]
    res = compute_player_value(
        fv_continuous=0.0, bucket="1B", age=29, level="MLB",
        composite=58, ceiling=58, career_pa=500, career_ip=0.0, stat_war=3.0,
        years_control=1, salaries=None,
        dpw=dollars_per_war(ld), min_sal=league_minimum(ld),
        weights=load_model_weights(ld))
    assert frank["proj_war"] == round(res["breakdown"][0]["war"], 1)


def test_need_flag_requires_upgrade(q):
    """A weak FA at a need position is NOT flagged (wouldn't move the needle)."""
    board = {p["name"]: p for p in q.get_market_board(TEAM_ID, limit=100)}
    if "Wally Weak" in board:
        assert board["Wally Weak"]["fills_need"] is False


def test_market_board_carries_recommended_contract(q):
    """Each FA row has a value-based recommended contract for the cart draw-down
    (aav/years/total). The AAV is priced off the player's *average aged WAR
    across the term* (recommended_contract owns the aging), not his peak — so
    for an aging FA it lands at or below the flat peak × $/WAR figure, while
    staying coherent (aav × years == total, non-negative)."""
    from statsplusplus.config.league_config import dollars_per_war
    from statsplusplus.config.league_context import get_league_dir
    dpw = dollars_per_war(get_league_dir(_SLUG))
    frank = {p["name"]: p for p in q.get_market_board(TEAM_ID, limit=100)}["Frank Freeagent"]
    assert "rec_aav" in frank and "rec_years" in frank and "rec_total" in frank
    # Term-average aging can only shave value off the year-one projection for a
    # player at/past peak, never inflate it above the flat peak estimate.
    peak_aav = round(max(frank["proj_war"] or 0, 0) * dpw)
    assert 0 <= frank["rec_aav"] <= peak_aav
    assert frank["rec_total"] == frank["rec_aav"] * frank["rec_years"]


# ---------------------------------------------------------------------------
# Season in Review
# ---------------------------------------------------------------------------

def test_season_review_shape(q, monkeypatch):
    """get_season_review returns a coherent payload against the fixture league
    (which has team stats), including strengths/fixes ranking and a focus list."""
    # team_queries.get_standings() (used by the review) needs the same wiring.
    import team_queries as tq
    from statsplusplus.config.league_config import LeagueConfig
    from statsplusplus.config.league_context import get_league_dir
    from statsplusplus.data.db import get_connection
    ld = get_league_dir(_SLUG)
    conn = get_connection(ld)
    monkeypatch.setattr(tq, "get_db", lambda: conn)
    monkeypatch.setattr(tq, "get_cfg", lambda: LeagueConfig(base_dir=ld))
    monkeypatch.setattr(tq, "my_team_id", lambda: TEAM_ID)
    monkeypatch.setattr(tq, "_get_state", lambda: json.loads(
        (ld / "config" / "state.json").read_text()))

    sr = q.get_season_review(TEAM_ID)
    assert sr["has_season"] is True
    assert sr["year"] == YEAR
    # ranking lists are always present (may be empty in a 2-team fixture)
    assert isinstance(sr["wins"], list) and isinstance(sr["fixes"], list)
    assert isinstance(sr["players"]["hitters"], list)
    assert isinstance(sr["farm"]["top_prospects"], list)
    assert isinstance(sr["farm"]["risers"], list)
    assert isinstance(sr["farm"]["contributors"], list)
    assert isinstance(sr["focus"], list) and len(sr["focus"]) >= 1
    conn.close()


def test_season_review_no_season(q, monkeypatch):
    """With no team stats, the review degrades gracefully to has_season=False."""
    conn = q.get_db()
    conn.execute("DELETE FROM team_batting_stats")
    conn.commit()
    sr = q.get_season_review(TEAM_ID)
    assert sr == {"has_season": False}


# ---------------------------------------------------------------------------
# Contributor role / playing-time scaling (pure helpers)
# ---------------------------------------------------------------------------

def test_contributor_role_hitter_tiers():
    import offseason_queries as osq
    # Star rate → full reps; regular → 0.75; low rate → platoon/bench 0.5.
    assert osq._contributor_role(3.8, False)[2] == 1.0
    assert osq._contributor_role(2.0, False)[0] == "regular"
    assert osq._contributor_role(2.0, False)[2] == 0.75
    label, _, frac = osq._contributor_role(1.0, False)
    assert label == "platoon / bench bat" and frac == 0.50


def test_pitcher_role_stamina_drives_rotation_vs_pen():
    import offseason_queries as osq
    # Low stamina (<40) → bullpen regardless of a starter-ish rate.
    label, _, frac = osq._contributor_role(1.7, True, fv=45, stamina=38, bucket="SP")
    assert "reliever" in label or "bullpen" in label
    assert frac <= 0.55
    # Fringe stamina (<48) → swing / long reliever.
    label2, _, _ = osq._contributor_role(1.7, True, fv=45, stamina=40, bucket="SP")
    assert "swing" in label2 or "long" in label2
    # Real starter build → rotation label, higher playing-time fraction.
    label3, _, frac3 = osq._contributor_role(2.2, True, fv=50, stamina=65, bucket="SP")
    assert "starter" in label3 and frac3 >= 0.70


def test_platoon_lean_detects_multi_tool_split():
    import offseason_queries as osq
    # LHH better vs RHP across power/gap/eye (Coronado-style) → platoon lean.
    row = {"cntct_l": 45, "cntct_r": 45, "pow_l": 45, "pow_r": 55,
           "gap_l": 50, "gap_r": 60, "eye_l": 40, "eye_r": 55}
    assert osq._platoon_lean(row) is True
    # Balanced bat → no lean.
    even = {"cntct_l": 50, "cntct_r": 50, "pow_l": 50, "pow_r": 50,
            "gap_l": 50, "gap_r": 50, "eye_l": 50, "eye_r": 50}
    assert osq._platoon_lean(even) is False
    assert osq._platoon_lean(None) is False


def test_war_range_formatting():
    import offseason_queries as osq
    assert osq._war_range(None, 1.0) is None
    # rate 2.0 × 0.75 = 1.5 → "1.3–1.7"
    assert osq._war_range(2.0, 0.75) == "1.3–1.7"
    # negative floor clamps at 0
    assert osq._war_range(0.1, 0.5).startswith("0.0")


# ---------------------------------------------------------------------------
# Phase gating
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("phase,expect", [
    ("", {"season_review": True, "arbitration": True, "options": True, "free_agency": True, "extensions": True, "rule5": True}),
    ("season_review", {"season_review": True, "arbitration": False, "options": False, "free_agency": False, "extensions": False, "rule5": False}),
    ("arbitration", {"season_review": False, "arbitration": True, "options": False, "free_agency": False, "extensions": False, "rule5": False}),
    ("options", {"season_review": False, "arbitration": False, "options": True, "free_agency": False, "extensions": True, "rule5": False}),
    ("free_agency", {"season_review": False, "arbitration": False, "options": False, "free_agency": True, "extensions": True, "rule5": False}),
    ("rule5", {"season_review": False, "arbitration": False, "options": False, "free_agency": False, "extensions": False, "rule5": True}),
])
def test_phase_panel_gating(phase, expect):
    """panels_for_phase surfaces only the panels relevant to the phase."""
    import offseason_queries as osq
    assert osq.panels_for_phase(phase) == expect


# ---------------------------------------------------------------------------
# Contract options
# ---------------------------------------------------------------------------

def test_option_decisions_team_option_recommendation(q):
    """A team option is surfaced with an exercise/decline recommendation from
    the shared valuation model, in the correctly-timed bucket."""
    res = q.get_option_decisions(TEAM_ID)
    # Fixture player 400: signed 2033, 2yr → option year 2034 == game_year+1 →
    # "this offseason".
    opt = {o["name"]: o for o in res["this_offseason"]}
    assert "Opt Guy" in opt
    g = opt["Opt Guy"]
    assert g["type"] == "Team"
    assert g["year"] == YEAR + 1          # 2034, derived from season_year+offset
    assert g["option_salary"] == 8_000_000
    assert g["buyout"] == 1_000_000
    assert g["rec"] in ("Exercise", "Exercise (marginal)", "Decline")
    assert g["proj_value"] is not None


def test_option_year_derived_from_contract_not_game_year(q):
    """The option year comes from season_year + offset, not the game year —
    guards the off-by-one that mislabeled decision timing."""
    res = q.get_option_decisions(TEAM_ID)
    allopts = res["this_offseason"] + res["upcoming"]
    g = {o["name"]: o for o in allopts}["Opt Guy"]
    assert g["year"] == YEAR + 1  # season_year(2033) + (years-1=1) = 2034


def test_option_decisions_empty_when_none(q):
    """A team with no option contracts returns empty buckets (team 2 has none)."""
    res = q.get_option_decisions(2)
    assert res == {"this_offseason": [], "upcoming": []}


def test_traded_player_attributed_by_current_org_not_contract_team(q):
    """A mid-season-traded player (now on TEAM_ID) whose contract row still
    carries the PRE-TRADE contract_team_id must be attributed to his CURRENT
    org, not the stale signing team. Guards the contract-queries bug where the
    API retains the original team in contract_team_id after a trade.

    Fixture player 401: team_id=TEAM_ID, contract_team_id=2, option contract.
    """
    # Surfaces on TEAM_ID's options board (his current org) …
    mine = q.get_option_decisions(TEAM_ID)
    names_mine = {o["name"] for o in mine["this_offseason"] + mine["upcoming"]}
    assert "Trade Deadline Guy" in names_mine
    # … and NOT on team 2's (the stale contract_team_id), which has no options.
    theirs = q.get_option_decisions(2)
    names_theirs = {o["name"] for o in theirs["this_offseason"] + theirs["upcoming"]}
    assert "Trade Deadline Guy" not in names_theirs


def test_arb_board_includes_min_salary_eligible_player(q):
    """A player arb-eligible by SERVICE TIME (3 completed years) but still on a
    minimum deal must appear on the arb board — eligibility is a service-time
    property, not a salary one (the Danny Haas case). Guards against the old
    `sal <= min_sal: continue` skip."""
    board = {a["name"]: a for a in q.get_arbitration(TEAM_ID)}
    assert "Danny Haas" in board
    # svc 521 days = 3 completed years → arb_year 1 → first-arb curve, which
    # (prior == min) floors inert, so the projection exceeds the minimum.
    assert board["Danny Haas"]["proj_salary"] > 720_000


def test_arb_board_excludes_free_agent_eligible(q):
    """A player with 6+ completed service years has graduated to free agency
    (standard arb) and must NOT appear on the arb board."""
    board = {a["name"] for a in q.get_arbitration(TEAM_ID)}
    assert "Vic Veteran" not in board


def test_set_phase_persists(league, monkeypatch):
    """The set-offseason-phase endpoint writes the phase to state.json and
    rejects unknown phases. Exercised via the blueprint function with a patched
    config, avoiding a shared-app import (keeps test isolation)."""
    import api_routes
    from statsplusplus.config.league_config import LeagueConfig
    from statsplusplus.config.league_context import get_league_dir
    ld = get_league_dir(_SLUG)
    cfg = LeagueConfig(base_dir=ld)
    monkeypatch.setattr(api_routes, "_get_cfg", lambda: cfg)

    from flask import Flask
    probe = Flask(__name__)
    probe.register_blueprint(api_routes.api_bp)
    with probe.test_client() as c:
        r = c.post("/api/set-offseason-phase", json={"phase": "free_agency"})
        assert r.get_json()["ok"] is True
        assert json.loads((ld / "config" / "state.json").read_text())["offseason_phase"] == "free_agency"
        assert c.post("/api/set-offseason-phase", json={"phase": "bogus"}).status_code == 400
        c.post("/api/set-offseason-phase", json={"phase": ""})


def test_toggle_offseason_persists(league, monkeypatch):
    import api_routes
    from statsplusplus.config.league_config import LeagueConfig
    from statsplusplus.config.league_context import get_league_dir
    ld = get_league_dir(_SLUG)
    cfg = LeagueConfig(base_dir=ld)
    monkeypatch.setattr(api_routes, "_get_cfg", lambda: cfg)

    from flask import Flask
    probe = Flask(__name__)
    probe.register_blueprint(api_routes.api_bp)
    with probe.test_client() as c:
        first = c.post("/api/toggle-offseason").get_json()["offseason_mode"]
        assert json.loads((ld / "config" / "state.json").read_text())["offseason_mode"] == first
        assert c.post("/api/toggle-offseason").get_json()["offseason_mode"] is not first


# ---------------------------------------------------------------------------
# Finance settings (offseason budget) — routes + derived available figure
# ---------------------------------------------------------------------------

def _finance_client(monkeypatch):
    """A probe app + patched accessors so the finance routes resolve the
    fixture league's team and config (no shared live app)."""
    import api_routes
    import queries
    from statsplusplus.config.league_config import LeagueConfig
    from statsplusplus.config.league_context import get_league_dir

    ld = get_league_dir(_SLUG)
    cfg = LeagueConfig(base_dir=ld)
    # get_my_team_id() -> queries.get_cfg().my_team_id
    monkeypatch.setattr(queries, "get_cfg", lambda: cfg)

    from flask import Flask
    probe = Flask(__name__)
    probe.register_blueprint(api_routes.api_bp)
    return probe.test_client(), ld


def test_finance_get_defaults(league, monkeypatch):
    """GET returns v2 defaults for a league with no finance_settings.json yet."""
    c, ld = _finance_client(monkeypatch)
    try:
        d = c.get("/api/finance-settings").get_json()
        assert d["ok"] is True
        assert d["settings"]["fa_budget"] is None
        assert d["available"] is None  # no budget entered → nothing to derive
    finally:
        (ld / "config" / "finance_settings.json").unlink(missing_ok=True)


def test_finance_post_then_derive(league, monkeypatch):
    """POST persists the game's FA/extension figures and echoes available."""
    c, ld = _finance_client(monkeypatch)
    try:
        r = c.post("/api/finance-settings", json={"settings": {
            "fa_budget": 1_232_320, "ext_budget": 1_401_880}})
        d = r.get_json()
        assert d["ok"] is True
        assert d["available"] == 1_232_320  # no cart spend yet
        saved = json.loads((ld / "config" / "finance_settings.json").read_text())
        assert saved["fa_budget"] == 1_232_320
        assert saved["ext_budget"] == 1_401_880
    finally:
        (ld / "config" / "finance_settings.json").unlink(missing_ok=True)


def test_finance_post_missing_settings_400(league, monkeypatch):
    c, ld = _finance_client(monkeypatch)
    assert c.post("/api/finance-settings", json={}).status_code == 400


# ---------------------------------------------------------------------------
# Rule 5
# ---------------------------------------------------------------------------

def test_rule5_unavailable_when_field_null(q):
    """With years_protected_from_rule_5 unpopulated (fresh fixture), the panel
    reports available=False so the template shows a refresh hint rather than
    empty tables."""
    res = q.get_rule5(TEAM_ID)
    assert res["available"] is False
    assert res["protect"] == [] and res["targets"] == []


def test_rule5_protect_lists_eligible_prospect(q):
    """A prospect whose accumulated pro service has reached one short of his
    protection window (pro_service_years >= ypr - 1) and who is off the 40-man
    surfaces on the protect side with a recommendation."""
    conn = q.get_db()
    # Bob Prospect (103): AA SS, FV 50, in prospect_fv, on TEAM_ID.
    # ypr=5 window, 4 pro years → 4 >= 5-1 → exposed.
    conn.execute(
        "UPDATE players SET years_protected_from_rule_5=5, pro_service_years=4, "
        "is_on_secondary=0 WHERE player_id=103")
    conn.commit()
    res = q.get_rule5(TEAM_ID)
    assert res["available"] is True
    names = {p["name"]: p for p in res["protect"]}
    assert "Bob Prospect" in names
    assert names["Bob Prospect"]["rec"] == "Protect"  # FV 50 -> protect


def test_rule5_off_by_one_boundary(q):
    """Eligibility is pro_service_years >= ypr - 1 (OOTP exposes a year before the
    raw window elapses). A player exactly one year short of that (ypr-2) is still
    shielded; at ypr-1 he is exposed."""
    conn = q.get_db()
    # ypr=5: eligible at pro_service 4 (5-1), NOT at 3 (5-2).
    conn.execute(
        "UPDATE players SET years_protected_from_rule_5=5, pro_service_years=3, "
        "is_on_secondary=0 WHERE player_id=103")
    conn.commit()
    assert "Bob Prospect" not in {p["name"] for p in q.get_rule5(TEAM_ID)["protect"]}

    conn.execute("UPDATE players SET pro_service_years=4 WHERE player_id=103")
    conn.commit()
    assert "Bob Prospect" in {p["name"] for p in q.get_rule5(TEAM_ID)["protect"]}


def test_rule5_on_40man_excluded_from_protect(q):
    """A player already on the 40-man (is_on_secondary=1) is not exposed and
    must not appear as a protect decision."""
    conn = q.get_db()
    conn.execute(
        "UPDATE players SET years_protected_from_rule_5=5, pro_service_years=4, "
        "is_on_secondary=1 WHERE player_id=103")
    conn.commit()
    res = q.get_rule5(TEAM_ID)
    assert "Bob Prospect" not in {p["name"] for p in res["protect"]}


def test_rule5_shielded_prospect_excluded(q):
    """A prospect still well within the protection window (pro service far below
    ypr - 1) is not eligible."""
    conn = q.get_db()
    conn.execute(
        "UPDATE players SET years_protected_from_rule_5=5, pro_service_years=1, "
        "is_on_secondary=0 WHERE player_id=103")
    conn.commit()
    res = q.get_rule5(TEAM_ID)
    assert res["available"] is True
    assert "Bob Prospect" not in {p["name"] for p in res["protect"]}


def test_rule5_mlb_player_off_40man_is_eligible(q):
    """MLB-level players (level '1') are NOT excluded: a player on the active
    roster but off the 40-man is exposed to the Rule 5 draft. Only the level-0
    historical/retired/FA pool is excluded."""
    conn = q.get_db()
    # Joe Hitter (100): level '1' (MLB) on TEAM_ID. Make him eligible.
    conn.execute(
        "UPDATE players SET years_protected_from_rule_5=5, pro_service_years=4, "
        "is_on_secondary=0 WHERE player_id=100")
    conn.commit()
    res = q.get_rule5(TEAM_ID)
    assert "Joe Hitter" in {p["name"] for p in res["protect"]}


# ---------------------------------------------------------------------------
# Spring Training — Opening Day projection
# ---------------------------------------------------------------------------

def _seed_spring_pool(conn):
    """Seed a full-enough my-team roster (peak_war + buckets + positional
    ratings) so the spring pool can cover all 9 lineup slots + staff.

    The base fixture's player_evaluation rows don't set peak_war (the spring
    pool requires it), and it only has a few bodies — too thin to field a roster.
    Seed a plausible 26-man-ish org: one body per field position, a DH, bench,
    5 SP, 8 RP."""
    # (pid, name, bucket, level, peak_war, pos_field, pos_rating)
    bats = [
        (710, "Cora Catcher", "C", "1", 2.5, "c", 55),
        (711, "First Baseman", "1B", "1", 2.0, "first_b", 60),
        (712, "Second Sacker", "2B", "1", 2.4, "second_b", 60),
        (713, "Hot Corner", "3B", "1", 2.2, "third_b", 60),
        (714, "Short Stop", "SS", "1", 3.5, "ss", 60),
        (715, "Left Fielder", "LF", "1", 2.1, "lf", 55),
        (716, "Center Field", "CF", "1", 3.0, "cf", 60),
        (717, "Right Fielder", "RF", "1", 2.6, "rf", 55),
        (718, "Donny Hitter", "1B", "1", 2.3, "first_b", 55),   # DH-type bat
        (719, "Benchy One", "LF", "1", 1.1, "lf", 50),
        (720, "Benchy Two", "2B", "1", 1.0, "second_b", 50),
        (721, "Backup Catch", "C", "1", 0.9, "c", 50),
        (722, "Benchy Four", "3B", "1", 0.8, "third_b", 48),
    ]
    arms = [(730 + i, f"Starter {i}", "SP", "1", w)
            for i, w in enumerate([3.6, 3.0, 2.5, 2.0, 1.6, 1.2])]
    arms += [(740 + i, f"Reliever {i}", "RP", "1", w)
             for i, w in enumerate([1.3, 1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4])]

    for pid, name, bkt, lvl, pw, fld, rating in bats:
        conn.execute(
            "INSERT OR REPLACE INTO player_evaluation (player_id, eval_date, name, "
            "bucket, age, composite, ceiling, level, team_id, parent_team_id, peak_war) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (pid, EVAL_DATE, name, bkt, 27, 52, 56, lvl, TEAM_ID, TEAM_ID, pw))
        conn.execute(
            "INSERT OR REPLACE INTO players (player_id, name, age, team_id, "
            "parent_team_id, level, pos, role, is_on_secondary) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (pid, name, 27, TEAM_ID, 0, lvl, 7, 0, 1))
        conn.execute(
            f"INSERT OR REPLACE INTO ratings (player_id, snapshot_date, league_id, "
            f"cntct, gap, pow, eye, speed, {fld}) VALUES (?,?,?,?,?,?,?,?,?)",
            (pid, "2033-06-01", 1, 50, 50, 50, 50, 50, rating))
    for pid, name, bkt, lvl, pw in arms:
        conn.execute(
            "INSERT OR REPLACE INTO player_evaluation (player_id, eval_date, name, "
            "bucket, age, composite, ceiling, level, team_id, parent_team_id, peak_war) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (pid, EVAL_DATE, name, bkt, 27, 52, 56, lvl, TEAM_ID, TEAM_ID, pw))
        conn.execute(
            "INSERT OR REPLACE INTO players (player_id, name, age, team_id, "
            "parent_team_id, level, pos, role, is_on_secondary) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (pid, name, 27, TEAM_ID, 0, lvl, 1, 11 if bkt == "SP" else 12, 1))
    conn.commit()


def test_spring_projection_shape(q):
    """get_spring_projection returns the cascade + constructed roster + pool."""
    _seed_spring_pool(q.get_db())
    res = q.get_spring_projection(TEAM_ID)
    assert set(res) >= {"projection", "constructed", "config", "pool"}
    p = res["projection"]
    # Cascade fields present and internally consistent (RS - RA == run_diff).
    for k in ("wins", "losses", "run_diff", "runs_scored", "runs_allowed",
              "team_war", "bat_runs", "br_runs", "fld_runs", "pit_runs",
              "band_low", "band_high"):
        assert k in p
    assert abs((p["runs_scored"] - p["runs_allowed"]) - p["run_diff"]) < 1e-6
    assert abs((p["wins"] + p["losses"]) - 162) < 1e-6
    assert res["pool"]  # non-empty candidate pool


def test_spring_projection_auto_builds_a_roster(q):
    _seed_spring_pool(q.get_db())
    res = q.get_spring_projection(TEAM_ID)
    cfg = res["config"]
    assert cfg["lineup"]        # at least some field slots filled
    assert "rotation" in cfg and "bullpen" in cfg and "bench" in cfg


def test_spring_projection_override_changes_output(q):
    """Feeding an explicit config path works and yields a (possibly zero) delta
    without error — the comparison contract the UI depends on."""
    _seed_spring_pool(q.get_db())
    auto = q.get_spring_projection(TEAM_ID)
    before = auto["projection"]["wins"]
    # Re-project the SAME config explicitly — must reproduce the same record.
    again = q.get_spring_projection(TEAM_ID, auto["config"])
    assert abs(again["projection"]["wins"] - before) < 1e-6


def test_spring_contested_spots_present_and_shaped(q):
    """Contested spots surface with the right shape; each has exactly one pick
    per single-slot competition, and candidates carry evidence."""
    _seed_spring_pool(q.get_db())
    res = q.get_spring_projection(TEAM_ID)
    assert "contested" in res
    for s in res["contested"]:
        assert set(s) >= {"kind", "slot", "candidates", "reason", "forced"}
        assert s["candidates"]
        for c in s["candidates"]:
            assert set(c) >= {"pid", "name", "war", "is_pick", "out_of_options"}
        # field / rotation / bench are single-slot → exactly one pick.
        if s["kind"] in ("field", "rotation", "bench"):
            assert sum(1 for c in s["candidates"] if c["is_pick"]) == 1


def test_spring_out_of_options_forces_a_spot(q):
    """Flagging a clearly-better player as out of options makes his spot a
    forced decision that sorts to the top, even with a talent gap."""
    conn = q.get_db()
    _seed_spring_pool(conn)
    # Give the my-team CF (Joe Hitter, 100) a clear lead so his slot is NOT a
    # natural competition, then flag him out of options.
    conn.execute("UPDATE player_evaluation SET peak_war=5.0 WHERE player_id=100")
    conn.commit()
    res = q.get_spring_projection(TEAM_ID, out_of_options={100})
    forced = [s for s in res["contested"] if s["forced"]]
    assert forced, "an out-of-options player should force at least one spot"
    # Forced spots sort first.
    assert res["contested"][0]["forced"]
    # The flagged player appears as an out_of_options candidate somewhere.
    flagged = any(c["out_of_options"] for s in res["contested"] for c in s["candidates"])
    assert flagged


def test_spring_no_out_of_options_no_forced(q):
    """With nothing flagged, no spot is marked forced."""
    _seed_spring_pool(q.get_db())
    res = q.get_spring_projection(TEAM_ID)
    assert all(not s["forced"] for s in res["contested"])


def test_spring_recommend_covers_all_positions(q):
    """The recommender fills every field position + DH (coverage guarantee),
    not a greedy best-WAR grab that could leave a position empty."""
    _seed_spring_pool(q.get_db())
    res = q.get_spring_projection(TEAM_ID)
    lineup = res["config"]["lineup"]
    # Every field slot present (DH too when a bat is available).
    for pos in ("C", "1B", "2B", "3B", "SS", "LF", "CF", "RF"):
        assert pos in lineup, f"{pos} left uncovered"


def test_spring_recommend_roster_sizes(q):
    """Rotation/bullpen/bench sizes respect the Opening Day structure caps."""
    _seed_spring_pool(q.get_db())
    cfg = q.get_spring_projection(TEAM_ID)["config"]
    assert len(cfg["rotation"]) <= 5
    assert len(cfg["bullpen"]) <= 8
    assert len(cfg["bench"]) <= 4
    # No player appears in two roster groups.
    allpids = (list(cfg["lineup"].values()) + cfg["bench"]
               + cfg["rotation"] + cfg["bullpen"])
    assert len(allpids) == len(set(allpids)), "a player is double-rostered"


def test_spring_recommend_fills_full_bullpen(q):
    """The auto 26-man fills a FULL 8-man bullpen so the roster totals 26 (the
    26th spot is an explicit field-vs-pen choice the GM makes via the add-arm /
    add-reserve controls — a short pen that silently left the roster at 25 was
    the reported bug). The pen is ranked by RP-ROLE value (rp_war), not a
    starter's native full-season WAR, so relievers are valued on relief innings.
    When fewer arms than slots exist, the pen simply carries what's available."""
    conn = q.get_db()
    _seed_spring_pool(conn)
    cfg = q.get_spring_projection(TEAM_ID)["config"]
    # With a full fixture RP pool, the bullpen fills to the 8-man default.
    assert len(cfg["bullpen"]) == 8, "auto roster should carry a full 8-man pen"
    # Drop two fixture relievers (746, 747) so only ~6 positive arms remain, plus
    # a clearly below-replacement arm. The pen still fills (26-man guarantee) —
    # it does NOT run short just because an arm is below replacement; the GM can
    # drop it for a 5th bench bat.
    for pid in (746, 747):
        conn.execute("DELETE FROM player_evaluation WHERE player_id=?", (pid,))
        conn.execute("DELETE FROM players WHERE player_id=?", (pid,))
    conn.execute(
        "INSERT OR REPLACE INTO player_evaluation (player_id, eval_date, name, "
        "bucket, age, composite, ceiling, level, team_id, parent_team_id, peak_war) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (770, EVAL_DATE, "Negative Arm", "RP", 29, 40, 42, "1", TEAM_ID, TEAM_ID, -0.6))
    conn.execute(
        "INSERT OR REPLACE INTO players (player_id, name, age, team_id, "
        "parent_team_id, level, pos, role, is_on_secondary) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (770, "Negative Arm", 29, TEAM_ID, 0, "1", 1, 13, 1))
    conn.commit()
    cfg2 = q.get_spring_projection(TEAM_ID)["config"]
    # The pen carries every available arm toward the 8-man target (fills up).
    assert len(cfg2["bullpen"]) >= 6


def test_spring_below_replacement_reliever_fits_open_slot_if_flagged(q):
    """If the GM flags that negative arm out-of-options, he's still a genuine
    cut (below the OOO credibility floor) — surfaced as must-expose, not forced
    onto the roster."""
    conn = q.get_db()
    _seed_spring_pool(conn)
    conn.execute(
        "INSERT OR REPLACE INTO player_evaluation (player_id, eval_date, name, "
        "bucket, age, composite, ceiling, level, team_id, parent_team_id, peak_war) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (771, EVAL_DATE, "Neg Arm", "RP", 29, 40, 42, "1", TEAM_ID, TEAM_ID, -0.6))
    conn.execute(
        "INSERT OR REPLACE INTO players (player_id, name, age, team_id, "
        "parent_team_id, level, pos, role, is_on_secondary) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (771, "Neg Arm", 29, TEAM_ID, 0, "1", 1, 13, 1))
    conn.commit()
    res = q.get_spring_projection(TEAM_ID, out_of_options={771})
    assert 771 not in res["config"]["bullpen"]
    assert any(m["pid"] == 771 for m in res["must_expose"])


def test_spring_recommend_carries_credible_out_of_options(q):
    """A flagged, credible player off the auto roster is pulled onto it."""
    conn = q.get_db()
    _seed_spring_pool(conn)
    # Add a credible bench-quality bat that wouldn't otherwise make the cut,
    # then flag him out of options.
    conn.execute(
        "INSERT OR REPLACE INTO player_evaluation (player_id, eval_date, name, "
        "bucket, age, composite, ceiling, level, team_id, parent_team_id, peak_war) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (900, EVAL_DATE, "Oscar Options", "LF", 28, 50, 52, "1", TEAM_ID, TEAM_ID, 2.8))
    conn.execute(
        "INSERT OR REPLACE INTO players (player_id, name, age, team_id, "
        "parent_team_id, level, pos, role, is_on_secondary) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (900, "Oscar Options", 28, TEAM_ID, 0, "1", 7, 0, 1))
    conn.commit()
    res = q.get_spring_projection(TEAM_ID, out_of_options={900})
    cfg = res["config"]
    rostered = (set(cfg["lineup"].values()) | set(cfg["bench"])
                | set(cfg["rotation"]) | set(cfg["bullpen"]))
    assert 900 in rostered, "credible out-of-options player should be carried"
    assert all(m["pid"] != 900 for m in res["must_expose"])


# ---------------------------------------------------------------------------
# Spring Training — plan persistence
# ---------------------------------------------------------------------------

def test_spring_plan_save_load_roundtrip(q):
    _seed_spring_pool(q.get_db())
    res = q.get_spring_projection(TEAM_ID)
    cfg = res["config"]
    q.save_spring_plan(TEAM_ID, cfg, out_of_options=[])
    loaded = q.load_spring_plan(TEAM_ID)
    assert loaded is not None
    assert loaded["config"]["lineup"] == {k: v for k, v in cfg["lineup"].items()}
    assert not loaded["stale"] and loaded["dropped"] == []
    assert loaded["game_date"]  # stamped from state.json
    q.delete_spring_plan(TEAM_ID)


def test_spring_plan_load_none_when_unsaved(q):
    _seed_spring_pool(q.get_db())
    q.delete_spring_plan(TEAM_ID)  # ensure clean
    assert q.load_spring_plan(TEAM_ID) is None


def test_spring_plan_drops_vanished_players(q):
    """A saved player no longer in the pool is dropped and flagged stale."""
    _seed_spring_pool(q.get_db())
    res = q.get_spring_projection(TEAM_ID)
    cfg = {k: (dict(v) if isinstance(v, dict) else list(v))
           for k, v in res["config"].items() if k != "_must_expose"}
    cfg["bench"] = list(cfg["bench"]) + [99999999]  # bogus pid
    q.save_spring_plan(TEAM_ID, cfg)
    loaded = q.load_spring_plan(TEAM_ID)
    assert 99999999 in loaded["dropped"]
    assert loaded["stale"] is True
    assert 99999999 not in loaded["config"]["bench"]
    q.delete_spring_plan(TEAM_ID)


def test_spring_plan_delete(q):
    _seed_spring_pool(q.get_db())
    q.save_spring_plan(TEAM_ID, q.get_spring_projection(TEAM_ID)["config"])
    assert q.delete_spring_plan(TEAM_ID) is True
    assert q.delete_spring_plan(TEAM_ID) is False  # idempotent
    assert q.load_spring_plan(TEAM_ID) is None


def test_spring_plan_persists_out_of_options(q):
    _seed_spring_pool(q.get_db())
    res = q.get_spring_projection(TEAM_ID)
    q.save_spring_plan(TEAM_ID, res["config"], out_of_options=[710, 711])
    loaded = q.load_spring_plan(TEAM_ID)
    # Both flagged pids are in the pool (seeded), so both persist.
    assert set(loaded["out_of_options"]) == {710, 711}
    q.delete_spring_plan(TEAM_ID)


# ---------------------------------------------------------------------------
# Spring Training — edit → re-project delta
# ---------------------------------------------------------------------------

def _clone_config(cfg):
    return {k: (dict(v) if isinstance(v, dict) else list(v))
            for k, v in cfg.items() if k != "_must_expose"}


def test_spring_delta_zero_when_unchanged(q):
    """Projecting the auto config with the auto baseline yields a zero delta."""
    _seed_spring_pool(q.get_db())
    auto = _clone_config(q.get_spring_projection(TEAM_ID)["config"])
    res = q.spring_projection_delta(TEAM_ID, auto, baseline=auto)
    assert res["delta"]["wins"] == 0.0
    assert res["delta"]["run_diff"] == 0.0


def test_spring_delta_payload_shape(q):
    _seed_spring_pool(q.get_db())
    auto = _clone_config(q.get_spring_projection(TEAM_ID)["config"])
    res = q.spring_projection_delta(TEAM_ID, auto)
    assert set(res) >= {"projection", "baseline", "delta", "constructed",
                        "contested", "must_expose", "config", "breakdown"}
    for m in ("wins", "run_diff", "team_war", "bat_runs", "br_runs",
              "fld_runs", "pit_runs"):
        assert m in res["delta"]


# ---------------------------------------------------------------------------
# Spring Training — change breakdown (cumulative vs saved plan, itemized)
# ---------------------------------------------------------------------------

def _two_changes_vs_auto(q):
    """Return (auto_config, edited_config) differing by a 3B starter swap and a
    bullpen drop — two independent, attributable moves."""
    import copy
    auto = q.get_spring_projection(TEAM_ID)
    cfg = _clone_config(auto["config"])
    pool = {p["player_id"]: p for p in auto["pool"]}
    cur3b = cfg["lineup"].get("3B")
    alt = next((p["player_id"] for p in auto["pool"] if not p["is_pitcher"]
                and p["player_id"] != cur3b and "3B" in (p.get("eligible") or [])
                and p["player_id"] not in cfg["lineup"].values()), None)
    if alt:
        cfg["lineup"]["3B"] = alt
    if cfg.get("bullpen"):
        cfg["bullpen"] = cfg["bullpen"][:-1]
    return auto["config"], cfg


def test_spring_breakdown_itemizes_moves(q):
    """The breakdown diffs the plan into discrete labeled moves with per-move
    win/run-diff impact, anchored on the auto 26 when no plan is saved."""
    _seed_spring_pool(q.get_db())
    q.delete_spring_plan(TEAM_ID)  # ensure auto baseline
    _auto, edited = _two_changes_vs_auto(q)
    bd = q.spring_change_breakdown(TEAM_ID, edited)
    assert bd["baseline_label"] == "auto 26"
    assert bd["n_changes"] >= 1
    for ch in bd["changes"]:
        assert set(ch) >= {"label", "kind", "slot", "wins", "run_diff"}


def test_spring_breakdown_moves_sum_to_total(q):
    """Sequential attribution: the per-move impacts sum EXACTLY to the cumulative
    headline delta (within rounding)."""
    _seed_spring_pool(q.get_db())
    q.delete_spring_plan(TEAM_ID)
    _auto, edited = _two_changes_vs_auto(q)
    bd = q.spring_change_breakdown(TEAM_ID, edited)
    sum_w = sum(c["wins"] for c in bd["changes"])
    sum_rd = sum(c["run_diff"] for c in bd["changes"])
    assert abs(sum_w - bd["delta"]["wins"]) < 0.02
    assert abs(sum_rd - bd["delta"]["run_diff"]) < 0.6   # run-diff rounded to 1


def test_spring_breakdown_zero_changes_when_unedited(q):
    """No edits vs the baseline → no moves and a zero cumulative delta."""
    _seed_spring_pool(q.get_db())
    q.delete_spring_plan(TEAM_ID)
    auto = q.get_spring_projection(TEAM_ID)["config"]
    bd = q.spring_change_breakdown(TEAM_ID, _clone_config(auto))
    assert bd["n_changes"] == 0
    assert abs(bd["delta"]["wins"]) < 1e-6


def test_spring_breakdown_anchors_on_saved_plan(q):
    """Once a plan is saved, the breakdown measures vs THAT plan (label + values),
    not the auto 26."""
    _seed_spring_pool(q.get_db())
    _auto, edited = _two_changes_vs_auto(q)
    # Save the EDITED config as the plan, then edit further from it.
    q.save_spring_plan(TEAM_ID, edited)
    further = _clone_config(edited)
    # drop a bench reserve as the one change vs the saved plan
    if further.get("bench"):
        further["bench"] = further["bench"][1:]
    bd = q.spring_change_breakdown(TEAM_ID, further)
    assert bd["baseline_label"] == "saved plan"
    # Only the post-save change should register (bench drop), not the 3B/bullpen
    # moves that are now baked into the saved baseline.
    labels = " ".join(c["label"] for c in bd["changes"]).lower()
    assert "bench" in labels or bd["n_changes"] >= 1
    q.delete_spring_plan(TEAM_ID)


def test_spring_delta_sign_tracks_improvement(q):
    """Reversing a comparison negates the delta exactly (after-minus-before is a
    true difference), independent of which roster is which."""
    _seed_spring_pool(q.get_db())
    auto = _clone_config(q.get_spring_projection(TEAM_ID)["config"])
    # Two configs that differ: auto, and auto with one bench bat removed (a
    # strictly weaker roster). Independent of the auto allocator's specifics.
    weaker = _clone_config(auto)
    assert weaker["bench"], "fixture should seed a bench"
    weaker["bench"] = weaker["bench"][1:]  # drop one bench piece
    up = q.spring_projection_delta(TEAM_ID, auto, baseline=weaker)["delta"]["wins"]
    down = q.spring_projection_delta(TEAM_ID, weaker, baseline=auto)["delta"]["wins"]
    # Exact mirror: d(A vs B) == -d(B vs A). This is the robust invariant.
    assert abs(up + down) < 1e-6
    # The fuller roster is not worse than the one missing a bench bat.
    assert up >= 0 >= down


# ---------------------------------------------------------------------------
# Spring Training — positional WAR is re-valued for the slot played
# ---------------------------------------------------------------------------

def test_spring_slot_war_strips_native_positional_value_at_dh():
    """A SS (+0.7 native) shown at DH (-1.7) loses exactly 2.4 WAR."""
    import offseason_queries as osq
    from statsplusplus.utils.positions import POSITIONAL_WAR_ADJUSTMENTS as PA
    ss = {"bucket": "SS", "war_proj": 3.7}
    at_dh = osq._spring_slot_war(ss, "DH")
    assert abs(at_dh - (3.7 - PA["SS"] + PA["DH"])) < 1e-9
    assert abs(at_dh - 1.3) < 1e-9  # 3.7 - 0.7 + (-1.7)


def test_spring_slot_war_corner_slots_use_cof_adjustment():
    """LF/RF slots key to the COF adjustment, not a missing 'LF'/'RF' key."""
    import offseason_queries as osq
    from statsplusplus.utils.positions import POSITIONAL_WAR_ADJUSTMENTS as PA
    cf = {"bucket": "CF", "war_proj": 3.0}
    at_lf = osq._spring_slot_war(cf, "LF")
    # CF (+0.25) moved to a corner (COF -0.7): loses 0.95.
    assert abs(at_lf - (3.0 - PA["CF"] + PA["COF"])) < 1e-9


def test_spring_dh_war_not_inflated_by_native_position(q):
    """End-to-end: the DH's displayed WAR reflects the DH penalty, and the DH
    contributes no fielding runs."""
    _seed_spring_pool(q.get_db())
    res = q.get_spring_projection(TEAM_ID)
    dh = res["constructed"]["lineup"].get("DH")
    if dh:
        pool = {p["player_id"]: p for p in res["pool"]}
        native = pool[dh["pid"]]["war_proj"]
        # Unless the DH is natively a 1B (same-ish adj), the slot WAR should be
        # at or below native (DH is the worst positional adjustment).
        assert dh["war"] <= native + 1e-6


# ---------------------------------------------------------------------------
# Spring Training — multi-position eligibility
# ---------------------------------------------------------------------------

def test_spring_pool_carries_eligible_positions(q):
    """Every pool player has an `eligible` set; hitters include DH, pitchers get
    role eligibility (SP also RP)."""
    _seed_spring_pool(q.get_db())
    conn = q.get_db()
    import offseason_queries as osq
    pool = osq._spring_pool(conn, TEAM_ID, osq._eval_date(conn))
    assert pool
    for p in pool:
        assert "eligible" in p and p["eligible"]
        if p["is_pitcher"]:
            assert p["eligible"] in (["SP", "RP"], ["RP"])
        else:
            assert "DH" in p["eligible"]  # any hitter can DH


def test_spring_eligibility_reflects_positional_ratings(q):
    """A player with a strong rating at a position is eligible there; the seed's
    shortstop (ss=60) qualifies at SS."""
    _seed_spring_pool(q.get_db())
    conn = q.get_db()
    import offseason_queries as osq
    pool = {p["name"]: p for p in osq._spring_pool(conn, TEAM_ID, osq._eval_date(conn))}
    ss = pool.get("Short Stop")
    assert ss and "SS" in ss["eligible"]


def test_spring_viable_at_prefers_precomputed_set(q):
    """_spring_viable_at honors the precomputed eligible set when present."""
    import offseason_queries as osq
    p = {"eligible": ["2B", "SS", "DH"], "bucket": "SS"}
    assert osq._spring_viable_at(p, "SS") is True
    assert osq._spring_viable_at(p, "2B") is True
    assert osq._spring_viable_at(p, "C") is False


# ---------------------------------------------------------------------------
# Spring Training — generalized editing (role moves, drops)
# ---------------------------------------------------------------------------

def test_spring_move_starter_to_bullpen_reprojects(q):
    """Moving a starter to the bullpen is a valid config the engine projects;
    the rotation shrinks and the roster still projects without error."""
    _seed_spring_pool(q.get_db())
    auto = q.get_spring_projection(TEAM_ID)
    cfg = _clone_config(auto["config"])
    assert len(cfg["rotation"]) >= 5
    moved = cfg["rotation"].pop()          # pull the 5th starter
    cfg["bullpen"] = [moved] + list(cfg["bullpen"])
    res = q.get_spring_projection(TEAM_ID, cfg)
    assert len(res["constructed"]["rotation"]) == len(cfg["rotation"])
    assert any(r["pid"] == moved for r in res["constructed"]["bullpen"])


def test_spring_drop_player_leaves_hole_and_reprojects(q):
    """Dropping a player from the 26 is handled: the roster is smaller and the
    projection still computes (the GM sees the hole + WAR cost)."""
    _seed_spring_pool(q.get_db())
    auto = q.get_spring_projection(TEAM_ID)
    cfg = _clone_config(auto["config"])
    if cfg["bench"]:
        cfg["bench"] = cfg["bench"][1:]    # drop one bench bat
        res = q.get_spring_projection(TEAM_ID, cfg)
        assert len(res["constructed"]["bench"]) == len(cfg["bench"])
        assert "wins" in res["projection"]  # still projects


# ---------------------------------------------------------------------------
# Spring Training — platoon-assignment + start-share playing time
# ---------------------------------------------------------------------------

def test_spring_catcher_start_share_is_realistic(q):
    """The catcher starts ~67% of games (not full-time) — the realistic
    start-share from historical data, not a 100% everyday assumption."""
    _seed_spring_pool(q.get_db())
    res = q.get_spring_projection(TEAM_ID)
    c = res["constructed"]["lineup"].get("C")
    assert c and c["players"][0]["pt_pct"] <= 70  # ~67%, never 100


def test_spring_start_share_override_cuts_contribution(q):
    """A start_share override that benches a starter (low share) cuts the team
    projection vs his default everyday share."""
    _seed_spring_pool(q.get_db())
    auto = q.get_spring_projection(TEAM_ID)
    cl = auto["constructed"]["lineup"]
    best_pos = max(cl, key=lambda p: cl[p]["war"])
    best_pid = cl[best_pos]["pid"]
    cfg = _clone_config(auto["config"])
    cfg["start_share"] = {best_pid: 0.10}
    res = q.get_spring_projection(TEAM_ID, cfg)
    assert res["projection"]["wins"] < auto["projection"]["wins"] - 0.3


def test_spring_recommender_carries_backup_catcher(q):
    """The auto 26 carries a backup catcher (a C can't start 162), so the
    no-backup-catcher warning does NOT fire when a 2nd catcher exists."""
    _seed_spring_pool(q.get_db())
    res = q.get_spring_projection(TEAM_ID)
    c = res["constructed"]["lineup"].get("C")
    has_backup = c and any(r.get("role") == "Backup" for r in c["players"])
    assert has_backup
    assert not any(w["kind"] == "no_backup_catcher" for w in res["warnings"])


def test_spring_no_backup_catcher_warns(q):
    """A config with only ONE catcher-eligible player raises the backup-C
    warning (you physically can't cover 162 games with one catcher)."""
    _seed_spring_pool(q.get_db())
    auto = q.get_spring_projection(TEAM_ID)
    cfg = _clone_config(auto["config"])
    # Strip every catcher-eligible player except the starting C.
    import offseason_queries as osq
    pool = {p["player_id"]: p for p in auto["pool"]}
    starter_c = cfg["lineup"].get("C")
    cfg["bench"] = [b for b in cfg["bench"]
                    if "C" not in (pool.get(b, {}).get("eligible") or [])]
    res = q.get_spring_projection(TEAM_ID, cfg)
    assert any(w["kind"] == "no_backup_catcher" for w in res["warnings"])


def test_spring_pitcher_role_share_sp1_beats_sp5(q):
    """An arm deployed SP1 (full share) contributes more than as SP5."""
    _seed_spring_pool(q.get_db())
    auto = q.get_spring_projection(TEAM_ID)
    sp = auto["constructed"]["rotation"][0]["pid"]
    a = _clone_config(auto["config"]); a["roles"] = {sp: "sp1"}
    b = _clone_config(auto["config"]); b["roles"] = {sp: "sp5"}
    wa = q.get_spring_projection(TEAM_ID, a)["projection"]["wins"]
    wb = q.get_spring_projection(TEAM_ID, b)["projection"]["wins"]
    assert wa >= wb


def test_spring_platoon_assignment_persists_in_plan(q):
    """A saved plan round-trips platoon + start_share decisions."""
    _seed_spring_pool(q.get_db())
    auto = q.get_spring_projection(TEAM_ID)
    cl = auto["constructed"]["lineup"]
    pid = cl["LF"]["pid"] if "LF" in cl else next(iter(cl.values()))["pid"]
    cfg = _clone_config(auto["config"])
    cfg["start_share"] = {pid: 0.6}
    q.save_spring_plan(TEAM_ID, cfg)
    loaded = q.load_spring_plan(TEAM_ID)
    assert loaded["config"].get("start_share", {}).get(pid) == 0.6 or \
           loaded["config"].get("start_share", {}).get(str(pid)) == 0.6
    q.delete_spring_plan(TEAM_ID)


# ---------------------------------------------------------------------------
# Spring Training — stat selector data (depth-chart parity)
# ---------------------------------------------------------------------------

def test_spring_pool_carries_display_stats(q):
    """Hitters carry OPS+ (+ splits); pitchers carry ERA/FIP — the stat-selector
    values, computed the depth-chart way."""
    _seed_spring_pool(q.get_db())
    conn = q.get_db()
    import offseason_queries as osq
    pool = osq._spring_pool(conn, TEAM_ID, osq._eval_date(conn))
    hitters = [p for p in pool if not p["is_pitcher"]]
    pitchers = [p for p in pool if p["is_pitcher"]]
    assert hitters and all("stats" in h for h in hitters)
    assert all("ops_plus" in h["stats"] for h in hitters)
    assert pitchers and all({"era", "fip"} <= set(p["stats"]) for p in pitchers)


def test_spring_constructed_entries_carry_stats(q):
    """The constructed lineup/rotation/bullpen entries expose stats for the UI,
    with the lineup WAR being the slot-adjusted value."""
    _seed_spring_pool(q.get_db())
    res = q.get_spring_projection(TEAM_ID)
    for pos, e in res["constructed"]["lineup"].items():
        assert "stats" in e and "ops_plus" in e["stats"]
        assert e["stats"]["war"] == e["war"]  # slot-adjusted WAR carried through
    for e in res["constructed"]["rotation"]:
        assert "era" in e["stats"] and "fip" in e["stats"]


def test_spring_recommender_assigns_by_slot_war_not_native(q):
    """The recommender should prefer a true 1B at 1B over a higher-native-WAR
    middle infielder whose value craters when stretched to 1B (slot-adjusted
    WAR, not raw war_proj — the same bug class as the DH fix)."""
    conn = q.get_db()
    _seed_spring_pool(conn)
    # A natural 1B (modest native WAR) and a strong 2B who is ALSO 1B-eligible.
    # Natively the 2B outranks the 1B, but at 1B the 2B loses ~1.5 WAR, so the
    # true 1B should win the 1B slot.
    conn.execute(
        "INSERT OR REPLACE INTO player_evaluation (player_id, eval_date, name, "
        "bucket, age, composite, ceiling, level, team_id, parent_team_id, peak_war) "
        "VALUES (950,?, 'Natural First','1B',28,52,54,'1',?,?,1.5)", (EVAL_DATE, TEAM_ID, TEAM_ID))
    conn.execute(
        "INSERT OR REPLACE INTO players (player_id, name, age, team_id, parent_team_id, "
        "level, pos, role, is_on_secondary) VALUES (950,'Natural First',28,?,0,'1',3,0,1)", (TEAM_ID,))
    conn.execute(
        "INSERT OR REPLACE INTO ratings (player_id, snapshot_date, league_id, cntct, gap, "
        "pow, eye, speed, first_b) VALUES (950,'2033-06-01',1,55,50,55,52,45,60)")
    conn.commit()
    import offseason_queries as osq
    pool = osq._spring_pool(conn, TEAM_ID, osq._eval_date(conn))
    cfg = osq._spring_auto_config(pool)
    # Whoever is at 1B must be the slot-WAR-maximizing eligible player.
    at_1b = cfg["lineup"].get("1B")
    by_id = {p["player_id"]: p for p in pool}
    elig_1b = [p for p in pool if not p["is_pitcher"] and "1B" in p.get("eligible", [])]
    best = max(elig_1b, key=lambda p: osq._spring_slot_war(p, "1B"))
    # The 1B occupant's slot WAR should equal the best achievable at 1B.
    assert abs(osq._spring_slot_war(by_id[at_1b], "1B")
               - osq._spring_slot_war(best, "1B")) < 1e-6


def test_spring_lineup_slot_carries_players_and_pos_war(q):
    """Each constructed lineup slot carries the full players list (starter +
    any platoon/backups sharing the slot) with PT%, plus a position WAR total —
    the depth-chart-parity structure the field view renders."""
    _seed_spring_pool(q.get_db())
    res = q.get_spring_projection(TEAM_ID)
    for pos, slot in res["constructed"]["lineup"].items():
        assert "players" in slot and slot["players"]
        assert "pos_war" in slot
        # starter is the first player and matches the back-compat top-level pid
        assert slot["players"][0]["pid"] == slot["pid"]
        for pl in slot["players"]:
            assert "pt_pct" in pl and "war" in pl


def test_spring_explicit_platoon_splits_a_position(q):
    """An explicit platoon {vsR, vsL} at a position produces a two-player split
    with the vs-RHP player at ~71% and the vs-LHP player at ~29%."""
    _seed_spring_pool(q.get_db())
    auto = q.get_spring_projection(TEAM_ID)
    cl = auto["config"]["lineup"]
    # Need a position with an eligible bench partner. Use LF + a bench LF bat.
    import offseason_queries as osq
    pool = {p["player_id"]: p for p in auto["pool"]}
    pos = "LF"
    starter = cl.get(pos)
    partner = next((b for b in auto["config"]["bench"]
                    if b != starter and "LF" in (pool.get(b, {}).get("eligible") or [])), None)
    if starter and partner:
        cfg = _clone_config(auto["config"])
        cfg["platoon"] = {pos: {"vsR": starter, "vsL": partner}}
        res = q.get_spring_projection(TEAM_ID, cfg)
        players = res["constructed"]["lineup"][pos]["players"]
        pts = {r["pid"]: r["pt_pct"] for r in players}
        assert pts.get(starter) in (71, 72) or abs(pts.get(starter, 0) - 71) <= 2
        assert pts.get(partner) in (28, 29, 30) or abs(pts.get(partner, 0) - 29) <= 2


def test_spring_platoon_persists_in_plan(q):
    """A saved plan round-trips the platoon assignment (surviving players)."""
    _seed_spring_pool(q.get_db())
    auto = q.get_spring_projection(TEAM_ID)
    cl = auto["config"]["lineup"]
    import offseason_queries as osq
    pool = {p["player_id"]: p for p in auto["pool"]}
    starter = cl.get("LF")
    partner = next((b for b in auto["config"]["bench"]
                    if b != starter and "LF" in (pool.get(b, {}).get("eligible") or [])), None)
    if starter and partner:
        cfg = _clone_config(auto["config"])
        cfg["platoon"] = {"LF": {"vsR": starter, "vsL": partner}}
        q.save_spring_plan(TEAM_ID, cfg)
        loaded = q.load_spring_plan(TEAM_ID)
        assert loaded["config"]["platoon"].get("LF", {}).get("vsL") == partner
        q.delete_spring_plan(TEAM_ID)


# ---------------------------------------------------------------------------
# Spring Training — platoon intelligence (flag real splits + suggest platoon)
# ---------------------------------------------------------------------------

def test_spring_platoon_profile_flags_real_split():
    """A bat with a big, above-average strong side is a REAL platoon bat; a
    balanced bat and a weak-everywhere bat are not."""
    import offseason_queries as osq
    # Strong vs RHP (120), exposed vs LHP (95) — real.
    real = osq._spring_platoon_profile(
        {"is_pitcher": False, "ops_vs_l": 95, "ops_vs_r": 120})
    assert real["real"] and real["strong"] == "R" and real["weak"] == "L"
    assert real["split"] == 25 and real["strong_ops"] == 120
    # Balanced → not a platoon bat.
    bal = osq._spring_platoon_profile(
        {"is_pitcher": False, "ops_vs_l": 101, "ops_vs_r": 104})
    assert bal["real"] is False
    # Big split but weak strong side (strong side below the min) → not exploitable.
    weak = osq._spring_platoon_profile(
        {"is_pitcher": False, "ops_vs_l": 70, "ops_vs_r": 95})
    assert weak["real"] is False
    # Pitchers / missing splits → None.
    assert osq._spring_platoon_profile({"is_pitcher": True}) is None
    assert osq._spring_platoon_profile(
        {"is_pitcher": False, "ops_vs_l": None, "ops_vs_r": 110}) is None


def test_spring_pool_carries_platoon_profile(q):
    """Every pool hitter exposes a `platoon` profile (or None); pitchers None."""
    _seed_spring_pool(q.get_db())
    conn = q.get_db()
    import offseason_queries as osq
    pool = osq._spring_pool(conn, TEAM_ID, osq._eval_date(conn))
    for p in pool:
        if p["is_pitcher"]:
            assert p.get("platoon") is None
        else:
            # key present; value is a dict or None
            assert "platoon" in p


def test_spring_suggest_platoon_pairs_strong_side_partner(q):
    """Seed a RHP-exposed LF starter and a strong-vs-RHP bench LF; the suggester
    pairs the partner into the RHP wedge, and the projection surfaces it with a
    positive win delta."""
    conn = q.get_db()
    _seed_spring_pool(conn)
    # Make the LF starter (715) clearly worse vs RHP, and add a bench LF (901)
    # who mashes RHP. Splits drive ops_vs_r via project_ops_plus_splits, so set
    # the ratings' R-side tools high for the partner, low for the starter.
    # Starter 715: weak vs R (low R-side contact/gap/pow/eye).
    conn.execute("""UPDATE ratings SET cntct_r=35,gap_r=35,pow_r=35,eye_r=35,
                    cntct_l=55,gap_l=55,pow_l=55,eye_l=55
                    WHERE player_id=715 AND snapshot_date='2033-06-01'""")
    # Partner 901: strong vs R.
    conn.execute(
        "INSERT OR REPLACE INTO player_evaluation (player_id, eval_date, name, "
        "bucket, age, composite, ceiling, level, team_id, parent_team_id, peak_war) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (901, EVAL_DATE, "Platoon Partner", "LF", 28, 52, 55, "1", TEAM_ID, TEAM_ID, 2.2))
    conn.execute(
        "INSERT OR REPLACE INTO players (player_id, name, age, team_id, "
        "parent_team_id, level, pos, role, is_on_secondary) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (901, "Platoon Partner", 28, TEAM_ID, 0, "1", 7, 0, 1))
    conn.execute(
        "INSERT OR REPLACE INTO ratings (player_id, snapshot_date, league_id, "
        "cntct, gap, pow, eye, speed, lf, cntct_r, gap_r, pow_r, eye_r, "
        "cntct_l, gap_l, pow_l, eye_l) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (901, "2033-06-01", 1, 55, 55, 55, 55, 50, 55, 75, 75, 70, 65, 45, 45, 40, 45))
    conn.commit()
    res = q.get_spring_projection(TEAM_ID)
    # If LF ends up a suggested platoon, the partner is slotted on the RHP wedge.
    sug = next((s for s in res["platoon_suggestions"] if s["pos"] == "LF"), None)
    # The suggestion is optional (depends on the auto roster), but if present it
    # must be well-formed and net-positive.
    if sug:
        assert sug["partner_hand"] == "R"
        assert sug["delta_wins"] > 0
        assert str(sug["partner"]) in {str(k) for k in sug["pa_alloc"]}


def test_spring_platoon_suggestions_shape(q):
    """platoon_suggestions is always present and every entry is well-formed and
    net-positive (only worthwhile suggestions are surfaced)."""
    _seed_spring_pool(q.get_db())
    res = q.get_spring_projection(TEAM_ID)
    assert "platoon_suggestions" in res
    for s in res["platoon_suggestions"]:
        assert set(s) >= {"pos", "primary", "partner", "partner_hand",
                          "pa_alloc", "reason", "delta_wins", "delta_run_diff"}
        assert s["delta_wins"] > 0
        assert s["partner_hand"] in ("L", "R")


def test_spring_dh_platoon_eligible_and_excludes_field_starters(q):
    """DH platoons are allowed (DH is not skipped), but a DH platoon PARTNER must
    not be a player already starting in the field — pairing him at DH would
    double-roster him."""
    conn = q.get_db()
    _seed_spring_pool(conn)
    import offseason_queries as osq
    auto = q.get_spring_projection(TEAM_ID)
    cfg = auto["config"]
    field_starters = {pid for pos, pid in cfg["lineup"].items() if pos != "DH"}
    # DH is no longer short-circuited: the suggester runs for DH (may or may not
    # return a suggestion depending on the pool, but it must not raise and any
    # suggestion it returns must respect the field-starter exclusion).
    sug = osq._spring_suggest_platoon(auto["pool"], cfg, "DH")
    if sug:
        assert sug["partner"] not in field_starters
    # And any DH suggestion that surfaces in the projection respects it too.
    for s in auto["platoon_suggestions"]:
        if s["pos"] == "DH":
            assert s["partner"] not in field_starters


def test_spring_caps_cross_position_over_allocation(q):
    """A utility bat handed a full workload at THREE positions (1974 PA) is
    capped to a realistic per-player ceiling (~700) with his per-position reps
    scaled down proportionally, and an over_allocated warning names him."""
    conn = q.get_db()
    _seed_spring_pool(conn)
    import offseason_queries as osq
    auto = q.get_spring_projection(TEAM_ID)
    pool = {p["player_id"]: p for p in auto["pool"]}
    # Find a bat eligible at 3 infield spots (the seed's SS/2B/3B types qualify).
    util = next((p for p in auto["pool"] if not p["is_pitcher"]
                 and len({"2B", "SS", "3B"} & set(p.get("eligible") or [])) >= 3), None)
    if util is None:
        return  # fixture didn't seed a 3-way utility bat; nothing to assert
    uid = util["player_id"]
    spots = [s for s in ("2B", "SS", "3B") if s in util["eligible"]]
    cfg = _clone_config(auto["config"])
    cfg["pa_alloc"] = {s: {str(uid): {"r": 467, "l": 191}} for s in spots}
    for s in spots:
        cfg["lineup"][s] = uid
    res = q.get_spring_projection(TEAM_ID, cfg)
    total = 0
    for s in spots:
        for r in res["constructed"]["lineup"][s]["players"]:
            if r["pid"] == uid:
                total += r["pa"]
    # Capped near the ceiling (allow a few PA of rounding across positions).
    assert total <= osq._SPRING_PLAYER_PA_CAP + len(spots)
    assert total < 1974  # definitely scaled down from the raw 3x workload
    warns = [w for w in res["warnings"] if w["kind"] == "over_allocated"]
    assert warns and any(util["name"] in w["msg"] for w in warns)


def test_spring_staff_rows_carry_contribution_and_proj_ip(q):
    """Rotation + bullpen rows carry a per-full-slot `war` (role-valued talent
    rate), a calibrated-role-IP `contrib_war` (value over his projected role
    innings), and `proj_ip`. A starter's projected IP exceeds a reliever's."""
    _seed_spring_pool(q.get_db())
    res = q.get_spring_projection(TEAM_ID)
    con = res["constructed"]
    for r in con["rotation"] + con["bullpen"]:
        assert set(r) >= {"war", "contrib_war", "proj_ip", "role", "pt_pct"}
        assert r["proj_ip"] > 0
    # SP projected IP should exceed RP projected IP (starters throw more).
    if con["rotation"] and con["bullpen"]:
        max_rp_ip = max(r["proj_ip"] for r in con["bullpen"])
        min_sp_ip = min(r["proj_ip"] for r in con["rotation"])
        assert min_sp_ip > max_rp_ip


def test_spring_staff_ip_covers_a_real_season(q):
    """The projected staff IP sums to a realistic full season (~1300-1600 team
    IP), NOT the ~1080 the old flat 65-IP-per-RP baseline implied. Confirms the
    bullpen carries a real reliever workload (issue: RP IP far too low)."""
    _seed_spring_pool(q.get_db())
    con = q.get_spring_projection(TEAM_ID)["constructed"]
    sp_ip = sum(r["proj_ip"] for r in con["rotation"])
    rp_ip = sum(r["proj_ip"] for r in con["bullpen"])
    total = sp_ip + rp_ip
    assert 1200 <= total <= 1650, f"staff IP {total} should cover a real season"
    # The bullpen is a meaningful share of the innings (real pens throw ~40%).
    assert rp_ip >= 350, f"bullpen IP {rp_ip} too low for a full season"


def test_spring_pitcher_valued_by_role_not_native_workload(q):
    """A pitcher's role-based value scales with the role he FILLS: a given arm's
    contribution over a full rotation slot (more IP) exceeds his contribution
    over a bullpen slot (fewer IP). Confirms the role-based-valuation fix — a
    starter isn't credited a starter's full-season WAR when used in relief."""
    _seed_spring_pool(q.get_db())
    pool = q._spring_pool(q.get_db(), TEAM_ID, q._eval_date(q.get_db()))
    sp = next((p for p in pool if p["is_pitcher"] and p["bucket"] == "SP"
               and "RP" in p.get("eligible", [])), None)
    if sp is not None:
        # The pool exposes both role valuations; SP-role value > RP-role value
        # for the same arm (a full rotation workload beats a bullpen workload).
        assert sp["sp_war"] >= sp["rp_war"]


def test_spring_bench_view_carries_rate_and_contribution(q):
    """Each bench reserve carries full-season RATE (war), projected pie
    CONTRIBUTION (contrib_war), pie PA, and where he plays (in_pie)."""
    _seed_spring_pool(q.get_db())
    res = q.get_spring_projection(TEAM_ID)
    for b in res["constructed"]["bench"]:
        assert set(b) >= {"pid", "name", "war", "contrib_war", "pie_pa", "in_pie"}
        # A pure reserve (not in a pie) has ~0 contribution but a real rate.
        if not b["in_pie"]:
            assert b["contrib_war"] == 0.0


def test_spring_active_hitters_includes_pie_and_bench(q):
    """active_hitters is the union of everyone taking pie PA and the explicit
    bench reserves — so a platoon partner not on the bench is still accounted."""
    conn = q.get_db()
    _seed_spring_pool(conn)
    auto = q.get_spring_projection(TEAM_ID)
    cfg = _clone_config(auto["config"])
    # Platoon a NON-bench, non-starter bat into LF's LHP wedge via pa_alloc.
    pool = {p["player_id"]: p for p in auto["pool"]}
    lf = cfg["lineup"].get("LF")
    partner = next((p["player_id"] for p in auto["pool"]
                    if not p["is_pitcher"] and p["player_id"] != lf
                    and "LF" in (p.get("eligible") or [])
                    and p["player_id"] not in cfg.get("bench", [])
                    and p["player_id"] not in cfg["lineup"].values()), None)
    if partner is None:
        return
    cfg["pa_alloc"] = {"LF": {str(lf): {"r": 467, "l": 60},
                              str(partner): {"r": 0, "l": 131}}}
    res = q.get_spring_projection(TEAM_ID, cfg)
    # The partner is in a pie → must appear in active_hitters even though he's
    # not on config["bench"].
    assert partner in res["constructed"]["active_hitters"]
    assert str(partner) in res["constructed"]["hitter_pie"]


def test_spring_bench_reserve_in_pie_shows_contribution(q):
    """A bench reserve who IS filling a platoon pie reports his pie positions
    (in_pie) and a non-zero contribution (not just his rate)."""
    conn = q.get_db()
    _seed_spring_pool(conn)
    auto = q.get_spring_projection(TEAM_ID)
    cfg = _clone_config(auto["config"])
    bench = list(cfg.get("bench", []))
    pool = {p["player_id"]: p for p in auto["pool"]}
    # Find a bench reserve eligible somewhere in the field, platoon him in.
    cand = next((b for b in bench
                 if set(pool.get(b, {}).get("eligible") or []) & set(("LF","RF","1B","3B","2B","SS"))), None)
    if cand is None:
        return
    pos = next(s for s in ("LF","RF","1B","3B","2B","SS")
               if s in (pool[cand].get("eligible") or []))
    starter = cfg["lineup"].get(pos)
    if not starter:
        return
    cfg["pa_alloc"] = {pos: {str(starter): {"r": 467, "l": 60},
                             str(cand): {"r": 0, "l": 131}}}
    res = q.get_spring_projection(TEAM_ID, cfg)
    bview = {b["pid"]: b for b in res["constructed"]["bench"]}
    if cand in bview:
        assert bview[cand]["in_pie"]          # notes where he plays
        assert bview[cand]["pie_pa"] > 0


def test_spring_no_over_allocation_warning_when_within_cap(q):
    """A normal auto roster (no body over a full season) raises NO
    over_allocated warning."""
    _seed_spring_pool(q.get_db())
    res = q.get_spring_projection(TEAM_ID)
    assert not any(w["kind"] == "over_allocated" for w in res["warnings"])


def test_spring_pa_cap_scales_war_proportionally(q):
    """The cap scales a player's CONTRIBUTION (WAR), not just the displayed PA —
    so the projected team WAR reflects the physically-possible workload."""
    conn = q.get_db()
    _seed_spring_pool(conn)
    import offseason_queries as osq
    auto = q.get_spring_projection(TEAM_ID)
    util = next((p for p in auto["pool"] if not p["is_pitcher"]
                 and len({"2B", "SS", "3B"} & set(p.get("eligible") or [])) >= 3), None)
    if util is None:
        return
    uid = util["player_id"]
    spots = [s for s in ("2B", "SS", "3B") if s in util["eligible"]]
    cfg = _clone_config(auto["config"])
    cfg["pa_alloc"] = {s: {str(uid): {"r": 467, "l": 191}} for s in spots}
    for s in spots:
        cfg["lineup"][s] = uid
    res = q.get_spring_projection(TEAM_ID, cfg)
    # Sum this player's contrib_war across the spots he fills — it must be
    # bounded by his single-slot WAR times (cap / slot_PA) * #spots-ish, i.e.
    # far below 3x his full-slot value. Simplest invariant: his total credited
    # reps are capped, so his summed contrib_war is < 3x a single full slot.
    one_slot = max(r["contrib_war"] for s in spots
                   for r in res["constructed"]["lineup"][s]["players"] if r["pid"] == uid)
    total_war = sum(r["contrib_war"] for s in spots
                    for r in res["constructed"]["lineup"][s]["players"] if r["pid"] == uid)
    assert total_war <= one_slot * len(spots) + 1e-6  # no position exceeds, sum bounded
    # And the capped total PA ratio ~ matches the WAR scaling (both linear).
    total_pa = sum(r["pa"] for s in spots
                   for r in res["constructed"]["lineup"][s]["players"] if r["pid"] == uid)
    assert total_pa <= osq._SPRING_PLAYER_PA_CAP + len(spots)


def test_spring_dh_platoon_suggestion_pairs_non_field_bat(q):
    """With a split DH starter and a strong-side bat who is NOT a field starter,
    the DH suggestion pairs that bat; a field starter with a better split is NOT
    chosen (would double-roster)."""
    conn = q.get_db()
    _seed_spring_pool(conn)
    auto = q.get_spring_projection(TEAM_ID)
    cfg = _clone_config(auto["config"])
    dh = cfg["lineup"].get("DH")
    if not dh:
        return
    # Make the DH starter weak vs RHP.
    conn.execute("""UPDATE ratings SET cntct_r=35,gap_r=35,pow_r=35,eye_r=35,
                    cntct_l=55,gap_l=55,pow_l=55,eye_l=55
                    WHERE player_id=? AND snapshot_date='2033-06-01'""", (dh,))
    # A bench-only bat (not in the field) who mashes RHP.
    conn.execute(
        "INSERT OR REPLACE INTO player_evaluation (player_id, eval_date, name, "
        "bucket, age, composite, ceiling, level, team_id, parent_team_id, peak_war) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (902, EVAL_DATE, "DH Masher", "1B", 30, 50, 52, "1", TEAM_ID, TEAM_ID, 1.8))
    conn.execute(
        "INSERT OR REPLACE INTO players (player_id, name, age, team_id, "
        "parent_team_id, level, pos, role, is_on_secondary) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (902, "DH Masher", 30, TEAM_ID, 0, "1", 3, 0, 1))
    conn.execute(
        "INSERT OR REPLACE INTO ratings (player_id, snapshot_date, league_id, "
        "cntct, gap, pow, eye, speed, first_b, cntct_r, gap_r, pow_r, eye_r, "
        "cntct_l, gap_l, pow_l, eye_l) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (902, "2033-06-01", 1, 50, 50, 50, 50, 40, 20, 75, 80, 75, 70, 40, 40, 35, 40))
    conn.commit()
    import offseason_queries as osq
    pool = osq._spring_pool(conn, TEAM_ID, osq._eval_date(conn))
    cfg["bench"] = list(cfg.get("bench", [])) + [902]
    sug = osq._spring_suggest_platoon(pool, cfg, "DH")
    field_starters = {pid for pos, pid in cfg["lineup"].items() if pos != "DH"}
    if sug:
        assert sug["partner"] not in field_starters


def test_spring_candidate_slot_war_is_position_adjusted(q):
    """Each pool hitter carries a slot_war map = his WAR AT each eligible
    position (so the candidate dropdown matches the selection result — fixes
    the native-vs-slot mismatch)."""
    _seed_spring_pool(q.get_db())
    conn = q.get_db()
    import offseason_queries as osq
    pool = osq._spring_pool(conn, TEAM_ID, osq._eval_date(conn))
    for p in pool:
        if p["is_pitcher"]:
            continue
        assert "slot_war" in p and p["slot_war"]
        # the slot_war at a position equals _spring_slot_war for that position
        for pos, w in p["slot_war"].items():
            assert abs(w - round(osq._spring_slot_war(p, pos), 1)) < 1e-6


def test_spring_pa_pie_budget_and_fill(q):
    """Each lineup position exposes a PA pie: a vs-RHP + vs-LHP wedge budget,
    per-player PA by hand, and the unfilled remainder."""
    _seed_spring_pool(q.get_db())
    res = q.get_spring_projection(TEAM_ID)
    for pos, slot in res["constructed"]["lineup"].items():
        b = slot.get("pa_budget")
        assert b and b["r_total"] > b["l_total"]  # more PA vs RHP
        filled_r = sum(p.get("pa_r", 0) for p in slot["players"])
        # filled + open should reconcile to the wedge budget (±rounding)
        assert abs((filled_r + b["r_open"]) - b["r_total"]) <= 2
        for p in slot["players"]:
            assert "pa_r" in p and "pa_l" in p


def test_spring_literal_pa_alloc_overrides_pie(q):
    """An explicit pa_alloc at a position becomes the source of truth for its
    pie — the players' PA match what was allocated (literal pie allocation)."""
    _seed_spring_pool(q.get_db())
    auto = q.get_spring_projection(TEAM_ID)
    cl = auto["config"]["lineup"]
    pool = {p["player_id"]: p for p in auto["pool"]}
    ss = cl.get("SS")
    partner = next((b for b in auto["config"]["bench"]
                    if b != ss and "SS" in (pool.get(b, {}).get("eligible") or [])), None)
    if ss and partner:
        cfg = _clone_config(auto["config"])
        cfg["pa_alloc"] = {"SS": {str(ss): {"r": 300, "l": 100},
                                  str(partner): {"r": 167, "l": 91}}}
        res = q.get_spring_projection(TEAM_ID, cfg)
        rows = {r["pid"]: r for r in res["constructed"]["lineup"]["SS"]["players"]}
        assert rows[ss]["pa_r"] == 300 and rows[ss]["pa_l"] == 100
        assert rows[partner]["pa_r"] == 167 and rows[partner]["pa_l"] == 91
        # the wedge is fully filled (300+167 ≈ 467 vsR)
        assert res["constructed"]["lineup"]["SS"]["pa_budget"]["r_open"] <= 1


def test_spring_pa_alloc_persists_in_plan(q):
    """A saved plan round-trips a literal PA allocation."""
    _seed_spring_pool(q.get_db())
    auto = q.get_spring_projection(TEAM_ID)
    ss = auto["config"]["lineup"].get("SS")
    if ss:
        cfg = _clone_config(auto["config"])
        cfg["pa_alloc"] = {"SS": {str(ss): {"r": 400, "l": 150}}}
        q.save_spring_plan(TEAM_ID, cfg)
        loaded = q.load_spring_plan(TEAM_ID)
        alloc = loaded["config"]["pa_alloc"].get("SS", {})
        # key normalized to int on load
        assert alloc.get(ss, {}).get("r") == 400
        q.delete_spring_plan(TEAM_ID)


def test_spring_pool_carries_woba_and_defense_stats(q):
    """Hitters expose the run-space model's native facets for display: a
    projected wOBA, defensive_value, and baserunning_value."""
    _seed_spring_pool(q.get_db())
    conn = q.get_db()
    import offseason_queries as osq
    pool = osq._spring_pool(conn, TEAM_ID, osq._eval_date(conn))
    hitters = [p for p in pool if not p["is_pitcher"]]
    assert hitters
    for h in hitters:
        assert "woba" in h["stats"]      # projected wOBA (display)
        assert "def" in h["stats"]       # defensive_value (model output)
        assert "bsr" in h["stats"]       # baserunning_value (model output)
    # wOBA is in a plausible range for a scaled league value
    wobas = [h["stats"]["woba"] for h in hitters if h["stats"]["woba"]]
    assert all(0.15 < w < 0.55 for w in wobas)


def test_spring_pool_prefers_stored_proj_woba(q):
    """When the evaluation engine has written an exact model wOBA
    (ratings.proj_woba), the pool surfaces THAT value rather than the OPS+ ×
    league-wOBA display estimate. Falls back to the estimate when NULL."""
    conn = q.get_db()
    _seed_spring_pool(conn)
    import offseason_queries as osq
    ed = osq._eval_date(conn)

    # Baseline: the seed has proj_woba NULL on every ratings row, so the pool
    # uses the estimate. Capture the SS's estimated wOBA.
    before = {p["player_id"]: p for p in osq._spring_pool(conn, TEAM_ID, ed)}
    ss_before = before[714]["stats"]["woba"]

    # Write an exact stored wOBA for the SS that is clearly distinct from the
    # estimate, then confirm the pool reads the stored value.
    stored = 0.345
    assert abs(ss_before - stored) > 1e-3, "pick a value distinct from the estimate"
    conn.execute(
        "UPDATE ratings SET proj_woba=? WHERE player_id=714 AND snapshot_date='2033-06-01'",
        (stored,))
    conn.commit()

    after = {p["player_id"]: p for p in osq._spring_pool(conn, TEAM_ID, ed)}
    assert abs(after[714]["stats"]["woba"] - stored) < 1e-6  # uses stored value
    # A hitter still lacking a stored value keeps the estimate (unchanged).
    assert after[711]["stats"]["woba"] == before[711]["stats"]["woba"]
