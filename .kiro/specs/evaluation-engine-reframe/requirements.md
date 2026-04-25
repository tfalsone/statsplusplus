# Requirements Document: Evaluation Engine Reframe

## Introduction

The evaluation engine currently produces a single `composite_score` as a replacement for OVR. After extensive testing, this approach has diminishing returns — OVR has access to internal game engine information that tool-based analysis cannot replicate. This reframe shifts the engine's purpose from "produce a better OVR" to "provide component-level analysis for divergence detection, profile understanding, and development tracking." The composite score is retained as a convenience metric and fallback, but component scores become the primary outputs.

## Glossary

- **Evaluation_Engine**: The `evaluation_engine.py` module that computes player evaluation scores from tool ratings. All computation functions are pure (no DB access, no side effects).
- **Component_Score**: An individual evaluation score covering one dimension of player value (offensive, baserunning, defensive, or durability). Produced on the 20-80 scouting scale.
- **Offensive_Grade**: A Component_Score derived from hitting tools only (contact, gap, power, eye) with the piecewise tool transform applied. Excludes speed, defense, and baserunning contributions.
- **Baserunning_Value**: A Component_Score derived from speed, steal, and steal rating tools.
- **Defensive_Value**: A Component_Score derived from positional defensive tools using position-specific weights (e.g., IFR/IFE/IFA/TDP for SS, OFR/OFE/OFA for CF).
- **Durability_Score**: A Component_Score for pitchers derived from stamina, representing workload capacity. Not applicable to position players.
- **Composite_Score**: The existing single-number evaluation on the 20-80 scale. Retained as a convenience metric and fallback, but no longer the primary output.
- **Divergence_Report**: A structured analysis comparing the Evaluation_Engine's tool-based assessment against OVR (and ceiling against POT) to identify hidden gems and landmines.
- **Tool_Profile**: A structured breakdown of a player including archetype classification, carrying tools, and red flag tools.
- **Ceiling_Projection**: A projected peak ability score derived from potential tool ratings, age, and development factors, independent of POT when POT is unavailable.
- **Snapshot_Delta**: The difference in tool ratings and component scores between two rating snapshots, used for development tracking.
- **FV_Calculator**: The `fv_calc.py` module that computes Future Value grades and surplus values for prospects and MLB players.
- **Web_UI**: The web application layer (`web/`) that displays player evaluation data.
- **Tool_Transform**: The existing piecewise non-linear transformation applied to core tools (below 40 penalized 1.5×, 40-60 linear, above 60 rewarded 1.3×).
- **EvaluationResult**: The dataclass returned by the Evaluation_Engine for each player, containing all scores and profile data.

## Requirements

### Requirement 1: Component Score Computation for Hitters

**User Story:** As a front office analyst, I want the evaluation engine to produce separate offensive, baserunning, and defensive component scores for hitters, so that I can understand WHY a player is good or bad rather than relying on a single composite number.

#### Acceptance Criteria

1. WHEN a hitter is evaluated, THE Evaluation_Engine SHALL compute an Offensive_Grade from contact, gap, power, and eye tools using the existing Tool_Transform and calibrated tool weights.
2. WHEN a hitter is evaluated, THE Evaluation_Engine SHALL compute a Baserunning_Value from speed, steal, and steal rating tools using calibrated tool weights.
3. WHEN a hitter is evaluated, THE Evaluation_Engine SHALL compute a Defensive_Value from positional defensive tools using the existing position-specific defensive weights.
4. THE Evaluation_Engine SHALL produce each Component_Score as an integer on the 20-80 scouting scale.
5. WHEN one or more tools within a component are missing (None), THE Evaluation_Engine SHALL re-normalize weights over available tools within that component and still produce a score.
6. WHEN all tools for a component are missing, THE Evaluation_Engine SHALL return None for that Component_Score rather than a default value.
7. THE EvaluationResult dataclass SHALL include fields for offensive_grade, baserunning_value, and defensive_value alongside the existing composite_score.

### Requirement 2: Component Score Computation for Pitchers

**User Story:** As a front office analyst, I want the evaluation engine to produce separate pitching and durability component scores for pitchers, so that I can distinguish between a pitcher's stuff quality and workload capacity.

#### Acceptance Criteria

1. WHEN a pitcher is evaluated, THE Evaluation_Engine SHALL compute a pitching composite from stuff, movement, and control tools using the existing Tool_Transform, role-specific weights, and arsenal quality bonus.
2. WHEN a starting pitcher is evaluated, THE Evaluation_Engine SHALL compute a Durability_Score from stamina on the 20-80 scale.
3. WHEN a relief pitcher is evaluated, THE Evaluation_Engine SHALL set Durability_Score to None since stamina is not a meaningful differentiator for relievers.
4. THE EvaluationResult dataclass SHALL include a durability_score field for pitchers.
5. THE Evaluation_Engine SHALL retain the existing SP innings-volume adjustment and platoon balance penalty within the pitching composite component.

### Requirement 3: Composite Score Retention as Secondary Output

**User Story:** As a front office analyst, I want the composite score retained as a convenience metric, so that I have a single-number fallback for quick comparisons and for leagues without component-aware downstream consumers.

#### Acceptance Criteria

1. THE Evaluation_Engine SHALL continue to compute composite_score using the existing weighted combination of offensive, baserunning, and defensive contributions.
2. THE Evaluation_Engine SHALL continue to compute composite_score on the 20-80 scouting scale with the same clamping and rounding behavior.
3. WHEN component scores are available, THE Evaluation_Engine SHALL derive composite_score from the component scores using the existing recombination weights (offense/defense/baserunning shares per position).
4. THE Evaluation_Engine SHALL produce identical composite_score values before and after the reframe when given the same inputs, ensuring backward compatibility.

### Requirement 4: Divergence Detection as First-Class Feature

**User Story:** As a front office analyst, I want divergence detection to be a prominent, structured feature that flags hidden gems and landmines, so that I can find market inefficiencies where the tool-based assessment disagrees with OVR.

#### Acceptance Criteria

1. WHEN OVR is available and the tool_only_score differs from OVR by 5 or more points, THE Evaluation_Engine SHALL classify the player as a "hidden_gem" (tool_only >= OVR + 5) or "landmine" (OVR >= tool_only + 5).
2. WHEN OVR is available and the ceiling_score differs from POT by 5 or more points, THE Evaluation_Engine SHALL classify the ceiling divergence as "ceiling_gem" or "ceiling_landmine."
3. THE Evaluation_Engine SHALL include the divergence magnitude (signed difference), the tool_only_score, and the OVR value in the Divergence_Report.
4. WHEN OVR is not available, THE Evaluation_Engine SHALL return None for the Divergence_Report rather than fabricating a comparison.
5. THE Evaluation_Engine SHALL include component-level divergence context in the Divergence_Report, identifying which components (offensive, baserunning, defensive) contribute most to the overall divergence.
6. THE Web_UI SHALL display divergence flags prominently on player pages when a divergence of 5 or more points exists.

### Requirement 5: Tool Profile Analysis

**User Story:** As a front office analyst, I want the evaluation engine to decompose players into archetypes, carrying tools, and red flags, so that I get actionable scouting profiles rather than a single number.

#### Acceptance Criteria

1. THE Evaluation_Engine SHALL classify each player into an archetype based on tool distribution (e.g., power-over-hit, contact-first, balanced, stuff-over-command).
2. THE Evaluation_Engine SHALL identify carrying tools — individual tools that grade significantly above the player's composite score.
3. THE Evaluation_Engine SHALL identify red flag tools — individual tools that grade significantly below the player's composite score and represent exploitable weaknesses.
4. THE Web_UI SHALL display the archetype, carrying tools, and red flag tools on player pages alongside the component scores.
5. THE Evaluation_Engine SHALL include the Tool_Profile data in the EvaluationResult dataclass.

### Requirement 6: Ceiling Projection Independent of POT

**User Story:** As a front office analyst, I want ceiling projections derived from potential tool ratings, age, and development factors that work independently of POT, so that I have a usable ceiling estimate for leagues without POT or when I want a second opinion.

#### Acceptance Criteria

1. THE Evaluation_Engine SHALL compute ceiling_score from potential tool ratings, age-weighted blending, work ethic, and accuracy modifiers using the existing ceiling formula.
2. WHEN POT is available, THE Evaluation_Engine SHALL apply the existing POT soft cap (ceiling cannot exceed POT + 8).
3. WHEN POT is not available, THE Evaluation_Engine SHALL compute ceiling_score without the POT soft cap, relying solely on potential tool ratings and development factors.
4. THE Evaluation_Engine SHALL floor the ceiling_score at the current composite_score so that ceiling is never below current ability.
5. THE Evaluation_Engine SHALL compute component-level ceilings (offensive ceiling, pitching ceiling) from potential tool ratings using the same component formulas applied to potential tools.

### Requirement 7: Development Tracking via Snapshot Deltas

**User Story:** As a front office analyst, I want to track tool changes over time and identify risers and fallers, so that I can spot development trends and decompose rating changes into which tools improved or declined.

#### Acceptance Criteria

1. WHEN two rating snapshots exist for a player, THE Evaluation_Engine SHALL compute per-tool deltas (current minus previous) for all shared non-None tool values.
2. THE Evaluation_Engine SHALL compute component-level deltas (offensive_grade delta, baserunning_value delta, defensive_value delta) between snapshots, not just composite_score delta.
3. WHEN the composite_score delta is 3 or more points, THE Evaluation_Engine SHALL flag the player as a "riser."
4. WHEN the ceiling_score delta is -3 or more points (decline), THE Evaluation_Engine SHALL flag the player as having a "reduced ceiling."
5. THE Evaluation_Engine SHALL identify which specific tools drove the largest component changes in the Snapshot_Delta.

### Requirement 8: FV Calculation Using Component Scores

**User Story:** As a front office analyst, I want the FV calculation to use component scores directly rather than a single composite, so that FV grades reflect the multi-dimensional nature of player value.

#### Acceptance Criteria

1. WHEN component scores are available, THE FV_Calculator SHALL use the offensive_grade, baserunning_value, and defensive_value as inputs to the FV formula instead of a single composite_score.
2. THE FV_Calculator SHALL apply the existing defensive bonus logic using the Defensive_Value component directly rather than re-deriving it from raw tools.
3. WHEN component scores are not available (legacy data or leagues without the reframed engine), THE FV_Calculator SHALL fall back to using composite_score as the single input, preserving backward compatibility.
4. THE FV_Calculator SHALL produce FV grades on the same scale (rounded to nearest 5, with plus modifier) as the current implementation.
5. IF the component-based FV formula produces a grade that differs from the composite-based formula by more than one FV tier for the same player, THEN THE FV_Calculator SHALL log a warning identifying the player and the discrepancy.

### Requirement 9: Web UI Component Score Display

**User Story:** As a front office analyst, I want the web UI to surface component breakdowns prominently on player pages, so that I can see the offensive, baserunning, and defensive dimensions at a glance.

#### Acceptance Criteria

1. THE Web_UI SHALL display offensive_grade, baserunning_value, and defensive_value (or pitching composite and durability_score for pitchers) on the player page alongside the existing composite_score.
2. THE Web_UI SHALL display the composite_score in a secondary position relative to the component scores, reflecting its role as a convenience metric rather than the primary output.
3. THE Web_UI SHALL display divergence flags (hidden gem, landmine) with the magnitude and direction when a divergence of 5 or more points exists.
4. THE Web_UI SHALL display the player's archetype, carrying tools, and red flag tools in the evaluation section of the player page.
5. WHEN component scores are not available for a player, THE Web_UI SHALL fall back to displaying composite_score as the primary metric.

### Requirement 10: Cross-League Portability

**User Story:** As a front office analyst managing multiple leagues, I want the component scores to provide a usable evaluation framework for leagues without OVR or POT, so that I have consistent analytical tools across all leagues.

#### Acceptance Criteria

1. THE Evaluation_Engine SHALL compute all component scores, composite_score, and ceiling_score without requiring OVR or POT as inputs.
2. WHEN OVR is not available, THE Evaluation_Engine SHALL skip divergence detection and return None for the Divergence_Report.
3. WHEN POT is not available, THE Evaluation_Engine SHALL compute ceiling_score without the POT soft cap.
4. THE FV_Calculator SHALL produce valid FV grades using component scores alone when OVR and POT are not available, using composite_score as the OVR substitute and ceiling_score as the POT substitute.
5. THE Evaluation_Engine SHALL use per-league calibrated tool weights from `tool_weights.json` when available, falling back to DEFAULT_TOOL_WEIGHTS when no calibrated config exists.
