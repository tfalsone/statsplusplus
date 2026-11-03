"""Team projection — pure computation (no DB, no I/O, no global state).

Projects a configured roster's season output as the cascade:

    estimated record (true-talent point estimate)
        run differential
            hitting / baserunning / fielding / pitching run contributions

Anchoring is the honest WAR identity — run diff is DERIVED from the record, not
summed independently, so the two always agree and both match league history:

    team_wins = replacement_wins + total_team_WAR
    run_diff  = (team_wins - games/2) * runs_per_win
    RS / RA   = lg_team_runs ± run_diff, split by offense-vs-pitching WAR share

Calibration constants (runs_per_win, lg_team_runs, win_band_sd, repl_winpct,
pyth_exp) are PER LEAGUE — the caller supplies a `ProjectionCalibration` derived
from that league's own team RS/RA/record history. See
`.kiro/specs/spring-training-page/design.md` §2.

Design note — uncertainty: the win band (±win_band_sd) is single-season luck and
is NOT actionable for comparisons. When two configs are compared, the luck term
cancels, so the win/run-diff DELTA is precise. The caller surfaces the delta as
the decision signal and the band only as quiet context.

Public API:
    ProjectionCalibration          # per-league constants
    PlayerContribution             # one roster slot's PT-weighted WAR
    TeamProjection                 # the cascade result
    project_team(contribs, calib)  # -> TeamProjection
    DEFAULT_CALIBRATION            # thin-history fallback
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

# Soft-saturation span for the win identity (wins ~ .500 ± span·tanh(...)). At
# 45, the map is near-linear within ~±30 WAR of the league mean (every real
# roster) and asymptotes toward .500 ± 45 wins (~36–126) so a pathological WAR
# total can't produce an absurd record. Tunable; not per-league.
_WIN_SATURATION_SPAN = 45.0

# Facet split of the OFFENSIVE half of the run differential. Priors (bat
# dominates; baserunning small; fielding moderate) — a position player's
# runs-above-avg spread is ~72% bat, ~8% baserunning, ~20% fielding. When the
# caller supplies per-player facet shares these are overridden per contribution.
_OFF_BAT_SHARE = 0.72
_OFF_BR_SHARE = 0.08
_OFF_FLD_SHARE = 0.20


@dataclass(slots=True)
class ProjectionCalibration:
    """Per-league constants for the record<->runs relationship.

    Derived from the league's own team-season history (see calibrate). Defaults
    on this dataclass are the generic fallback for thin-history leagues.
    """

    runs_per_win: float = 8.8       # wins-above-.500 per run of differential, inv
    lg_team_runs: float = 760.0     # league-average team RS == RA over a season
    win_band_sd: float = 9.0        # stdev of (actual - pythag-expected) wins
    repl_winpct: float = 0.294      # replacement-level win% (used if no WAR center)
    pyth_exp: float = 1.83          # pythagorean exponent (also a league setting)
    games: int = 162
    # Optional league-mean projected team-WAR. When set, the .500 point is
    # anchored HERE instead of at repl_winpct — i.e. a league-average roster
    # projects to exactly games/2 wins. This removes the systematic bias when
    # the ratings-based WAR scale is uniformly optimistic/pessimistic (an
    # average team summed ~84 WAR-wins on vMLB; anchoring recenters it to 81).
    lg_mean_team_war: float | None = None
    # Optional league-mean HITTER and PITCHER team-WAR, measured the same way as
    # lg_mean_team_war. These let each facet be expressed vs its OWN league
    # baseline (true facet strength), not as a slice of the overall run diff —
    # so an average team that's great-hitting/poor-pitching shows bat>0, pit<0
    # instead of a flat ~0 everywhere. Default split of lg_mean_team_war when
    # not supplied: ~offense-share of a team's WAR goes to hitters.
    lg_mean_hit_war: float | None = None
    lg_mean_pit_war: float | None = None


DEFAULT_CALIBRATION = ProjectionCalibration()


@dataclass(slots=True)
class PlayerContribution:
    """One roster slot's already-playing-time-weighted contribution.

    `war` is the WAR the player accrues in his assigned role/share this season
    (current-age peak_war x aging, x playing-time share, x readiness discount).
    `is_pitcher` routes the WAR to run prevention vs run scoring. Optional
    per-player facet shares override the offensive-split priors (e.g. a burner's
    higher baserunning share); when omitted the priors apply.
    """

    player_id: int
    name: str
    war: float
    is_pitcher: bool
    bat_share: float | None = None
    br_share: float | None = None
    fld_share: float | None = None


@dataclass(slots=True)
class TeamProjection:
    """The cascade result for one configured roster."""

    wins: float
    losses: float
    run_diff: float
    runs_scored: float
    runs_allowed: float
    team_war: float
    hit_war: float
    pit_war: float
    # Facet runs above average.
    bat_runs: float
    br_runs: float
    fld_runs: float
    pit_runs: float
    # Single-season luck band (±1 sigma) — context only, NOT applied to deltas.
    band_low: float
    band_high: float
    band_sd: float


def project_team(
    contribs: Iterable[PlayerContribution],
    calib: ProjectionCalibration = DEFAULT_CALIBRATION,
) -> TeamProjection:
    """Project the record->run-diff->facet cascade for a configured roster.

    Args:
        contribs: playing-time-weighted per-slot contributions (see
            PlayerContribution). WAR is already share-scaled by the caller.
        calib: per-league calibration constants.

    Returns:
        TeamProjection with the full cascade. Record is the true-talent point
        estimate; run diff is derived from it; RS/RA split by the offense/
        pitching WAR share; facet runs sum to the offensive half.
    """
    contribs = list(contribs)
    hit_war = sum(c.war for c in contribs if not c.is_pitcher)
    pit_war = sum(c.war for c in contribs if c.is_pitcher)
    team_war = hit_war + pit_war

    games = calib.games
    if calib.lg_mean_team_war is not None:
        # Anchored at the league mean: wins above/below .500 from WAR above/below
        # the mean, with a SOFT tanh saturation so realistic rosters stay nearly
        # linear but pathological WAR totals can't exceed a sane ceiling (a real
        # team can't win 162). span sets the gentle cap (~.500 ± span wins).
        raw_above = team_war - calib.lg_mean_team_war
        span = _WIN_SATURATION_SPAN
        wins = games / 2.0 + span * math.tanh(raw_above / span)
    else:
        # No anchor: the simple replacement-baseline identity (hard-clamped).
        wins = calib.repl_winpct * games + team_war
    wins = max(0.0, min(float(games), wins))
    losses = games - wins

    rpw = calib.runs_per_win

    # --- Facets measured vs their OWN league baseline (true facet strength) ---
    # Each facet's runs-above-average = (this team's facet WAR − the league's
    # average facet WAR) × runs/win. Independent of the overall differential, so
    # a .500 team that's great-hitting / poor-pitching reads bat>0, pit<0.
    #
    # League facet baselines: split the league-mean hitter/pitcher team-WAR into
    # per-facet baselines by the offensive-share priors. Fall back to splitting
    # lg_mean_team_war when the hit/pit split isn't supplied.
    lg_hit = calib.lg_mean_hit_war
    lg_pit = calib.lg_mean_pit_war
    if lg_hit is None or lg_pit is None:
        if calib.lg_mean_team_war is not None:
            # Typical team: ~offense drives slightly more than half of WAR.
            lg_hit = calib.lg_mean_team_war * 0.55
            lg_pit = calib.lg_mean_team_war * 0.45
        else:
            lg_hit = lg_pit = 0.0
    base_bat = lg_hit * _OFF_BAT_SHARE
    base_br = lg_hit * _OFF_BR_SHARE
    base_fld = lg_hit * _OFF_FLD_SHARE

    # This team's facet WAR (per-player shares where supplied, else priors).
    tbat = tbr = tfld = 0.0
    for c in contribs:
        if c.is_pitcher:
            continue
        b = c.bat_share if c.bat_share is not None else _OFF_BAT_SHARE
        r = c.br_share if c.br_share is not None else _OFF_BR_SHARE
        f = c.fld_share if c.fld_share is not None else _OFF_FLD_SHARE
        tot = (b + r + f) or 1.0
        tbat += c.war * b / tot
        tbr += c.war * r / tot
        tfld += c.war * f / tot

    bat_runs = (tbat - base_bat) * rpw
    br_runs = (tbr - base_br) * rpw
    fld_runs = (tfld - base_fld) * rpw
    pit_runs = (pit_war - lg_pit) * rpw

    # RS / RA and the run differential now come from the ABSOLUTE facets, so the
    # cascade is internally consistent (run_diff == RS − RA == sum of facets).
    # The RECORD stays anchored to the WAR identity (the trustworthy part); the
    # facets/run-diff tell the honest vs-league story that drives the headline.
    off_rd = bat_runs + br_runs + fld_runs
    runs_scored = calib.lg_team_runs + off_rd
    runs_allowed = calib.lg_team_runs - pit_runs
    run_diff = runs_scored - runs_allowed

    sd = calib.win_band_sd
    return TeamProjection(
        wins=wins, losses=losses, run_diff=run_diff,
        runs_scored=runs_scored, runs_allowed=runs_allowed,
        team_war=team_war, hit_war=hit_war, pit_war=pit_war,
        bat_runs=bat_runs, br_runs=br_runs, fld_runs=fld_runs, pit_runs=pit_runs,
        band_low=wins - sd, band_high=wins + sd, band_sd=sd,
    )


def projection_delta(
    before: TeamProjection, after: TeamProjection
) -> dict[str, float]:
    """The decision signal: the change between two configs.

    Season luck cancels between two projections, so these deltas are precise —
    the band does NOT apply to them. Returned as a plain dict for the caller/UI.
    """
    return {
        "wins": after.wins - before.wins,
        "run_diff": after.run_diff - before.run_diff,
        "bat_runs": after.bat_runs - before.bat_runs,
        "br_runs": after.br_runs - before.br_runs,
        "fld_runs": after.fld_runs - before.fld_runs,
        "pit_runs": after.pit_runs - before.pit_runs,
        "team_war": after.team_war - before.team_war,
    }
