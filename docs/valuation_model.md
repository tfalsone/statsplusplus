# Player Valuation Model

Plain-language explanation of how Stats++ values prospects and MLB players.
For implementation details, see `system_overview.md`. For constant tables, see
`scripts/constants.py`.

---

## Core Concepts

Every player has a **surplus value** — the difference between what they're worth on
the field and what they cost in salary over their remaining team control. A player
earning $2M who produces $15M of value has $13M of surplus. Surplus is the currency
of trades: a fair trade has roughly equal surplus on both sides.

**$/WAR** is the market rate for one win above replacement, derived from actual
free agent contracts in the league. Currently $8.62M. This converts WAR into dollars.

---

## Prospect Valuation

### FV Grade (Future Value)

FV is a scouting-style grade on the standard 20-80 scale that estimates a prospect's
future MLB ceiling. It answers: *how good could this player become?*

The base formula blends current ability (Ovr) with ceiling (Pot), weighted by how
much development time remains:

    FV = Ovr + (Pot - Ovr) × development_weight

**Development weight** depends on age relative to level norms. A 19-year-old in A-ball
gets heavy weight on Pot (lots of projection). A 25-year-old in AAA gets almost none
(what you see is what you get).

**Modifiers** adjust FV up or down:

- Defensive bonus (+1 to +3): premium glove at a key position
- Versatility bonus (+1 to +2): can play multiple positions
- Work ethic (+1 for high, -1 for low)
- Critical tool penalty (-3 to -5): fatally weak contact (hitters) or control/movement (pitchers)
- Platoon split penalty (-2 to -3): severe weakness against one handedness
- Scouting accuracy penalty (-2): low-accuracy scouting reports are less trustworthy

**RP positional discount**: Relief pitchers produce less WAR per talent grade than
other positions. Before calculating FV, an RP's Pot is scaled to 80% of its raw value.
This means only elite RPs (Pot 70+) earn FV 50, and a typical Pot 55 RP grades out
around FV 40 rather than FV 45. RPs are also hard-capped at FV 50. This discount
is for display/ranking only — surplus uses the raw Pot through a separate RP WAR table
to avoid double-counting.

**FV grades use 5-point increments** (40, 45, 50, etc.) with a "+" modifier for
half-grades (45+ means between 45 and 50). The "+" is awarded when the remainder
is large enough or when the player has significant upside room and is young for
their level.

### Prospect Surplus

Surplus converts the FV grade into a dollar value representing what the prospect is
worth in a trade. It projects six years of team control (3 pre-arb + 3 arb) and
sums up the difference between market value and salary in each year.

**Step 1 — Peak WAR.** The FV grade maps to an expected peak WAR per season.
Hitters, SP, and RP each have their own table, calibrated from the league's
actual Ovr→WAR regression data:

| FV  | Hitter Peak WAR | SP Peak WAR | RP Peak WAR |
|-----|-----------------|-------------|-------------|
| 40  | 1.8             | 1.5         | 0.7         |
| 45  | 2.6             | 2.0         | 0.9         |
| 50  | 3.3             | 2.5         | 1.0         |
| 55  | 4.0             | 3.0         | 1.2         |
| 60  | 4.8             | 3.4         | 1.4         |
| 65  | 5.5             | 3.9         | 1.6         |
| 70  | 6.2             | 4.4         | 1.8         |

SPs produce less WAR per FV grade than hitters because pitchers accumulate
fewer plate appearances worth of value. RPs produce even less due to fewer
innings. These tables are derived from the league's own data via `calibrate.py`
and stored in `config/model_weights.json`.

**Step 2 — Realization blend.** For prospects who are nearly maxed out (Ovr close
to Pot), the model blends the FV-based peak WAR with the player's actual current
WAR output. A fully maxed player (Ovr = Pot) uses 100% current production; a
developing player (Ovr/Pot < 0.7) uses 100% FV projection. This prevents a
discontinuity where a AAA player's value would jump dramatically on the day they
get called up to MLB.

**Step 3 — Year-by-year projection.** For each of the six control years:

- WAR is adjusted for aging (peaks at 27-28, declines ~3%/yr in early 30s, steeper after)
- Early years are ramped (60% of peak in year 1, 80% in year 2, 100% after)
- Market value = WAR × $/WAR, time-discounted at 5% per year
- Salary = league minimum for pre-arb years, then arb percentages (21%/18%/34% of market value)
- Surplus = market value minus salary

**Step 4 — Adjustments.** The raw surplus total is multiplied by three factors:

- **Development discount** (0.15 to 0.95): probability the player actually reaches
  their projected FV. Higher levels = higher probability. Flattened curve (Session 33):
  AAA 0.88, AA 0.78, A 0.68, Rookie 0.45, Intl 0.35. Adjusted for age at 4%/yr —
  younger players at a given level get a bonus, older players get a penalty.

- **Certainty multiplier** (0.85 to 1.0): how much of the ceiling is already
  realized. A player at 30% of their Pot gets a penalty (-15%). Capped at 1.0 —
  no bonus for maxed prospects (proximity already rewarded by dev discount and
  time-value discount).

- **Scarcity multiplier** (0.0 to 1.0): based on Pot (ceiling), not FV. Low-ceiling
  players (Pot 40-44) are freely available on waivers and minor league free agency,
  so their theoretical surplus has no real trade value. Calibrated from actual
  free agent availability data in the league (sigmoid mapping, monotonic).
  Position-adjusted: premium positions get a Pot shift before scarcity lookup
  (SS: +4, CF: +2, SP: +2, C/2B/3B: +1, COF/RP: -2, 1B: -3). For defense-dependent
  positions (CF/SS/C/2B/3B), the shift scales with defensive potential rating
  (full at 70+, linear 50-70, zero below 50).

**Step 5 — Option value.** The model computes upside scenarios: what if the player
develops beyond their current FV? It blends base, mid-ceiling, and full-ceiling
outcomes weighted by probability. Probabilities scale with two factors: youth
(+5%/yr under 20) and the Pot-FV gap (wider gap = more development runway). A
Pot 80 / FV 50 player gets ~30% base / 45% mid / 25% ceiling; a Pot 52 / FV 50
player gets ~60% base / 30% mid / 10% ceiling. The final surplus is the higher
of the base and the option-weighted value.

---

## MLB Player Valuation

### Contract Surplus

For MLB players, surplus is the difference between projected on-field value and
actual contract cost over remaining team control.

**WAR projection** uses a blend of two approaches:

- **Stat-based WAR**: recent performance, weighted toward the most recent season
  (3yr weighted average with 60/30/10 splits). Pitcher WAR blends standard WAR
  with RA9-WAR for stability.
- **Ratings-based WAR**: maps current Ovr to expected WAR using a position-specific
  table. Each position bucket (C, SS, 2B, 3B, CF, COF, 1B, SP, RP) has its own
  regression-derived curve. For example, an Ovr 60 SS produces ~4.4 WAR while an
  Ovr 60 C produces ~3.7 WAR. These tables are calibrated from the league's own
  data via `calibrate.py`.

For most players, stat WAR drives the projection. For young players (under peak age)
whose ratings suggest more upside than their stats show, the model blends in ratings
WAR — up to 50% at age 21, fading to 0% by peak age. This prevents undervaluing
young players with limited track records.

**Salary** comes from the actual contract if one exists. For pre-arb players, the
model estimates remaining control years from service time and projects arb salaries
using an Ovr-based exponential model calibrated to actual league arb outcomes. If
projected arb salary exceeds market value, the player is assumed to be non-tendered
(control truncated).

**Aging curve** projects WAR decline year by year. Hitters decline ~3%/yr from 29-31,
~6%/yr from 32-34, steeper after. Pitchers decline slightly faster from 32+ due to
injury and velocity risk.

---

## How FV and Surplus Relate

FV and surplus measure different things:

- **FV** is a scouting grade — it tells you how good the player projects to be,
  adjusted for position (RPs are discounted). It's useful for comparing prospects
  within a position and for quick-glance rankings.

- **Surplus** is a trade value — it tells you what the player is worth in a deal.
  It factors in everything FV doesn't: age, level, development risk, years of
  control, salary, scarcity, and positional WAR differences.

Two players with the same FV can have very different surplus values. A 20-year-old
FV 45 SP in AA is worth more than a 25-year-old FV 45 SP in AAA because the younger
player has more development runway and more cheap control years ahead.

FV and surplus rankings should generally agree on the top tier (the best prospects
are the best prospects). Where they diverge is informative:

- **FV higher than surplus rank**: the player grades well but has risk factors
  (old for level, high bust probability, low scarcity ceiling)
- **Surplus higher than FV rank**: the player's grade is modest but the economics
  are favorable (young, cheap, high-scarcity position)

---

## Key Constants

All valuation constants live in `scripts/constants.py`, with calibrated overrides
loaded from `config/model_weights.json` when present:

- `FV_TO_PEAK_WAR` — FV grade to expected peak WAR (generic hitter average, fallback)
- `FV_TO_PEAK_WAR_BY_POS` — per-bucket hitter tables (COF, SS, C, CF, 2B, 3B, 1B)
- `FV_TO_PEAK_WAR_SP` — same for starting pitchers
- `FV_TO_PEAK_WAR_RP` — same for relief pitchers
- `SCARCITY_MULT` — scarcity curve by Pot grade
- `OVR_TO_WAR` / `OVR_TO_WAR_CALIBRATED` — Ovr to WAR mapping (position-specific when calibrated)
- `DEVELOPMENT_DISCOUNT` — bust probability by level (AAA 0.88, AA 0.78, A 0.68, Rookie 0.45, Intl 0.35)
- `YEARS_TO_MLB` — estimated years until debut by level
- `PROSPECT_DISCOUNT_RATE` — annual time-value discount (5%)
- `ARB_PCT` — arb salary as percentage of market value by arb year
- `AGING_HITTER` / `AGING_PITCHER` — aging curve multipliers

Calibration runs automatically during refresh via `calibrate.py`, deriving tables
from the league's own data (position-specific Ovr→WAR regression, per-bucket
FV→WAR, FA availability scarcity, arb salary outcomes). Falls back to hardcoded
defaults for new leagues or when data is insufficient.

---

*Last updated: Session 33 (2033-06-23 game date)*
