# Implementation Plan: Evaluation Engine Reframe

## Overview

Restructure the evaluation engine to expose component-level scores (offensive grade, baserunning value, defensive value, durability score) as first-class outputs, while retaining the composite as a secondary convenience metric. The implementation touches four layers: evaluation engine computation, database schema, FV calculator consumption, and web UI display. All changes are additive — no existing formulas change, and backward compatibility is maintained via NULL fallbacks.

## Tasks

- [x] 1. Add component score extraction functions to `evaluation_engine.py`
  - [x] 1.1 Implement `compute_offensive_grade(tools, weights)` — extract hitting contribution from contact, gap, power, eye using `_tool_transform` and re-normalized offensive weights; return integer on 20-80 scale or None
    - Reuse the offensive tool loop from `compute_composite_hitter`, isolating only the hitting tools (exclude speed, steal, stl_rt, defense)
    - Re-normalize weights over available offensive tools to sum to 1.0
    - _Requirements: 1.1, 1.4, 1.5, 1.6_

  - [x] 1.2 Implement `compute_baserunning_value(tools, weights)` — extract baserunning contribution from speed, steal, stl_rt using linear values (no piecewise transform); return integer on 20-80 scale or None
    - Use the same linear treatment as `compute_composite_hitter` for speed/steal/stl_rt
    - Re-normalize weights over available baserunning tools
    - _Requirements: 1.2, 1.4, 1.5, 1.6_

  - [x] 1.3 Implement `compute_defensive_value(defense, def_weights)` — extract defensive contribution from positional defensive tools using `DEFENSIVE_WEIGHTS`; return integer on 20-80 scale or None
    - Same weighted sum as the defensive component in `compute_composite_hitter`
    - _Requirements: 1.3, 1.4, 1.5, 1.6_

  - [x] 1.4 Implement `compute_durability_score(stamina, role)` — return stamina on 20-80 for SP, None for RP
    - _Requirements: 2.2, 2.3_

  - [x] 1.5 Implement `derive_composite_from_components(offensive_grade, baserunning_value, defensive_value, recombination)` — recombine component scores using position-specific offense/defense/baserunning shares; must produce identical output to `compute_composite_hitter` for the same inputs
    - _Requirements: 3.3, 3.4_

  - [x] 1.6 Write property test: Component scores are bounded integers on the 20-80 scale
    - **Property 1: Component scores are bounded integers on the 20-80 scale**
    - Use existing `hitter_tools_st`, `pitcher_tools_st` strategies
    - Verify `compute_offensive_grade`, `compute_baserunning_value`, `compute_defensive_value`, `compute_durability_score` all return integers in [20, 80] for valid inputs
    - **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 2.2**

  - [x] 1.7 Write property test: Partial tools produce valid component scores
    - **Property 2: Partial tools produce valid component scores**
    - Custom strategy with mixed None/non-None tools where at least one tool per component is non-None
    - Verify each component function returns a valid integer in [20, 80], not None
    - **Validates: Requirements 1.5**

  - [x] 1.8 Write property test: Composite decomposition round-trip
    - **Property 3: Composite decomposition round-trip**
    - For any valid hitter tools, weights, defense, def_weights, and recombination shares, verify `derive_composite_from_components(off, br, def, recom)` == `compute_composite_hitter(tools, weights, defense, def_weights)`
    - **Validates: Requirements 3.3, 3.4**

  - [x] 1.9 Write property test: RP durability is always None
    - **Property 7: RP durability is always None**
    - For any stamina in [20, 80], verify `compute_durability_score(stamina, "RP")` returns None
    - **Validates: Requirements 2.3**

- [x] 2. Enrich `EvaluationResult` and update `_run_impl` to compute and store component scores
  - [x] 2.1 Add component score fields to `EvaluationResult` dataclass — `offensive_grade`, `baserunning_value`, `defensive_value`, `durability_score`, `offensive_ceiling`, `baserunning_ceiling`, `defensive_ceiling`
    - _Requirements: 1.7, 2.4_

  - [x] 2.2 Update `_run_impl` to call the new component functions for each player and populate `EvaluationResult` with component scores
    - For hitters: compute offensive_grade, baserunning_value, defensive_value
    - For pitchers: store pitching composite as offensive_grade, compute durability_score for SP
    - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2, 2.3, 2.5_

  - [x] 2.3 Implement `compute_component_ceilings` — compute per-component ceilings from potential tools with age-weighted blend, floored at current component values
    - _Requirements: 6.5_

  - [x] 2.4 Update `_run_impl` to compute component ceilings and include them in the DB write
    - _Requirements: 6.5_

  - [x] 2.5 Write property test: Component ceilings are floored at current component scores
    - **Property 5: Component ceilings are floored at current component scores**
    - Verify each component ceiling >= corresponding current component score, and each is an integer in [20, 80]
    - **Validates: Requirements 6.5**

- [x] 3. Enrich divergence detection with component context
  - [x] 3.1 Extend `detect_divergence` to accept an optional `components` dict and include `component_context` in the return value when divergence exists — list of component entries sorted by value descending
    - _Requirements: 4.5_

  - [x] 3.2 Update `_run_impl` to pass component scores to `detect_divergence`
    - _Requirements: 4.5_

  - [x] 3.3 Write property test: Divergence report includes component context when components are provided
    - **Property 4: Divergence report includes component context when components are provided**
    - For any tool_only_score and OVR where |tool_only_score - OVR| >= 5, and non-None component scores, verify `detect_divergence` returns a dict with `component_context` sorted by value descending
    - **Validates: Requirements 4.5**

- [x] 4. Extend snapshot deltas with component-level deltas
  - [x] 4.1 Update `compute_snapshot_deltas` to include `offensive_delta`, `baserunning_delta`, `defensive_delta`, and `top_component_change` fields
    - _Requirements: 7.2, 7.5_

  - [x] 4.2 Write property test: Component snapshot deltas are correct arithmetic differences
    - **Property 6: Component snapshot deltas are correct arithmetic differences**
    - For any two snapshots with component scores, verify deltas equal (current - previous) and `top_component_change` identifies the component with the largest absolute delta
    - **Validates: Requirements 7.2, 7.5**

- [x] 5. Checkpoint — Ensure all evaluation engine tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Database schema migration for component score columns
  - [x] 6.1 Add `_migrate_ratings_components` to `db.py` — add `offensive_grade`, `baserunning_value`, `defensive_value`, `durability_score`, `offensive_ceiling` columns to both `ratings` and `ratings_history` tables using the existing idempotent `ALTER TABLE ADD COLUMN` pattern
    - _Requirements: 1.7, 2.4, 6.5_

  - [x] 6.2 Call `_migrate_ratings_components` from `init_schema`
    - _Requirements: 1.7, 2.4_

  - [x] 6.3 Update the `_run_impl` batch UPDATE statement to write component scores and component ceilings to the `ratings` table, and update the `ratings_history` UPDATE to include component scores
    - _Requirements: 1.7, 2.4, 6.5_

  - [x] 6.4 Write unit tests for the migration — verify columns are added idempotently on an in-memory DB
    - _Requirements: 1.7, 2.4_

- [x] 7. Update FV calculator to consume component scores
  - [x] 7.1 Add component score columns (`offensive_grade`, `baserunning_value`, `defensive_value`, `durability_score`, `offensive_ceiling`) to `RATINGS_SQL` in `fv_calc.py`
    - _Requirements: 8.1_

  - [x] 7.2 Update `fv_calc.run()` to pass `defensive_value` through to `calc_fv` as `_defensive_value` when `use_custom_scores` is enabled and the value is non-None
    - _Requirements: 8.1, 8.2_

  - [x] 7.3 Update `fv_model.py` `calc_fv` (or the defensive bonus logic) to use `_defensive_value` when available, falling back to `defensive_score()` when not
    - _Requirements: 8.2, 8.3_

  - [x] 7.4 Add FV tier discrepancy warning — when component-based defensive bonus produces an FV grade differing from the old path by more than one FV tier (5 FV points), log a warning with player ID and both values
    - _Requirements: 8.5_

  - [x] 7.5 Write unit tests for FV integration — verify `fv_calc` uses `defensive_value` when available and falls back when not; verify FV grades remain on the same scale
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

- [x] 8. Checkpoint — Ensure all engine and FV tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Update web layer to display component scores
  - [x] 9.1 Extend `_build_evaluation_data` in `player_queries.py` to extract `offensive_grade`, `baserunning_value`, `defensive_value`, `durability_score`, `offensive_ceiling` from the ratings row and include them in the result dict
    - _Requirements: 9.1_

  - [x] 9.2 Update `_build_evaluation_data` to pass component scores to `detect_divergence` so the divergence dict includes `component_context`
    - _Requirements: 9.3_

  - [x] 9.3 Update `player.html` evaluation summary section — display component scores (Offense / Baserunning / Defense for hitters; Pitching / Durability for pitchers) as the primary display, with composite/ceiling moved to a secondary line below
    - Use the existing `grade()` macro with color-coded grade bars for component scores
    - Show pitcher-specific layout when `is_pitcher` is true
    - _Requirements: 9.1, 9.2_

  - [x] 9.4 Update `player.html` divergence display to include component context — show which component drives the divergence (e.g., "offense-driven") alongside the existing hidden gem / landmine badge
    - _Requirements: 9.3_

  - [x] 9.5 Update `player.html` snapshot deltas section to display component-level deltas (`offensive_delta`, `baserunning_delta`, `defensive_delta`) and `top_component_change`
    - Exclude component score keys from the tool_deltas table to avoid duplication
    - _Requirements: 7.2, 7.5_

  - [x] 9.6 Add NULL fallback in `player.html` — when component scores are not available (legacy data), fall back to displaying composite_score as the primary metric
    - _Requirements: 9.5_

  - [x] 9.7 Write unit tests for web layer — verify `_build_evaluation_data` extracts component scores, verify template renders component scores when present and falls back when absent
    - _Requirements: 9.1, 9.5_

- [x] 10. Dead code sweep — remove vestigial code from the prior approach
  - Remove `BAT_FLOOR_THRESHOLDS` constant from `evaluation_engine.py` (retained as reference but no longer used)
  - Scan for any unused parameters, functions, or imports that became dead after the reframe
  - Verify no remaining references to removed code
  - _Requirements: N/A (code hygiene)_

- [x] 11. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document (Properties 1-7)
- Unit tests validate specific examples, edge cases, and integration points
- The design uses Python throughout — all implementation uses the existing Python codebase with Hypothesis for property-based testing
- The composite_score must produce identical values before and after the reframe (Property 3 / Requirement 3.4) — this is the critical backward compatibility constraint
