"""
prospect_value.py — Prospect surplus value calculator.
Usage: python3 scripts/prospect_value.py --player <player_id>
       python3 scripts/prospect_value.py --fv <fv> --age <age> --level <level> --bucket <bucket>

Implements Step 3 of docs/trade_analysis_guide.md.
"""

import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from player_utils import dollars_per_war, league_minimum, POSITIONAL_WAR_ADJUSTMENTS, RP_WAR_CAP, aging_mult, LEVEL_NORM_AGE
from constants import ARB_PCT, FV_TO_PEAK_WAR, DEVELOPMENT_DISCOUNT, YEARS_TO_MLB, PROSPECT_DISCOUNT_RATE, REPLACEMENT_WAR

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---------------------------------------------------------------------------
# Core calculation
# ---------------------------------------------------------------------------

def peak_war(fv, bucket="SP"):
    """Map FV to expected peak WAR/year. Interpolate between defined points.
    Half-grade (+) is handled by the caller passing fv+0.5.
    RP WAR is capped regardless of FV.
    """
    fv_points = sorted(FV_TO_PEAK_WAR.keys())
    if fv >= max(fv_points):
        war = FV_TO_PEAK_WAR[max(fv_points)]
    elif fv <= min(fv_points):
        war = FV_TO_PEAK_WAR[min(fv_points)]
    else:
        war = FV_TO_PEAK_WAR[min(fv_points)]
        for i in range(len(fv_points) - 1):
            f0, f1 = fv_points[i], fv_points[i+1]
            if f0 <= fv <= f1:
                t = (fv - f0) / (f1 - f0)
                war = FV_TO_PEAK_WAR[f0] + t * (FV_TO_PEAK_WAR[f1] - FV_TO_PEAK_WAR[f0])
                break
    if bucket == "RP":
        war = min(war, RP_WAR_CAP)
    return war

def _age_adjusted_discount(level, age):
    """Development discount adjusted for age vs level norm.
    +3% per year younger than norm, -3% per year older. Clamped [0.15, 0.95]."""
    base = DEVELOPMENT_DISCOUNT.get(level, 0.45)
    norm_key = level.lower().replace(" ", "-")
    # "Rookie" level label maps to USL in the norm age table
    if norm_key == "rookie":
        norm_key = "usl"
    norm_age = LEVEL_NORM_AGE.get(norm_key)
    if norm_age is None:
        return base
    return max(0.15, min(0.95, base + (norm_age - age) * 0.03))


def _certainty_mult(ovr, pot):
    """Adjust surplus based on how much ceiling is already realized.
    Realization ~1.0 (maxed out) = +15% (low variance, safe bet).
    Realization ~0.5 = neutral. Realization ~0.3 = -8% to -15% (raw, high variance).
    """
    if not ovr or not pot or pot <= 0:
        return 1.0
    realization = ovr / pot
    return max(0.85, min(1.15, 0.8 + 0.4 * realization))


def prospect_surplus(fv, age, level, bucket, positional_adjust=False, fv_plus=False,
                     ovr=None, pot=None):
    """
    Compute surplus value for a prospect over their 6-year control period.
    fv: integer FV grade (strip '+' before passing; use fv_plus=True for half-grades).

    WAR ramp: players don't immediately produce peak WAR on debut. Early control
    years are discounted to reflect MLB adjustment and development variance:
      Year 1: 60% of peak, Year 2: 80%, Year 3+: 100%
    """
    dpw       = dollars_per_war()
    lg_min    = league_minimum()
    years_out = YEARS_TO_MLB.get(level, 3.5)
    debut_age = age + years_out
    fv_eff    = fv + (0.5 if fv_plus else 0)
    pw        = peak_war(fv_eff, bucket)
    pos_adj   = POSITIONAL_WAR_ADJUSTMENTS.get(bucket, 0.0) if positional_adjust else 0.0

    RAMP = {1: 0.60, 2: 0.80}  # year 3+ = 1.0

    rows = []
    total_surplus = 0.0
    dev_discount  = _age_adjusted_discount(level, age)

    for yr in range(6):
        ctrl_year  = yr + 1
        player_age = debut_age + yr
        discount   = (1 - PROSPECT_DISCOUNT_RATE) ** (years_out + yr)
        ramp       = RAMP.get(ctrl_year, 1.0)

        war = (pw + pos_adj) * aging_mult(player_age, bucket) * ramp

        market_val = war * dpw * discount if war >= REPLACEMENT_WAR else lg_min

        # Arb salary uses undiscounted WAR × $/WAR — no ramp (arb is based on prior performance)
        if ctrl_year <= 3:
            salary = lg_min
        else:
            arb_yr = ctrl_year - 3
            salary = ARB_PCT[arb_yr] * (pw + pos_adj) * aging_mult(player_age, bucket) * dpw

        surplus = market_val - salary
        total_surplus += surplus

        rows.append({
            "control_year": ctrl_year,
            "player_age":   round(player_age, 1),
            "war":          round(war, 2),
            "market_value": round(market_val),
            "salary":       round(salary),
            "surplus":      round(surplus),
        })

    cert_mult = _certainty_mult(ovr, pot)
    base_surplus = max(0, round(total_surplus * dev_discount * cert_mult))

    return {"fv": fv, "bucket": bucket, "level": level, "age": age,
            "years_to_mlb": years_out, "debut_age": round(debut_age, 1),
            "dev_discount": dev_discount, "certainty_mult": cert_mult,
            "total_surplus": base_surplus, "breakdown": rows}


def _ceiling_fv(pot):
    """Map Pot to a ceiling FV grade (discounted slightly — not everyone maxes out)."""
    raw = pot - 5
    return min(70, max(40, 5 * round(raw / 5)))


def prospect_surplus_with_option(fv, age, level, bucket, ovr=None, pot=None,
                                  fv_plus=False, positional_adjust=False):
    """Compute surplus including option value from upside scenarios.
    Returns the higher of base surplus and probability-weighted blended surplus."""
    base = prospect_surplus(fv, age, level, bucket, positional_adjust=positional_adjust,
                            fv_plus=fv_plus, ovr=ovr, pot=pot)
    base_val = base["total_surplus"]

    cfv = _ceiling_fv(pot) if pot else fv
    if cfv <= fv:
        return base_val

    mid_fv = 5 * round(((fv + cfv) / 2) / 5)
    s_mid = prospect_surplus(mid_fv, age, level, bucket, ovr=ovr, pot=pot)["total_surplus"]
    s_ceil = prospect_surplus(cfv, age, level, bucket, ovr=ovr, pot=pot)["total_surplus"]

    # Upside probability scales with youth: +5% per year under 20
    youth_bonus = max(0, (20 - age)) * 0.05
    p_mid = min(0.40, 0.30 + youth_bonus)
    p_ceil = min(0.20, 0.10 + youth_bonus * 0.5)
    p_base = 1.0 - p_mid - p_ceil

    blended = p_base * base_val + p_mid * s_mid + p_ceil * s_ceil
    return max(base_val, round(blended))

# ---------------------------------------------------------------------------
# Player lookup
# ---------------------------------------------------------------------------

def find_player(player_id):
    """Look up FV, level, bucket, and age from the DB (prospect_fv + players)."""
    import db
    conn = db.get_conn()
    row = conn.execute("""
        SELECT pf.fv, pf.fv_str, pf.level, pf.bucket, p.age
        FROM prospect_fv pf
        JOIN players p ON p.player_id = pf.player_id
        WHERE pf.player_id = ?
        ORDER BY pf.eval_date DESC LIMIT 1
    """, (player_id,)).fetchone()
    conn.close()
    if row:
        fv_plus = str(row["fv_str"]).endswith("+")
        return row["fv"], row["level"], row["bucket"], row["age"], fv_plus
    return None, None, None, None, False

# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def print_result(result):
    print(f"\nProspect Surplus Value")
    print(f"  Player:      FV {result['fv']} | {result['bucket']} | {result['level']} | Age {result['age']}")
    print(f"  MLB debut:   ~{result['debut_age']} ({result['years_to_mlb']} yrs out)")
    print(f"  Dev discount: {result['dev_discount']:.0%}")
    cert = result.get('certainty_mult', 1.0)
    if cert != 1.0:
        print(f"  Certainty:    {cert:.2f}x")
    print(f"\n  {'Yr':>2}  {'Age':>5}  {'WAR':>5}  {'Mkt Value':>12}  {'Salary':>10}  {'Surplus':>10}")
    print(f"  {'--':>2}  {'---':>5}  {'---':>5}  {'---------':>12}  {'------':>10}  {'-------':>10}")
    for r in result["breakdown"]:
        print(f"  {r['control_year']:>2}  {r['player_age']:>5}  {r['war']:>5.2f}  "
              f"${r['market_value']:>11,}  ${r['salary']:>9,}  ${r['surplus']:>9,}")
    print(f"\n  Total surplus: ${result['total_surplus']:,}")

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Prospect surplus value calculator")
    parser.add_argument("--player", type=int, help="Player ID (looks up FV/level from history)")
    parser.add_argument("--fv",     type=int, help="FV grade (manual override)")
    parser.add_argument("--age",    type=float, help="Player age")
    parser.add_argument("--level",  help="Level (AAA, AA, A, A-Short, USL, DSL, Intl)")
    parser.add_argument("--bucket", help="Positional bucket (SP, RP, C, SS, 2B, CF, COF, 3B, 1B)")
    parser.add_argument("--pos-adjust", action="store_true",
                        help="Apply positional WAR adjustment (use for cross-position comparisons)")
    args = parser.parse_args()

    if args.player:
        fv, level, bucket, db_age, fv_plus = find_player(args.player)
        if not fv:
            print(f"Player {args.player} not found in prospect_fv. Use --fv/--age/--level/--bucket.")
            sys.exit(1)
        fv     = args.fv     or fv
        level  = args.level  or level
        bucket = args.bucket or bucket
        age    = args.age    or db_age
        if not age:
            print("--age required when player not found in DB")
            sys.exit(1)
    else:
        if not all([args.fv, args.age, args.level, args.bucket]):
            parser.print_help()
            sys.exit(1)
        fv, age, level, bucket = args.fv, args.age, args.level, args.bucket
        fv_plus = False

    result = prospect_surplus(fv, age, level, bucket,
                              positional_adjust=args.pos_adjust, fv_plus=fv_plus)
    print_result(result)
    return result

if __name__ == "__main__":
    main()
