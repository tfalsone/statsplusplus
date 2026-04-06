# Task List

Open work items. Completed items are in `docs/changelog.md`.

---

## Code Quality

- [ ] **Additional ratings scales** — Support 1-20 scale (maps to 20-80 in increments of ~3). Currently only 1-100 and 20-80 are supported; auto-detection checks if any rating exceeds 80. **LOE: Low.**

---

## Model & Data

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

- [ ] **Power rankings trend indicators** — store historical rank snapshots (per eval_date or game_date) and show ▲/▼/— movement arrows next to rank. Needs: new DB table or JSON file for rank history, delta calculation. **LOE: Medium.**
- [ ] **League news / milestone ticker** — horizontal strip between standings and power rankings showing notable milestones (e.g. "Player X: 3 HR from 50"). Needs: milestone detection logic from stats. **LOE: Medium-High.**

### Draft Tab — Future Improvements
- [ ] **Draft prospect ranking** — sort by `prospect_surplus` instead of FV. Partially done Session 43: surplus now computed in `_build_prospect`, board sorts by surplus, `$Val` column added. Remaining: review RP bucketing for draft-age arms. **LOE: Low.**
- [ ] **Sleeper/value flags — shelved.** Investigated during Session 43. The intuitive definition — "players others will let fall" — requires knowing how other GMs will rank prospects. In OOTP leagues, GMs primarily draft by Pot. Our FV model is heavily correlated with Pot (Pot is the primary input), so FV rank vs Pot rank deltas are mostly noise. The cases where they diverge (positional value, character modifiers, Acc=L penalty, RP vs SP) are real but sparse. For this to be genuinely useful, we'd need to replace game-generated Ovr/Pot with our own independent ratings model — at which point the divergence between our model and the game's Pot would be a meaningful signal. Not worth building on top of the current architecture. Specific actionable flags (Acc=L avoid, high-Pot RP trap) could still be added cheaply if desired.
- [ ] **Advanced filtering** — min/max threshold sliders per tool (e.g., "show power ≥ 55 with contact ≥ 45"). **LOE: Medium.**
- [ ] **Post-draft grades** — team haul summaries after draft completion. **LOE: Medium.**

---

## Web UI — Player Page

- [ ] **Player development history chart** — chart showing rating trajectories over time using `ratings_history` snapshots (monthly in-game). Display current + potential for primary tools (hitter: cntct/gap/pow/eye/ks; pitcher: stf/mov/ctrl + individual pitches), ovr/pot headline, and extended ratings (babip/hra/pbabip) when available. Waiting for multiple snapshots to accumulate before building the UI. **LOE: Medium.**

---

## Web UI — Navigation

- [ ] **Minor league team pages** — extend `/team/<id>` to affiliate team IDs (AAA/AA/A/etc.). Show notable prospects as player cards with at-a-glance overview (FV, key tools, age, level). Include a promotion/demotion indicator based on age-vs-level norms, ratings, and development trajectory — flag players who should be moving up or down the system. Stats data will be limited (API returns empty for minors), so lean on ratings and prospect data. **LOE: Medium-High.**

---

## Web UI — Visual Overhaul

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
