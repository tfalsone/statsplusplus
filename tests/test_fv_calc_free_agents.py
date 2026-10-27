"""Regression tests for free-agent handling in fv_calc.

A free agent (``team_id = 0``, ``free_agent = 1``) is an unsigned player on the
open market, not a cost-controlled asset or a farm-system prospect. fv_calc must
NOT:
  - grade him with a prospect FV (he is not a prospect), nor
  - assign him a controlled-asset surplus projection (pre-arb / arb / 6-year
    control), which is meaningless for a player no team controls.

Before the fix, every free agent in a league fell through to the pre-arb /
minor-leaguer branches and was stored with ``ctrl_type = 'pre-arb'``,
``years_control = 6``, an FV grade, and a large phantom surplus — so a 29-year-old
veteran free agent read on the player page as a cheap cost-controlled youngster.
See docs/changelog.md (free-agent valuation fix).
"""

from __future__ import annotations

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "scripts"))

from statsplusplus.data.db import get_connection
from statsplusplus.data.fv_calc import run as fv_calc_run
from tests._fixture_league import build_fixture, remove_fixture, EVAL_DATE, TEAM_ID

SLUG = "fvcalc_fa_test"


def _seed_free_agent(league_dir: Path) -> None:
    """Add a veteran free agent (team_id=0, free_agent=1) WITH real career MLB
    stats, so the exclusion is driven by free-agent status — not by the
    separate 'no career stats' pre-arb heuristic."""
    conn = get_connection(league_dir)

    def _ins(table, **cols):
        keys = ",".join(cols)
        conn.execute(
            f"INSERT OR REPLACE INTO {table} ({keys}) "
            f"VALUES ({','.join('?' * len(cols))})",
            list(cols.values()),
        )

    # 29-year-old FA 2B with a long MLB track record, currently unsigned.
    _ins("players", player_id=300, name="Vet FreeAgent", age=29,
         team_id=0, parent_team_id=0, level="0", pos=4, role=0, free_agent=1)
    _ins("ratings", player_id=300, snapshot_date="2033-04-01",
         ovr=52, pot=54, composite_score=52, ceiling_score=54, league_id=1,
         cntct=55, gap=50, pow=52, eye=54, ks=50, speed=52, steal=48,
         pot_cntct=55, pot_gap=50, pot_pow=52, pot_eye=54, pot_ks=50,
         c=20, ss=50, second_b=55, third_b=50, first_b=45, lf=45, cf=48, rf=45,
         ofr=48, ofa=50, ofe=50, ifr=50, ifa=50, ife=50, tdp=50,
         acc="A", wrk_ethic="N", height=183, bats="R", throws="R")
    # Multiple seasons of real MLB batting stats (well over the 130-AB threshold).
    for yr in (2030, 2031, 2032):
        _ins("batting_stats", player_id=300, year=yr, team_id=2, split_id=1,
             pa=600, ab=540, h=145, d=28, t=2, hr=16, r=70, rbi=65, bb=50, k=95,
             sb=6, g=150, avg=0.269, obp=0.335, slg=0.440, war=2.2)
    conn.commit()
    conn.close()


def test_free_agent_excluded_from_fv_and_controlled_surplus():
    league_dir = build_fixture(SLUG, with_ovr=True)
    try:
        _seed_free_agent(league_dir)
        fv_calc_run(league_dir)

        conn = get_connection(league_dir)
        ed = conn.execute("SELECT MAX(eval_date) FROM player_evaluation").fetchone()[0]

        fa = conn.execute(
            "SELECT fv, fv_str, surplus, surplus_yr1, years_control, ctrl_type "
            "FROM player_evaluation WHERE player_id=300 AND eval_date=?",
            (ed,),
        ).fetchone()
        assert fa is not None, "FA should still appear in player_evaluation"
        # No prospect FV grade for a free agent.
        assert fa["fv"] is None, f"FA must have no FV grade, got {fa['fv']}"
        # No controlled-asset surplus — he is unsigned.
        assert fa["ctrl_type"] == "fa", f"FA ctrl_type should be 'fa', got {fa['ctrl_type']}"
        assert fa["years_control"] == 0, f"FA years_control should be 0, got {fa['years_control']}"
        assert (fa["surplus"] or 0) == 0, f"FA surplus should be 0, got {fa['surplus']}"

        # The FA must NOT appear in the prospect_fv view.
        assert conn.execute(
            "SELECT 1 FROM prospect_fv WHERE player_id=300"
        ).fetchone() is None, "FA leaked into prospect_fv"

        # Controlled players are unaffected: the fixture MLB hitter still has a
        # real controlled surplus (not an FA).
        ctrl = conn.execute(
            "SELECT surplus, ctrl_type FROM player_evaluation WHERE player_id=100 AND eval_date=?",
            (ed,),
        ).fetchone()
        assert ctrl is not None
        assert ctrl["ctrl_type"] != "fa"

        conn.close()
    finally:
        remove_fixture(SLUG)


def _seed_draft_amateur(league_dir: Path) -> None:
    """Add a draft-eligible amateur: flagged unsigned exactly like a free agent
    (team_id=0, free_agent=1, level='0') but draft_eligible=1, and with NO MLB
    career stats. In the pre-draft window OOTP presents the amateur pool this
    way, and the draft board needs these players graded — so the FA skip must
    NOT swallow them."""
    conn = get_connection(league_dir)

    def _ins(table, **cols):
        keys = ",".join(cols)
        conn.execute(
            f"INSERT OR REPLACE INTO {table} ({keys}) "
            f"VALUES ({','.join('?' * len(cols))})",
            list(cols.values()),
        )

    # 18-year-old draft-eligible SS, unsigned (looks like an FA), no pro stats.
    # pro_service_years=0 is a REAL value (the game tracks his service) — this
    # is what marks a current amateur apart from a post-draft veteran FA whose
    # service is blank/NULL.
    _ins("players", player_id=301, name="Amateur Prospect", age=18,
         team_id=0, parent_team_id=0, level="0", pos=6, role=0,
         free_agent=1, draft_eligible=1, pro_service_years=0)
    _ins("ratings", player_id=301, snapshot_date="2033-04-01",
         ovr=40, pot=60, composite_score=40, ceiling_score=60, league_id=1,
         cntct=40, gap=45, pow=50, eye=45, ks=45, speed=60, steal=55,
         pot_cntct=55, pot_gap=55, pot_pow=60, pot_eye=55, pot_ks=50,
         c=20, ss=55, second_b=50, third_b=50, first_b=45, lf=45, cf=50, rf=45,
         pot_ss=60, pot_second_b=55, pot_third_b=55,
         ofr=48, ofa=50, ofe=50, ifr=55, ifa=55, ife=50, tdp=50,
         acc="A", wrk_ethic="N", height=183, bats="R", throws="R")

    # Post-draft veteran-FA shape: carries draft_eligible=1 but BLANK pro service
    # (the game is no longer tracking him as a current amateur). Same unsigned
    # flags as the amateur above, but he must NOT be graded as a prospect — this
    # is the cohort the pro_service_years guard exists to exclude.
    _ins("players", player_id=302, name="Stale Eligible Vet", age=33,
         team_id=0, parent_team_id=0, level="0", pos=4, role=0,
         free_agent=1, draft_eligible=1, pro_service_years=None)
    _ins("ratings", player_id=302, snapshot_date="2033-04-01",
         ovr=45, pot=45, composite_score=45, ceiling_score=45, league_id=1,
         cntct=45, gap=45, pow=45, eye=45, ks=45, speed=45, steal=45,
         pot_cntct=45, pot_gap=45, pot_pow=45, pot_eye=45, pot_ks=45,
         c=20, ss=45, second_b=48, third_b=45, first_b=45, lf=45, cf=45, rf=45,
         ofr=48, ofa=50, ofe=50, ifr=48, ifa=48, ife=50, tdp=50,
         acc="A", wrk_ethic="N", height=183, bats="R", throws="R")
    conn.commit()
    conn.close()


def test_draft_eligible_amateur_is_graded_not_skipped():
    """A draft-eligible amateur carries the same unsigned flags as a free agent
    (team_id=0, free_agent=1) but MUST receive a prospect FV and appear in
    prospect_fv — otherwise the draft board (which inner-joins prospect_fv)
    renders empty. Regression for the 'draft sims / team lists return nothing'
    bug."""
    league_dir = build_fixture(SLUG, with_ovr=True)
    try:
        _seed_draft_amateur(league_dir)
        fv_calc_run(league_dir)

        conn = get_connection(league_dir)
        ed = conn.execute("SELECT MAX(eval_date) FROM player_evaluation").fetchone()[0]

        row = conn.execute(
            "SELECT fv, fv_str, level, surplus, years_control, ctrl_type "
            "FROM player_evaluation WHERE player_id=301 AND eval_date=?", (ed,),
        ).fetchone()
        assert row is not None, "draft amateur missing from player_evaluation"
        assert row["fv"] is not None, "draft amateur must receive an FV grade"
        assert row["level"] == "Draft", f"expected level 'Draft', got {row['level']!r}"
        # Surplus pass must also treat him as a controllable prospect, NOT an FA:
        # a draft pick comes with a full pre-arb control period, which is what
        # makes it valuable. An FA-typed row would zero his surplus.
        assert row["ctrl_type"] != "fa", (
            f"draft amateur must not be ctrl_type 'fa', got {row['ctrl_type']}"
        )
        assert (row["years_control"] or 0) > 0, "draft amateur must have team-control years"

        # Must be visible in the prospect_fv view the draft board joins on.
        pf = conn.execute(
            "SELECT fv FROM prospect_fv WHERE player_id=301"
        ).fetchone()
        assert pf is not None, "draft amateur did not reach prospect_fv — board would be empty"

        # The blank-service draft_eligible veteran must NOT be graded as a
        # prospect: no FV grade, and absent from the prospect_fv view.
        vet = conn.execute(
            "SELECT fv FROM player_evaluation WHERE player_id=302 AND eval_date=?",
            (ed,),
        ).fetchone()
        assert vet is None or vet["fv"] is None, (
            "blank-service draft_eligible veteran must not receive an FV grade"
        )
        assert conn.execute(
            "SELECT 1 FROM prospect_fv WHERE player_id=302"
        ).fetchone() is None, "blank-service veteran leaked into prospect_fv"

        conn.close()
    finally:
        remove_fixture(SLUG)
