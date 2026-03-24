#!/usr/bin/env python3
"""
calibrate.py — Derive league-specific valuation tables from actual data.

Produces config/model_weights.json with:
  - OVR_TO_WAR: position-specific Ovr→WAR regression (slope + intercept)
  - FV_TO_PEAK_WAR: derived from OVR_TO_WAR by mapping FV→expected peak Ovr
  - ARB_PCT: arb salary as fraction of market value by arb year
  - SCARCITY_MULT: FA availability by Pot grade (mid-season only)

Falls back to constants.py defaults when insufficient data.

Usage: python3 scripts/calibrate.py [--dry-run]
"""

import json, os, sys, math
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE / "scripts"))

import db as _db
from league_context import get_league_dir
from league_config import config as _cfg
from player_utils import assign_bucket
from constants import (OVR_TO_WAR, FV_TO_PEAK_WAR, FV_TO_PEAK_WAR_RP,
                        ARB_PCT, SCARCITY_MULT)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MIN_REGRESSION_N = 40  # minimum seasons for position-specific regression
CALIBRATION_YEARS = 3  # use most recent N complete years
HITTER_BUCKETS = ("C", "SS", "2B", "3B", "CF", "COF", "1B")
PITCHER_BUCKETS = ("SP", "RP")

# Key mapping from DB column names to player_utils expected names
_KEY_MAP = {
    "pot_c": "PotC", "pot_ss": "PotSS", "pot_second_b": "Pot2B",
    "pot_third_b": "Pot3B", "pot_first_b": "Pot1B", "pot_lf": "PotLF",
    "pot_cf": "PotCF", "pot_rf": "PotRF",
    "c": "C", "ss": "SS", "second_b": "2B", "third_b": "3B",
    "first_b": "1B", "lf": "LF", "cf": "CF", "rf": "RF",
    "stm": "Stm", "ovr": "Ovr", "pot": "Pot",
    "pot_fst": "PotFst", "pot_snk": "PotSnk", "pot_crv": "PotCrv",
    "pot_sld": "PotSld", "pot_chg": "PotChg", "pot_splt": "PotSplt",
    "pot_cutt": "PotCutt", "pot_cir_chg": "PotCirChg", "pot_scr": "PotScr",
    "pot_frk": "PotFrk", "pot_kncrv": "PotKncrv", "pot_knbl": "PotKnbl",
}


def _linreg(xs, ys):
    """Simple OLS regression. Returns (slope, intercept, r_squared, n)."""
    n = len(xs)
    if n < 5:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    ss_xx = sum((x - mx) ** 2 for x in xs)
    ss_xy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    ss_yy = sum((y - my) ** 2 for y in ys)
    if ss_xx == 0 or ss_yy == 0:
        return None
    slope = ss_xy / ss_xx
    intercept = my - slope * mx
    r_sq = (ss_xy ** 2) / (ss_xx * ss_yy)
    return slope, intercept, r_sq, n


def _war_at(slope, intercept, ovr):
    return max(0.0, round(slope * ovr + intercept, 2))


def _bucket_player(row, role_map):
    """Assign bucket to a player row from the calibration query."""
    p = dict(row)
    p["Pos"] = str(p.get("pos") or "")
    p["_role"] = role_map.get(str(p.get("role") or 0), "position_player")
    p["_is_pitcher"] = (p["Pos"] == "P" or p["_role"] in ("starter", "reliever", "closer"))
    p["Age"] = p["age"]
    for db_key, api_key in _KEY_MAP.items():
        if db_key in p:
            p[api_key] = p[db_key]
    return assign_bucket(p, use_pot=False)


# ---------------------------------------------------------------------------
# Step 1: OVR_TO_WAR regression
# ---------------------------------------------------------------------------

def _calibrate_ovr_to_war(conn, game_year, role_map):
    """Run Ovr→WAR regression per position bucket using recent complete seasons."""
    year_lo = game_year - CALIBRATION_YEARS - 1  # exclusive lower bound
    year_hi = game_year - 1  # inclusive upper bound (exclude current partial season)

    # Hitters
    hitter_rows = conn.execute("""
        SELECT r.player_id, r.ovr, r.pot, p.age, p.pos, p.role,
               r.pot_c, r.pot_ss, r.pot_second_b, r.pot_third_b, r.pot_first_b,
               r.pot_lf, r.pot_cf, r.pot_rf,
               r.c, r.ss, r.second_b, r.third_b, r.first_b, r.lf, r.cf, r.rf,
               r.stm,
               r.pot_fst, r.pot_snk, r.pot_crv, r.pot_sld, r.pot_chg,
               r.pot_splt, r.pot_cutt, r.pot_cir_chg, r.pot_scr, r.pot_frk,
               r.pot_kncrv, r.pot_knbl,
               bs.war
        FROM latest_ratings r
        JOIN players p ON r.player_id = p.player_id
        JOIN batting_stats bs ON bs.player_id = p.player_id
        WHERE p.level = 1 AND bs.split_id = 1
          AND bs.year > ? AND bs.year <= ? AND bs.ab >= 300
    """, (year_lo, year_hi)).fetchall()

    # Pitchers
    pitcher_rows = conn.execute("""
        SELECT r.player_id, r.ovr, r.pot, p.age, p.pos, p.role,
               r.stm,
               r.pot_fst, r.pot_snk, r.pot_crv, r.pot_sld, r.pot_chg,
               r.pot_splt, r.pot_cutt, r.pot_cir_chg, r.pot_scr, r.pot_frk,
               r.pot_kncrv, r.pot_knbl,
               (ps.war + COALESCE(ps.ra9war, ps.war)) / 2.0 as war,
               ps.gs, ps.ip
        FROM latest_ratings r
        JOIN players p ON r.player_id = p.player_id
        JOIN pitching_stats ps ON ps.player_id = p.player_id
        WHERE p.level = 1 AND ps.split_id = 1
          AND ps.year > ? AND ps.year <= ?
          AND ((p.role IN (12,13) AND ps.ip >= 20 AND ps.gs <= 3)
               OR (COALESCE(p.role,0) NOT IN (12,13) AND ps.ip >= 40))
    """, (year_lo, year_hi)).fetchall()

    bucket_data = defaultdict(list)
    for r in hitter_rows:
        bucket = _bucket_player(r, role_map)
        bucket_data[bucket].append((r["ovr"], r["war"]))
    for r in pitcher_rows:
        bucket = _bucket_player(r, role_map)
        bucket_data[bucket].append((r["ovr"], r["war"]))

    # Run regression per bucket; fall back to grouped for small samples
    all_hitter_data = []
    for b in HITTER_BUCKETS:
        all_hitter_data.extend(bucket_data.get(b, []))

    regressions = {}
    for bucket in list(HITTER_BUCKETS) + list(PITCHER_BUCKETS):
        data = bucket_data.get(bucket, [])
        if len(data) >= MIN_REGRESSION_N:
            result = _linreg([d[0] for d in data], [d[1] for d in data])
            if result:
                # RP regression targets P75 instead of mean: a team's primary
                # RP at a given OVR is a closer/setup, not a mop-up arm.
                # Shift intercept up by the mean residual of the top quartile.
                if bucket == "RP":
                    slope, intercept = result[0], result[1]
                    residuals = sorted(y - (slope * x + intercept) for x, y in data)
                    p75_shift = residuals[int(len(residuals) * 0.75)]
                    result = (slope, intercept + p75_shift, result[2], result[3])
                regressions[bucket] = result
                continue
        # Fall back to grouped hitter regression
        if bucket in HITTER_BUCKETS and len(all_hitter_data) >= MIN_REGRESSION_N:
            result = _linreg([d[0] for d in all_hitter_data],
                             [d[1] for d in all_hitter_data])
            if result:
                regressions[bucket] = (*result[:3], f"grouped({len(all_hitter_data)})")

    return regressions, bucket_data


def _build_ovr_to_war_table(regressions):
    """Convert regression results into OVR_TO_WAR format: list of (Ovr, hitter, SP, RP) tuples.
    
    For hitters, uses position-specific regressions. The table stores per-position values
    rather than a single hitter column.
    """
    ovr_points = [80, 75, 70, 65, 60, 55, 50, 45, 40]
    table = {}  # bucket -> {ovr: war}

    for bucket in list(HITTER_BUCKETS) + list(PITCHER_BUCKETS):
        reg = regressions.get(bucket)
        if reg:
            slope, intercept = reg[0], reg[1]
            table[bucket] = {ovr: _war_at(slope, intercept, ovr) for ovr in ovr_points}
        else:
            # Use defaults from constants.py
            if bucket in PITCHER_BUCKETS:
                col = 2 if bucket == "SP" else 3
                table[bucket] = {row[0]: row[col] for row in OVR_TO_WAR}
            else:
                table[bucket] = {row[0]: row[1] for row in OVR_TO_WAR}

    return table


# ---------------------------------------------------------------------------
# Step 2: FV_TO_PEAK_WAR — derived from OVR_TO_WAR
# ---------------------------------------------------------------------------

def _derive_fv_to_peak_war(ovr_table):
    """Map FV grades to peak WAR using the calibrated OVR_TO_WAR.
    
    FV represents expected peak Ovr. A prospect with FV 55 is expected to
    peak around Ovr 55-60. We use FV+5 as the expected peak Ovr (prospects
    who reach their FV typically settle slightly above it at peak).
    
    Produces per-bucket tables for all positions so the surplus model can
    use position-specific WAR expectations (a FV 50 COF produces less WAR
    than a FV 50 SS).
    """
    fv_points = [80, 70, 65, 60, 55, 50, 45, 40]

    def _interp_table(tbl, ovr):
        """Interpolate from a {ovr: war} dict."""
        pts = sorted(tbl.keys())
        if ovr >= pts[-1]:
            return tbl[pts[-1]]
        if ovr <= pts[0]:
            return tbl[pts[0]]
        for i in range(len(pts) - 1):
            if pts[i] <= ovr <= pts[i + 1]:
                t = (ovr - pts[i]) / (pts[i + 1] - pts[i])
                return tbl[pts[i]] + t * (tbl[pts[i + 1]] - tbl[pts[i]])
        return tbl[pts[0]]

    # Per-bucket hitter FV→WAR tables
    hitter_fv_tables = {}
    for bucket in HITTER_BUCKETS:
        if bucket in ovr_table:
            hitter_fv_tables[bucket] = {}
            for fv in fv_points:
                peak_ovr = min(fv + 5, 80)
                hitter_fv_tables[bucket][fv] = round(
                    _interp_table(ovr_table[bucket], peak_ovr), 1)

    # Generic hitter average (fallback for unknown buckets)
    hitter_fv_avg = {}
    for fv in fv_points:
        peak_ovr = min(fv + 5, 80)
        wars = [_interp_table(ovr_table[b], peak_ovr)
                for b in HITTER_BUCKETS if b in ovr_table]
        hitter_fv_avg[fv] = round(sum(wars) / len(wars), 1) if wars else FV_TO_PEAK_WAR.get(fv, 2.0)

    # SP FV→WAR
    sp_fv = {}
    if "SP" in ovr_table:
        for fv in fv_points:
            peak_ovr = min(fv + 5, 80)
            sp_fv[fv] = round(_interp_table(ovr_table["SP"], peak_ovr), 1)
    else:
        sp_fv = dict(FV_TO_PEAK_WAR)

    # RP FV→WAR
    rp_fv = {}
    if "RP" in ovr_table:
        for fv in fv_points:
            peak_ovr = min(fv + 5, 80)
            rp_fv[fv] = round(_interp_table(ovr_table["RP"], peak_ovr), 1)
    else:
        rp_fv = dict(FV_TO_PEAK_WAR_RP)

    return hitter_fv_avg, hitter_fv_tables, sp_fv, rp_fv


# ---------------------------------------------------------------------------
# Step 3: ARB_PCT calibration
# ---------------------------------------------------------------------------

def _calibrate_arb_pct(conn, game_year, dpw):
    """Compute arb salary as fraction of market value by estimated arb year."""
    year_lo = game_year - CALIBRATION_YEARS
    year_hi = game_year - 1

    rows = conn.execute("""
        SELECT c.player_id, p.age, c.salary_0, r.ovr
        FROM contracts c
        JOIN players p ON c.player_id = p.player_id
        JOIN latest_ratings r ON r.player_id = p.player_id
        WHERE c.years = 1 AND c.salary_0 > 825000 AND c.salary_0 < 20000000
          AND p.age < 30 AND p.level = 1
    """).fetchall()

    arb_data = defaultdict(list)
    for r in rows:
        pid = r["player_id"]
        svc = conn.execute("""
            SELECT COUNT(DISTINCT year) FROM (
                SELECT year FROM batting_stats WHERE player_id=? AND split_id=1 AND ab >= 100
                UNION
                SELECT year FROM pitching_stats WHERE player_id=? AND split_id=1 AND ip >= 20
            )
        """, (pid, pid)).fetchone()[0]

        # Get prior year WAR
        bat = conn.execute(
            "SELECT SUM(war) as war FROM batting_stats WHERE player_id=? AND split_id=1 AND year=? AND ab >= 100",
            (pid, game_year - 1)).fetchone()
        pit = conn.execute(
            "SELECT SUM((war + COALESCE(ra9war, war))/2.0) as war FROM pitching_stats WHERE player_id=? AND split_id=1 AND year=? AND ip >= 20",
            (pid, game_year - 1)).fetchone()

        war = (pit["war"] if pit and pit["war"] is not None else
               bat["war"] if bat and bat["war"] is not None else None)
        if war is None or war <= 0:
            continue

        mkt = war * dpw
        pct = r["salary_0"] / mkt
        arb_yr = max(1, svc - 2)
        if 1 <= arb_yr <= 3:
            arb_data[arb_yr].append(pct)

    # Use median (robust to outliers)
    import statistics
    result = {}
    for yr in (1, 2, 3):
        pcts = arb_data.get(yr, [])
        if len(pcts) >= 5:
            result[yr] = round(statistics.median(pcts), 2)
        else:
            result[yr] = ARB_PCT[yr]

    return result


# ---------------------------------------------------------------------------
# Step 4: Scarcity curve
# ---------------------------------------------------------------------------

def _calibrate_scarcity(conn, game_date):
    """Compute scarcity multiplier by Pot band. Mid-season only.
    
    Measures how concentrated talent is at each Pot level among rostered
    players (team_id > 0). Uses the fraction of rostered players at each
    Pot who are NOT on MLB rosters as a proxy for availability — low-Pot
    talent is abundant in the minors, high-Pot talent gets absorbed into MLB.
    
    Compares each band's non-MLB rate to the baseline (Pot 38-42) and maps
    through a sigmoid. Adapts to leagues with different roster structures.
    Returns None during offseason.
    """
    game_month = int(game_date[5:7])
    if game_month < 4 or game_month > 10:
        print("  Scarcity: skipped (offseason — FA pool is flooded)")
        return None

    rows = conn.execute("""
        SELECT r.pot,
               SUM(CASE WHEN p.level != 1 THEN 1 ELSE 0 END) as non_mlb,
               COUNT(*) as total
        FROM latest_ratings r
        JOIN players p ON r.player_id = p.player_id
        WHERE r.pot >= 38 AND p.team_id > 0 AND p.age BETWEEN 18 AND 32
        GROUP BY r.pot ORDER BY r.pot
    """).fetchall()

    if not rows:
        return None

    # Group into 2-point bands for smoothing
    bands = defaultdict(lambda: [0, 0])
    for r in rows:
        center = (r["pot"] // 2) * 2
        bands[center][0] += r["non_mlb"]
        bands[center][1] += r["total"]

    avail_rates = {}
    for center in sorted(bands.keys()):
        non_mlb, total = bands[center]
        if total >= 15:
            avail_rates[center] = non_mlb / total

    if not avail_rates:
        return None

    # Baseline: average non-MLB rate at Pot 38-42 (abundant talent)
    baseline_pts = [v for k, v in avail_rates.items() if k <= 42]
    baseline = sum(baseline_pts) / len(baseline_pts) if baseline_pts else 0.95

    # Map ratio-to-baseline through a sigmoid:
    # ratio ~1.0 (as available as low-Pot talent) → scarcity 0.0
    # ratio ~0.65 → scarcity ~0.5
    # ratio ~0.3 → scarcity ~0.95
    import math
    def _ratio_to_scarcity(ratio):
        if ratio <= 0:
            return 1.0
        return max(0.0, min(1.0, 1.0 / (1.0 + math.exp(10 * (ratio - 0.65)))))

    raw = {}
    for pot in sorted(avail_rates.keys()):
        ratio = avail_rates[pot] / baseline if baseline > 0 else 0
        raw[pot] = round(_ratio_to_scarcity(ratio), 2)

    # Enforce monotonic non-decreasing
    pts = sorted(raw.keys())
    scarcity = {}
    prev = 0.0
    for pot in pts:
        val = max(prev, raw[pot])
        scarcity[pot] = val
        prev = val

    # Find where scarcity first hits 1.0 and cap
    result = {}
    hit_one = False
    for pot in pts:
        if hit_one:
            continue
        result[pot] = scarcity[pot]
        if scarcity[pot] >= 1.0:
            hit_one = True
    result[80] = 1.0

    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def calibrate(dry_run=False):
    league_dir = get_league_dir()
    conn = _db.get_conn(league_dir)

    with open(league_dir / "config" / "state.json") as f:
        state = json.load(f)
    game_date = state["game_date"]
    game_year = int(game_date[:4])

    with open(league_dir / "config" / "league_averages.json") as f:
        avgs = json.load(f)
    dpw = avgs.get("dollar_per_war", 8_976_775)

    role_map = {str(k): v for k, v in _cfg.role_map.items()}

    print(f"Calibrating model weights for game date {game_date}")
    print(f"  Using {CALIBRATION_YEARS} years of data ({game_year - CALIBRATION_YEARS}-{game_year - 1})")
    print(f"  $/WAR: ${dpw:,.0f}")
    print()

    # Step 1: OVR_TO_WAR
    print("=== OVR_TO_WAR Regression ===")
    regressions, bucket_data = _calibrate_ovr_to_war(conn, game_year, role_map)
    ovr_table = _build_ovr_to_war_table(regressions)

    for bucket in list(HITTER_BUCKETS) + list(PITCHER_BUCKETS):
        reg = regressions.get(bucket)
        if reg:
            n_str = reg[3] if isinstance(reg[3], str) else reg[3]
            print(f"  {bucket:<4} N={n_str:<5} slope={reg[0]:.4f} R²={reg[2]:.3f}  "
                  f"WAR@50={ovr_table[bucket][50]:.2f}  @60={ovr_table[bucket][60]:.2f}  "
                  f"@70={ovr_table[bucket][70]:.2f}")
        else:
            print(f"  {bucket:<4} (using defaults — insufficient data)")

    # Step 2: FV_TO_PEAK_WAR
    print("\n=== FV_TO_PEAK_WAR (derived) ===")
    hitter_fv, hitter_fv_tables, sp_fv, rp_fv = _derive_fv_to_peak_war(ovr_table)
    print(f"  {'FV':<4} {'HitAvg':>7} {'COF':>5} {'SS':>5} {'C':>5} {'CF':>5} {'SP':>7} {'RP':>7}")
    for fv in sorted(hitter_fv.keys(), reverse=True):
        cof = hitter_fv_tables.get("COF", {}).get(fv, "?")
        ss  = hitter_fv_tables.get("SS", {}).get(fv, "?")
        c   = hitter_fv_tables.get("C", {}).get(fv, "?")
        cf  = hitter_fv_tables.get("CF", {}).get(fv, "?")
        cof_s = f"{cof:>5.1f}" if isinstance(cof, float) else f"{cof:>5}"
        ss_s  = f"{ss:>5.1f}" if isinstance(ss, float) else f"{ss:>5}"
        c_s   = f"{c:>5.1f}" if isinstance(c, float) else f"{c:>5}"
        cf_s  = f"{cf:>5.1f}" if isinstance(cf, float) else f"{cf:>5}"
        print(f"  {fv:<4} {hitter_fv[fv]:>7.1f} {cof_s} {ss_s} {c_s} {cf_s} {sp_fv[fv]:>7.1f} {rp_fv[fv]:>7.1f}")

    # Step 3: ARB_PCT
    print("\n=== ARB_PCT ===")
    arb_pct = _calibrate_arb_pct(conn, game_year, dpw)
    for yr in (1, 2, 3):
        old = ARB_PCT[yr]
        print(f"  Arb {yr}: {arb_pct[yr]:.0%} (was {old:.0%})")

    # Step 4: Scarcity
    print("\n=== SCARCITY_MULT ===")
    scarcity = _calibrate_scarcity(conn, game_date)
    if scarcity:
        for pot in sorted(scarcity.keys()):
            old = SCARCITY_MULT.get(pot, "—")
            print(f"  Pot {pot}: {scarcity[pot]:.2f} (was {old})")
    else:
        print("  Using existing curve (no update)")
        scarcity = {str(k): v for k, v in SCARCITY_MULT.items()}

    conn.close()

    # Build output
    # OVR_TO_WAR stored as position-specific dicts for flexibility
    weights = {
        "calibration_date": game_date,
        "calibration_years": f"{game_year - CALIBRATION_YEARS}-{game_year - 1}",
        "OVR_TO_WAR": {bucket: {str(k): v for k, v in tbl.items()}
                       for bucket, tbl in ovr_table.items()},
        "FV_TO_PEAK_WAR": {str(k): v for k, v in hitter_fv.items()},
        "FV_TO_PEAK_WAR_BY_POS": {bucket: {str(k): v for k, v in tbl.items()}
                                   for bucket, tbl in hitter_fv_tables.items()},
        "FV_TO_PEAK_WAR_SP": {str(k): v for k, v in sp_fv.items()},
        "FV_TO_PEAK_WAR_RP": {str(k): v for k, v in rp_fv.items()},
        "ARB_PCT": {str(k): v for k, v in arb_pct.items()},
        "SCARCITY_MULT": {str(k): v for k, v in
                          (scarcity if scarcity else SCARCITY_MULT).items()},
    }

    if dry_run:
        print("\n=== DRY RUN — would write: ===")
        print(json.dumps(weights, indent=2))
    else:
        out_path = league_dir / "config" / "model_weights.json"
        with open(out_path, "w") as f:
            json.dump(weights, f, indent=2)
        print(f"\nWrote {out_path}")

    return weights


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    calibrate(dry_run=dry_run)
