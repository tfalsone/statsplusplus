"""Tests for the pure team-projection engine (evaluation.team_projection).

Covers the invariants that must hold for the record<->run-diff cascade:
  - WAR identity (wins = baseline + team WAR)
  - league-mean-WAR anchor recenters an average roster to games/2
  - run diff DERIVED from the record (consistency with runs_per_win)
  - RS/RA split by offense/pitching share and reconcile to the diff
  - facet runs sum to the offensive half
  - the delta between two configs is exact (the decision signal)
"""

from statsplusplus.evaluation.team_projection import (
    ProjectionCalibration,
    PlayerContribution,
    project_team,
    projection_delta,
    DEFAULT_CALIBRATION,
)

CAL = ProjectionCalibration(
    runs_per_win=8.29, lg_team_runs=770.0, win_band_sd=9.5,
    pyth_exp=1.83, lg_mean_team_war=36.0,
)


def _roster(hit_war, pit_war):
    return [
        PlayerContribution(1, "H", hit_war, is_pitcher=False),
        PlayerContribution(2, "P", pit_war, is_pitcher=True),
    ]


def test_average_roster_centers_at_half_games():
    """An average-WAR roster projects to exactly games/2 under the WAR anchor."""
    p = project_team([PlayerContribution(1, "avg", 36.0, False)], CAL)
    assert abs(p.wins - 81.0) < 1e-6
    assert abs(p.run_diff) < 1e-6


def test_war_identity_above_average():
    """Wins rise ~1:1 with team WAR above the anchored center (near-linear in
    the realistic range; the soft saturation barely bends it at +4 WAR)."""
    p = project_team([PlayerContribution(1, "x", 40.0, False)], CAL)
    assert abs(p.wins - 85.0) < 0.5  # ~81 + (40 - 36), tanh bend is tiny here


def test_run_diff_equals_facet_sum_and_rs_minus_ra():
    """run_diff is the sum of the four (vs-baseline) facets AND RS − RA — the
    cascade is internally consistent (facets drive the diff, not the record)."""
    p = project_team(_roster(30.0, 12.0), CAL)
    assert abs(p.run_diff - (p.bat_runs + p.br_runs + p.fld_runs + p.pit_runs)) < 1e-6
    assert abs(p.run_diff - (p.runs_scored - p.runs_allowed)) < 1e-6


def test_rs_ra_reconcile_to_run_diff():
    """RS - RA must equal the run differential."""
    p = project_team(_roster(32.0, 10.0), CAL)
    assert abs((p.runs_scored - p.runs_allowed) - p.run_diff) < 1e-6


def test_rs_ra_split_by_war_share():
    """A pitching-heavy roster puts more of the diff on run prevention."""
    off_heavy = project_team(_roster(40.0, 4.0), CAL)
    def_heavy = project_team(_roster(4.0, 40.0), CAL)
    # same team WAR, same wins/diff; different split
    assert abs(off_heavy.wins - def_heavy.wins) < 1e-6
    assert off_heavy.bat_runs > def_heavy.bat_runs
    assert def_heavy.pit_runs > off_heavy.pit_runs


def test_facets_sum_to_run_diff():
    """The four facets (bat+br+fld+pit), each measured vs its league baseline,
    sum to the run differential — the cascade stays internally consistent."""
    p = project_team(_roster(30.0, 12.0), CAL)
    assert abs((p.bat_runs + p.br_runs + p.fld_runs + p.pit_runs) - p.run_diff) < 1e-6
    assert abs((p.runs_scored - p.runs_allowed) - p.run_diff) < 1e-6


def test_facets_show_identity_for_average_team():
    """An average-WAR team with a hitting/pitching IMBALANCE shows non-flat
    facets (the per-facet-baseline fix): great bats + weak arms -> bat>0, pit<0,
    even though the record is ~.500."""
    cal = ProjectionCalibration(
        runs_per_win=8.29, lg_team_runs=770.0, win_band_sd=9.5, pyth_exp=1.83,
        lg_mean_team_war=36.0, lg_mean_hit_war=20.0, lg_mean_pit_war=16.0)
    # Hitters well above the 20.0 baseline, pitchers well below the 16.0 — same
    # total (36) as an average team, so the record is ~.500.
    roster = [PlayerContribution(1, "bats", 28.0, False),
              PlayerContribution(2, "arms", 8.0, True)]
    p = project_team(roster, cal)
    assert abs(p.wins - 81.0) < 1.5           # ~.500 by total WAR
    assert p.bat_runs > 20                    # clearly above-average offense
    assert p.pit_runs < -40                   # clearly below-average pitching


def test_per_player_facet_shares_override_priors():
    """A burner with a high baserunning share shifts the facet split."""
    base = [PlayerContribution(1, "normal", 30.0, False),
            PlayerContribution(2, "P", 10.0, True)]
    burner = [PlayerContribution(1, "burner", 30.0, False,
                                 bat_share=0.5, br_share=0.4, fld_share=0.1),
              PlayerContribution(2, "P", 10.0, True)]
    pb = project_team(base, CAL)
    pr = project_team(burner, CAL)
    assert pr.br_runs > pb.br_runs
    assert pr.bat_runs < pb.bat_runs


def test_delta_is_exact_and_luck_free():
    """The delta between two configs is the precise decision signal."""
    before = project_team(_roster(30.0, 10.0), CAL)
    after = project_team(_roster(31.0, 10.0), CAL)
    d = projection_delta(before, after)
    assert abs(d["wins"] - (after.wins - before.wins)) < 1e-9
    assert d["wins"] > 0  # adding WAR adds wins
    # band is unchanged context, not part of the delta
    assert before.band_sd == after.band_sd


def test_band_is_one_sigma_window():
    p = project_team(_roster(30.0, 10.0), CAL)
    assert abs(p.band_high - p.band_low - 2 * CAL.win_band_sd) < 1e-6


def test_default_calibration_without_anchor_uses_replacement():
    """With no lg_mean_team_war, the baseline is repl_winpct * games."""
    p = project_team([PlayerContribution(1, "x", 33.0, False)], DEFAULT_CALIBRATION)
    expected = DEFAULT_CALIBRATION.repl_winpct * DEFAULT_CALIBRATION.games + 33.0
    assert abs(p.wins - expected) < 1e-6


def test_wins_clamped_to_schedule():
    """An absurd WAR total can't exceed the games count."""
    p = project_team([PlayerContribution(1, "x", 500.0, False)], CAL)
    assert p.wins <= CAL.games
    assert p.losses >= 0


def test_win_identity_saturates_at_extremes():
    """Realistic rosters are near-linear, but a pathological WAR total produces
    a capped (not absurd) record — the soft tanh saturation."""
    # Near-linear in range: +10 WAR over the 36 mean ~ 91 wins.
    near = project_team([PlayerContribution(1, "x", 46.0, False)], CAL)
    assert abs(near.wins - 91.0) < 1.0
    # Extreme: 72 WAR would be 117 linearly; saturation keeps it well under.
    extreme = project_team([PlayerContribution(1, "x", 72.0, False)], CAL)
    assert extreme.wins < 117.0 and extreme.wins > 100.0
    # Asymptote: even 300 WAR can't approach 162.
    absurd = project_team([PlayerContribution(1, "x", 300.0, False)], CAL)
    assert absurd.wins < 130.0
