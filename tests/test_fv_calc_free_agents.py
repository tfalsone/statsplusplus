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
