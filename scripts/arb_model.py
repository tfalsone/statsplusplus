"""
arb_model.py — MLB arbitration and service time estimation.

Estimates player service time and remaining team control years from game
appearance data. Used by contract_value.py and team_queries.py.

Public API:
  estimate_service_time(conn, player_id)                    → float
  estimate_control(conn, player_id, age, salary, bucket)    → (ctrl_years, salaries, pre_arb_left)
"""

import math
from constants import (
    SERVICE_GAMES_HITTER, SERVICE_STARTS_SP, SERVICE_GAMES_RP,
    ARB_DEEP_SALARY_THRESHOLD,
    ARB_HITTER_BASE, ARB_HITTER_EXP, ARB_RP_BASE, ARB_RP_EXP,
    ARB_RAISE_INTERCEPT, ARB_RAISE_SLOPE, ARB_RAISE_MIN,
)


def arb_salary(ovr, bucket, arb_year, prior_salary, min_sal):
    """Project arb salary for a given arb year (1-indexed).

    Uses RP-specific exponential model for RPs (calibrated from 35 RP arb contracts).
    Uses hitter/SP exponential base + annual raise model for all other positions.

    arb_year: 1 = first arb year, 2 = second, 3 = third
    prior_salary: previous year's salary (used for raise calculation)
    min_sal: league minimum salary
    """
    if bucket == "RP":
        rp_base = ARB_RP_BASE * math.exp(ARB_RP_EXP * ovr)
        return round(rp_base * (0.75 + 0.25 * (arb_year - 1)))
    if arb_year == 1:
        return round(ARB_HITTER_BASE * math.exp(ARB_HITTER_EXP * ovr))
    raise_amt = max(ARB_RAISE_MIN, round(ARB_RAISE_INTERCEPT + ARB_RAISE_SLOPE * ovr))
    return prior_salary + raise_amt


def estimate_service_time(conn, player_id):
    """Estimate fractional MLB service years from games played.

    Uses role-adjusted denominators per year:
      Hitters: g / SERVICE_GAMES_HITTER
      SP (gs >= g/2): gs / SERVICE_STARTS_SP
      RP (gs < g/2): g / SERVICE_GAMES_RP
    Caps each year at 1.0, sums across all years.
    """
    bat_by_year = {row[0]: row[1] for row in conn.execute(
        "SELECT year, SUM(g) FROM batting_stats WHERE player_id=? AND split_id=1 GROUP BY year",
        (player_id,)).fetchall()}

    pit_by_year = {row[0]: (row[1], row[2]) for row in conn.execute(
        "SELECT year, SUM(g), SUM(gs) FROM pitching_stats WHERE player_id=? AND split_id=1 GROUP BY year",
        (player_id,)).fetchall()}

    total = 0.0
    for yr in set(bat_by_year) | set(pit_by_year):
        bat_frac = bat_by_year.get(yr, 0) / SERVICE_GAMES_HITTER
        pg, pgs = pit_by_year.get(yr, (0, 0))
        pit_frac = (pgs / SERVICE_STARTS_SP if pgs >= pg * 0.5 else pg / SERVICE_GAMES_RP) if pg else 0.0
        total += min(1.0, max(bat_frac, pit_frac))
    return total


def estimate_control(conn, player_id, age, salary, bucket=None):
    """Estimate remaining team control years and salary schedule for 1yr contracts.

    Returns (ctrl_years, salaries, pre_arb_left) or (None, None, None) for FA deals.

    Pre-arb: salary == league_min. Uses games-based service time.
    Arb: salary > league_min, age < 30. Rounds up service time (games undercount roster days).
    FA deal: age >= 30 and salary > league_min → return None.
    """
    from player_utils import league_minimum
    min_sal = league_minimum()
    svc = estimate_service_time(conn, player_id)

    if salary <= min_sal:
        if age >= 30 or (age >= 28 and svc >= 3) or svc >= 6:
            return None, None, None
        svc_years = int(svc)
        remaining = max(1, 6 - svc_years)
        pre_arb_left = max(0, 3 - svc_years)
        return remaining, [None] * remaining, pre_arb_left

    if age >= 30:
        return None, None, None

    est_svc = max(math.ceil(svc), 4 if salary > ARB_DEEP_SALARY_THRESHOLD else 3)
    remaining = max(1, 6 - est_svc)
    return remaining, [None] * remaining, 0
