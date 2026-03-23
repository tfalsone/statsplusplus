# EMLB Assistant GM — Requirements Document

**Created:** 2026-03-17
**Status:** Draft
**Scope:** Trade analysis and transaction planning tooling for the EMLB project

---

## 1. Purpose

The Assistant GM tool provides structured, repeatable, data-driven analysis to support transaction decisions for the Anaheim Angels. It answers the question: *is this trade good for us, and by how much?*

The tool is not a recommendation engine — it does not tell the GM what to do. It quantifies the value exchange in a proposed transaction so the GM can make an informed decision. The agent provides interpretation; the tool provides the numbers.

---

## 2. Use Cases

### 2.1 Trade Evaluation
Given a proposed trade (players and/or cash moving in both directions, with optional salary retention), compute the net surplus value exchange for each side.

**Inputs:**
- One or more players moving in each direction
- Salary retention percentage on any player (0–100%)
- Optional: cash considerations

**Outputs:**
- Surplus value of each player in the deal (contract players: WAR projection minus salary; prospects: development-adjusted surplus)
- Net surplus per side
- Verdict: which side wins, by how much, and under what assumptions

**Example:** Angels trade Briggs + Starks, retain 15% of Briggs' salary. Tool outputs Briggs' contract surplus (-$X), Starks' prospect surplus (+$Y), net to acquiring team, net to Angels.

---

### 2.2 Contract Valuation
Given a player's contract, project their WAR over the remaining years and compute surplus or deficit relative to salary.

**Inputs:**
- Player ID (pulls contract and ratings from data store)
- Optional: manual WAR override for sensitivity analysis

**Outputs:**
- Projected WAR by year (with aging curve applied)
- Market value by year (WAR × $/WAR)
- Surplus/deficit by year and total
- Sensitivity range (optimistic / base / pessimistic)

**Example:** Is Rohnson's $30.2M/year contract above or below his projected value over the next 9 years?

---

### 2.3 Prospect Valuation
Given a prospect's FV, age, level, and positional bucket, compute their surplus value over the pre-arb and arbitration control period.

**Inputs:**
- Player ID (pulls FV, age, level from prospect history or scaffold)
- Optional: manual FV override

**Outputs:**
- Development probability (likelihood of reaching FV ceiling)
- Expected WAR over control period (probability-weighted)
- Expected salary over control period (pre-arb + arb estimates)
- Surplus value (market value of expected WAR minus expected salary)

**Example:** What is Starks worth as a trade chip? What is Marshall worth?

---

### 2.4 Salary Retention Optimizer
Given a player with negative surplus value, compute how much salary retention is needed to bring the deal to neutral or positive for the acquiring team.

**Inputs:**
- Player ID
- Target surplus for acquiring team (default: 0 = neutral)

**Outputs:**
- Required retention percentage to reach target surplus
- Dollar amount retained at that percentage
- Resulting net cost to Angels

**Example:** How much of Briggs' salary do we need to eat to make him tradeable without attaching a prospect?

---

### 2.5 Extension Valuation
Given a player and a proposed extension offer, compute the surplus value of the extension relative to what the player would earn through arbitration and free agency.

**Inputs:**
- Player ID
- Proposed extension: years, annual value (or year-by-year salary)
- Extension start year

**Outputs:**
- Projected market value over extension years (WAR × $/WAR)
- Surplus/deficit vs. proposed salary
- Comparison: extension cost vs. projected arb + free agent cost if not extended

**Example:** What is a fair extension for Crochet? What AAV locks in meaningful surplus?

---

### 2.6 Roster Payroll Projection
Project the Angels' payroll commitments forward 3–5 years, accounting for existing contracts, expected arbitration costs, and upcoming free agents.

**Inputs:**
- Current contracts (from data store)
- Arbitration-eligible players and estimated arb salaries
- Free agent departures (players whose contracts expire)

**Outputs:**
- Year-by-year payroll projection
- Committed vs. projected vs. available budget
- Free agent class by year (who is hitting the market and when)

**Example:** What does the 2035 payroll look like if we extend Crochet and McClanahan but let Grimaldo walk?

---

## 3. Out of Scope (Phase 1)

The following are explicitly deferred to later phases:

- **League-wide trade target identification** — requires SQLite and league-wide data sync (Phase 3)
- **Automated trade proposal generation** — requires supply/demand matching across all teams (Phase 4)
- **UI** — command-line and agent-driven only in Phase 1 (Phase 5)
- **Draft analysis** — separate problem domain, not addressed here
- **International signing valuation** — deferred

---

## 4. Data Requirements

All inputs must be derivable from existing data files or computable from them. No manual data entry should be required for standard use cases.

| Data needed | Source |
|---|---|
| Player contract (salary, years, NTC, options) | `contracts` table in `league.db` |
| Player ratings (Ovr, Pot, age, position) | `ratings` table in `league.db` |
| Prospect FV and level | `prospect_fv` table in `league.db` |
| League minimum salary | `config/league_settings.json` |
| $/WAR (league-calibrated) | `config/league_averages.json` |
| Aging curves | `docs/ootp/aging_and_development.md` (encoded in scripts) |
| Development probability by FV tier | `docs/trade_analysis_guide.md` |
| Arbitration salary estimates | Derived from service time + ratings (formula to be defined) |

---

## 5. Key Assumptions & Constraints

### Valuation model
- WAR projections use EMLB-adjusted aging curves (0.930 aging modifier applied)
- $/WAR is league-calibrated from actual EMLB contract and WAR data, not real-world estimates
- Prospect surplus uses a development probability table by FV tier — probabilities are initially estimated, to be refined empirically as `prospect_history.json` accumulates data
- All valuations produce a base case plus optimistic/pessimistic range — point estimates alone are insufficient

### OOTP-specific constraints
- Releasing a player requires immediate payment of full remaining salary — no gradual absorption
- NTC players cannot be traded without consent — flag NTC in all trade outputs
- Minor league contracts cost $0 — prospect surplus is purely WAR value minus expected future salary
- Service time manipulation (keeping players in minors to delay clock) is a valid roster management tool — the payroll projection should account for this where relevant

### Scope constraints
- Phase 1 covers Angels transactions only
- The tool quantifies value; it does not account for non-financial factors (clubhouse fit, positional need urgency, win-now vs. rebuild context) — those are the GM's judgment call
- Outputs are inputs to a decision, not the decision itself

---

## 6. Success Criteria

The tool is working correctly when:

1. The Briggs + Starks trade analysis from the 2033-04-22 session can be reproduced by running a single script with those players as inputs, producing the same directional conclusions with documented assumptions
2. Extension valuations for Crochet and McClanahan produce a defensible AAV range with clear surplus projections
3. The 3-year payroll projection correctly reflects all existing contracts, flags upcoming free agents, and estimates arbitration costs for pre-arb players
4. A new trade proposal can be evaluated end-to-end (inputs → surplus output) without requiring the agent to reconstruct methodology from scratch

---

## 7. Design Decisions (resolved)

### Q1 — Development probability by FV tier
Use adjusted real-world estimates as the initial table, with a ~3–5 point upward nudge to reflect the EMLB's 1.030 development modifier. Treat as provisional — flag for empirical recalibration after 3+ evaluation cycles accumulate in `prospect_history.json`.

| FV | Reaches ceiling | Becomes MLB regular | MLB depth/bust |
|---|---|---|---|
| 60+ | 43% | 35% | 22% |
| 55 | 33% | 36% | 31% |
| 50 | 23% | 36% | 41% |
| 45 | 15% | 28% | 57% |
| 40 | 8% | 15% | 77% |

For surplus value calculation, use the probability-weighted expected WAR: `(P_ceiling × ceiling_WAR) + (P_regular × regular_WAR) + (P_bust × bust_WAR)`.

### Q2 — Arbitration salary formula
Use real-world rule-of-thumb approximations as the initial model. Recalibrate after observing actual EMLB arbitration awards.

| Arb year | % of estimated market value |
|---|---|
| Year 1 (3 yrs service) | 45% |
| Year 2 (4 yrs service) | 65% |
| Year 3 (5 yrs service) | 80% |

EMLB arb cycle data can be provided to refine these percentages. Pre-arb players (0–2 yrs service) earn league minimum ($825K).

### Q3 — $/WAR calibration
$/WAR is calibrated from multi-year MLB contracts signed in the current season (salary ≥ $5M, years > 1). The multi-year filter excludes arbitration contracts, which are set by a formula rather than the open market and would understate the true cost of a win. The active figure is stored in `config/league_averages.json` and recalculated on each league refresh. Current value: **$8.62M/WAR** (2033).

### Q4 — WAR by position normalization
Apply positional adjustments only in cross-position comparisons (e.g. comparing a SS prospect to a 1B prospect in a trade). Single-player valuations use Ovr directly without adjustment. Positional adjustment values (runs/year above average):

| Position | Adjustment |
|---|---|
| C | +12 |
| SS | +7 |
| 2B | +3 |
| CF | +2.5 |
| 3B | +2 |
| RF | -7 |
| LF | -7 |
| 1B | -12 |
| DH | -17 |

Revisit after initial implementation to validate against observed OOTP outcomes.

### Q5 — Pitcher role transitions
Use the farm analysis guide's bucketing logic as the source of truth for projected role (3+ pitches projecting to 45+, Stm ≥ 40 → SP; otherwise RP). WAR projections use projected role, not current role. Flag any player where current role ≠ projected role in tool output.

**Implementation note:** The bucketing logic currently lives in `docs/farm_analysis_guide.md` and is implemented in `scripts/farm_analysis.py`. Rather than duplicating it, refactor the shared logic into a utility module (`scripts/player_utils.py`) that both `farm_analysis.py` and the new trade scripts import. This is the single source of truth for bucketing, normalization, and any other logic shared across analysis types.
