# Design Document: Prospect Development-Speed Metric

**Status:** v1 (display) implemented Session 88 — `evaluation/dev_speed.py`
(pure), `dev_speed` table written by `fv_calc`, displayed on the player page,
Development tab, league prospect lists, and team farm. Validated via a POC
(since removed) against the Rays' vMLB system. Model integration
(risk/outcomes) deferred — gated on multi-season benchmarking data.

## Overview

A per-player metric that quantifies **how fast a prospect is developing relative
to expectation** — normalized by position bucket, age, and league environment —
so it is comparable across profiles (a 17-yo hitter and a 23-yo pitcher develop
on very different curves). The goal is to flag prospects developing faster or
slower than the baseline for their bucket, surfacing two archetypes the rest of
the app is blind to:

- **Stalled with upside** — a high ceiling the player is *not* tracking toward
  (a risk the FV/surplus systems, which read the ceiling as achievable, miss).
- **Rising with room** — fast development toward a still-unrealized ceiling
  (a breakout / buy candidate; ETA may beat the industry).

It is a **confidence-adjuster on existing evaluations, not a new ranking axis.**
It measures *trajectory*, orthogonal to the *level* that FV/surplus measure. It
must never be folded into FV or surplus — doing so would re-hide exactly the
information (a stalled player's trajectory vs his ceiling) that makes it useful.

## What it measures

Development is read from longitudinal `ratings_history` (monthly in-game
snapshots of full ratings incl. our composite/component scores). For a trailing
window, we measure the **annualized movement of the developmentally-relevant
component**, then express it as a **z-score vs same-bucket, same-age-band, same-
league peers**.

- **Primary signal — component-split, NOT blended composite:**
  - **Hitters → offensive-grade movement.** Rationale (empirically confirmed on
    Joe Read + a cohort of defense-driven risers, and mechanically confirmed by
    OOTP docs): positional composite ratings *increase with experience at a
    position, not skill* ("C/SS/CF grades increase toward max as the player
    gains experience — not purely skill-based"). Measuring the blended composite
    would credit "development" merely for accumulating innings at a position and
    would over-credit already-maxed defenders. The bat is the limiting component
    for most hitters and is what determines their MLB future.
  - **Pitchers → composite movement.** No defensive confound. Validated on the
    Rays' arms.
- **z-score:** `(player_annual_movement − bucket/band mean) / bucket/band SD`,
  computed per league (a high-development league like eMLB has a higher baseline;
  the z normalizes it away — eMLB develops ~3× faster than vMLB in raw terms).
- **POT-gap qualifier:** the current OVR→POT gap (remaining upside). The z alone
  conflates "done developing / near ceiling" with "rising with room"; the gap
  turns pace into the archetype.
- **Gap-change decomposition (ΔOVR vs ΔPOT):** a shrinking gap can mean OVR rose
  toward POT (real development) *or* POT fell toward OVR (the engine/scout giving
  up on the ceiling — a bust signal, NOT progress). OOTP POT is scout- and
  TCR-mutable, so this decomposition is essential — it was the single most
  clarifying addition in validation and matters *more* for pitchers (ceilings
  erode readily; e.g. Jose Serrano ΔPOT −8 while "gap closed 0.55").

## Signal classification (z × gap)

| | Wide gap (upside remains) | Small gap (near ceiling) |
|---|---|---|
| **Fast (z ≥ +1)** | ⚡ Rising (room) — closing on a high ceiling ahead of schedule | ⚡ Rising (realizing) — arriving at ceiling early; limited further upside |
| **Slow (z ≤ −1)** | ⚠ Stalled — upside at risk | ⚠ Regressing/plateaued |
| **Mid, z ≤ −0.5 + wide gap** | ⚠ Watch — slow vs upside | — |
| **Otherwise** | On pace | On pace |

**Labels stay descriptive (observation, not verdict).** "Stalled with upside" is
an *ambiguous* reading the metric cannot adjudicate — it can mean "late
bloomer / fixable / mis-leveled" (→ buy-low, promote) or "overrated by the
tools / bust track" (→ fade, don't-protect). The correct action depends on the
decision's **cost structure** (cheap optionality → chase upside; expensive
roster commitment → default to no), which is why decision-specific framing lives
in the trade and Rule 5 surfaces, not the core badge.

## OOTP grounding (why the signal is real and how the engine shapes it)

From `docs/ootp/aging_and_development.md` and `ratings_and_attributes.md`:

- Development is driven by concrete modeled factors: **coaching, playing time,
  challenge/level-fit, age, injuries, TCR randomness, personality** (WrkEthic/
  Int). Rating movement is a lossy readout of these — legitimizing the signal.
- **Talent Change Randomness (TCR):** random rating jumps occur any time and are
  **most pronounced among the most skilled players.** So high-ceiling prospects
  (our archetype cohort) are the *noisiest* — a short-window high-POT stall is
  more likely noise/reversible than a low-POT stall. Argues for caution and for
  the confidence tier below.
- **Challenge / level-fit** is a first-class dev driver: "a player dominating AA
  without being promoted may stagnate." A stall can mean *mis-leveled* (a
  promotion cue), not "ceiling is fake."
- **Playing time gates minor-league development:** a low-PA/IP window means the
  player "hasn't had the reps" — not a talent signal. Must be surfaced.
- **Positional composites are experience-inflated** (see component-split above).
- **Scouting accuracy (`Acc`):** low Acc means the ceiling itself is unreliable
  — the tiebreaker for the stall interpretation ("overrated" vs "real stall").
- **Pitcher POT can reflect projected role** (RP↔SP), so pitcher gap/POT moves
  can be role reprojection, not skill — caveat pitcher readings.

## Confidence tier (decided Session 88)

The dev-speed z is a point estimate whose reliability varies per player. Ship a
**two-part output: the signal (z + label + gap context) AND a confidence tier**
(High / Medium / Low), derived from the factors validation showed matter:

- **Window length / snapshot count** (primary; grows automatically as history
  accumulates). Currently every player has ~one 1-year window, so confidence is
  inherently capped today.
- **Scouting accuracy (`Acc`)** — low Acc → lower confidence.
- **Playing time** in the window — thin PA/IP → lower confidence.
- (Optional) down-weight the highest ceilings for the TCR effect.

**Gate:** below a minimum history threshold (**~6 months span and a minimum
snapshot count**), do not show a verdict at all. Above it, always show the signal
*with* its confidence tier so the user knows how much weight to put on it. This
elegantly handles the young/low-composite case (e.g. German Maciel: "developing,
Low confidence — short window, raw profile") rather than hard-hiding a genuine
riser or falsely alarming.

## Baseline / calibration

- Per **(dev-group, age-band, league)** mean + SD of annualized component
  movement, computed **longitudinally** from `ratings_history` (distinct from the
  existing *cross-sectional* dev curves in `calibrate.py`, which are a population
  snapshot by age, not same-player movement over time).
- **dev-group, not fielding position (decided Session 88).** Offensive
  development rate is essentially position-independent for hitters — validated:
  1B/2B/3B/SS/CF/COF offensive-dev means cluster within ~0.5/yr of each other in
  both vMLB and eMLB. So the baseline does **not** slice hitters by fielding
  bucket (that only thins the sample and injects small-cell noise). Groups are:
  **SP, RP, C, HIT** (all non-catcher hitters). Catcher is kept separate because
  its bat develops slower (workload/defensive-demand drag — a real gap in vMLB,
  ~0.7/yr below the field; per-league calibration makes it harmless where no
  effect exists, e.g. eMLB). The SP/RP split is real and kept. The player's true
  position bucket is still used for *display*, only the baseline uses the group.
- **Signals use OUR model's composite/ceiling, never the game's OVR/POT
  (decided Session 88).** The z uses composite (hitters: offensive_grade)
  movement; the gap and ΔOVR/ΔPOT decomposition use `composite_score` /
  `ceiling_score`. OVR/POT are NULL in OVR-less leagues (PPL) and inconsistent
  with the rest of the app even where present. (Legacy field names `d_ovr`/`d_pot`
  retained in storage but represent current-composite / ceiling deltas.)
- Age bands of 2 years. `MIN_GROUP_N ≈ 20` per cell, with a `(group, "ALL")`
  all-ages fallback for tiny leagues.
- Buckets from the canonical **`assign_bucket`** (`statsplusplus.utils.positions`)
  — proven necessary: role-code-only bucketing misclassified relievers (Mendez,
  Schnurr are role-12/low-stamina arms that must compare against the RP baseline).
- The **baseline uses the full population** (broad, well-sampled cells); the
  **noise floor only gates reporting**, not the baseline math.
- Currently computed in a dedicated pass in `fv_calc` (writes the `dev_speed`
  table). Baseline could move to `calibrate.py` → `model_weights.json`
  (`DEV_SPEED_BASELINE`) later; the per-run computation is fine for now.

## Validation summary (POC)

Validated on vMLB against the user's Rays system (hitters + pitchers):

- **Component split** correctly vindicated Joe Read (bat genuinely +8/yr, defense
  flat/maxed → still Rising for the *right* reason) while neutralizing
  defense-only "risers" (Bobby Scott, Danny Herrera: composite-z ~+1.3 collapse
  to offense-z ~0).
- **Surfaced hidden stalls** the composite masked: Jaylen Sabree (bat frozen at
  AAA, Acc H, 970 PA, POT eroding → confident fade signal) vs Ronnie Toney (bat
  flat but POT holding → investigate, not fade) — the engine context
  distinguishes two players with the same surface stall.
- **Pitchers** sorted sensibly against RP/SP baselines once `assign_bucket` was
  used (Mendez RP z +3.19 breakout; Serrano ceiling-eroding; Schnurr near-ready).

## Known limitations / real-build punch list

1. **Noise floor too blunt for young low-composite players** — hides genuine
   early risers (Maciel). Use the confidence tier to *dampen* rather than
   hard-suppress; consider flooring on POT/age instead of composite alone.
2. **Promotion / level-change artifacts** — a level jump can flatten ratings for
   a season and look like a stall. Needs level-transition detection.
3. **Gap-note phrasing** — the ceiling-trajectory line only asserts "eroding" when
   ΔCeiling < −1 AND ΔComposite ≤ 1, and "developing toward the ceiling" when
   ΔComposite > 1; the ambiguous both-rose / gap-widened case shows neither
   assertion (just the raw deltas). Adequate for v1; could be richer later.
4. **Single ~1-year window** — all leagues currently have ~one window; the metric
   strengthens and could show a trend (not just a point) as history accumulates.
5. **Pitcher POT role-reprojection** caveat — consider role-change detection.
6. **Coaching / level aggregation** (mean dev-speed z by level/affiliate) — the
   weakest, most-confounded use (roster composition, promotion timing, small n).
   Ship last, framed as exploratory, once more history exists.

## Integration research & decisions (Session 88)

Read the actual inputs of every candidate system to assess double-counting. The
unifying finding: **every downstream system is currently trajectory-blind** — FV,
risk, surplus, and outcomes consume a *static snapshot* (composite, ceiling, gap,
age) plus *population-average* expectations (age-based gap-closure). None knows
whether *this* player is actually tracking toward his ceiling. Dev-speed is the
first player-specific trajectory signal, so it's genuinely new information — but
it shares *ingredients* with each system, so integration must be surgical.

Key distinction: is the existing element a **cross-sectional prior** (population
expectation, must work for zero-history players) or a **player-specific proxy**
(a crude attempt to measure *this* player)? Replacing a prior with sparse
evidence breaks the model; replacing a crude proxy with a better one is a clean
upgrade.

Per-system verdict:

- **FV grade — keep the prior; do NOT replace with dev-speed.** FV's age-based
  gap-closure is a *prior* ("what should a player like this become?") that must
  be computable for a just-drafted / just-acquired player with no history.
  Dev-speed returns nothing for ~85% of the age≤25 population (needs a ~6-mo
  window; ~2,641 reportable of ~12,000 in vMLB). Replacing the prior would make
  FV uncomputable/unstable exactly where it matters most. A future
  *prior-plus-evidence* Bayesian nudge (keep prior, adjust toward observed
  trajectory where confident) is possible but high-blast-radius (FV feeds surplus/
  trades/rankings app-wide) — deferred, needs realized-outcome benchmarking.
- **Risk label — the clean replacement target.** Risk =
  `closure × base_discount × gap_scale + char_adj`, and it *already* has a
  player-specific hook: `stat_risk_modifier`, which infers "is he developing?"
  indirectly from MiLB box-score stats. Dev-speed measures the *same thing*
  (realization of the ceiling) *directly* from rating movement. The principled
  move (per user, Session 88) is to **replace `stat_risk_modifier` with a
  dev-speed-based modifier — a proxy swap, not a stack** (no double-count). This
  is the most compelling integration, gated on benchmarking.
- **Career outcomes / confidence — addition, not replacement (strong candidate).**
  Two players with identical ovr/pot/age get identical outcome curves today —
  the model is trajectory-blind. Dev-speed could legitimately shift the
  `p_base/p_mid/p_ceil` scenario weights via `_adjust_scenario_probs` (which
  currently reads only profile *shape*). **Must NOT** multiply into the `dev`
  term — that already uses `realization = ovr/pot` + age-adjusted discount
  (double-count). The scenario-shift hook is clean/non-overlapping. (The model's
  existing `confidence` = level × realization is a *different* confidence than
  our data-reliability confidence tier — don't conflate.)
- **Surplus / future WAR — no independent proxy to replace.** Surplus is
  FV-derived, so any trajectory influence must flow *through* FV or outcomes,
  never a direct surplus multiplier (would double-count FV). Deferred.

### Benchmarking constraint (the gate)

A risk/development change should be validated against **realized outcomes** ("did
the prospect actually reach his ceiling?"), which needs multi-season *forward*
`ratings_history`. Data audit (Session 88):

- `ratings_history` is uniformly **shallow (~2 years) in ALL leagues** — it only
  started accumulating recently. PPL is deepest (1953–1955, ~2 yr, 6,329 players
  with all 10 snapshots) and is the target league for eventual benchmarking.
- PPL's *stats* go back to 1938, but the *ratings* history (what dev-speed is
  computed from) does not — so we cannot yet do "measure dev-speed at T, observe
  realization at T+3/T+5" in any league.
- Earliest feasible check: a **one-step-ahead proxy test** on PPL (compute
  dev-speed from year-1 snapshots, test whether it predicts year-2 composite
  movement better than `stat_risk_modifier`) — weaker than a true outcome
  benchmark but doable with current density.

**Consequence:** display-only v1 is not just conservative — it is *data-generating*:
shipping it live means every refresh accumulates the forward `ratings_history`
that future risk/FV benchmarking requires. "Display now, integrate later" is the
correct sequence regardless of caution.

## Integration plan (where it threads in)

Positioned as a **second-opinion signal displayed adjacent to model outputs, not
blended into them** (v1). The one eventually-justified computational influence is
the outcomes scenario shift; the one eventually-justified replacement is
dev-speed → risk's `stat_risk_modifier`. Both gated on benchmarking.

**v1 — display only (no model interaction, zero double-count):**
- Per-player metric computed + stored (calibration baseline in `calibrate.py`).
- **Player page (prospect):** badge + component z + POT-gap context + confidence
  tier + plain-language label, next to the existing development chart.
- **Prospect lists / farm view:** a dev-speed column/badge to scan for
  stalled-upside and breakout cases.

**Deferred (gated on accumulated forward `ratings_history`, benchmarked on PPL):**
- **Risk label:** replace `stat_risk_modifier` with a dev-speed modifier (proxy
  swap). Validate one-step-ahead now; true outcome benchmark when data exists.
- **Career outcomes:** scenario-probability shift via `_adjust_scenario_probs`.
- **FV:** prior-plus-evidence nudge (highest risk, latest).
- **Surplus:** only via FV/outcomes, never directly.

**Never:** a direct dev-speed multiplier on FV or surplus (double-counts the
gap/age/closure those already embed).

**Other display surfaces (later):** trade targets (flag dev-speed vs FV
contradiction — decision-context framing lives here), Rule 5 protect/expose lean,
coaching/level aggregation (exploratory, last).

## Design principles

- Pure computation for the metric math; DB/pipeline only in the calibration and
  storage passes (consistent with the package architecture).
- Per-league calibration; no hardcoded baselines.
- Descriptive labels in the core badge; decision-specific framing in trade/Rule 5.
- Confidence tier + hard gate below a history floor; never present a low-history
  reading as a verdict.
