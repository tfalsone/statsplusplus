# Run-Space Facet Evaluation Model — Requirements

**Status:** Draft (Session 92). Companion to `design.md`. Defines acceptance
criteria for the run-space hitter evaluation redesign.

## Context

The hitter composite currently blends three facets (bat/baserunning/defense) in
grade-space using shares that were reverse-engineered against total WAR. With
each facet now calibrated on its own proper target (bat→wOBA this session), the
shares are orphaned. This redesign recombines the facets **additively in runs**
(the common currency), anchored to OOTP WAR, producing one run-based spine that
feeds composite, WAR projection, and surplus — and (B2) blends stats/age/
convergence per facet.

## Scope

- **In:** hitter composite, ceiling, tool-WAR projection, and their downstream
  effects (FV, surplus, rankings). Per-league calibration of grade→runs curves.
- **Out (v1):** pitchers (stay on composite→WAR); explicit versatility premium.

---

## Requirements

### R1 — Facet runs in a shared unit
1.1 The system SHALL compute, for each hitter, three facet run values above
    average: bat (wRAA), baserunning (UBR-runs), and fielding (fielding runs),
    plus a positional adjustment in runs.
1.2 The facet run values SHALL sum additively to a total runs-above-average.
1.3 WHEN a facet's inputs are missing (e.g. no defensive tools) the system SHALL
    degrade gracefully (treat that facet as 0 runs / league-average) rather than
    fail the whole evaluation.

### R2 — Bat runs from wOBA
2.1 Bat runs SHALL be computed as wRAA from projected wOBA, the league wOBA, and
    the league wOBA-scale, on a 600-PA full-time baseline.
2.2 The wOBA weights and scale SHALL be the per-league/year run-environment-
    derived values (reusing `evaluation/woba.py`), with the canonical fallback
    for thin/in-progress seasons.
2.3 The wOBA SCALE SHALL be derived as canonical FanGraphs scale (1.277) × the
    run-environment factor applied to the weights (i.e. `derived_1B / canonical_1B`),
    keeping wRAA run-magnitudes self-consistent with the derived weights. On PPL
    1954 this gives ~1.30 (vs canonical 1.277) — confound-free and consistent
    with a WAR-regression cross-check (~1.31-1.45). *(RESOLVED B1 prototyping.)*

### R3 — Baserunning runs from UBR
3.1 Baserunning runs SHALL be derived from a per-league calibrated curve mapping
    speed/steal tool grades → UBR runs (not total WAR).
3.2 The calibration SHALL use stored per-player `ubr` as the target.

### R4 — Fielding runs from defensive tools
4.1 Fielding runs SHALL be derived from a per-league calibrated curve mapping
    defensive tools → fielding runs (ZR) per position group.
4.2 WHERE a position's target data is sparse (e.g. catcher framing) or the sample
    is small, the system SHALL fall back to / shrink toward a positional prior.
4.3 The fielding-runs facet SHALL apply the strongest prior-shrinkage of the
    three facets (defense is the noisiest).

### R5 — Multi-position handling (best position)
5.1 The ability composite SHALL evaluate `fielding_runs + positional_adj` at the
    player's **best** position — the position maximizing that sum — using the
    existing `estimate_all_positions` / `assign_bucket` machinery.
5.2 The ability composite SHALL NOT split defensive value across multiple
    positions; the realized multi-position split SHALL remain in the downstream
    depth-chart / surplus playing-time layer.

### R6 — OOTP-anchored WAR
6.1 Runs-per-win and replacement level SHALL be solved so that summed-facet-runs
    → WAR reproduces OOTP's qualified-hitter WAR distribution for the anchor
    season (per league), NOT derived from a run-environment formula.
6.2 The anchor SHALL be validated: our league-total hitter WAR ≈ OOTP's within a
    stated tolerance.

**Cross-league validation (B1 prototype, Session 92):** the anchor self-solves to
consistent, realistic values across all three run environments, with strong
new-WAR~OOTP-WAR fidelity:
- PPL (1955 retro, 20-80): rpw 8.9, repl 15.6, **R² 0.71**
- eMLB (1-100): rpw 9.0, repl 18.0, **R² 0.84** (n=311)
- vMLB (20-80): rpw 9.3, repl 17.3, **R² 0.70**
(vs ~0.10 for the current composite→WAR path.) Different rating scales handled.
Weak spots confirming the shrinkage need: vMLB catcher (r=0.26) and 3B (r=0.34) —
small samples on noisy positions → strongest prior-shrinkage, value from the
positional adjustment.

### R7 — Composite scale continuity
7.1 The run total SHALL map to a 20-80 composite calibrated to the current MLB
    composite distribution (mean/sd), so league-average ≈ 50 and the scale is
    preserved.
7.2 New-vs-old composite rank correlation SHALL be reported; large movers SHALL
    be explainable by baseball-sound reasons (positional value now in runs).

### R8 — Integration with stat-blend / aging (B1: whole-player)
8.1 The run-based tool-WAR SHALL enter `compute_player_value` where `tool_war`
    does today; the existing whole-player `stat_confidence` blend with stat-
    history WAR, aging curves, and development ramp SHALL continue to apply
    unchanged in B1.
8.2 `peak_war_from_score` SHALL be retired as the primary hitter path but kept
    for pitchers and as a missing-tool fallback.

### R9 — Per-facet dynamics (B2)
9.1 Each facet SHALL blend its tool-projected runs with its OBSERVED historical
    runs (bat→historical wRAA, baserunning→`ubr`, defense→fielding runs) using a
    facet-specific `stat_confidence` reflecting that metric's stabilization rate.
9.1a **PROSPECT MiLB-stat blend (data-constrained, confirmed B1 prototyping).**
    Prospects currently get MiLB-stat integration via PAC (Performance-Adjusted
    Ceiling, ±6 on ceiling from level-relative OPS+). The run-spine MUST preserve
    and improve this PER FACET: prospect **bat**-runs blend MiLB **wRAA** (MiLB
    batting is rich: 28,967 rows / 7,001 qualified on PPL, `ubr` populated),
    prospect **baserunning**-runs blend MiLB `ubr`, but prospect **fielding**-runs
    stay TOOL-ONLY (MiLB fielding is EMPTY — 0 rows — a StatsPlus API limitation;
    also baseball-correct since low-level fielding runs are noise). Concrete need
    confirmed: a tool-only prototype over-credits prospects whose MiLB production
    lags their tools (e.g. Cubs CF Steve Colley projected composite 60 on tools
    despite a .299/.303 MiLB line) — the bat-facet MiLB blend is what corrects
    this, per-facet and stabilization-weighted (wRAA slow to stabilize → modest
    early weight).
9.2 Each facet SHALL age on a facet-specific aging curve (baserunning earliest/
    fastest decline; bat classic; defense its own).
9.3 The composite and the WAR projection SHALL derive from the SAME run total
    (folding in composite↔projection convergence); the weak `compute_composite_mlb`
    stat-blend SHALL be replaced by this shared total.
9.4 Facet calibration SHALL guard small samples (shrink toward priors), with
    baserunning/defense leaning on stronger universal priors.

### R10 — Ad-hoc adjustments
10.1 Grade-space compensators (contact-scaled baserunning boost, elite-defense
     boost, speed×contact synergy) SHALL be removed, after verifying (regression
     check) they add no residual signal in run-space.
10.2 Tool-reliability penalties (sub-MLB floor penalty, tool-imbalance penalty)
     SHALL be retained, re-expressed as run penalties (they encode bust-risk,
     orthogonal to run conversion).

### R11 — Architecture
11.1 The run math SHALL live in a new pure module `evaluation/facet_runs.py`
     (no DB, no I/O, no global state); `composite.py` maps runs→20-80;
     `player_value.py` consumes the tool-WAR. facet_runs SHALL be the tool-WAR
     source only and SHALL NOT duplicate `war.py`'s stat-history-WAR path.
11.2 All per-league calibrated curves/tables SHALL be produced by
     `data/calibrate.py` into the existing weight JSON files.

### R12 — Testing & validation
12.1 New pure functions SHALL have unit tests (facet-runs math, best-position
     selection, runs↔grade mapping, anchor solve).
12.2 The change SHALL pass the full suite and `model_regression.py --test
     holdout`, with any WAR-R² tradeoff stated and justified.
12.3 Validation SHALL cover eMLB, vMLB, and PPL (small-sample guards exercised).
12.4 Player spot-checks SHALL confirm: power-first hitters up; premium up-the-
     middle defenders correctly valued; 1B/DH offense not double-penalized.

### R13 — Backward compatibility
13.1 The composite SHALL remain a 20-80 integer at every downstream boundary
     (FV, ceiling, surplus, rankings, draft board, dev_speed) — no consumer
     signature changes.
13.2 Single-league leagues (eMLB/vMLB) SHALL be unaffected by any multi-league
     scoping; the redesign SHALL respect the existing `mlb_*` view scoping.
