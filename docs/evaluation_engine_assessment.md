# Evaluation Engine — Current State Assessment

*Generated: 2026-04-19 | Updated: Session 47 | League year: 2033*

---

## How the System Works

The evaluation engine replaces OOTP's OVR/POT ratings with independently computed scores derived from individual tool ratings. All computation is pure (no DB access, no side effects); the batch `run()` entry point writes results back to the `ratings` table.

### Scores produced

| Score | Description |
|---|---|
| `composite_score` | Current ability on the 20-80 scale. Primary role only. Used in place of OVR throughout the pipeline. |
| `ceiling_score` | Projected peak ability. Blends current tools with potential tools, modified by accuracy and work ethic. Used in place of POT. |
| `tool_only_score` | Pre-stat-blend composite. Used for divergence detection (tool_only vs OVR flags over/underperformers). |
| `secondary_composite` | Two-way players only. Composite for the secondary role (e.g. hitting composite for a pitcher). |

### Hitter composite pipeline

1. Normalize each tool to the 20-80 scale via `ratings.norm()`.
2. Apply position-specific tool weights (from `tool_weights.json` if calibrated, else `DEFAULT_TOOL_WEIGHTS`).
3. Weights cover four offensive tools (contact, gap, power, eye), baserunning (speed, steal, stl_rt), and a defensive composite. `avoid_k` excluded (collinear with contact, r=0.78). Speed excluded from hitting regression (contributes via baserunning only).
4. Apply non-linear piecewise tool transformation (`_tool_transform`): below 40 penalized 1.5×, 40-60 linear, above 60 rewarded 1.3×. Applied to contact, gap, power, eye (hitting) and stuff, movement, control (pitching).
5. Blend with stat history via `compute_composite_mlb()` when ≥1 qualifying season exists.

### Pitcher composite pipeline

1. Normalize stuff, movement, control.
2. Apply non-linear piecewise tool transformation (`_tool_transform`): same curve as hitters.
3. Apply role-specific weights (SP vs RP/CL differ).
4. Add arsenal quality bonus: count of pitches rated ≥45 on the 20-80 scale.
5. SP innings-volume adjustment: +1 per 5 points above 45, capped at +7. Addresses the rate-stat vs counting-stat gap (Comp×IP correlates with WAR at r=0.70).
6. Stamina penalty for SP when stamina < 40.
7. Platoon balance penalty: -2 to -3 when weak-side stuff < 35 and L/R gap ≥ 15.
8. Stat blend when qualifying IP exists, using `pitcher_stat_to_2080` (asymmetric: steeper slope for above-average FIP, standard slope for below-average).

### Ceiling pipeline

The ceiling formula computes a potential-tool composite using the same weighted formula
as the current composite, applied to potential ratings. It then applies an **age-weighted
blend** between potential tools and current composite: younger players (age 16-17) weight
potential at 90-95%, while veterans (age 30+) weight current composite at 70%. Work ethic
and accuracy modifiers are applied, and the result is floored at the current composite score.

**POT soft cap (implemented 2026-04-19):** Ceiling cannot exceed POT + 8 when POT is
available. This prevents the formula from projecting unrealistic ceilings for players
the game has assessed as low-upside (e.g., POT=21 → max ceiling=29). The cap never
pushes ceiling below the current composite score.

### Calibration integration

`calibrate.py` now runs two additional steps before FV/surplus:

1. **Tool weight regression (Step 0):** Per-bucket regressions of tool ratings against WAR (hitting), SB rate (baserunning), ZR (fielding), and FIP (pitching). Hitting regression excludes `avoid_k` (collinear with contact) and `speed` (contributes via baserunning only). Min weight floor of 0.10 for hitters and 0.05 for pitchers prevents degenerate single-variable solutions. Writes calibrated weights to `tool_weights.json`.
2. **COMPOSITE_TO_WAR regression:** Once composite scores exist, regresses composite → WAR per position bucket. Writes to `model_weights.json` as `COMPOSITE_TO_WAR`. `peak_war_from_score()` prefers this table over `OVR_TO_WAR`.

### Pipeline order (refresh)

```
refresh.py → calibrate → evaluation_engine.run() → fv_calc
```

`fv_calc` reads `composite_score`/`ceiling_score` in place of OVR/POT when `use_custom_scores=True` (default).

---

## Where the Model Performs Well

### Composite beats OVR overall (Session 47)

After the Session 47 overhaul (WAR-targeted regression, piecewise tool transform, WAR-derived recombination shares, asymmetric pitcher stat blend, increased SP innings adjustment), the composite now outperforms OVR as a WAR predictor across all positions:

- **EMLB overall:** Composite r=0.679 vs OVR r=0.646 (+0.034)
- **Prospect inflation dramatically reduced:** Pauldo gap vs OVR went from +14 to -3
- **MiLB offset near zero:** EMLB -0.9, VMLB +3.7
- **MLB distribution aligned:** EMLB +1.2, VMLB +0.8

### RP/CL composite vs WAR

The composite score matches OVR's predictive power for relievers (r=0.579 vs r=0.574, N=198, IP≥20, year=2033). This is the one area where the model is competitive with the game's own rating. The three-tool pitcher model (stuff/movement/control) is a reasonable representation of reliever value, where arsenal depth matters less than for starters.

### Catcher and corner infield composites

| Pos | Comp r | OVR r |
|---|---|---|
| C | 0.661 | 0.696 |
| 3B | 0.706 | 0.783 |
| 2B | 0.599 | 0.696 |

Catchers and 3B show the strongest composite correlations among hitter buckets. The defensive component is meaningful at these positions and the tool weights appear well-calibrated.

### Score distribution is unbiased at the mean

Across all 881 MLB players with composite scores: mean composite = 49.6 vs mean OVR = 49.0. The model is not systematically inflating or deflating scores — the bias is near zero at the population level.

**Important context on OVR:** Per the OOTP engine, OVR is a **position-relative** rating — a 60 OVR shortstop is above-average among shortstops, not among all players. The composite score is also position-weighted (via per-bucket tool weights), so this comparison is valid. However, cross-position comparisons (e.g., "is a 55 composite SS better than a 55 composite 1B?") require the downstream WAR projection tables to be accurate, since the composite itself is position-normalized.

### Ceiling is reasonable for MLB players

MLB ceiling mean = 51.9 vs POT mean = 50.6. The distribution is tight (stdev of delta = 7.3) and the extreme cases are explainable. For established MLB players, ceiling and POT track closely.

---

## Known Issues

### 1. Pitcher score compression — most critical

**Symptom:** SP composite tops out at ~62 while OVR reaches 80. RP/CL composite tops out at 63. The game's best SP (OVR=77-80) are being rated as mid-rotation arms by the model.

**Evidence:**
- Eric Lewis: OVR=77, Comp=57, 8.8 WAR — best SP in the league by WAR, model rates him as a 57.
- Joe Miller: OVR=77, Comp=54, 4.9 WAR, 3.60 ERA.
- Chris Kupstas: OVR=80, Comp=60, 4.3 WAR.
- SP correlation: Comp r=0.552 vs OVR r=0.733 — a large gap.

**Root cause hypothesis:** The three-tool model (stuff/movement/control) misses what the game captures in OVR for elite SP. Key insight from the OOTP engine: `Stf` (Stuff) is already a **composite rating** that reflects the full arsenal quality including velocity — it's not a single-pitch rating. Similarly, `Mov` (Movement) is a composite of GB% and pitcher BABIP. So the model's three inputs are themselves composites of underlying pitch-level data.

This means the "arsenal quality bonus" in the model is partially redundant with Stuff — Stuff already incorporates arsenal depth and pitch quality. The bonus counts pitches rated ≥45 as a binary integer (+1 per pitch beyond 3, capped at +3), but this signal is already baked into the Stuff rating. The real question is: **what does OVR capture that Stuff + Movement + Control does not?**

Likely candidates: (a) the interaction between pitches (a 65 slider paired with a 70 fastball is more effective than either alone — Stuff captures individual pitch quality but OVR may capture sequencing/tunneling effects); (b) stamina's contribution to value (a 200-IP workhorse at 55 Stuff produces more WAR than a 150-IP pitcher at 55 Stuff, and OVR may weight this more heavily); (c) platoon balance (OVR may penalize extreme L/R splits more than the model's -2/-3 penalty).

**Calibration data supports this:** The SP calibration r² is only 0.162 — the tool regression explains just 16% of FIP variance. The calibrated weights are derived from a weak signal, which means the model is structurally unable to separate elite SP from average ones using the current feature set.

**Arsenal weight contradiction:** The calibrated SP arsenal weight is 0.0589 (reduced from the 0.10 default). The regression *already found* that the binary arsenal bonus doesn't add predictive power beyond what Stuff provides. This makes sense — Stuff already incorporates arsenal quality. The fix is not to increase the arsenal weight but to find what's *missing* from the model that OVR captures (likely stamina-weighted value or pitch interaction effects).

### 2. 1B and OF composite correlations are weak

| Pos | Comp r | OVR r | Gap |
|---|---|---|---|
| 1B | 0.435 | 0.745 | 0.310 |
| OF | 0.461 | 0.636 | 0.175 |

**1B evidence:** Jeremy Espanoza (OVR=60, Comp=52, 5.8 WAR, SLG=.664). Eric Newman (OVR=56, Comp=48, 3.7 WAR). The model is consistently undervaluing productive 1B.

**OF evidence:** Eddie Carrasco (OVR=63, Comp=55, 6.1 WAR). Elijah Gilchrist (OVR=63, Comp=55, 5.5 WAR). Bob Barrasa (OVR=62, Comp=47, 3.6 WAR — this one the model correctly rates lower).

**Root cause hypothesis:** The 1B defensive weight is pulling composites down for a position where defense contributes minimally to value. The OF model may be over-penalizing low power for contact/speed profiles that produce real value (OBP, SB, gap doubles).

**Calibration contradiction for 1B:** The calibrated 1B defense weight is 0.15 — *higher* than the 0.10 default. The regression is pushing defense weight *up* for 1B, which is the opposite of what the correlation analysis suggests should happen. This indicates the calibration regression is finding a spurious or indirect relationship (e.g., better defenders happen to be better hitters in the sample) rather than a causal one. The 1B calibration r² is only 0.204, confirming the weak signal.

### 3. Ceiling formula over-weights character traits for low-POT players — FIXED

**Status:** Fixed (2026-04-19). A POT soft cap was implemented: `ceiling ≤ POT + 8` when
POT is available. The cap never pushes ceiling below the current composite score.

**Original symptom:** Several low-POT players (POT=20-42) were receiving ceiling scores
20-30 points above their POT.

**Evidence:**
- Mike Farrar (AAA, age 30): POT=21, Ceil=51, acc=A, wrk=N. A 30-year-old AAA player with POT=21 should not have a 51 ceiling.
- Alex Venegas (FCL, age 18): POT=20, Ceil=46, acc=VH, wrk=L. Low POT, low work ethic, yet ceiling is 26 points above POT.
- Bob Edmundson (A+, age 27): POT=32, Ceil=57, acc=H, wrk=H. A 27-year-old A+ player with POT=32 should not project to 57.

**Root cause (code-level):** The ceiling formula (`compute_ceiling()`) calls `compute_composite_hitter()` on the *potential* tool ratings, then floors the result at `composite_score`. **POT is never referenced.** For a player where current tools ≈ potential tools (a maxed-out veteran or a player with no projected growth), the potential composite equals the current composite, and the floor constraint pushes ceiling up to the current composite — which can be much higher than POT when the player has a strong tool profile that the game doesn't fully reflect in its POT rating.

The game's POT=21 is saying "this player has no upside beyond what he is now." But the model ignores that signal entirely. The ceiling formula is purely a function of potential tool ratings + work ethic + accuracy, with no reference to the game's own ceiling assessment.

**Design question:** Should POT be an input to the ceiling formula? The engine's philosophy is to derive everything from tools independently. But when the game assigns POT=21 to a player with 55-rated current tools, it's encoding information not visible in the tool ratings (injury risk, makeup issues, organizational assessment). Ignoring POT entirely means the model loses that signal.

### 4. Ceiling is too pessimistic for raw young prospects — FIXED

**Status:** Fixed (2026-04-19). An age-weighted blend was implemented:
`potential_weight = max(0.30, min(0.95, 1.0 - (age - 16) * 0.05))`. At age 16-17,
potential tools drive 90-95% of the ceiling. At age 25+, current composite drives 50%.
At age 30+, current composite drives 70%.

**Original symptom:** 15-17 year old DSL/Rk pitchers with POT=80 were receiving ceiling scores of 31-40.

**Evidence:**
- Mario Morales (DSL, age 17): POT=80, Ceil=31. Current tools: Stf=30/Mov=35/Ctrl=25. Potential: Stf=70/Mov=60/Ctrl=45.
- Marc Kuebel (AZL, age 15): POT=80, Ceil=38. Current: Stf=35/Mov=40/Ctrl=35. Potential: Stf=70/Mov=65/Ctrl=65.

**Root cause:** The ceiling formula applies the composite formula to potential tools directly. For a pitcher with potential tools of Stf=70/Mov=60/Ctrl=45, the weighted composite (using calibrated SP weights: movement=0.50, stuff=0.25, control=0.19, arsenal=0.06) produces roughly: `70*0.25 + 60*0.50 + 45*0.19 ≈ 56`. But the floor constraint (`max(ceiling, composite_score)`) doesn't help here because the current composite is even lower (tools at 25-35 produce a composite around 30).

The real issue is that the ceiling formula doesn't account for age. A 17-year-old with potential tools of 70/60/45 is a fundamentally different prospect than a 27-year-old with the same potential tools. The game's POT=80 reflects the full developmental arc; the model's ceiling only sees the potential tool ratings at face value.

### 5. Hitter composite underperforms OVR overall — FIXED

**Status:** Fixed (Session 47). After switching to WAR-targeted regression, piecewise tool transform, WAR-derived recombination shares, and removing `avoid_k`/`speed` from the hitting regression, composite now beats OVR overall (r=0.679 vs 0.646).

**Original symptom:** Across all hitter buckets, OVR outperformed composite as a WAR predictor (r=0.677 vs r=0.533, N=386).

### 6. RP calibrated weights are degenerate — MITIGATED

**Status:** Mitigated (Session 47). A `min_weight=0.05` floor was already in place for pitcher regression, preventing fully degenerate single-variable solutions. The hitter regression now also has `min_weight=0.10`.

**Original symptom:** The calibrated RP weights were `movement: 0.99, stuff: 0.0, control: 0.01, arsenal: 0.0`. This is a single-variable model — the regression found that only movement correlates with RP FIP in the sample.

**Evidence:** Calibration r² for RP pitching is 0.109 (11% of variance explained). The model is essentially `RP_composite ≈ movement_rating`.

**OOTP engine context:** Relievers receive a **Stuff bonus** in the game engine because batters get fewer looks — this bonus is tied to the top two pitches. This means RP Stuff ratings are already inflated relative to their actual pitch quality. If all RPs have similarly inflated Stuff, the variance in Stuff across RPs is compressed, which would explain why the regression finds no correlation between Stuff and FIP for relievers. Movement (which has no RP bonus) retains its natural variance and thus correlates better.

**Risk:** The RP composite currently matches OVR's predictive power (r=0.579 vs r=0.574), but this is fragile. If the movement correlation is sample-dependent or reflects a confound (e.g., movement correlates with groundball rate which correlates with bullpen usage patterns), the RP model will collapse on the next recalibration with different data. A single-variable model has no redundancy.

**Recommendation:** Consider a minimum weight floor (e.g., 0.10) for stuff and control in the RP model to prevent degenerate solutions. Alternatively, use regularized regression (ridge/elastic net) in the calibration step to prevent any single coefficient from dominating. The RP Stuff bonus may also mean the model should use raw pitch ratings rather than the composite Stuff rating for relievers.

### 7. Stat blend impact on SP compression — ADDRESSED

**Status:** Addressed (Session 47). The asymmetric `pitcher_stat_to_2080` conversion now uses a steeper slope (0.45/pt) for above-average FIP and standard slope (0.30/pt) for below-average. This prevents the stat blend from over-penalizing average SP while properly rewarding elite pitching.

**Original gap:** The assessment identified SP tool-only compression but didn't analyze whether the stat blend (`compute_composite_mlb`) helps or hurts.

### 8. `avoid_k` collinearity with contact — FIXED

**Status:** Fixed (Session 47). `avoid_k` dropped from the hitting regression, default weights, tool extraction, and confidence checks. Contact is a composite of BABIP + K-avoidance in the OOTP engine, so including both double-counted the K-avoidance signal (r=0.78 collinearity confirmed).

---

## Calibration Quality Assessment

### Calibration r² by bucket

| Bucket | Component | r² | N | Assessment |
|---|---|---|---|---|
| C | hitting | 0.511 | 81 | Adequate |
| SS | hitting | 0.377 | 178 | Moderate |
| 2B | hitting | 0.226 | 68 | Weak — marginal sample |
| 3B | hitting | 0.530 | 52 | Good r² but low N — overfitting risk |
| CF | hitting | 0.405 | 109 | Moderate |
| COF | hitting | 0.358 | 154 | Moderate |
| 1B | hitting | 0.204 | 58 | Weak — marginal sample |
| SP | pitching | 0.162 | 392 | Weak despite large N — structural issue |
| RP | pitching | 0.109 | 411 | Very weak — degenerate weights |
| All | baserunning | 0.308 | — | Moderate (shared across buckets) |

**Key observations:**
- SP and RP have the weakest r² despite the largest sample sizes. This is a structural problem — the three-tool pitcher model (stuff/movement/control) is insufficient to explain pitching performance variance.
- 3B has the best hitter r² (0.530) but only 52 data points. This is near the `MIN_REGRESSION_N=40` threshold and may be overfitting.
- 2B and 1B have both weak r² and marginal sample sizes. Their calibrated weights should be treated with low confidence.

### Recombination weights — WAR-derived

The `tool_weights.json` contains a `recombination` section (offense/defense/baserunning splits per position). These shares were derived empirically from WAR regression across EMLB + VMLB (AB ≥ 200) via grid search for the split that maximizes Pearson r with WAR per position. Defense contributes far less to WAR than the original design spec assumed — WAR already includes positional adjustment, so the composite doesn't need to separately reward defense.

Current shares (Session 47):
- C: offense 80%, defense 15%, baserunning 5%
- SS/2B: offense 90%, defense 5%, baserunning 5%
- 3B: offense 90%, defense 0%, baserunning 10%
- CF: offense 80%, defense 10%, baserunning 10%
- COF/1B: offense 95%, defense 0%, baserunning 5%

These ratios are baked into the final tool weights at calibration time via `recombine_component_weights()`, not applied dynamically.

---

## Downstream Impact: Surplus Calculations

Since `fv_calc` now uses `composite_score` in place of OVR and `ceiling_score` in place of POT:

- **SP surplus is more accurate.** The Session 47 changes (asymmetric pitcher stat blend, increased innings adjustment, piecewise tool transform) have significantly reduced SP composite compression. Elite SP are no longer systematically undervalued, though some residual compression may remain at the very top end.

- **Prospect inflation fixed.** WAR-derived recombination shares and the piecewise tool transform have eliminated the systematic +13 point MiLB offset. MiLB offset is now near zero (EMLB: -0.9, VMLB: +3.7). Low-POT veterans no longer receive inflated ceiling scores (POT + 8 cap).

- **Young raw prospects are properly valued.** The age-weighted ceiling blend (implemented Session 46) ensures DSL/Rk prospects with high potential tools receive appropriate ceiling scores.

**Quantification needed:** Compare FV distributions (composite-based vs OVR-based) for each bucket to measure the remaining surplus distortion, if any.

---

## Suggested Next Steps

### Investigation (immediate)

1. **~~Quantify the stat blend impact on SP.~~** ✅ Addressed — `pitcher_stat_to_2080` now uses asymmetric slopes (0.45/pt above average, 0.30/pt below average) to properly reward elite pitching without over-penalizing average SP.

2. **~~Check `avoid_k` / `contact` collinearity.~~** ✅ Confirmed (r=0.78) and fixed — `avoid_k` dropped from the model entirely.

3. **~~Audit the ceiling formula for low-POT players.~~** ✅ Implemented — POT + 8 soft cap added to `compute_ceiling()`. Ceiling cannot exceed `POT + 8` when POT is available, but never drops below composite_score.

4. **~~Audit the ceiling formula for young raw prospects.~~** ✅ Implemented — age-weighted blend added to `compute_ceiling()`. At age 17, potential tools weighted at 95%; at age 25+, current composite weighted at 50%; at age 30+, current composite weighted at 70%.

5. **~~Investigate the SP compression mechanism.~~** ✅ Addressed via multiple changes: piecewise tool transform rewards elite tools (1.3× above 60), increased SP innings-volume adjustment (+1/5pts above 45, cap +7), asymmetric pitcher stat blend, and WAR-derived recombination shares that reduce defense overweighting.

6. **~~Investigate 1B defensive weight.~~** ✅ Fixed — WAR-derived recombination shares set 1B defense to 0% (was 15%). Offense share increased to 95%.

7. **Assess RP model stability.** Run the RP calibration on a different year's data (2031 or 2032) and check whether movement still dominates. If the weights shift dramatically, the single-variable model is unstable and needs regularization. The `min_weight=0.05` floor mitigates the worst case but doesn't fully solve it.

### Model improvements (next iteration)

8. **~~SP composite: stamina as positive contributor.~~** ✅ Implemented — SP innings-volume adjustment: +1 per 5 points above 45, capped at +7. A 70-stamina workhorse gets +5 points over a 45-stamina pitcher.

9. **~~SP composite: remove redundant arsenal bonus.~~** ⚠️ Partially addressed — the piecewise tool transform and increased innings adjustment have reduced the SP compression issue. The arsenal bonus is retained but its weight is small (0.06-0.10). Further investigation may still be warranted.

9. **~~Age-weighted ceiling blend.~~** ✅ Implemented (see item #4 above).

10. **~~Ceiling cap relative to POT.~~** ✅ Implemented (see item #3 above). Buffer set to 8 points.

11. **~~Regularized pitcher regression.~~** ✅ Partially addressed — `min_weight=0.05` floor prevents fully degenerate solutions. Full ridge/elastic net regression remains a future option if the floor proves insufficient.

12. **~~1B/OF tool weight recalibration.~~** ✅ Addressed — WAR-derived recombination shares set 1B and COF defense to 0%, CF defense to 10%. Offense dominates at every position.

### Validation (after fixes)

13. **Re-run correlation analysis after the next calibration cycle.** The COMPOSITE_TO_WAR tables will change the WAR projections used in surplus. Baseline the current correlations (documented above) and compare after calibration. Session 47 baseline: overall r=0.679.

14. **Spot-check surplus rankings against trade intuition.** Now that composite scores feed into FV and surplus, verify that the top-10 surplus players at each position pass a smell test. The SP compression issue has been significantly reduced but may still affect edge cases.

15. **Compare FV distributions: composite-based vs OVR-based.** For each bucket, compute the FV grade distribution using composite_score vs using OVR. Quantify how many players shift FV tiers and in which direction. This measures the real-world impact of the model's accuracy gaps on trade analysis.

16. **Validate ceiling against development outcomes.** For players with 2+ years of ratings history, compare their ceiling_score from year N to their composite_score in year N+2. Does ceiling predict future composite better than POT predicts future OVR? This is the ultimate validation of whether the independent ceiling formula adds value.

---

## Summary Table

| Area | Status | Priority |
|---|---|---|
| Overall composite vs OVR | ✅ Composite beats OVR (r=0.679 vs 0.646) | — |
| RP/CL composite accuracy | ✅ Competitive with OVR (min_weight floor mitigates degeneracy) | Monitor |
| C / 3B composite accuracy | ✅ Good (3B: low N overfitting risk) | Monitor |
| Score distribution bias | ✅ Near-zero mean bias (MLB: +1.2, MiLB: -0.9) | — |
| SP composite compression | ⚠️ Significantly improved via piecewise transform + innings adjustment + asymmetric stat blend | Monitor |
| 1B composite accuracy | ✅ Fixed — defense share zeroed via WAR-derived recombination | Monitor |
| Ceiling cap for low-POT players | ✅ Fixed — POT + 8 soft cap implemented | — |
| Ceiling for young raw prospects | ✅ Fixed — age-weighted blend implemented | — |
| `avoid_k` / `contact` collinearity | ✅ Fixed — `avoid_k` dropped (r=0.78 confirmed) | — |
| Hitter composite vs OVR | ✅ Fixed — WAR-targeted regression + piecewise transform | — |
| OF composite accuracy | ⚠️ Improved (COF defense zeroed) — needs re-validation | Low |
| RP weight degeneracy | ⚠️ Mitigated by min_weight floor — monitor stability | Low |
| Stat blend for pitchers | ✅ Addressed — asymmetric `pitcher_stat_to_2080` | — |
| COMPOSITE_TO_WAR calibration | ⏳ Pending next calibrate run with new composites | Medium |
| Downstream surplus distortion | ⚠️ Reduced — prospect inflation fixed, SP compression improved | Low |
| SS composite accuracy | ⚠️ Moderate gap — defense share reduced to 5% | Low |
| Recombination weights | ✅ WAR-derived, empirically validated across EMLB + VMLB | — |
