# Run-Space Facet Evaluation Model — Tasks

**Status:** Draft (Session 92). Companion to `design.md` / `requirements.md`.
Task ordering follows the B1 (whole-player run-spine) → B2 (per-facet dynamics)
staging. Requirement refs in brackets. The whole model+eval update ships as ONE
release (user directive Session 92) — do not partial-release.

---

## Phase 0 — Done / staged (Session 92)

- [x] **0.1 Offense target → wOBA.** `evaluation/woba.py` (per-player wOBA +
  per-league/year run-env weight derivation, canonical fallback, sample guards);
  `_calibrate_tool_weights` regresses offense tools against wOBA not WAR. 8 unit
  tests; full suite 965 passed. *Staged, uncommitted — ships with the redesign.*

---

## STATUS (Session 92): CORE SHIPPED (B1 spine + B2 stat-blend). Aging deferred.

- [x] B1 calibration + `facet_runs.py` spine (bat/br/def runs, OOTP anchor, runs→comp mapping).
- [x] B1 composite/engine wiring (run-space composite, graceful grade-space fallback).
- [x] B2 per-facet MLB blend (observed career wRAA/UBR/ZR by stabilization confidence).
- [x] B2 prospect MiLB blend (level-relative wRAA/UBR; defense tool-only; Step-2 double-count guarded).
- [x] B2 composite↔projection convergence (OPS+ `compute_composite_mlb` replaced for run-space hitters).
- [ ] **DEFERRED — per-facet aging into projection** (curves defined, not wired into `compute_player_value`; highest blast radius, needs surplus-validation gate).
- [ ] **DEFERRED — B1.7 reliability penalties as run penalties** (still grade-space-fallback only).
- [ ] **DEFERRED — dev_speed recalibration; scratch-harness cleanup.**
- [ ] **OUT OF SCOPE v1 — pitcher run-space model.**

---

## Phase B1 — Run-space spine, whole-player blend

### Calibration (data/calibrate.py → weight JSON)
- [ ] **B1.1 wRAA inputs.** Persist per-league wOBA-scale + league wOBA (already
  derivable from the run-env anchor) so bat runs can be computed. [R2]
- [ ] **B1.2 Baserunning grade→UBR curve.** Regress `ubr` on speed/steal grades,
  per league; prior-shrink small samples. [R3, R9.4]
- [ ] **B1.3 Fielding grade→ZR-runs curve, per position group.** Regress ZR on
  defensive tools (IF range, OF range; catcher framing prior-fallback). Strongest
  shrinkage. [R4]
- [ ] **B1.4 OOTP WAR anchor.** Solve runs-per-win + replacement so summed facet
  runs → WAR reproduces OOTP qualified-hitter WAR distribution; store per league;
  assert league-total tolerance. [R6]
- [ ] **B1.5 Runs→20-80 mapping params.** Calibrate affine map from the run
  distribution to the current MLB composite mean/sd. [R7]

### Pure computation (evaluation/facet_runs.py — NEW)
- [ ] **B1.6 Facet run functions.** `bat_runs` (wRAA), `baserunning_runs`,
  `fielding_runs` (best-position via `estimate_all_positions`), `positional_adj`;
  `total_runs_above_avg`; `runs_to_war` (anchored); `runs_to_composite` (20-80).
  Pure, missing-input-safe. [R1, R2, R3, R4, R5, R6, R7, R11.1]
- [ ] **B1.7 Reliability penalties in run-space.** Re-express sub-MLB floor +
  tool-imbalance penalties as run penalties; DROP grade-space compensators after
  a residual-signal check. [R10]

### Wiring
- [ ] **B1.8 composite.py → run-spine.** `compute_composite_hitter` computes via
  facet_runs and maps to 20-80; retire `DEFENSE_SHARES` / `BASERUNNING_SHARE`.
  Keep the 20-80 integer boundary. [R7, R13.1]
- [ ] **B1.9 ceiling.py.** Ceiling uses the same run spine (ceiling-grade inputs).
  Confirm FV consumes composite/ceiling unchanged. [R5.1, R13.1]
- [ ] **B1.10 player_value.py.** Run-based tool-WAR enters where `tool_war` does;
  retire `peak_war_from_score` as primary hitter path (keep pitcher + fallback);
  whole-player stat-blend/aging/ramp unchanged. [R8]
- [ ] **B1.11 evaluation_engine.py / fv_calc.py.** Batch path computes the new
  composite/ceiling/WAR; no signature changes downstream. [R11.2, R13.1]

### Tests / validation (B1)
- [ ] **B1.12 Unit tests** for facet_runs math, best-position, runs↔grade, anchor
  solve. [R12.1]
- [ ] **B1.13 Validate B1 in isolation:** full suite; holdout WAR-R²; composite
  rank-correlation vs old + large-mover review; eMLB/vMLB/PPL; player spot-checks
  (power-first up, up-the-middle D valued, 1B/DH not double-penalized). [R12]

---

## Phase B2 — Per-facet stat-blend / aging / convergence

### Historical observed-runs (data)
- [ ] **B2.1 Historical facet runs from stat history.** Per season: bat→wRAA
  (from stored counting stats), baserunning→stored `ubr`, defense→ZR-runs. Feed a
  per-facet analogue of `stat_peak_war`. [R9.1]

### Calibration
- [ ] **B2.2 Per-facet stabilization ramps.** Facet-specific `stat_confidence`
  (wRAA slow, UBR fast, fielding slowest); per league with priors. [R9.1, R9.4]
- [ ] **B2.3 Per-facet aging curves.** Split aging into bat / baserunning
  (earliest, fastest) / defense curves; per league with universal priors for
  baserunning/defense. [R9.2, R9.4]

### Computation / wiring
- [ ] **B2.4 Per-facet blend+age in facet_runs.** Each facet blends tool-runs
  with observed-runs by its `sc`, ages on its curve, THEN sum. [R9.1, R9.2]
- [ ] **B2.5 Composite↔projection convergence.** Composite and WAR projection
  derive from the SAME run total; replace the weak `compute_composite_mlb`
  stat-blend. [R9.3]

### Tests / validation (B2)
- [ ] **B2.6 Unit tests** for per-facet blend/aging and convergence.
- [ ] **B2.7 Validate B2 vs B1 baseline:** confirm per-facet dynamics improve
  (young speedsters not over-credited with baserunning "upside"; aging veterans'
  legs discounted before bats); holdout, cross-league, spot-checks, full suite.
  [R12]

---

## Phase C — Ship (single combined release)
- [ ] **C.1 Docs pass:** changelog, task_list (close the offense-tool-weight +
  this redesign items), system_overview (new facet_runs module, run spine, DB/
  calibration changes), STRUCTURE.md, valuation_model.md / evaluation_model.md,
  tools_reference.
- [ ] **C.2 Recalibrate + fv_calc on all leagues;** final full-suite + holdout.
- [ ] **C.3 Release:** minor+ version bump (evaluation-model change), commit,
  push main, annotated tag, Discord post, update `discord_posts.json`. Note the
  migration caveat (per-league calibrated data updates on next refresh/calibrate;
  code degrades gracefully until then).

---

## Notes / risks
- **Small-sample calibration** (recurring concern): every per-league curve needs
  a prior-shrinkage floor; defense strongest. Reuse the wOBA sample-guard pattern.
- **Ranking continuity** is the main user-visible risk — B1.13 rank-correlation
  gate before proceeding.
- **Do not duplicate `war.py`'s stat-history path** — facet_runs is tool-WAR only.
- **Pitchers untouched** — verify no accidental coupling via shared composite code.
