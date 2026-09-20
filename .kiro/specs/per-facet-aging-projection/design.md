# Per-Facet Aging + Development Projection — Design

**Status:** Investigation / design (Session 92). Deferred follow-up from the
run-space facet model. Ties together the deferred **per-facet aging** and the
existing **dev_speed** metric into one per-facet, run-space projection of a
player's facet-runs across the control window.

**Blast radius:** rewires `compute_player_value`'s year-by-year WAR derivation —
the highest-impact code in the model (surplus for every player, every trade
value). Requires a surplus-validation gate. Own scoped session.

---

## 1. The problem with the current projection

`compute_player_value` projects year-by-year WAR with two whole-player, crude
mechanisms (see the year loop):

- **Aging:** `aging_mult(player_age, bucket)` — ONE curve per bucket, applied to
  the whole `year_war`. Cannot express that a 33-yo's legs (baserunning) have
  declined while his bat is near-peak.
- **Development:** a flat `composite → ceiling` growth at rate 0.6, gated on
  `has_development_room`, blended by a heuristic `dev_weight`. Whole-player,
  generic (every prospect develops at the same modeled rate), and disconnected
  from the dev_speed metric we already compute.

The run-space model now decomposes a player into **bat / baserunning / fielding**
run components — so the projection SHOULD decompose too. And `dev_speed` (a
per-peer z-score of a player's *actual* development pace, already keyed on the
offensive component for hitters) is the natural personalization input for the
development side.

## 2. The unifying model — facet-runs over time

Project EACH facet's runs across the control window, then sum → WAR per year.
Each facet has its own peak age, its own development curve, and its own aging
curve — so a single player can be developing his bat while his legs decline.

```
for each control year Y (player_age = a):
  bat_runs(a)  = project_facet("bat", current_bat, ceiling_bat, a, dev_pace)
  br_runs(a)   = project_facet("baserunning", current_br, ceiling_br, a, dev_pace)
  fld_runs(a)  = project_facet("fielding", current_fld, ceiling_fld, a, dev_pace)
  year_runs(a) = bat + br + fld + positional_adj
  year_war(a)  = runs_to_war(year_runs(a), anchor)
```

### project_facet(facet, cur, ceil, age, dev_pace)
Two regimes that meet at the facet's peak age (`AGING_*` curve peak):

- **Development (age < facet_peak, cur < ceil):** grow from `cur` toward `ceil`.
  - Base rate: a per-facet development curve — **bat develops most and latest;
    baserunning is near-fixed early (little growth); fielding moderate.** (Mirror
    of the aging curves — the up-slope before peak.)
  - **dev_pace personalization:** scale the growth rate by the player's dev_speed
    z-score → a fast developer (z>0) closes the cur→ceil gap sooner / more fully;
    a stalled one (z<0) plateaus below ceiling. dev_speed is per-hitter keyed on
    the offensive component, so it maps most directly to the BAT facet growth
    rate (baserunning/fielding growth stays curve-driven — they don't "develop"
    the way the bat does).
- **Aging (age >= facet_peak):** decline via `AGING_BAT/BASERUNNING/DEFENSE`
  applied to the facet's peak runs (baserunning earliest/steepest, bat latest).

## 3. The dev_speed tie-in — the hard rule

dev_speed enters as a **RATE (timing) input to the development projection**, NOT
as a grade/ceiling adjustment. This distinction is the guardrail:

- **Allowed:** dev_pace changes *when* / *how fully* a player reaches his already-
  determined facet-ceiling (a fast developer realizes his bat-ceiling by 24 vs
  27; a stalled one may top out below it). This affects the *shape* of the
  year-by-year curve, hence surplus timing.
- **FORBIDDEN:** dev_speed must not change *what* the ceiling is, nor be added to
  FV. That would re-hide the trajectory information that makes dev_speed useful
  as an independent axis (the existing hard rule from the dev_speed spec) and
  double-count.

Net effect on surplus: a fast-developing high-ceiling prospect gets more of his
peak WAR *earlier* in team control (more surplus while cheap); a stalled one gets
less. This is a legitimate, intuitive refinement — and it finally connects
dev_speed to value without violating the separation.

## 4. Data / inputs needed
- **Per-facet current runs:** already computed in the run spine (facet_runs).
- **Per-facet ceiling runs:** run the CEILING (potential) tools through the same
  facet spine (already done for the ceiling composite — expose the facet split).
- **Per-facet peak ages + curves:** `AGING_*` peaks define the dev→aging pivot;
  need per-facet DEVELOPMENT (up-slope) curves — literature priors (bat latest,
  speed earliest), shrink-adjust per league only where data supports.
- **dev_pace:** the dev_speed z-score (already computed, in the `dev_speed`
  table / `compute_dev_speed`). Needs a defined mapping z → growth-rate
  multiplier (e.g. clamp to [0.5x, 1.5x] so it's a modifier, not a driver).

## 5. Design decisions

**Resolved (Session 92):**
- **[R] dev_pace scope = BAT facet only.** dev_speed is offensive-component-keyed;
  speed/defense growth stays curve-driven (they don't "develop" like the bat).
- **[R] dev_pace mapping = modifier, not driver.** Map the dev_speed z-score to a
  growth-rate multiplier clamped to ~[0.6, 1.4]×, pulled toward 1.0 when
  dev_speed confidence is low (short history / low PT). Never dominant.
- **[R] Stage P1 (per-facet aging) first** as a validated checkpoint before
  development (P2) and the dev_speed tie-in (P3).

**Still open (resolve within each stage):**
- Aging phase applies to the blended (tool+observed) facet runs (P1).
- Development projection keeps the `stat_confidence` gate (established players
  don't "develop") (P2).
- Prospect ceiling-facet split exposed cleanly (bat via tool→wOBA on potentials;
  br/fielding ceiling ≈ current) (P2).
- Exact dev_pace clamp endpoints + confidence-fade curve (P3).


## 6. Staging

**STATUS (Session 92): P1 + P2 + P3 ALL IMPLEMENTED.**
- [x] **P1 — per-facet aging.** `facet_aging_mult` blends bat/br/fielding aging
  curves by positive-run share; wired into `compute_player_value` (hitters).
  Bat-first ages slower than glove/speed-first (age 34: 1B 0.59 vs SS 0.46).
- [x] **P2 — per-facet development curves.** `DEV_BAT/BASERUNNING/DEFENSE` +
  `_dev_progress`/`project_facet_runs`; the development projection now follows the
  age-based BAT curve (bat develops latest/most) not a flat linear ramp.
- [x] **P3 — dev_speed tie-in.** `dev_pace_from_z` maps the prior-run dev_speed
  z-score to a clamped [0.6,1.4] growth-rate modifier (confidence-faded), applied
  to the prospect development ramp: fast developers reach peak sooner (more
  surplus while cheap), stalled ones later. **FV/ceiling unchanged** (validated
  0/10 FV moves on high-|z| prospects; 7/7 fast up, 3/3 stalled down/flat).
  dev_speed read from the PRIOR run's `dev_speed` table (avoids circularity;
  slow-moving trailing metric).
- Tests: `test_facet_aging.py`, `test_facet_development.py`. All leagues re-evaluated.

**Original staging plan (below) — all three stages done in one session.**

- **P1:** per-facet AGING only (wire `AGING_BAT/BASERUNNING/DEFENSE` into the
  year loop, replacing the single `aging_mult`). Lower risk, no dev_speed. The
  facet-runs split is already available. Validate surplus deltas (should be
  small — mostly older players, baserunning/defense fading faster).
- **P2:** per-facet DEVELOPMENT curves (up-slope), replacing the flat 0.6 growth.
- **P3:** dev_pace personalization of the bat development rate (the dev_speed
  tie-in). Highest scrutiny — the FV-separation guardrail.

Each stage its own surplus-validation gate. P1 alone is a clean, shippable
improvement.
