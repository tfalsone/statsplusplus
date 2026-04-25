# Implementation Plan: Custom Player Evaluation

## Overview

This plan implements a custom Evaluation Engine that computes Composite_Score, Ceiling_Score, and Tool_Only_Score for every player from individual tool ratings, replacing the system's dependency on OOTP's OVR/POT ratings. The implementation is ordered: schema → core engine → config → calibration → downstream model migration → UI → final integration.

All code is Python. Tests use pytest with Hypothesis for property-based tests.

## Tasks

- [x] 1. Database schema changes
  - [x] 1.1 Add new columns to `ratings` table in `scripts/db.py`
    - Add `composite_score INTEGER`, `ceiling_score INTEGER`, `tool_only_score INTEGER`, `secondary_composite INTEGER` columns
    - Add migration logic in `_migrate_ratings()` following the existing pattern (check `existing` set, `ALTER TABLE` if missing)
    - _Requirements: 15.1, 15.4_

  - [x] 1.2 Add new columns to `ratings_history` table in `scripts/db.py`
    - Add `composite_score INTEGER`, `ceiling_score INTEGER` columns to `ratings_history` in both `SCHEMA` and a new `_migrate_ratings_history()` migration function
    - _Requirements: 15.2_

  - [x] 1.3 Update `init_schema()` to call both migration functions
    - Ensure `init_schema()` calls `_migrate_ratings_history()` alongside `_migrate_ratings()`
    - _Requirements: 15.4_

- [x] 2. Core Evaluation Engine — pure computation functions
  - [x] 2.1 Create `scripts/evaluation_engine.py` with module structure and imports
    - Create the new module file with docstring, imports (`sqlite3`, `pathlib.Path`, `json`, `math`), and type annotations
    - Define the `EvaluationResult` dataclass
    - Implement `load_tool_weights(league_dir: Path) -> dict` and `validate_tool_weights(weights: dict) -> bool`
    - Embed the default weights dict as a module-level constant `DEFAULT_TOOL_WEIGHTS`
    - _Requirements: 5.1, 5.2, 5.4, 17.1, 17.4_

  - [x] 2.2 Write property test for invalid config fallback (Property 16)
    - **Property 16: Invalid config falls back to defaults**
    - **Validates: Requirements 5.4**

  - [x] 2.3 Implement `compute_composite_hitter()` pure function
    - Weighted sum of normalized tool ratings (contact, gap, power, eye, avoid_k, speed, steal, stl_rt) plus defensive component
    - L/R split weighted average (60% vs-RHP, 40% vs-LHP) with fallback to overall rating
    - Defensive component using `DEFENSIVE_WEIGHTS` from `fv_model.py`, scaled by positional defense weight
    - Clamp output to [20, 80], round to nearest integer
    - Handle missing tools by re-normalizing weights over available tools
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 17.1, 17.3_

  - [x] 2.4 Write property tests for hitter composite (Properties 1, 2, 3)
    - **Property 1: Hitter Composite Score is a valid weighted sum in [20, 80]**
    - **Property 2: L/R split weighted average**
    - **Property 3: Defensive component uses positional weights**
    - **Validates: Requirements 1.1, 1.2, 1.3, 1.4**

  - [x] 2.5 Implement `compute_composite_pitcher()` pure function
    - Weighted sum of stuff, movement, control using role-specific weights
    - Arsenal depth bonus: +1 per pitch rated 45+ beyond the third (capped at +3), top-pitch quality bonus (+1 if best ≥ 65, +2 if ≥ 70)
    - Stamina penalty for SP: `min(5, (40 - stamina) × 0.15)` when stamina < 40
    - Platoon balance penalty: -2 to -3 when weak side < 35 and gap ≥ 15
    - Role determination via existing `assign_bucket()` from `player_utils.py`
    - Clamp output to [20, 80], round to nearest integer
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 17.1, 17.3_

  - [x] 2.6 Write property tests for pitcher composite (Properties 4, 5, 6)
    - **Property 4: Pitcher Composite Score is a valid weighted sum in [20, 80]**
    - **Property 5: Arsenal bonus correctly computed**
    - **Property 6: Stamina penalty for starting pitchers**
    - **Validates: Requirements 2.1, 2.2, 2.3**

  - [x] 2.7 Implement `compute_tool_only_score()` pure function
    - Delegates to `compute_composite_hitter()` or `compute_composite_pitcher()` based on player type
    - Always returns the pre-stat-blend score
    - _Requirements: 3.6, 6.7, 17.1_

  - [x] 2.8 Implement `compute_composite_mlb()` pure function for stat blending
    - Stat normalization: `stat_2080 = 20 + (stat_plus / 200) × 60`, clamped [20, 80]
    - Blend formula: `tool_only × (1 - blend_weight) + stat_signal × blend_weight`
    - `blend_weight = min(0.5, qualifying_seasons × 0.15)`
    - Recency weighting: most recent season 3×, second 2×, third 1×
    - Young player blend: reduce blend_weight for players under peak age with tools > stats
    - No-stat fallback: return tool_only_score when no qualifying seasons
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 17.1_

  - [x] 2.9 Write property tests for MLB stat blending (Properties 7, 8, 9, 10)
    - **Property 7: Stat blending formula for MLB players**
    - **Property 8: No-stat fallback produces tool-only score**
    - **Property 9: Stat normalization to 20-80 scale**
    - **Property 10: Tool_Only_Score always retained for MLB players**
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.6**

  - [x] 2.10 Implement `compute_ceiling()` pure function
    - Same positional weight formula applied to potential tool ratings
    - Floor constraint: `ceiling = max(ceiling, composite)`
    - Work ethic modifier: High/VH → +1, Low → -1
    - Accuracy variance: `Acc=L` → -2 penalty
    - Clamp to [20, 80]
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 17.1_

  - [x] 2.11 Write property tests for ceiling score (Properties 11, 12, 13, 14)
    - **Property 11: Ceiling Score uses potential tool ratings**
    - **Property 12: Ceiling Score is never below Composite Score**
    - **Property 13: Scouting accuracy penalty on Ceiling Score**
    - **Property 14: Work ethic modifier on Ceiling Score**
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5**

- [x] 3. Checkpoint — Core computation functions
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Two-way player handling and tool profile analysis
  - [x] 4.1 Implement `is_two_way_player()` pure function
    - Pitcher position AND hitting tools non-trivial: `norm(cntct) >= 35` AND `norm(pow) >= 30`
    - OR: appears in both batting_stats (AB ≥ 130) and pitching_stats (IP ≥ 40) in same season
    - _Requirements: 18.1, 17.1_

  - [x] 4.2 Implement `compute_two_way_scores()` and `compute_combined_value()` pure functions
    - Compute separate hitter and pitcher Composite_Scores
    - Primary = higher score, secondary = lower score
    - Combined value: `primary + min(8, max(0, (secondary - 35) × 0.3))`
    - Ceiling computed for each role separately, primary ceiling = higher
    - _Requirements: 18.2, 18.3, 18.4, 18.5, 18.6, 17.1_

  - [x] 4.3 Write property tests for two-way players (Properties 28, 29)
    - **Property 28: Two-way player dual scoring**
    - **Property 29: Two-way combined value formula**
    - **Validates: Requirements 18.2, 18.3, 18.4, 18.5**

  - [x] 4.4 Implement divergence detection: `detect_divergence()` pure function
    - Compare Tool_Only_Score vs OVR: hidden_gem if diff ≥ 5, landmine if diff ≤ -5, agreement otherwise
    - Return None when OVR is None
    - Same logic for Ceiling_Score vs POT
    - _Requirements: 6.1, 6.2, 6.3, 6.6, 6.7, 17.1_

  - [x] 4.5 Write property tests for divergence detection (Properties 19, 20)
    - **Property 19: Divergence classification is correct**
    - **Property 20: Divergence is None when OVR/POT unavailable**
    - **Validates: Requirements 6.1, 6.2, 6.3, 6.6**

  - [x] 4.6 Implement tool profile analysis: `classify_archetype()`, `identify_carrying_tools()`, `identify_red_flag_tools()` pure functions
    - Archetype classification per the design table (contact-first, power-over-hit, balanced, elite defender, speed-first, stuff-over-command, command-over-stuff, pitch-mix specialist)
    - Carrying tools: rated 15+ above Composite_Score
    - Red-flag tools: rated 15+ below Composite_Score
    - _Requirements: 7.1, 7.2, 17.1_

  - [x] 4.7 Write property tests for tool profile analysis (Property 21)
    - **Property 21: Tool profile analysis is consistent with thresholds**
    - **Validates: Requirements 7.1, 7.2**

  - [x] 4.8 Write property tests for OVR/POT independence and partial scoring (Properties 24, 25)
    - **Property 24: Composite Score is independent of OVR/POT**
    - **Property 25: Partial score for incomplete tool ratings**
    - **Validates: Requirements 12.1, 12.2, 16.4**

  - [x] 4.9 Write property test for position-specific weights (Property 15)
    - **Property 15: Position-specific weights produce different scores**
    - **Validates: Requirements 5.3**

- [x] 5. Checkpoint — Two-way and analysis functions
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Tool weight derivation and calibration integration
  - [x] 6.1 Implement `derive_tool_weights()`, `normalize_coefficients()`, and `recombine_component_weights()` pure functions in `evaluation_engine.py`
    - `derive_tool_weights()`: accepts tool rating vectors and target stat values, runs OLS regression, returns coefficients or None if N < min_n or R² < 0.05
    - `normalize_coefficients()`: clamp negative coefficients to zero, normalize to sum to 1.0
    - `recombine_component_weights()`: scale hitting coefficients by offense share, baserunning (speed, steal, stl_rt) by baserunning share, defense by defense share; normalize final weights to 1.0
    - _Requirements: 5.5, 5.6, 5.7, 5.8, 5.9, 5.10, 13.8, 13.9, 17.1_

  - [x] 6.2 Write property tests for weight derivation (Properties 17, 18, 26, 27, 30)
    - **Property 17: Regression-derived weights are non-negative and sum to 1.0**
    - **Property 18: Regression fallback on insufficient data**
    - **Property 26: Component regression produces domain-appropriate weights**
    - **Property 27: Recombination preserves weight sum invariant**
    - **Property 30: Per-league regression independence**
    - **Validates: Requirements 5.5, 5.7, 5.8, 13.4, 13.5, 13.8, 13.9**

  - [x] 6.3 Add Step 0 to `scripts/calibrate.py`: component-level tool weight regression
    - New function `_calibrate_tool_weights(conn, game_year, role_map)` that:
      - Runs hitting regression per hitter bucket: `OPS+ ~ contact + gap + power + eye + avoid_k + speed` (AB ≥ 300, split_id=1)
      - Runs baserunning regression (pooled): `SB_rate ~ speed + steal + stl_rt` (AB ≥ 300, SB+CS ≥ 5)
      - Runs fielding regression per bucket: `ZR ~ defensive_composite` (IP ≥ 400)
      - Runs pitcher regression per role: `FIP ~ stuff + movement + control + arsenal` (SP: IP ≥ 40, RP: IP ≥ 20, GS ≤ 3)
      - Calls `normalize_coefficients()` and `recombine_component_weights()` from evaluation_engine
      - Writes results to `data/<league>/config/tool_weights.json`
    - Integrate into `calibrate()` function before existing Step 1
    - _Requirements: 5.5, 5.6, 5.7, 5.8, 5.9, 5.10, 13.5, 13.6, 13.7, 13.8, 13.9_

  - [x] 6.4 Add COMPOSITE_TO_WAR regression step to `scripts/calibrate.py`
    - New function `_calibrate_composite_to_war(conn, game_year, role_map)` using same methodology as `_calibrate_ovr_to_war()` but reading `composite_score` column
    - Store results in `model_weights.json` under `COMPOSITE_TO_WAR` key
    - Derive `FV_TO_PEAK_WAR_COMPOSITE` tables from COMPOSITE_TO_WAR
    - Skip when composite_score data is insufficient (first run)
    - _Requirements: 13.1, 13.2, 13.3, 13.4_

- [x] 7. Batch pipeline entry point
  - [x] 7.1 Implement `run()` function in `scripts/evaluation_engine.py`
    - Accept optional `league_dir` and `conn` parameters (dependency injection)
    - Load tool weights via `load_tool_weights()`
    - Query all players from `ratings` + `players` tables
    - For each player: determine bucket, compute composite/ceiling/tool_only scores, detect two-way, compute divergence, classify archetype, identify carrying/red-flag tools
    - For MLB players: load qualifying stat seasons, compute stat signal, blend
    - Batch write `composite_score`, `ceiling_score`, `tool_only_score`, `secondary_composite` to `ratings` table
    - Write `composite_score`, `ceiling_score` to `ratings_history` for current snapshot
    - Handle errors: skip players with no tool ratings, flag partial confidence, rollback on failure
    - Performance target: < 10 seconds for 2000+ players
    - _Requirements: 16.1, 16.2, 16.3, 16.4, 17.2, 17.6_

  - [x] 7.2 Write integration tests for the batch pipeline
    - Seed in-memory DB with player/ratings data → run evaluation engine → verify scores in ratings table
    - Verify two-way player pipeline: composite_score = higher role, secondary_composite = lower role
    - Verify performance: 2000+ players completes under 10 seconds
    - _Requirements: 16.1, 16.2, 16.3, 18.2, 18.3_

- [x] 8. Checkpoint — Engine and calibration complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. FV model migration
  - [x] 9.1 Update `scripts/fv_calc.py` to use composite scores
    - Import and call `evaluation_engine.run()` before the FV/surplus loop
    - In the player loop, set `p["Ovr"] = p.get("composite_score") or p.get("Ovr") or 0` and `p["Pot"] = p.get("ceiling_score") or p.get("Pot") or 0`
    - For two-way players, use `combined_value` as the effective Composite_Score
    - Add `use_custom_scores` config flag in `league_settings.json` (default: `true`) to allow reverting to OVR/POT
    - No changes to `fv_model.py` itself — migration happens at the call site
    - _Requirements: 9.1, 9.2, 9.4, 11.5_

  - [x] 9.2 Write property test for FV backward compatibility (Property 23)
    - **Property 23: FV backward compatibility**
    - **Validates: Requirements 9.3**

- [x] 10. WAR model migration
  - [x] 10.1 Update `scripts/war_model.py` to use composite scores
    - Rename `peak_war_from_ovr()` to `peak_war_from_score()` with backward-compatible alias
    - Read from `COMPOSITE_TO_WAR` tables when available in `OVR_TO_WAR_CALIBRATED`, fall back to `OVR_TO_WAR`
    - Update `scripts/constants.py` to load `COMPOSITE_TO_WAR` from `model_weights.json` when present
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

- [x] 11. Surplus model migration
  - [x] 11.1 Update `scripts/prospect_value.py` to use composite scores
    - `_certainty_mult()` accepts composite_score/ceiling_score (same formula, different inputs)
    - `_scarcity_mult()` uses ceiling_score instead of pot for scarcity lookup
    - _Requirements: 11.1, 11.2_

  - [x] 11.2 Update `scripts/contract_value.py` to use composite scores
    - Development ramp projects composite_score growth toward ceiling_score (was OVR toward POT)
    - `peak_war_from_ovr()` calls pass composite_score instead of OVR
    - _Requirements: 11.3_

  - [x] 11.3 Update `scripts/arb_model.py` to use composite scores
    - `arb_salary(ovr, ...)` accepts composite_score as the first argument (same exponential formula)
    - _Requirements: 11.4_

- [x] 12. Refresh pipeline integration
  - [x] 12.1 Update `scripts/refresh.py` to include evaluation engine in the pipeline
    - Execution order: `refresh.py` → `calibrate.py` pass 1 (tool weights + OVR_TO_WAR) → `evaluation_engine.py` → `calibrate.py` pass 2 (COMPOSITE_TO_WAR, skipped on first run) → `fv_calc.py`
    - Ensure `init_schema()` is called before evaluation engine runs (to create new columns)
    - _Requirements: 16.1, 16.3_

  - [x] 12.2 Write integration test for end-to-end calibration pipeline
    - Seed DB with full historical data → run calibrate pass 1 → run evaluation engine → run calibrate pass 2 → verify all config files consistent
    - Verify component regression targets: hitting→OPS+, baserunning→SB metrics, fielding→ZR, pitching→FIP
    - Verify per-league weight independence with two different league DBs
    - _Requirements: 13.1, 13.5, 13.7_

- [x] 13. Checkpoint — Backend complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 14. Development tracking
  - [x] 14.1 Implement snapshot delta computation and flagging
    - Add helper function to compute tool-level deltas between two `ratings_history` snapshots
    - Flag "riser" when Composite_Score increases by 3+ points between snapshots
    - Flag "reduced ceiling" when Ceiling_Score decreases by 3+ points
    - Surface deltas in the player data dict returned by `get_player()` in `web/player_queries.py`
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

  - [x] 14.2 Write property test for snapshot deltas (Property 22)
    - **Property 22: Snapshot delta flagging**
    - **Validates: Requirements 8.2, 8.3, 8.4**

- [x] 15. Web UI updates
  - [x] 15.1 Update `web/player_queries.py` to include composite scores in player data
    - Return `composite_score`, `ceiling_score`, `tool_only_score`, `secondary_composite` in the player dict from `get_player()`
    - Include divergence data (type, magnitude) when OVR/POT available
    - Include archetype, carrying tools, red-flag tools
    - Include development tracking deltas and riser/reduced-ceiling flags
    - For two-way players, include both role scores and combined value
    - _Requirements: 14.1, 14.5, 7.3, 8.2, 18.7_

  - [x] 15.2 Update `web/queries.py` to use composite scores
    - `get_top_prospects()` and `get_all_prospects()`: use composite_score for display
    - `search_players()`: return composite_score instead of ovr
    - `get_player_card()`: include composite_score and divergence
    - _Requirements: 14.3, 14.4_

  - [x] 15.3 Update `web/team_queries.py` to use composite scores
    - `get_roster()`, `get_roster_hitters()`, `get_roster_pitchers()`: display composite_score in "Ovr" column
    - `get_farm()`: use composite_score for prospect display
    - _Requirements: 14.2, 14.3_

  - [x] 15.4 Update `web/templates/player.html` for composite score display
    - Display Composite_Score and Ceiling_Score in header where OVR/POT currently appear
    - When OVR/POT available, show alongside with divergence color coding (green=hidden gem, red=landmine, neutral=agreement)
    - Add tool profile section: archetype label, carrying tools in green, red-flag tools in red
    - Add development tracking section: tool-level deltas between snapshots
    - For two-way players: show both role scores with labels and combined value
    - Use same grade bar color-coding tiers for composite scores
    - _Requirements: 14.1, 14.5, 14.6, 7.3, 8.2, 18.7_

  - [x] 15.5 Update roster and prospect templates for composite scores
    - `web/templates/team.html`: update roster tables to show "Comp" column
    - `web/templates/league.html`: update prospect rankings with composite scores, add riser/reduced-ceiling badges
    - _Requirements: 14.2, 14.3, 8.3, 8.4_

  - [x] 15.6 Write integration tests for web query updates
    - Seed DB with composite scores → call `get_player()`, `get_roster()`, `search_players()` → verify composite_score appears in results
    - _Requirements: 14.1, 14.2, 14.3, 14.4_

- [x] 16. Final checkpoint — All tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document (30 properties total)
- Unit tests validate specific examples and edge cases
- The evaluation engine module follows SOLID principles: all computation functions are pure, DB access is confined to `run()`, dependency injection enables testing with in-memory SQLite
- No changes to `fv_model.py` — the FV migration happens at the call site in `fv_calc.py`
- Existing OVR/POT columns are never dropped — new columns coexist for backward compatibility
- All downstream consumers fall back to OVR/POT when composite_score is NULL
