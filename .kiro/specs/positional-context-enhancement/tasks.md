# Implementation Plan: Positional Context Enhancement

## Overview

Adds positional context to the evaluation engine through four coordinated enhancements: carrying tool bonus, positional medians in divergence detection, defense as positional access in FV, and ceiling enhancement for carrying tools. Implementation proceeds bottom-up — config and pure functions first, then integration into the batch pipeline, then FV and calibration, then web UI.

All new computation functions are pure (no DB access). The batch pipeline (`_run_impl`) gains a two-pass structure: pass 1 computes all scores (with carrying tool bonus), then positional medians are aggregated, then pass 2 enriches divergence reports with positional context.

## Tasks

- [x] 1. Carrying tool config and bonus computation
  - [x] 1.1 Add `load_carrying_tool_config()` and `DEFAULT_CARRYING_TOOL_CONFIG` to `evaluation_engine.py`
    - Create the `DEFAULT_CARRYING_TOOL_CONFIG` dict matching the schema in the design (positions, carrying_tools with war_premium_factor, scarcity_schedule)
    - Implement `load_carrying_tool_config(league_dir: Path) -> dict` that reads `carrying_tool_config.json` from the league config directory
    - Fall back to `DEFAULT_CARRYING_TOOL_CONFIG` when the file is missing or malformed JSON (log warning for malformed)
    - Validate on load: raise `ValueError` for negative `war_premium_factor` or non-positive `scarcity_multiplier` values
    - Use default scarcity schedule when `scarcity_schedule` key is missing from config
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [x] 1.2 Implement `compute_carrying_tool_bonus()` and `apply_carrying_tool_bonus()` in `evaluation_engine.py`
    - `compute_carrying_tool_bonus(tools, position, config)` → `(total_bonus, breakdown)`
    - For each offensive tool (contact, gap, power, eye) grading 65+, check if tool/position is in config
    - Compute per-tool bonus: `war_premium_factor × (tool_grade - 60) × scarcity_multiplier(tool_grade)`
    - Scarcity multiplier uses linear interpolation between schedule breakpoints
    - Return zero bonus for speed, defensive tools, or grades below 65
    - Return `(0.0, [])` when position not in config or all tools are None
    - `apply_carrying_tool_bonus(base_offensive_grade, tools, position, config)` → `(enhanced_grade, bonus_amount, breakdown)`
    - Adds bonus to base grade, clamps to [20, 80]
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8_

  - [x] 1.3 Write property test for carrying tool bonus qualification (Property 1)
    - **Property 1: Carrying tool bonus qualification**
    - Test that bonus is non-zero iff tool is offensive (contact/gap/power/eye), grades 65+, and tool/position is in config
    - Zero bonus for speed, defensive tools, or grades below 65
    - **Validates: Requirements 1.1, 1.5, 1.6, 1.8**

  - [x] 1.4 Write property test for carrying tool bonus formula and summation (Property 2)
    - **Property 2: Carrying tool bonus formula and summation**
    - Verify enhanced grade = `clamp(base_raw + sum(individual_bonuses), 20, 80)`
    - Each individual bonus = `war_premium_factor × (tool_grade - 60) × scarcity_multiplier(tool_grade)`
    - **Validates: Requirements 1.2, 1.3, 1.4**

  - [x] 1.5 Write property test for carrying tool bonus monotonicity (Property 3)
    - **Property 3: Carrying tool bonus monotonicity**
    - For any position/tool combo and grades a < b where both in [65, 80], bonus(b) > bonus(a)
    - **Validates: Requirements 1.7**

  - [x] 1.6 Write property test for config validation (Property 4)
    - **Property 4: Carrying tool config validation**
    - Configs with negative `war_premium_factor` or non-positive `scarcity_multiplier` raise `ValueError`
    - **Validates: Requirements 2.5**

- [x] 2. Extend `EvaluationResult` and integrate carrying tool bonus into offensive grade
  - [x] 2.1 Add new fields to `EvaluationResult` dataclass
    - Add `carrying_tool_bonus: float = 0.0`
    - Add `carrying_tool_breakdown: list[dict] = field(default_factory=list)`
    - Add `ceiling_carrying_tool_bonus: float = 0.0`
    - Add `ceiling_carrying_tool_breakdown: list[dict] = field(default_factory=list)`
    - Add `positional_percentile: float | None = None`
    - Add `positional_median: int | None = None`
    - _Requirements: 1.9, 6.4_

  - [x] 2.2 Integrate carrying tool bonus into the hitter branch of `_run_impl`
    - Load carrying tool config at the top of `_run_impl` via `load_carrying_tool_config(league_dir)`
    - In the hitter branch, after computing `offensive_grade` via `compute_offensive_grade()`, call `apply_carrying_tool_bonus()` with the raw offensive grade, hitter tools, bucket, and config
    - Replace the clamped `offensive_grade` with the enhanced grade
    - Store `carrying_tool_bonus` and `carrying_tool_breakdown` for later use
    - Do the same for the two-way player hitter-side offensive grade
    - _Requirements: 1.1, 1.4, 1.9, 7.1_

  - [x] 2.3 Wire enhanced offensive grade into composite score computation
    - Ensure `derive_composite_from_components` receives the enhanced offensive grade (with carrying tool bonus) as the offensive input
    - Verify no separate carrying tool adjustment is applied to composite — bonus flows through offensive grade only
    - _Requirements: 7.1, 7.2, 7.3_

- [x] 3. Ceiling enhancement for carrying tools
  - [x] 3.1 Apply carrying tool bonus to offensive ceiling in `compute_component_ceilings`
    - After computing `raw_offensive` from potential tools, call `compute_carrying_tool_bonus()` with potential tools, position, and config
    - Add the ceiling bonus to the raw offensive ceiling before the age-weighted blend
    - Pass carrying tool config as a new optional parameter to `compute_component_ceilings`
    - Store `ceiling_carrying_tool_bonus` and `ceiling_carrying_tool_breakdown`
    - Do NOT apply ceiling bonus to defensive or baserunning ceilings
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

  - [x] 3.2 Wire ceiling carrying tool bonus into `_run_impl`
    - Pass carrying tool config and bucket to `compute_component_ceilings` calls in the hitter and two-way branches
    - Ensure the enhanced `offensive_ceiling` (with ceiling bonus) flows into `ceiling_score` computation
    - _Requirements: 6.5_

  - [x] 3.3 Write property test for ceiling carrying tool bonus consistency (Property 11)
    - **Property 11: Ceiling carrying tool bonus consistency**
    - Same tool grades produce same bonus whether used as current or potential tools
    - `compute_carrying_tool_bonus(tools, pos, config)` is deterministic and config-driven
    - **Validates: Requirements 6.1, 6.2, 6.3, 6.6**

- [x] 4. Checkpoint — Verify carrying tool bonus end-to-end
  - Ensure all tests pass, ask the user if questions arise.
  - Verify that a hitter with 65+ offensive tools at a carrying-tool position gets a non-zero bonus in offensive grade and ceiling
  - Verify that pitchers and hitters at non-carrying-tool positions are unaffected

- [x] 5. Positional median computation and divergence enrichment
  - [x] 5.1 Implement `compute_positional_medians()` in `evaluation_engine.py`
    - Takes `offensive_grades: dict[str, list[int]]` (position bucket → list of MLB offensive grades)
    - Returns dict mapping position bucket to `{"median": int, "p25": int, "p75": int, "count": int}`
    - Omit buckets with fewer than `min_sample_size` (default 15) players
    - Use `statistics.median` for median computation
    - _Requirements: 4.1, 4.4, 4.5_

  - [x] 5.2 Implement `compute_positional_percentile()` in `evaluation_engine.py`
    - Takes offensive grade, position, medians dict, and raw grade lists
    - Returns percentile as float in [0, 100], or None if position data unavailable
    - Percentile = percentage of grades in the position bucket that are ≤ the target grade
    - _Requirements: 4.2_

  - [x] 5.3 Extend `detect_divergence()` with optional `positional_context` parameter
    - Add `positional_context: dict | None = None` parameter with keys: `percentile`, `position`, `median`
    - When provided and divergence type is "landmine" with percentile > 60th: add `"positional_context"` annotation
    - When provided and divergence type is "hidden_gem" with percentile < 25th: add `"positional_context"` annotation
    - Do NOT change existing ±5 threshold logic — positional context is additive annotation only
    - When positional_context is None, produce existing result format unchanged
    - _Requirements: 3.1, 3.3, 3.4, 3.5, 3.6_

  - [x] 5.4 Write property test for positional median computation (Property 5)
    - **Property 5: Positional median computation with minimum sample enforcement**
    - Correct median for buckets with ≥ min_sample_size entries, omit buckets below threshold
    - **Validates: Requirements 3.7, 4.1, 4.4**

  - [x] 5.5 Write property test for positional percentile computation (Property 6)
    - **Property 6: Positional percentile computation**
    - Correct percentile rank (% of grades ≤ target) for any grade list and target
    - **Validates: Requirements 4.2**

  - [x] 5.6 Write property test for divergence positional context annotations (Property 7)
    - **Property 7: Divergence positional context annotations**
    - Landmine + percentile > 60 → annotation present; hidden_gem + percentile < 25 → annotation present; otherwise no annotation
    - **Validates: Requirements 3.1, 3.3, 3.4**

  - [x] 5.7 Write property test for divergence classification thresholds preserved (Property 8)
    - **Property 8: Divergence classification thresholds preserved**
    - Classification determined solely by ±5 threshold regardless of positional context
    - **Validates: Requirements 3.5**

- [x] 6. Integrate positional medians into `_run_impl` (two-pass approach)
  - [x] 6.1 Restructure `_run_impl` into two passes
    - **Pass 1**: Existing loop computes all scores (offensive grade with carrying tool bonus, composite, ceiling). Collect MLB hitter offensive grades by position bucket into a dict.
    - **Median computation**: After pass 1, call `compute_positional_medians()` on the collected MLB grades.
    - **Pass 2**: For each hitter with divergence, compute `compute_positional_percentile()` and re-call `detect_divergence()` with positional context. Update the divergence result.
    - Store `positional_percentile` and `positional_median` in the ratings update tuples
    - Use only MLB-level players (level == 1) for median computation
    - _Requirements: 3.1, 3.2, 3.6, 3.7, 4.1, 4.3, 4.5, 4.6_

  - [x] 6.2 Add `positional_percentile` and `positional_median` columns to the ratings table
    - Add nullable float column `positional_percentile` and nullable int column `positional_median` to the `UPDATE ratings` statement in `_run_impl`
    - Handle the case where columns don't exist yet (ALTER TABLE or migration in `db.py`)
    - _Requirements: 4.6_

- [x] 7. Checkpoint — Verify positional medians and divergence enrichment
  - Ensure all tests pass, ask the user if questions arise.
  - Verify that MLB hitters get positional percentiles and medians populated
  - Verify that divergence reports include positional context annotations where applicable

- [x] 8. Defense as positional access in FV
  - [x] 8.1 Implement `positional_access_premium()` in `fv_model.py`
    - Add `POSITIONAL_ACCESS` dict with SS, C, CF parameters (access_threshold, base_premium, offense_scale)
    - `positional_access_premium(bucket, offensive_grade, defensive_value, access_threshold=50)` → float
    - Returns positive premium for premium positions (SS, C, CF) when `defensive_value >= access_threshold`
    - Premium formula: `base_premium + (offensive_grade - 40) × offense_scale`
    - Returns 0 for non-premium positions (2B, 3B, COF, 1B)
    - _Requirements: 5.1, 5.2, 5.3, 5.5_

  - [x] 8.2 Replace defensive bonus in `calc_fv()` with positional access mechanism
    - For premium positions (SS, C, CF): replace the existing `comp >= 60` defensive bonus block with a call to `positional_access_premium()`
    - Pass the player's `offensive_grade` (from `_offensive_grade` or `EvaluationResult`) and `defensive_value` to the premium function
    - Retain existing defensive bonus logic for non-premium positions (2B, 3B, COF, 1B)
    - When offensive_grade is not available (None), fall back to existing defensive bonus logic
    - Cap the premium so `fv` does not exceed `pot`
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [x] 8.3 Wire offensive grade into `calc_fv()` player dict
    - Ensure the player dict passed to `calc_fv()` includes `_offensive_grade` from the evaluation engine results
    - Update `fv_calc.py` to pass the offensive grade through when available
    - _Requirements: 5.1, 5.6_

  - [x] 8.4 Write property test for positional access premium (Property 9)
    - **Property 9: Positional access premium at premium positions**
    - Positive premium iff premium position AND defensive_value >= threshold
    - Premium monotonically non-decreasing with offensive grade when defense meets threshold
    - **Validates: Requirements 5.1, 5.2, 5.3**

  - [x] 8.5 Write property test for non-premium position unchanged (Property 10)
    - **Property 10: Non-premium position defensive bonus unchanged**
    - `positional_access_premium` returns 0 for non-premium positions
    - Existing defensive bonus logic produces same result for non-premium positions
    - **Validates: Requirements 5.5**

- [x] 9. Checkpoint — Verify FV positional access
  - Ensure all tests pass, ask the user if questions arise.
  - Verify SS/C/CF prospects with adequate defense get positional premium instead of generic defensive bonus
  - Verify non-premium positions retain existing defensive bonus behavior

- [x] 10. Calibration extension for carrying tool parameters
  - [x] 10.1 Implement `_calibrate_carrying_tools()` in `calibrate.py`
    - Query WAR data grouped by position and tool grade
    - For each position/tool: compute mean WAR for players with 65+ grade vs position mean WAR
    - Compute scarcity percentage (% of players at position with 65+ grade in each tool)
    - Exclude speed at all positions
    - Exclude combinations with fewer than 10 qualifying players
    - Write derived `carrying_tool_config.json` to the league config directory
    - Return None if insufficient data overall
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [x] 10.2 Wire `_calibrate_carrying_tools()` into the `calibrate()` main function
    - Call `_calibrate_carrying_tools(conn, game_year, role_map)` after existing calibration steps
    - Write the resulting config to `data/<league>/config/carrying_tool_config.json`
    - Log the calibration results (positions/tools included, sample sizes)
    - _Requirements: 8.3_

- [x] 11. Web UI positional context display
  - [x] 11.1 Extend `_build_evaluation_data()` in `web/player_queries.py` to include carrying tool bonus and positional context
    - Add `carrying_tool_bonus`, `carrying_tool_breakdown`, `positional_percentile`, `positional_median` to the evaluation data dict
    - Compute carrying tool bonus on-the-fly from stored offensive grade, player position, and carrying tool config (or read from new rating columns if added)
    - _Requirements: 9.1, 9.2, 9.5_

  - [x] 11.2 Update `web/templates/player.html` to display positional context
    - Show carrying tool bonus amount and qualifying tools in the evaluation section when non-zero
    - Show positional percentile (e.g., "70th percentile for SS") when available
    - Show positional context annotations alongside divergence flags when present
    - Show positional access assessment for prospects at premium positions
    - Fall back to existing display when data is not available
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

- [x] 12. Validation against findings test cases
  - [x] 12.1 Write unit test for the Hudson case (SS, offensive_grade=51, defensive=63)
    - Jeff Hudson (SS, off=51, def=63): verify positional percentile is above 60th for SS
    - Verify not flagged as landmine with positional context annotation
    - Verify carrying tool bonus is zero (no tools at 65+)
    - _Requirements: 3.3, Finding 6 from positional_context_findings.md_

  - [x] 12.2 Write unit test for the Read case (SS prospect, potential contact=80)
    - Joe Read (SS prospect, pot_contact=80): verify ceiling carrying tool bonus is non-zero and significant
    - Verify the ceiling reflects the franchise-defining value of elite contact at SS
    - Verify the bonus uses the SS contact war_premium_factor from config
    - _Requirements: 6.1, Finding 7 from positional_context_findings.md_

  - [x] 12.3 Write unit test for default config structure
    - Verify `DEFAULT_CARRYING_TOOL_CONFIG` has all required position/tool combinations from Req 2.6
    - Verify SS has contact, power, eye; C has contact, power; CF has contact, power; etc.
    - _Requirements: 2.6_

  - [x] 12.4 Write unit test for composite passthrough
    - Verify enhanced offensive grade (with carrying tool bonus) flows through `derive_composite_from_components` correctly
    - Verify no separate carrying tool adjustment is applied to composite
    - _Requirements: 7.1, 7.2, 7.3_

  - [x] 12.5 Write integration test for full batch pipeline with carrying tools
    - Run `_run_impl()` with mock data including hitters at carrying-tool positions with 65+ tools
    - Verify carrying tool bonuses are computed and stored in ratings
    - Verify positional medians are computed from MLB hitters
    - Verify divergence reports include positional context
    - _Requirements: 1.9, 3.1, 4.5, 4.6_

- [x] 13. Final checkpoint — Full regression and validation
  - Ensure all tests pass, ask the user if questions arise.
  - Verify backward compatibility: when no `carrying_tool_config.json` exists, behavior is identical to pre-feature (default config applies, but with zero-bonus positions unchanged)
  - Verify the Hudson and Read test cases pass
  - Verify FV positional access produces expected premiums for SS/C/CF prospects

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP, but are strongly recommended — the property tests catch edge cases that unit tests miss
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation at natural break points
- The two-pass restructuring of `_run_impl` (task 6.1) is the most structurally complex change — take care to preserve existing behavior for pitchers and non-carrying-tool positions
- Property tests use Hypothesis (already configured in the project via `.hypothesis/` directory)
- The carrying tool bonus is the core feature — tasks 1-2 should be implemented first and validated before proceeding
- The FV positional access (task 8) replaces the existing defensive bonus for premium positions only — non-premium positions are unchanged
