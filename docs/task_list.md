# Task List

Open work items. Completed items are in `docs/changelog.md`.

---

## Code Quality

- [x] **Full codebase review** — ~~Systematic review of all Python and template files for clean coding principles.~~ Completed Session 41: constants consolidated, `norm`/`norm_floor` standardized, `dollar_per_war`/`minimum_salary` centralized, `ROLE_MAP` deduplicated, file restructuring (ratings/fv_model/war_model/arb_model), arb formula consolidated, logger names fixed, hardcoded slug fallbacks removed. **Done Session 41.**
- [ ] **Web layer integration tests** — Add tests for web query functions (`player_queries.py`, `team_queries.py`, `queries.py`) using a minimal SQLite fixture. Current unit tests only cover pure model functions; inline import errors and runtime failures in the web layer are invisible until a page is hit in the browser. Tests should verify each query function returns without error and produces the expected shape. **LOE: Medium.**

---

## Multi-League Support — Post-Alpha Backlog

- [ ] **3.6 Settings page hardening** — Confirmation dialogs, input validation, backup before edits, team ID mismatch handling, read-only derived settings, undo support. **Deferred.**
- [ ] **3.7 Onboarding wizard resilience** — Step 2 GET-capable (resume on browser refresh), `beforeunload` warning during refresh, detect existing league directory on re-onboard and skip to appropriate step, `setup_complete` sentinel in state.json. **Deferred.**
- [ ] **Additional ratings scales** — Support 1-20 scale (maps to 20-80 in increments of ~3). Currently only 1-100 and 20-80 are supported; auto-detection checks if any rating exceeds 80. **LOE: Low.**
- [x] **3.8 Data wipe from settings** — ~~Button in settings to wipe league data.~~ Implemented: `/api/wipe-league` endpoint with single-league and full wipe, confirmation dialog in settings UI, redirect to `/onboard` after wipe. **Done Session 28.**

---

## Model & Data

- [ ] **Projection model reuse** — `projections.py` now has calibrated OPS+, ERA/FIP, WAR, and ratings interpolation models. Explore using these in: (1) prospect pages — show projected MLB stat lines at current and future development stages, (2) draft evaluation — project draft prospect ratings into expected MLB production, (3) trade calculator — replace or supplement surplus model with projected stat lines for more intuitive valuation, (4) farm analysis — add projected stat context to scouting summaries. **LOE: Varies per integration.**
- [x] **Payroll Adjusted Performance (PAP) score** — ~~rate MLB players on a 1-10 scale measuring current-year value efficiency.~~ Implemented: production-based (actual WAR pace vs salary), league-calibrated scale (2×stdev via calibrate.py), displayed on player page, team stats tabs, hover popup. Formula: `5 + 5 × tanh(annualized_surplus / scale)`. **Done Session 40.**
- [x] **Career outcome probability chart (prospects)** — ~~on prospect pages, show a distribution chart with buckets for prime WAR/season outcomes and the player's probability of landing in each.~~ Implemented: horizontal bar chart with 0.125 WAR increments, logistic CDF with smooth elite compression, mid-50% zone highlighting, threshold summary (Contributor/Regular/All-Star), position average WAR marker, confidence meter. **Done Session 35.**
- [x] **RP WAR calibration review** — ~~investigate whether `ip / 70` scaling is too generous for middle relievers.~~ Fixed: calibration IP threshold lowered to 20 for RPs (was 40). P75 regression shift added in Session 36, then removed in Session 38 (was inflating low-end RP projections 2-3×). RP regression now targets mean like all other positions. **Done Session 36, revised Session 38.**
- [x] **RP qualification threshold** — ~~current qualifying thresholds (IP≥40 or similar) may be too high for relievers, who pitch far fewer innings than starters.~~ Fixed: percentile pool uses 0.35 IP/team game for RPs (vs 0.7 for SP). Service time estimation now uses games-based fractional model (Session 39). **Done Session 31.**
- [x] **Positional surplus model calibration** — ~~run the same regression/analysis done for RPs for all positions.~~ Subsumed by league-calibrated model. Position-specific `OVR_TO_WAR` regression now covers all 9 buckets. `FV_TO_PEAK_WAR` split into hitter/SP/RP tables. **Done Session 32.**
- [x] **Scarcity curve refinement** — ~~position-blind scarcity.~~ Implemented position-adjusted scarcity with defense scaling. SS: +4, CF: +2, SP: +2, C/2B/3B: +1, COF/RP: -2, 1B: -3. Defense-dependent positions scale shift with PotDef rating (full at 70+, linear 50-70, zero below 50). **Done Session 34.**
- [x] **League-calibrated valuation model** — ~~build calibration pipeline deriving tables from league data.~~ Built `calibrate.py`: position-specific `OVR_TO_WAR` regression (9 buckets), derived `FV_TO_PEAK_WAR` (hitter/SP/RP), `ARB_PCT` from arb outcomes, `SCARCITY_MULT` from FA availability. Stored in `config/model_weights.json`, loaded by `constants.py` with fallback defaults. Runs automatically during refresh. **Done Session 32.**
- [x] **Data-driven scarcity model** — ~~compute scarcity from league data.~~ Subsumed by league-calibrated model. Sigmoid mapping from FA availability rate, 2-point Pot bands, monotonic enforcement, mid-season only. **Done Session 32.**
- [x] **MLB service time control model** — ~~current `_estimate_control()` uses qualifying season counting (AB≥100/IP≥40) as a proxy for service time.~~ Replaced with games-based fractional service time model. Uses role-adjusted denominators (hitters: g/162, SP: gs/32, RP: g/65) to compute fractional service years per season, summed across career. Pre-arb players use floor(svc); arb players use ceil(svc) to account for unobservable roster days. Age gates tightened: age ≥30 on min salary → veteran minor league deal. Affected 275 of 916 MLB players (225 gained control years, 50 lost). **Done Session 39.**
- [ ] **Pending contract extensions not captured** — ~~the StatsPlus API returns the current active contract but not pending extensions signed during the season.~~ Fixed: API does expose extensions via `/contractextension/`. Now pulled during refresh, stored in `contract_extensions` table, wired into surplus model, displayed on player Contract tab. **Done Session 40.**
- [ ] **Org overview scaffold** — automate the org overview report template pulling farm summary, roster summary, contracts, surplus rankings, extension priorities. Lower priority — report structure changes between evaluations.
- [ ] **Surplus model validation suite** — systematic validation of prospect and contract surplus models against real league data. Subtasks: (1) sanity-check top/bottom 25 prospects by surplus — do rankings match intuition? (2) cross-position trade equivalence — test model-fair swaps (FV 55 SP vs SS, FV 50 C vs 1B, elite RP vs mid SP) for smell test; (3) prospect→MLB crossover — compare AAA prospect value to same player's contract value after debut, check for discontinuities; (4) age sensitivity — verify younger prospects properly valued over older ones at same FV/Pot; (5) validate against actual league trades — run completed trades through calculator; (6) FA contract validation — compare $/WAR and market value projections to actual free agent signings; (7) SP/hitter arb salary spot-checks — extend the RP arb validation to other positions. **LOE: Medium.**
- [x] **Rookie-eligible players in prospect rankings** — ~~players with <100 MLB games should appear in top prospect lists.~~ Implemented: <130 career AB AND <50 career IP AND age ≤ 24. Appear in `prospect_fv` with level "MLB" and in all web prospect views. **Done Session 34.**
- [x] **Top 100 prospect audit — model tuning** — ~~Session 32 audit of the calibrated model's top 100 revealed several issues.~~ Fixed in Session 33: (1) position-specific FV→WAR for hitters (COF flood: 34→25), (2) flattened dev discount (AAA concentration: 81→60), (3) certainty cap at 1.0, (4) steeper age adjustment (4%/yr), (5) gap-scaled option value, (6) prospect age cutoff ≤24. **Done Session 33.**

---

## Web UI — Team Page

- [ ] **Playing time model edge cases** — current model is 77% within 100 PA, 92% within 200 PA across 4 test teams. Known gaps: (1) ~~two-way players excluded from hitter query~~ (fixed Session 23 — detected and shown on Hitters tab, but PT allocation for TW players may still be off); (2) utility players with <3 games at every position get sprayed across the diamond via ratings fallback (e.g. Meza on NYY); (3) DH-primary detection uses 50% batting-fielding gap threshold — teams that rotate DH duties without a primary DH leave the slot empty; (4) bench players squeezed below realistic PA when starter is a multi-position player claiming the slot (e.g. Ransaw behind Gentry); (5) **global position optimization** — model assigns positions per-player, not globally. Doesn't consider moving a starter to a different position to make room for a better overall lineup (e.g. Rockwell LF→RF to open LF for Pettit, gaining ~0.5 WAR total). Would require a constraint-satisfaction or linear-programming approach to maximize total team WAR across all positions simultaneously. **LOE: Low-Medium per item, High for #5.**
- [x] **Current-season surplus on team stats** — ~~hitter/pitcher stats tables show total contract surplus (all remaining years).~~ Now shows current-season surplus (this year's market value minus salary) via `surplus_yr1` column. **Done Session 36.**
- [ ] **Positional strength/weakness map** — starter Ovr + surplus vs league average at each position. **LOE: Medium.**
- [ ] **Pipeline view** — MLB starter → AAA depth → top prospect chain per position bucket. **LOE: Medium.**
- [ ] **Division rival comparison** — side-by-side surplus/farm/record for division teams. **LOE: Medium.**
- [ ] **Roster projection** — project next year's roster from contracts, arb estimates, FA departures. **LOE: High.**

---

## Web UI — League Page

- [x] **Trade review tab** — ~~interactive trade builder on the league page (Overview | Prospects | Trade). Org picker per side, filterable roster tables, player cards with surplus valuations, career outcome summaries for prospects, salary retention sliders, cash considerations, live trade balance with pessimistic/base/optimistic scenarios.~~ Implemented: full two-column trade builder with org picker (Side A defaults to user's team), level filters, name search, MLB + prospect roster tables, player cards with contract breakdown / career outcome details, retention sliders, cash considerations, live balance panel with verdict. Balance uses crossed scenarios (pessimistic = sent players overperform + received underperform) and mid-season pro-rating. Spec: `.kiro/specs/trade-review-tab.md`. **Done Session 37.**
- [ ] **Power rankings trend indicators** — store historical rank snapshots (per eval_date or game_date) and show ▲/▼/— movement arrows next to rank. Needs: new DB table or JSON file for rank history, delta calculation. **LOE: Medium.**
- [ ] **League news / milestone ticker** — horizontal strip between standings and power rankings showing notable milestones (e.g. "Player X: 3 HR from 50"). Needs: milestone detection logic from stats. **LOE: Medium-High.**
- [x] **Draft tab** — ~~amateur draft scouting and tracking tool on the league page.~~ Implemented: Draft tab (Overview | Prospects | Trade | Draft) with CSV pool upload, FV calculation tuned for draft prospects (Pot-weighted), JS-rendered table with All/Hitters/Pitchers views, individual position defense and pitch columns, color-graded ratings, prospect detail panel with StatsPlus-style grids, compare mode (checkbox side-by-side), draft pick tracking via API, My Picks panel, search/filter/hide-drafted. Spec: `.kiro/specs/draft-page.md`. **Done Session 40.**

### Draft Tab — Future Improvements
- [ ] **Split B/T into separate columns** — allow sorting/filtering by bats and throws individually. **LOE: Low.**
- [ ] **Pill displays** — use pill/badge styling for FV, Acc, W/E, Level columns for better visual scanning. **LOE: Low.**
- [ ] **Advanced filtering** — min/max threshold sliders per tool (e.g., "show power ≥ 55 with contact ≥ 45"). **LOE: Medium.**
- [ ] **Comparison diff view** — middle pane showing tool-by-tool deltas between two compared prospects. **LOE: Low.**
- [ ] **Post-draft grades** — team haul summaries after draft completion. **LOE: Medium.**

---

## Web UI — Player Page

- [ ] **Player development history chart** — chart showing rating trajectories over time using `ratings_history` snapshots (monthly in-game). Display current + potential for primary tools (hitter: cntct/gap/pow/eye/ks; pitcher: stf/mov/ctrl + individual pitches), ovr/pot headline, and extended ratings (babip/hra/pbabip) when available. Waiting for multiple snapshots to accumulate before building the UI. **LOE: Medium.**
- [ ] **Similar players / prospect comps** — ~~"Find Similar" button on player page. Two modes: (1) match any player's current ratings against others with similar profile for trade target identification; (2) match a prospect's Pot ratings against MLB players' current Ovr ratings to find ceiling comps.~~ Mode 2 (prospect comps) implemented in Session 40. Mode 1 (current-ratings trade target matching) deprioritized — surplus and trade tab already cover the use case. **Partially done Session 40.**
- [ ] **Player hover panel — extended ratings alignment** — ~~the player hover/side panel doesn't display correctly for leagues with extended ratings (BABIP, HRA, PBABIP, Prone). Layout should match the player card format used elsewhere.~~ Fixed: prospect side panel tool ordering and sub-rating styling now matches the player page. Defensive positions sorted by diamond order. **Done Session 40.**

---

## Web UI — Navigation

- [ ] **Global player search** — ~~site-wide search bar in the nav header (available on all pages). Reuses `/api/player-search` endpoint built for the trade tab. Typing a name shows autocomplete dropdown; selecting a result navigates to `/player/<pid>`.~~ Implemented: debounced search input in nav, dropdown with up to 15 results, keyboard navigation. **Done Session 40.**
- [ ] **Minor league team pages** — extend `/team/<id>` to affiliate team IDs (AAA/AA/A/etc.). Show notable prospects as player cards with at-a-glance overview (FV, key tools, age, level). Include a promotion/demotion indicator based on age-vs-level norms, ratings, and development trajectory — flag players who should be moving up or down the system. Stats data will be limited (API returns empty for minors), so lean on ratings and prospect data. **LOE: Medium-High.**

---

## Web UI — Visual Overhaul

- [ ] **Team logos** — add team logos to team pages and player pages. Source or generate logo assets for all 34 MLB teams. Display in page headers, standings, and anywhere team identity appears. **LOE: Low-Medium.**
- [ ] **UI overhaul exploration** — current layout is functional but generic. Investigate alternative visual styles, layouts, and design patterns to give the app more personality. Areas to explore: card-based layouts, data visualization (sparklines, heat maps, radar charts), typography, color palette refinement, dashboard density vs whitespace tradeoffs, inspiration from sports analytics sites (FanGraphs, Baseball Savant, etc.). No specific direction yet — this is an open-ended exploration task. **LOE: Medium-High.**

---

## Data & Research

- [ ] **Team vs team history** — head-to-head record lookup from the `games` table. Could be a standalone query function or CLI tool. Useful for beat reporter articles and rivalry context. **LOE: Low.**
- [x] **Transaction log** — ~~track trades, callups, DFA, waiver claims over time.~~ Investigated: StatsPlus API does not expose transaction data. Inferring from roster diffs is unreliable. **Shelved.**

---

## Long-term

- [ ] **Phase 2 — Interactive tools** — trade workbench, prospect explorer, free agent planner.
- [ ] **Phase 3 — AI assistant** — chat interface with league/team context.
- [ ] **Code architecture cleanup** — connection context manager, consistent row_factory, route-level error handling, test suite. Ongoing incremental work.
- [ ] **Stat/ratings divergence flag** — surface confidence signal when `stat_peak_war` and `peak_war_from_ovr` differ by >1.5 WAR in trade calculator output. Player page already shows over/underperformance; this extends it to trade evaluation context.
