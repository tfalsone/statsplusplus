# Task List

Open work items. Completed items are in `docs/changelog.md`.

---

## Code Quality

- [x] **Additional ratings scales** — Support 1-20 scale (maps to 20-80 via linear `20 + (raw-1)/19 * 60`). Auto-detection: max rating ≤20 → 1-20, >80 → 1-100, else 20-80. Added to settings and onboarding dropdowns. **Done Session 57.**
- [x] **Snapshot test fragility** — `test_prospect_value.py` now stubs `dollars_per_war()` and `league_minimum()` via `unittest.mock.patch` to fixed values ($7M, $800K). Tests are fully deterministic regardless of `league_averages.json` state. Structural invariants (monotonicity, option ≥ base, SP > RP) plus a $/WAR scaling test. `test_player_utils.py` was already stable (exact FV grades depend on model_weights.json which only changes during recalibration, not refresh). **Done Session 57.**
- [x] **Evaluation engine docs** — Add `evaluation_engine.py` to `docs/tools_reference.md` and `docs/system_overview.md`. Document the `run()` entry point, pure computation functions, and the batch pipeline integration in `refresh.py`. **LOE: Low.**

---

## Evaluation Engine Tuning

- [x] **Score compression further tuning** — Replaced elite tool bonus with piecewise tool transform (Session 47). Peak tool bonus for ceiling added (Session 48). 1.2× above-60 bonus restored (Session 52) to decompress top end. Composite range now 41-80 on eMLB, 37-76 on VMLB.
- [x] **Calibration on VMLB** — Full calibrate → evaluation_engine → fv_calc pipeline run on VMLB (Session 48). R²-blended defaults and raised min_weight floors produce stable cross-league weights (cosine similarity 0.98+).
- [x] **Carrying tool config review** — Percentile-based threshold (P85) now adapts to league distributions. VMLB calibrates all 7 positions (was only 2). Default merge fills gaps. Carrying tool bonus fully disabled (composite Session 56, ceiling Session 57) as redundant with tool transform (1.3× above 60) + peak tool bonus. **Done Session 57.**
- [x] **Tool interaction terms** — contact×eye, power×eye (hitters) and stuff×movement (pitchers) added Session 56, disabled Session 57. Were dead code (weights never written to `tool_weights.json`). Multivariate OLS shows residual correlation ~0.01 — collinear with individual tools (r=0.85-0.93), no explanatory power beyond linear model. Tool transform already captures the non-linearity. **Removed Session 57.**
- [x] **Stat blending: ERA- conversion and P95 calibration** — `_compute_stat_signal` now uses ERA- for pitchers (was FIP-). OOTP WAR is RA9-based; FIP systematically undervalued contact-management pitchers. P95 calibration still pending (slopes not yet wired). **Done Session 54 (ERA- part).**
- [x] **Evaluation model documentation** — `docs/evaluation_model.md` written with full pipeline diagram, formulas, constants, weight tables, and design rationale. **Done Session 52.**
- [ ] **SP underrepresentation in prospect rankings** — 18-20/100 SP in VMLB, 6/100 in EMLB. Investigated Session 49: OOTP generates tighter pitcher tool distributions (stuff/mov SD ≈ 11 vs hitter power SD ≈ 18), especially on 1-100 scale. HRA/PBABIP now included in pitcher composite for differentiation. VMLB representation is close to real baseball (~25-30%); EMLB is a league composition issue. **LOE: N/A — understood limitation.**
- [x] **SP FV undervaluation** — Investigated Session 50. Pitcher true_ceiling runs ~5-6 below game POT (e.g. 59 vs 65 for Schwarzenberg). Root cause: stuff rating already incorporates individual pitch quality, so the arsenal bonus partially double-counts. The 5-6 point gap is a stable, predictable offset that affects all SP equally. The FV system compensates through ceiling-credit — Schwarzenberg correctly grades at FV 50 Medium despite the ceiling compression. Increasing arsenal weight would risk double-counting. **Accepted as known limitation.**
- [x] **Per-league dynamic aging/development curves** — Gap closure rates, age runway tables, and expected gap tables now calibrated per league from cross-sectional OVR/POT data during `calibrate.py`. Stored in `model_weights.json`, loaded by `fv_model.py` with hardcoded VMLB-derived fallbacks. EMLB shows significantly higher closure rates than VMLB (e.g. hitter age 22: 0.91 vs 0.67). **Done Session 51.**
- [ ] **Cross-sectional survivorship bias** — Investigated Session 51. OOTP revises POT downward for players who fail to develop: only 22% of POT 50+ players at age 17 still have POT 50+ at age 26. Cross-sectional realization rates are inflated because busts appear as "low-POT, high-realization" players. Impact: gap closure rates (→ risk labels) are slightly optimistic for high-ceiling prospects. FV grade formula is unaffected (uses current snapshot only). Expected gap tables are correct for their cross-sectional use case. The bust_discount (0.55-0.85 by age, raised Session 52 from 0.30-0.60) partially mitigates. True fix requires longitudinal tracking across multiple seasons via `ratings_history`. Player coverage is near-complete at ages 17-21 (100%) but drops to 72% at age 26 due to unsigned players lacking ratings. **LOE: N/A until multi-season data accumulated.**
- [x] **FV 45+ inflation residual** — Now at ~10/org vs Fangraphs ~8.3. Accepted as a methodology difference: our tool-based composite is intentionally more generous than the game's OVR for developing players. The sub-MLB floor penalty (Session 51) reduced it from ~11 to ~10. Further reduction would require penalizing unproven tools, which conflicts with the design principle that composite = pure tool value. **Accepted at current level.**
- [x] **Composite-OVR divergence investigation** — Prospect composites run +7-8 above OVR. Investigated Session 51: the divergence IS the development gap — the difference between what tools say and what the player has proven. The game's OVR likely includes a "proven-ness" factor our composite intentionally omits. The sub-MLB floor penalty addresses the portion caused by disqualifying tool weaknesses. Remaining divergence is accepted as a design feature. **Closed — accepted as design choice.**
- [x] **COMPOSITE_TO_WAR calibration** — Now that composite scores exist on both leagues, run a second calibration pass to produce COMPOSITE_TO_WAR tables. These feed into `peak_war_from_score()` for surplus calculations. **Done Session 48.**

### FV Pipeline Migration to Composite/Ceiling Inputs

Legacy components designed for OVR/POT that need updating for composite/ceiling:

- [x] **`dev_weight()` curve tuning** — diff>=2 now gets 0.60 (was 0.50), rookie cap raised to 0.55. Fixes Joe Read-type undervaluation. **Done Session 49.**
- [x] **`effective_pot()` override removal** — Was dead code (column name mismatch). Removed from calc_fv. **Done Session 49.**
- [x] **`RP_POT_DISCOUNT` (0.8×) review** — Reduced to 0.85×. Old value double-counted RP devaluation in pitcher composite weights. FV 57 cap still limits top end. **Done Session 49.**
- [x] **Prospect discount + dev_weight interaction** — Resolved by dev_weight fix. Discount impact on FV is now ~2 points (acceptable). **Done Session 49.**

---

## Model & Data

- [x] **Arb salary calibration broken** — Fixed Session 56. Added WAR ≥ 1.0 floor, outlier cap, N ≥ 10 minimum, monotonic enforcement. Switched from flat-percentage model to raise-based (arb_model.arb_salary). Fixed discount mismatch (salary now discounted same as value). EMLB: {1:0.24, 2:0.24, 3:0.32}. **Done Session 56.**
- [ ] **Arb salary constants recalibration** — `ARB_HITTER_BASE` and `ARB_HITTER_EXP` constants produce arb estimates ~20-30% below actual OOTP arb outcomes for 3-4 WAR players. Should be calibrated per league from actual arb contracts (exponential fit on OVR/composite vs salary). **LOE: Low. Priority: Low.**
- [x] **Prospect WAR projection methodology** — Current approach uses `FV_TO_PEAK_WAR` lookup table (FV 50 → 2.0 WAR) with aging curve and ramp. Investigated Session 56: using ceiling→WAR would double-count upside (FV already encodes development probability). FV→WAR is correct in principle. Now passes continuous FV (pre-rounding) to `prospect_surplus` for interpolation within tiers. **Done Session 57.**
- [ ] **Platoon exposure modeling** — Current composite uses overall ratings; FV platoon penalty (-2/-3) partially addresses severe splits. Full platoon modeling would value platoon contributors in context (e.g., a LHH with 70 contact vs RHP and 30 vs LHP has real value as a platoon piece). Requires research: how to weight L/R splits, what threshold defines "platoon only," how to reflect platoon value in surplus. **LOE: Medium-High.**
- [x] **Surface tool_only_score on MLB player pages** — MLB players now show pure tool score in parentheses next to the stat-blended composite. **Done Session 51.**
- [x] **Risk labels in prospect list templates** — Risk initials with color coding now rendered in league prospect list, team org overview, and team farm top 15. **Done Session 51.**
- [ ] **Projection model reuse** — `projections.py` now has calibrated OPS+, ERA/FIP, WAR, and ratings interpolation models. Explore using these in: (1) prospect pages — show projected MLB stat lines at current and future development stages, (2) draft evaluation — project draft prospect ratings into expected MLB production, (3) trade calculator — replace or supplement surplus model with projected stat lines for more intuitive valuation, (4) farm analysis — add projected stat context to scouting summaries. **LOE: Varies per integration.**
- [ ] **Org overview scaffold** — automate the org overview report template pulling farm summary, roster summary, contracts, surplus rankings, extension priorities. Lower priority — report structure changes between evaluations.
- [ ] **Surplus model validation suite** — systematic validation of prospect and contract surplus models against real league data. Subtasks: (1) sanity-check top/bottom 25 prospects by surplus — do rankings match intuition? (2) cross-position trade equivalence — test model-fair swaps (FV 55 SP vs SS, FV 50 C vs 1B, elite RP vs mid SP) for smell test; (3) prospect→MLB crossover — compare AAA prospect value to same player's contract value after debut, check for discontinuities; (4) age sensitivity — verify younger prospects properly valued over older ones at same FV/Pot; (5) validate against actual league trades — run completed trades through calculator; (6) FA contract validation — compare $/WAR and market value projections to actual free agent signings; (7) SP/hitter arb salary spot-checks — extend the RP arb validation to other positions. **LOE: Medium.**

---

## Web UI — Team Page

- [ ] **Playing time model edge cases** — current model is 77% within 100 PA, 92% within 200 PA across 4 test teams. Known gaps: (1) utility players with <3 games at every position get sprayed across the diamond via ratings fallback; (2) DH-primary detection uses 50% batting-fielding gap threshold — teams that rotate DH duties without a primary DH leave the slot empty; (3) bench players squeezed below realistic PA when starter is a multi-position player claiming the slot; (4) **global position optimization** — model assigns positions per-player, not globally. Would require a constraint-satisfaction or linear-programming approach to maximize total team WAR across all positions simultaneously. **LOE: Low-Medium per item, High for #4.**
- [ ] **Positional strength/weakness map** — starter Ovr + surplus vs league average at each position. CLI version done (`team_needs.py`). Web UI version (visual map on team page) still pending. **LOE: Medium.**
- [ ] **Pipeline view** — MLB starter → AAA depth → top prospect chain per position bucket. **LOE: Medium.**
- [ ] **Division rival comparison** — side-by-side surplus/farm/record for division teams. **LOE: Medium.**
- [ ] **Roster projection** — project next year's roster from contracts, arb estimates, FA departures. **LOE: High.**

---

## Web UI — League Page

- [x] **Positional rankings page** — League-wide page showing top players by position group (C, IF, OF, SP, RP), split into MLB and prospect sections. For MLB: rank by composite/WAR. For prospects: rank by FV/surplus. **Already implemented.**
- [ ] **Power rankings trend indicators** — store historical rank snapshots (per eval_date or game_date) and show ▲/▼/— movement arrows next to rank. Needs: new DB table or JSON file for rank history, delta calculation. **LOE: Medium.**
- [ ] **League news / milestone ticker** — horizontal strip between standings and power rankings showing notable milestones (e.g. "Player X: 3 HR from 50"). Needs: milestone detection logic from stats. **LOE: Medium-High.**

### Draft Tab — Future Improvements
- [x] **Draft prospect ranking** — sort by FV (primary) then surplus (secondary). Web UI already uses this sort. CLI `draft_board.py pick` uses draft value sort (FV + ceiling bonus + ctl penalty). **Done Session 53.**
- [x] **ADP and draft simulation** — Expected draft position based on POT rank. Draft sim with randomized other-team picks. Urgency-greedy list building for auto-draft upload. Org needs as tiebreaker. Web UI sim + upload buttons. **Done Session 55.**
- [ ] **"My List" draft board builder** — Sidebar panel where users build a ranked draft list by clicking prospects from the board. Features: (1) "Add to My List" button per prospect row, (2) reorderable list via drag-and-drop or up/down arrows, (3) localStorage persistence across sessions, (4) export as commissioner format (numbered list with game position + name) or StatsPlus upload format (plain text IDs, one per line). **LOE: Medium.**
- [x] **Visual flag badges** — Show Acc=L warning badge (⚠) and Extreme risk badge (☠) directly in the draft board table rows next to player name. **Done Session 57.**
- [x] **Sleeper/value flags** — Implemented via ADP system (Session 55). POT rank vs FV rank gap produces Sleeper/Value/Goes Early/Reach labels. Displayed in draft board table and CLI output. **Done Session 55.**
- [x] **Advanced filtering** — Collapsible tool filter panel on draft board with min-threshold inputs for potential tools (Con/Pow/Eye/Spd for hitters, Stf/Mov/Ctrl for pitchers) plus Pot and FV minimums. Filters apply in real-time. **Done Session 57.**
- [ ] **Post-draft grades** — team haul summaries after draft completion. **LOE: Medium.**

---

## Web UI — Player Page

- [ ] **Player development history chart** — chart showing rating trajectories over time using `ratings_history` snapshots (monthly in-game). Display current + potential for primary tools (hitter: cntct/gap/pow/eye/ks; pitcher: stf/mov/ctrl + individual pitches), ovr/pot headline, and extended ratings (babip/hra/pbabip) when available. Waiting for multiple snapshots to accumulate before building the UI. **LOE: Medium.**

---

## Web UI — Navigation

- [x] **Minor league team pages** — ~~extend `/team/<id>` to affiliate team IDs~~ Done. Notable player filter tuned: "young for level" now requires ceiling ≥ 45 (was age-only). Fixes Intl/Rookie levels where every teenager qualified. Results: Intl 9.7→5.9/team, Rookie 6.2→4.7/team. Upper levels unchanged (~12-15/team, appropriate for prospect-heavy affiliates). **Done Session 57.**

---

## Web UI — Visual Overhaul

- [ ] **In-app help system** — Add contextual help for key concepts (FV, risk, composite, surplus, etc.). Options: (1) "?" icon next to metrics that opens a tooltip/popover with explanation, (2) a slide-out help panel accessible from the nav, (3) a glossary page. Current tooltips via `title` attributes cover basics; a richer system would improve onboarding for new users. **LOE: Medium.**
- [ ] **Team logos** — add team logos to team pages and player pages. Source or generate logo assets for all 34 MLB teams. Display in page headers, standings, and anywhere team identity appears. **LOE: Low-Medium.**
- [ ] **UI overhaul exploration** — current layout is functional but generic. Investigate alternative visual styles, layouts, and design patterns to give the app more personality. **LOE: Medium-High.**

---

## Data & Research

- [ ] **Team vs team history** — head-to-head record lookup from the `games` table. Could be a standalone query function or CLI tool. Useful for beat reporter articles and rivalry context. **LOE: Low.**

---

## Long-term

- [ ] **Phase 2 — Interactive tools** — trade workbench, prospect explorer, free agent planner. Trade analysis CLI toolset complete (Session 44): `trade_targets.py`, `trade_assets.py`, `team_needs.py`, `trade_calculator.py` improvements, `trade-analyst.md` agent. Remaining: web-based trade workbench UI, prospect explorer UI, FA planner UI.
- [ ] **Phase 3 — AI assistant** — chat interface with league/team context.
- [ ] **Code architecture cleanup** — connection context manager, consistent row_factory, route-level error handling. Ongoing incremental work.
- [ ] **Stat/ratings divergence flag** — surface confidence signal when `stat_peak_war` and `peak_war_from_ovr` differ by >1.5 WAR in trade calculator output. Player page already shows over/underperformance; this extends it to trade evaluation context.

- [x] **Comp-based FV validation tool** — CLI tool (`scripts/comp_validate.py`) finds MLB players with similar tool profiles and shows WAR distribution. Web UI shows "Ceiling Profile" summary on prospect pages. Uses potential ratings, rate-normalized WAR (per 600PA/180IP), year filtering. Data limitation: uses current ratings vs historical stats; most reliable for recent seasons. **Done Session 56.**
