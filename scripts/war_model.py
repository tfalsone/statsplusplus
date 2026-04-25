"""
war_model.py — WAR projection and stat history utilities.

Provides WAR estimation from Ovr ratings and aging curves, plus stat history
loading for the MLB contract surplus model. No DB schema knowledge — takes
connections as parameters.

Public API:
  peak_war_from_ovr(ovr, bucket)                    → float
  aging_mult(age, bucket)                            → float
  load_stat_history(conn, game_date)                 → (bat_hist, pit_hist, two_way)
  stat_peak_war(pid, bucket, bat_hist, pit_hist, ...) → float | None
"""

from constants import OVR_TO_WAR, OVR_TO_WAR_CALIBRATED, AGING_HITTER, AGING_PITCHER

# ---------------------------------------------------------------------------
# WAR interpolation helpers
# ---------------------------------------------------------------------------

def _interp(table_rows, value, col_idx):
    for i in range(len(table_rows) - 1):
        v0, v1 = table_rows[i][0], table_rows[i+1][0]
        if v1 <= value <= v0:
            t = (value - v1) / (v0 - v1)
            return table_rows[i+1][col_idx] + t * (table_rows[i][col_idx] - table_rows[i+1][col_idx])
    if value >= table_rows[0][0]: return table_rows[0][col_idx]
    return table_rows[-1][col_idx]


def _interp_dict(tbl, ovr):
    pts = sorted(tbl.keys())
    if ovr >= pts[-1]: return tbl[pts[-1]]
    if ovr <= pts[0]:  return tbl[pts[0]]
    for i in range(len(pts) - 1):
        if pts[i] <= ovr <= pts[i + 1]:
            t = (ovr - pts[i]) / (pts[i + 1] - pts[i])
            return tbl[pts[i]] + t * (tbl[pts[i + 1]] - tbl[pts[i]])
    return tbl[pts[0]]


# ---------------------------------------------------------------------------
# WAR projection
# ---------------------------------------------------------------------------

def peak_war_from_score(score, bucket):
    """Project peak WAR/season from a score (Composite_Score or OVR) and positional bucket.

    Uses COMPOSITE_TO_WAR tables when available, falls back to calibrated
    OVR_TO_WAR tables, then to default OVR_TO_WAR.

    This is the canonical WAR projection function. Both Composite_Score and OVR
    are on the 20-80 scale, so the same interpolation logic applies.
    """
    from constants import COMPOSITE_TO_WAR
    # Prefer COMPOSITE_TO_WAR when available
    if COMPOSITE_TO_WAR and bucket in COMPOSITE_TO_WAR:
        return _interp_dict(COMPOSITE_TO_WAR[bucket], score)
    # Fall back to calibrated OVR_TO_WAR
    if OVR_TO_WAR_CALIBRATED and bucket in OVR_TO_WAR_CALIBRATED:
        return _interp_dict(OVR_TO_WAR_CALIBRATED[bucket], score)
    col = 2 if bucket == "SP" else (3 if bucket == "RP" else 1)
    return _interp(OVR_TO_WAR, score, col)


def peak_war_from_ovr(ovr, bucket):
    """Backward-compatible alias for peak_war_from_score().

    Accepts either OVR or Composite_Score — both are on the 20-80 scale.
    """
    return peak_war_from_score(ovr, bucket)


def aging_mult(age, bucket):
    """Aging curve multiplier on peak WAR. Interpolated between defined age points."""
    table = AGING_PITCHER if bucket in ("SP", "RP") else AGING_HITTER
    ages  = sorted(table)
    if age <= ages[0]:  return 1.0
    if age >= ages[-1]: return table[ages[-1]]
    for i in range(len(ages) - 1):
        a0, a1 = ages[i], ages[i+1]
        if a0 <= age <= a1:
            t = (age - a0) / (a1 - a0)
            return table[a0] + t * (table[a1] - table[a0])
    return 0.35


# ---------------------------------------------------------------------------
# Stat history (used by contract_value.py and fv_calc.py)
# ---------------------------------------------------------------------------

def load_stat_history(conn, game_date):
    """Load completed-season stats into memory. Excludes current partial season.
    Aggregates across teams for traded players."""
    game_year = int(game_date[:4])

    bat_rows = conn.execute(
        """SELECT player_id, year, SUM(war) as war, SUM(ab) as ab,
                  MAX(stint) as max_stint, COUNT(team_id) as team_count
           FROM batting_stats WHERE split_id=1 AND year < ?
           GROUP BY player_id, year""", (game_year,)
    ).fetchall()
    pit_rows = conn.execute(
        """SELECT player_id, year,
                  SUM((war + COALESCE(ra9war, war)) / 2.0) as war,
                  SUM(gs) as gs, SUM(ip) as ip,
                  MAX(stint) as max_stint, COUNT(team_id) as team_count
           FROM pitching_stats WHERE split_id=1 AND year < ?
           GROUP BY player_id, year""", (game_year,)
    ).fetchall()

    bat_hist = {}
    for r in bat_rows:
        if (r["ab"] or 0) < 130:
            continue
        incomplete = (r["max_stint"] == 1 and r["team_count"] == 1)
        bat_hist.setdefault(r["player_id"], []).append(
            {"year": r["year"], "war": r["war"] or 0, "incomplete": incomplete})

    pit_hist = {}
    for r in pit_rows:
        incomplete = (r["max_stint"] == 1 and r["team_count"] == 1)
        pit_hist.setdefault(r["player_id"], []).append(
            {"year": r["year"], "war": r["war"] or 0,
             "is_sp": (r["gs"] or 0) >= 10, "incomplete": incomplete})

    two_way = set()
    bat_by_year = {}
    for r in bat_rows:
        if (r["ab"] or 0) >= 130:
            bat_by_year.setdefault(r["player_id"], set()).add(r["year"])
    for r in pit_rows:
        if (r["gs"] or 0) >= 10:
            pid = r["player_id"]
            if pid in bat_by_year and r["year"] in bat_by_year[pid]:
                two_way.add(pid)

    for d in (bat_hist, pit_hist):
        for pid in d:
            d[pid].sort(key=lambda x: x["year"], reverse=True)

    return bat_hist, pit_hist, two_way


def stat_peak_war(pid, bucket, bat_hist, pit_hist, two_way=None):
    """3-year weighted WAR average for role-consistent seasons. Returns None if insufficient."""
    if two_way and pid in two_way:
        return _two_way_peak_war(pid, bucket, bat_hist, pit_hist)

    role_changed = False
    if bucket in ("SP", "RP"):
        is_sp = bucket == "SP"
        seasons = [s for s in pit_hist.get(pid, []) if s["is_sp"] == is_sp]
        if not seasons:
            seasons = [s for s in pit_hist.get(pid, []) if s["is_sp"] != is_sp]
            role_changed = bool(seasons)
    else:
        seasons = bat_hist.get(pid, [])

    if not seasons:
        return None
    weights = [3, 2, 1][:len(seasons)]
    effective_wars = [s["war"] / (0.5 if s.get("incomplete") else 1.0) for s in seasons]
    result = sum(w * ew for w, ew in zip(weights, effective_wars)) / sum(weights)
    if role_changed:
        result *= 0.46 if bucket == "RP" else 2.15
    return result


def _two_way_peak_war(pid, bucket, bat_hist, pit_hist):
    bat_by_yr = {s["year"]: s["war"] for s in bat_hist.get(pid, [])}
    pit_by_yr = {s["year"]: s["war"] for s in pit_hist.get(pid, [])}
    years = sorted(set(bat_by_yr) | set(pit_by_yr), reverse=True)
    if not years:
        return None
    combined = [bat_by_yr.get(y, 0) + pit_by_yr.get(y, 0) for y in years[:3]]
    weights = [3, 2, 1][:len(combined)]
    return sum(w * c for w, c in zip(weights, combined)) / sum(weights)
