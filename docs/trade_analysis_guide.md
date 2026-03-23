# Trade Analysis Guide

## Purpose

This document defines the repeatable process for evaluating trades, contracts, extensions, and payroll projections for the Anaheim Angels. It is the methodology specification for the assistant GM scripts.

All assumptions are documented here. When assumptions change (empirical recalibration, new OOTP data), update this document first, then update the scripts.

---

## Constants

These values are used across all calculations. Source of truth is `config/league_averages.json`.

| Constant | Value | Notes |
|---|---|---|
| `$/WAR` | $8.62M | Calibrated from 70 multi-year MLB contracts signed in 2033 (salary ≥ $5M, years > 1). Multi-year filter excludes arb contracts which understate true market value. Recalculated each league refresh from `config/league_averages.json`. |
| League minimum salary | $825,000 | From `config/league_settings.json` |
| Arb $/WAR | ~$1.8-2.8M | OOTP arb pays 20-33% of FA market rate. Arb salary modeled via Ovr-based raise formula, not flat % of market value. |
| Standard service year | 172 days | Per OOTP financial model |
| Free agency threshold | 6 years MLB service | Default OOTP setting |
| Arbitration threshold | 3 years MLB service | Default OOTP setting |
| Super 2 threshold | Top 17% of players with 2+ years service | Triggers arb one year early |

---

## Step 1 — Determine Player Type

Every player in a transaction is one of three types. The type determines which valuation method applies.

| Type | Definition | Valuation method |
|---|---|---|
| **MLB contract** | Player on a major league contract | Contract valuation (Step 2) |
| **Prospect** | Player on a minor league contract | Prospect valuation (Step 3) |
| **Cash** | Dollar amount with no player attached | Face value |

---

## Step 2 — Contract Valuation

Applies to any player on a major league contract.

### 2a — Determine projected role

Use the bucketing logic from `farm_analysis_guide.md` (implemented in `scripts/player_utils.py`):
- Pitchers: SP if 3+ pitches projecting to pot ≥ 45 AND Stm ≥ 40; otherwise RP
- Position players: bucket by positional grade thresholds

If current role ≠ projected role, flag in output and use projected role for WAR projection.

### 2b — Project peak WAR

Peak WAR is derived from the player's `Ovr` rating using the following scale. `Ovr` is position-relative — a 60 Ovr player is above-average among peers at their position.

| Ovr | Peak WAR/year (position player) | Peak WAR/year (SP) | Peak WAR/year (RP) |
|---|---|---|---|
| 80 | 8.0 | 7.0 | 2.5 |
| 75 | 6.0 | 5.5 | 2.0 |
| 70 | 4.5 | 4.0 | 1.5 |
| 65 | 3.5 | 3.0 | 1.2 |
| 60 | 2.5 | 2.2 | 1.0 |
| 55 | 1.8 | 1.6 | 0.7 |
| 50 | 1.2 | 1.0 | 0.5 |
| 45 | 0.6 | 0.5 | 0.3 |
| 40 | 0.1 | 0.1 | 0.1 |

Interpolate linearly between rows. Use current `Ovr` as the baseline — this represents what the player produces today.

### 2c — Apply aging curve

Apply the EMLB-adjusted aging curves from `docs/ootp/aging_and_development.md`. Multiply peak WAR by the age adjustment factor for each contract year.

**Position players:**

| Age | Multiplier |
|---|---|
| ≤ 27 | 1.00 (at or approaching peak) |
| 28 | 1.00 |
| 29 | 0.97 |
| 30 | 0.95 |
| 31 | 0.90 |
| 32 | 0.82 |
| 33 | 0.73 |
| 34 | 0.63 |
| 35 | 0.52 |
| 36+ | 0.40 |

**Starting pitchers:**

| Age | Multiplier |
|---|---|
| ≤ 26 | 1.00 |
| 27 | 1.00 |
| 28 | 0.97 |
| 29 | 0.95 |
| 30 | 0.88 |
| 31 | 0.80 |
| 32 | 0.71 |
| 33 | 0.61 |
| 34 | 0.50 |
| 35+ | 0.38 |

**Relief pitchers:** Apply SP multipliers but cap peak WAR at the RP scale above. RP value is inherently more volatile — treat RP projections as having a wider confidence interval than SP or position player projections.

### 2d — Compute surplus by year

```
market_value[year] = projected_WAR[year] × $/WAR
surplus[year] = market_value[year] - salary[year] × (1 - retention_pct)
```

Where `retention_pct` is the fraction of salary the trading team retains (0.0 to 1.0).

Sum across all remaining contract years for total surplus.

### 2e — Sensitivity range

Run three scenarios using WAR multipliers of 0.85× (pessimistic), 1.0× (base), and 1.15× (optimistic) applied to the entire projection. Report all three in output.

### 2f — Flag contract features

Always flag in output:
- **NTC:** Player cannot be traded without consent
- **Team option:** Note the year and value — acquiring team inherits the decision
- **Player option:** Note the year and value — player retains the right to opt out

---

## Step 3 — Prospect Valuation

Applies to any player on a minor league contract.

### 3a — Determine FV

Use the player's most recent FV from `history/prospect_history.json`. If not present, use the current scaffold. FV represents expected MLB contribution at peak — it is already the probability-weighted ceiling, not the raw ceiling.

### 3b — Map FV to expected WAR at peak

| FV | Expected peak WAR/year |
|---|---|
| 80 | 10.0 |
| 70 | 7.0 |
| 65 | 5.5 |
| 60 | 4.2 |
| 55 | 2.9 |
| 50 | 2.0 |
| 45 | 1.2 |
| 40 | 0.5 |

*These represent the player's projected WAR if they reach the majors and contribute at their projected level. Development risk is handled separately via the development discount (below), not baked into the WAR values.*

### 3c — Development discount

Multiply total surplus by a development discount based on current level. This represents the probability of reaching the majors and contributing at the projected FV level (bust risk only). Time value of money is handled separately by the per-year discount rate (`PROSPECT_DISCOUNT_RATE = 5%`).

| Level | Realization Rate |
|---|---|
| MLB | 100% |
| AAA | 90% |
| AA | 75% |
| A | 60% |
| A-Short | 50% |
| USL / DSL | 38% |
| Intl | 25% |

The rate is further adjusted ±3% per year younger/older than the level's norm age (clamped to 15%–95%).

```
total_surplus = undiscounted_surplus × development_discount × certainty_mult
```

### 3c — Estimate control period

A prospect's value is realized over their pre-arb and arbitration years — typically 6 years of team control once they reach the majors.

Estimate years until MLB debut based on level:

| Level | Years to MLB (estimate) |
|---|---|
| MLB | 0 |
| AAA | 0.5 |
| AA | 1.5 |
| A | 2.5 |
| A-Short | 3.5 |
| USL/DSL/Intl | 4.5+ |

Discount future value at **5% per year** to account for time value and residual development risk not captured in FV.

### 3d — Estimate salary over control period

Pre-arb years (first 3 years): league minimum ($825K/year)
Arbitration years (years 4–6): Ovr-based raise model calibrated to OOTP arb outcomes.

**First arb year** (from pre-arb): `salary = $318,400 × e^(0.0495 × Ovr)`
**Subsequent arb years**: `salary = prior_year_salary + max($1M, -$2.5M + $110K × Ovr)`

OOTP arb pays ~20-33% of FA market rate — much lower than real-world MLB (~45-80%). The model was calibrated against 7 Angels players with known game arb estimates (MAE $0.53M/yr).

For MLB players on 1yr contracts, `contract_value.py` estimates remaining team control via `_estimate_control()`:
- Salary = $825K → pre-arb. Remaining = 6 - qualifying seasons (AB≥300 or IP≥100).
- Salary > $825K, age < 30 → arb. Service floor = 3 (or 4 if salary > $5.5M).
- Age ≥ 30, salary > $825K → 1yr FA deal (no control extension).

### 3e — Compute surplus value

```
for each year in control_period:
    market_value[year] = projected_WAR[year] × $/WAR × discount_factor[year]
    surplus[year] = market_value[year] - estimated_salary[year]

total_surplus = sum(surplus)
```

Where `projected_WAR[year]` applies the aging curve starting from the estimated MLB debut age.

### 3f — Positional adjustment for cross-position comparisons

When comparing prospects at different positions in the same trade, apply the positional adjustment (runs/year converted to WAR: divide by 10) to the market value calculation:

| Position bucket | WAR adjustment/year |
|---|---|
| C | +1.2 |
| SS | +0.7 |
| 2B | +0.3 |
| CF | +0.25 |
| 3B | +0.2 |
| COF (RF/LF) | -0.7 |
| 1B | -1.2 |
| DH | -1.7 |
| SP | 0 (baseline) |
| RP | -1.0 |

Apply only when the output explicitly compares players at different positions. Do not apply in single-player valuations.

---

## Step 4 — Trade Balance Calculation

### 4a — Compute each side

For each player in the trade:
1. Determine player type (Step 1)
2. Apply the appropriate valuation (Steps 2 or 3)
3. Apply salary retention if applicable: the retaining team keeps `retention_pct × remaining_salary` on their books; the acquiring team's net cost is `(1 - retention_pct) × remaining_salary`

### 4b — Net surplus per side

```
net_surplus[team] = sum(surplus of players received) - sum(surplus of players sent)
```

A positive net surplus means the team gained more value than they gave up.

### 4c — Output format

```
TRADE SUMMARY
=============
Angels receive:   [player list]
Angels send:      [player list + retention details]

ANGELS SIDE
  Received:  [player]: $X surplus
  Sent:      [player]: $Y surplus  [NTC flag if applicable]
  Retention: [player]: $Z retained ($W/year × N years)
  Net:       $[total] ([positive = Angels win / negative = Angels lose])

ACQUIRING TEAM SIDE
  Received:  [player]: $X surplus (base) / $Y (pessimistic) / $Z (optimistic)
  Sent:      [player]: $W surplus
  Net:       $[total] ([positive = acquiring team wins])

VERDICT
  [One sentence: which side wins, by how much, under what scenario]
  [NTC flags, option flags, role transition flags]
```

---

## Step 5 — Extension Valuation

### 5a — Project market value over extension years

Use the contract valuation method (Step 2) but substitute the proposed extension salary for the actual salary. The player's current age and Ovr are the inputs.

### 5b — Compare to arb + free agent cost

Estimate what the player would cost without an extension:
- Remaining pre-arb years: league minimum
- Arb years: use arb salary table (Step 3d)
- Free agent years: market value (surplus ≈ 0 — player earns what they're worth)

```
extension_surplus = sum(market_value[year] - extension_salary[year])
no_extension_cost = sum(arb_salary[year]) + sum(market_value[free_agent_years])
extension_savings = no_extension_cost - sum(extension_salary)
```

A positive `extension_surplus` means the extension is below market. A positive `extension_savings` means the extension costs less than the arb + free agent path.

### 5c — Output

Report both metrics. A good extension has positive surplus AND saves money vs. the alternative path. An extension can have positive surplus but still cost more than letting the player walk if the free agent years are priced at market — flag this case explicitly.

---

## Step 6 — Payroll Projection

### 6a — Committed payroll

For each year in the projection window (default: current year + 4):
- Sum all existing contract salaries for that year
- Flag contracts expiring that year (free agent decisions)
- Flag option years (team or player) and note the decision deadline

### 6b — Projected arbitration costs

For each pre-arb player on the roster:
- Estimate their arb year salaries using Step 3d
- Add to projected payroll in the appropriate years

### 6c — Output

Year-by-year table:

```
Year | Committed | Projected Arb | Total Projected | Expiring Contracts | Notes
-----|-----------|---------------|-----------------|-------------------|------
2033 | $XXXm     | $Xm           | $XXXm           | [names]           |
2034 | $XXXm     | $Xm           | $XXXm           | [names]           |
...
```

---

## Repeatable Process

Run in this order for any trade analysis:

1. Read `config/state.json` — confirm game date
2. Confirm data is current (ratings, contracts, prospect history)
3. Run `python3 scripts/trade_calculator.py --trade "[JSON trade definition]"` — produces output per Step 4c
4. For extension analysis: `python3 scripts/contract_value.py --player [ID] --extension "[JSON offer]"`
5. For payroll projection: `python3 scripts/contract_value.py --payroll --years 4`
6. Interpret output in context — the scripts quantify value; the agent applies judgment on non-financial factors (positional need, timeline fit, win-now context)

---

## Model Evolution Notes

### $/WAR — Marginal cost model (deferred)

The flat $/WAR model treats each WAR as equally valuable regardless of total output. In reality, elite players (5+ WAR) command a scarcity premium — there are very few of them, and teams pay disproportionately more to acquire one. A more accurate model would use a **cumulative marginal cost approach**: the first WAR costs less than the fifth, with the rate increasing at each tier (e.g. $5M/WAR for 0–1, $9.5M for 1–3, $13M for 3–5, $18M for 5+). Total contract value is the sum across tiers, not WAR × top-tier rate.

This model is deferred until a trade involving a star player makes it necessary. For now, the flat $8.62M/WAR rate is used. Valuations for elite players (projected 5+ WAR) should be treated as a floor — the flat model understates their true market value.

---

## Calibration Log

Track assumption changes here as empirical data accumulates.

| Date | Assumption | Old value | New value | Reason |
|---|---|---|---|---|
| 2033-04-22 | $/WAR | — | $9.5M | Initial estimate, Angels payroll inference |
| 2033-04-25 | $/WAR | $9.5M | $6.28M | Recalibrated from 127 MLB contracts signed 2033 (salary ≥ $5M). Included arb contracts — understated true market rate. |
| 2033-04-25 | $/WAR | $6.28M | $8.62M | Filtered to multi-year contracts only (years > 1) to exclude arb deals. 70 contracts, $1,206.9M salary / 140.0 WAR. |
| 2033-04-22 | Dev probability table | — | Adjusted real-world | Initial estimate, EMLB modifier applied |
| 2033-04-22 | Arb salary %s | — | 45/65/80% | Initial estimate, real-world approximation |
| 2033-04-22 | FV→WAR table | — | Revised downward | Initial values overstated surplus for low-WAR prospects; FV 45 reduced from 1.0 to 0.6 WAR |
| 2033-04-22 | FV→WAR table | Conservative (0.6 @ FV45) | Middle (0.8 @ FV45) + dev discount | Separated development risk into explicit level-based discount; WAR table now represents ceiling-if-arrives |
| 2033-04-22 | RP WAR cap | — | 2.0 WAR | Guide defines RP FV ceiling at 50 because peak RP value ≤2.0 WAR; cap set to match that ceiling |
| 2026-03-18 | FV→WAR table | FV 50=1.5, FV 55=2.4, FV 60=3.3 | FV 50=2.0, FV 55=2.9, FV 60=4.2, added FV 70=6.0, FV 80=8.5 | Recalibrated to midpoints of guide WAR bands; previous values were understating FV 50+ prospects |
| 2033-04-25 | FV→WAR table | FV 40=0.35, FV 70=6.0, FV 80=8.5, no FV 65 | FV 40=0.5, FV 65=5.5, FV 70=7.0, FV 80=10.0 | FV 40 too low for bench bat (~0.5 WAR). Added FV 65 anchor. Upper end pushed up for convex shape — elite talent is non-linearly valuable. Gaps now accelerate: +0.7/+0.8/+0.9/+1.3/+1.3/+1.5/+1.5/+1.5 |
| 2033-04-25 | Aging curves | Aggressive hand-set values | Recalibrated to consensus research | Prior curves too steep from 32+. Hitter age-34: 0.63→0.76. Pitcher age-34: 0.50→0.65. |
| 2033-04-22 | FV+ half-grade | — | FV + 0.5 for interpolation | Half-grades were being stripped; FV 40+ was mapping identically to FV 40 |
| 2033-04-22 | OVR→WAR table | Ovr 50 = 1.2 WAR | Ovr 50 = 2.0 WAR | Recalibrated to real-world anchor; league-average everyday player should be ~2 WAR/yr |
| 2033-04-22 | Contract aging curve | Absolute multiplier applied to peak WAR | Relative decline from current age | OOTP Ovr already reflects current ability; applying absolute aging was double-counting decline |
| 2033-04-22 | Contract WAR estimation | OVR→WAR table only | `estimate_peak_war()`: stat-weighted 3yr avg if 3+ qualifying seasons, else Ovr/Pot blend | Stat history more reliable than Ovr for established players; Ovr/Pot blend handles role transitions |
| 2033-04-25 | Aging curves (hitter + pitcher) | Aggressive hand-set values | Recalibrated to Marcel/BP/FanGraphs consensus | Prior curves too steep from age 32+: age-34 hitter was 0.63 (now 0.76), age-34 pitcher was 0.50 (now 0.65). Peak unchanged at 27-28. Decline rates: ~3%/yr 29-31, ~6-7%/yr 32-34, ~9-10%/yr 35-37, ~12%/yr 38+. Pitchers slightly steeper than hitters from 32+ to reflect injury/velocity risk. |
| 2033-04-22 | Extension alt path FA salary | Market value (surplus = 0) | Market value × FA premium (1.05–1.30x, scales with peak WAR) | Elite players command above-market bids; flat market assumption understated cost of losing them |
| 2033-04-22 | Extension model | Flat AAV only | Per-year salaries via `ext_salaries`; `pre_arb_years` and `arb_years_remaining` params added | Graduated structures and accurate arb clock positioning required for real negotiation analysis |

| 2033-04-25 | DEVELOPMENT_DISCOUNT | Conflated (time + bust): AAA 0.85, AA 0.70, A 0.55, A-Short 0.45, USL/DSL 0.30, Intl 0.20 | Bust-only: AAA 0.90, AA 0.75, A 0.60, A-Short 0.50, USL/DSL 0.38, Intl 0.25 | Time value was double-counted — already handled by PROSPECT_DISCOUNT_RATE (5%/yr) in per-year market value calc. Separated concerns: DEVELOPMENT_DISCOUNT now represents bust probability only. Impact: +7-10% surplus for AA/A, +23-29% for Intl prospects. |

| 2033-04-25 | ARB_PCT | Real-world MLB: 45/65/80% | OOTP-calibrated: 20/22/33% | Analyzed 86 arb-eligible OOTP players with WAR > 0.5. OOTP arb pays ~$1.8-2.8M/WAR vs $8.62M FA rate. Old values massively overstated arb salaries, understating surplus for arb-controlled players. |
| 2033-04-25 | Arb salary projection | Flat ARB_PCT × peak_war × $/WAR | Ovr-based raise model | First arb from pre-arb: `0.3184 * e^(0.0495 * Ovr)`. Subsequent: `prior + max($1M, -$2.5M + $110K * Ovr)`. MAE $0.53M/yr vs $5-15M/yr. Calibrated against 7 Angels players with known game arb estimates. |
| 2033-04-25 | 1yr contract control estimation | 1 year only | `_estimate_control()` infers full pre-arb + arb control | Pre-arb ($825K): `6 - qualifying_seasons` (AB≥300/IP≥100). Arb (>$825K, age<30): floor service at 3; >$5.5M floors at 4. Age≥30 = 1yr FA deal. 7/7 correct vs game data. Affects 646 of 920 MLB players (70%). |

*Update this table whenever a constant or table is recalibrated.*
