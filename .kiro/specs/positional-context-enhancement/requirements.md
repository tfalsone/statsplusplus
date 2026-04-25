# Requirements Document: Positional Context Enhancement

## Introduction

The evaluation engine currently measures raw tool quality without positional context. A 51 offensive grade means "average hitter" regardless of position — but a SS who hits at that level is one of the best players in baseball, while a 1B at the same level is merely adequate. This feature adds positional context through four enhancements: a carrying tool bonus for elite offensive tools at positions where they are scarce and high-impact, positional context in divergence detection, defense as a positional access mechanism in the FV calculation, and ceiling enhancement for carrying tools. The enhancements are grounded in empirical WAR premium data from `docs/positional_context_findings.md` and are additive to the existing evaluation engine — they do not change the base weighted average formulas.

## Glossary

- **Evaluation_Engine**: The `evaluation_engine.py` module that computes player evaluation scores from tool ratings. All computation functions are pure (no DB access, no side effects).
- **FV_Calculator**: The `fv_calc.py` / `fv_model.py` modules that compute Future Value grades for prospects and MLB players.
- **Carrying_Tool**: An individual offensive tool (contact, gap, power, eye) that grades 65 or higher at a position where that tool is scarce and produces a significant WAR premium. Defined per position in the Carrying_Tool_Config.
- **Carrying_Tool_Bonus**: An additive adjustment to the offensive grade and offensive ceiling for players who possess one or more Carrying_Tools. The bonus scales with tool grade rarity.
- **Carrying_Tool_Config**: A per-league configuration structure (stored in `tool_weights.json` or a dedicated config file) that defines which tool/position combinations qualify as carrying tools, their WAR premium factors, and scarcity multipliers.
- **Offensive_Grade**: The component score derived from hitting tools only (contact, gap, power, eye) on the 20-80 scouting scale, as defined in the evaluation-engine-reframe spec.
- **Offensive_Ceiling**: The projected peak offensive grade derived from potential tool ratings, as defined in the evaluation-engine-reframe spec.
- **Composite_Score**: The existing single-number evaluation on the 20-80 scale, derived from component scores using recombination weights.
- **Positional_Median**: The median offensive grade for MLB players at a given position within a league, computed from the league's own data.
- **Positional_Percentile**: A player's offensive grade expressed as a percentile rank relative to other players at the same position within the league.
- **Divergence_Report**: A structured analysis comparing the evaluation engine's tool-based assessment against OVR, enriched with positional context.
- **Positional_Access**: The concept that defense enables a player to hold a premium defensive position (SS, C, CF), which multiplies the value of adequate offense at that position.
- **Premium_Position**: A defensive position (SS, C, CF) where adequate offense combined with the ability to hold the position produces a significant WAR premium over non-premium positions.
- **Scarcity_Multiplier**: A scaling factor that accelerates the carrying tool bonus as tool grade increases, reflecting that higher grades are exponentially rarer. Derived from empirical grade distributions.
- **WAR_Premium_Factor**: A position-and-tool-specific coefficient derived from the empirical WAR premium data, representing how much additional WAR a 65+ grade in that tool produces at that position relative to the position average.

## Requirements

### Requirement 1: Carrying Tool Bonus Computation

**User Story:** As a front office analyst, I want the evaluation engine to apply an additive bonus to the offensive grade when a hitter possesses elite offensive tools that are scarce and high-impact at the player's position, so that the offensive grade reflects the outsized value of rare hitting ability at premium defensive positions.

#### Acceptance Criteria

1. WHEN a hitter has an offensive tool (contact, gap, power, or eye) grading 65 or higher AND that tool/position combination is defined as a carrying tool in the Carrying_Tool_Config, THE Evaluation_Engine SHALL compute a Carrying_Tool_Bonus for that tool.
2. THE Evaluation_Engine SHALL compute each individual tool bonus using the formula: `bonus = war_premium_factor × (tool_grade - 60) × scarcity_multiplier(tool_grade)`, where `war_premium_factor` and `scarcity_multiplier` are defined in the Carrying_Tool_Config.
3. WHEN a hitter has multiple qualifying carrying tools, THE Evaluation_Engine SHALL sum the individual tool bonuses to produce the total Carrying_Tool_Bonus.
4. THE Evaluation_Engine SHALL add the total Carrying_Tool_Bonus to the offensive grade after the base weighted average computation and before clamping to the 20-80 scale.
5. THE Evaluation_Engine SHALL NOT apply a Carrying_Tool_Bonus for speed tools at any position.
6. THE Evaluation_Engine SHALL NOT apply a Carrying_Tool_Bonus for defensive tools at any position.
7. THE Evaluation_Engine SHALL scale the Scarcity_Multiplier so that higher tool grades produce disproportionately larger bonuses, reflecting that an 80-grade tool is exponentially rarer than a 65-grade tool.
8. WHEN a tool grades below 65, THE Evaluation_Engine SHALL apply zero Carrying_Tool_Bonus for that tool regardless of position.
9. THE Evaluation_Engine SHALL include the Carrying_Tool_Bonus amount and the qualifying tools in the EvaluationResult so downstream consumers can see the bonus breakdown.

### Requirement 2: Carrying Tool Configuration

**User Story:** As a front office analyst managing multiple leagues, I want the carrying tool bonus parameters to be configurable per league and derived from empirical WAR premium data, so that the bonus reflects each league's actual positional scarcity patterns rather than hand-tuned values.

#### Acceptance Criteria

1. THE Carrying_Tool_Config SHALL define, for each position, which offensive tools qualify as carrying tools and their associated WAR_Premium_Factor.
2. THE Carrying_Tool_Config SHALL define the Scarcity_Multiplier schedule mapping tool grade thresholds to multiplier values.
3. THE Carrying_Tool_Config SHALL be stored in the per-league config directory (alongside `tool_weights.json`) so that each league can have independent carrying tool parameters.
4. WHEN no Carrying_Tool_Config exists for a league, THE Evaluation_Engine SHALL use a default configuration derived from the combined EMLB+VMLB WAR premium data in `docs/positional_context_findings.md`.
5. THE Evaluation_Engine SHALL validate the Carrying_Tool_Config on load, rejecting configurations where WAR_Premium_Factor values are negative or Scarcity_Multiplier values are non-positive.
6. THE Carrying_Tool_Config SHALL support the following position/tool combinations at minimum: SS (contact, power, eye), C (contact, power), CF (contact, power), 2B (power, contact), 3B (power, contact, eye, gap), COF (contact), 1B (contact).

### Requirement 3: Positional Context in Divergence Detection

**User Story:** As a front office analyst, I want divergence detection to compare a player's offensive grade against position-specific medians rather than raw composite vs OVR, so that a SS with a 51 offensive grade is recognized as an above-average SS hitter rather than flagged as a landmine.

#### Acceptance Criteria

1. WHEN a hitter's divergence is computed and Positional_Medians are available, THE Evaluation_Engine SHALL include the player's Positional_Percentile for offensive grade in the Divergence_Report.
2. THE Evaluation_Engine SHALL compute Positional_Medians from the league's own MLB player data, grouped by position bucket.
3. WHEN a hitter's offensive grade is above the 60th percentile for the position AND the player is classified as a "landmine" by the existing divergence logic, THE Evaluation_Engine SHALL add a "positional_context" annotation to the Divergence_Report indicating that the offensive grade is above the positional median.
4. WHEN a hitter's offensive grade is below the 25th percentile for the position AND the player is classified as a "hidden_gem" by the existing divergence logic, THE Evaluation_Engine SHALL add a "positional_context" annotation to the Divergence_Report indicating that the offensive grade is below the positional floor.
5. THE Evaluation_Engine SHALL NOT change the existing divergence classification thresholds (tool_only vs OVR ± 5). The positional context is additive annotation, not a replacement for the existing logic.
6. WHEN Positional_Medians are not available (insufficient data or missing league data), THE Evaluation_Engine SHALL skip positional context annotations and produce the existing Divergence_Report without modification.
7. THE Evaluation_Engine SHALL require a minimum sample size per position bucket before computing Positional_Medians, to avoid unreliable percentiles from small samples.

### Requirement 4: Positional Median Computation

**User Story:** As a front office analyst, I want positional offensive grade medians and percentiles computed from the league's own data, so that positional context reflects the actual talent distribution in each league rather than assumed baselines.

#### Acceptance Criteria

1. THE Evaluation_Engine SHALL compute Positional_Medians by grouping all MLB-level hitters by position bucket and computing the median offensive grade for each bucket.
2. THE Evaluation_Engine SHALL compute Positional_Percentiles as the percentile rank of a player's offensive grade within the player's position bucket.
3. THE Evaluation_Engine SHALL use only MLB-level players (level = MLB) when computing Positional_Medians, excluding minor leaguers.
4. WHEN a position bucket has fewer than 15 MLB players with offensive grades, THE Evaluation_Engine SHALL skip Positional_Median computation for that bucket and return None.
5. THE Evaluation_Engine SHALL recompute Positional_Medians on each evaluation run, using the current snapshot's offensive grades.
6. THE Evaluation_Engine SHALL store the computed Positional_Medians in the evaluation context so they are available to divergence detection and downstream consumers without recomputation.

### Requirement 5: Defense as Positional Access in FV

**User Story:** As a front office analyst, I want the FV calculation to treat defense as enabling positional access at premium positions rather than as a standalone composite bonus, so that a SS with average offense and elite defense receives FV credit for the positional value premium rather than a generic defensive bump.

#### Acceptance Criteria

1. WHEN a prospect plays a Premium_Position (SS, C, CF) AND the prospect's defensive value meets the positional access threshold (defensive_value >= 50), THE FV_Calculator SHALL apply a positional value premium to the FV grade.
2. THE FV_Calculator SHALL scale the positional value premium based on the combination of offensive grade and defensive value: higher offense at a premium position with adequate defense produces a larger premium than lower offense.
3. THE FV_Calculator SHALL NOT apply the positional value premium when the prospect's defensive value is below the positional access threshold, even if the prospect nominally plays a premium position.
4. THE FV_Calculator SHALL replace the existing generic defensive bonus in `calc_fv` with the positional access mechanism, so that defense contributes to FV through positional value rather than as a flat additive bonus.
5. THE FV_Calculator SHALL retain the existing defensive bonus logic for non-premium positions (2B, 3B, COF, 1B) where defense does not provide a significant positional value premium.
6. WHEN the prospect's offensive grade is not available (legacy data), THE FV_Calculator SHALL fall back to the existing defensive bonus logic using composite-based position ratings.
7. THE FV_Calculator SHALL derive the positional value premium magnitudes from the empirical WAR premium data: controlling for offense, elite defense at C adds approximately +1.10 WAR equivalent and at CF adds approximately +1.28 WAR equivalent.

### Requirement 6: Ceiling Enhancement for Carrying Tools

**User Story:** As a front office analyst, I want the ceiling calculation to apply the carrying tool bonus to potential tool ratings, so that a SS prospect with potential Contact=80 receives a ceiling that reflects the franchise-defining value of elite contact at shortstop rather than a diluted weighted average.

#### Acceptance Criteria

1. WHEN computing the offensive ceiling for a hitter, THE Evaluation_Engine SHALL apply the Carrying_Tool_Bonus to potential tool ratings that qualify (potential tool grade >= 65 at a carrying tool position/tool combination).
2. THE Evaluation_Engine SHALL use the same Carrying_Tool_Config and bonus formula for ceiling computation as for current offensive grade computation.
3. THE Evaluation_Engine SHALL add the ceiling Carrying_Tool_Bonus to the offensive ceiling after the base potential-weighted-average computation and before clamping.
4. THE Evaluation_Engine SHALL include the ceiling Carrying_Tool_Bonus breakdown in the EvaluationResult alongside the current-tool bonus breakdown.
5. WHEN the overall ceiling_score is computed (the single-number ceiling), THE Evaluation_Engine SHALL use the enhanced offensive ceiling (with carrying tool bonus) as the offensive component input, so the carrying tool bonus flows through to the final ceiling.
6. THE Evaluation_Engine SHALL NOT apply the ceiling Carrying_Tool_Bonus to defensive potential tools or speed potential tools.

### Requirement 7: Composite Score Passthrough

**User Story:** As a front office analyst, I want the composite score to reflect the carrying tool bonus through the offensive grade component, so that the single-number composite captures positional context without requiring a separate adjustment.

#### Acceptance Criteria

1. WHEN the offensive grade includes a Carrying_Tool_Bonus, THE Evaluation_Engine SHALL use the enhanced offensive grade (with bonus) as the offensive component input to `derive_composite_from_components`.
2. THE Evaluation_Engine SHALL NOT apply a separate carrying tool adjustment to the composite score — the bonus flows through the offensive grade component only.
3. THE Evaluation_Engine SHALL continue to derive the composite from components using the existing recombination weights, with the enhanced offensive grade as the offensive input.

### Requirement 8: Calibration Support for Carrying Tool Parameters

**User Story:** As a front office analyst, I want the calibration pipeline to derive carrying tool parameters from the league's WAR regression data, so that the bonus is empirically grounded in each league's actual positional scarcity and WAR premium patterns.

#### Acceptance Criteria

1. WHEN the calibration pipeline runs, THE Calibration_Engine SHALL compute per-position, per-tool WAR premiums for tools grading 65 or higher by comparing the mean WAR of players with 65+ grade in that tool against the position's overall mean WAR.
2. THE Calibration_Engine SHALL compute tool grade scarcity percentages (percentage of players at each position with 65+ grade in each tool) to inform the Scarcity_Multiplier.
3. THE Calibration_Engine SHALL write the derived Carrying_Tool_Config to the per-league config directory.
4. WHEN the calibration sample size for a position/tool combination is below 10 players with 65+ grade, THE Calibration_Engine SHALL exclude that combination from the Carrying_Tool_Config rather than producing unreliable estimates.
5. THE Calibration_Engine SHALL exclude speed from carrying tool calibration at all positions, consistent with the empirical finding that speed produces zero or negative WAR premium.

### Requirement 9: Web UI Positional Context Display

**User Story:** As a front office analyst, I want the web UI to display positional context information on player pages, so that I can see carrying tool bonuses, positional percentiles, and the positional access assessment at a glance.

#### Acceptance Criteria

1. WHEN a player has a non-zero Carrying_Tool_Bonus, THE Web_UI SHALL display the bonus amount and the qualifying tools on the player evaluation section.
2. WHEN positional percentile data is available, THE Web_UI SHALL display the player's offensive grade percentile relative to the position (e.g., "70th percentile for SS").
3. WHEN a divergence report includes positional context annotations, THE Web_UI SHALL display the annotation alongside the existing divergence flag.
4. THE Web_UI SHALL display the positional access assessment for prospects at premium positions, indicating whether the prospect meets the defensive threshold to hold the position.
5. WHEN carrying tool bonus or positional context data is not available for a player, THE Web_UI SHALL fall back to displaying the existing evaluation data without positional context.
