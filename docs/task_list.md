# Task List

Open work items. Completed items are in `docs/changelog.md`.

---

## Multi-League Support (Alpha Readiness)

Full spec: `docs/multi_league_spec.md`. Decisions log and implementation plan in §9-10.

### Layer 1 — Data Layer Refactor
- [x] **1.1 Directory structure + migration** — `data/emlb/` layout with symlinks, `data/app_config.json`, migration script at `scripts/migrate_to_multi_league.py`.
- [x] **1.2 Dynamic DB path** — `db.py` resolves DB from league directory via `league_context.get_league_dir()`. Falls back to legacy `emlb.db`.
- [x] **1.3 Dynamic league config** — `league_config.py` accepts `base_dir`, resolves settings/state from league directory.
- [x] **1.4 Dynamic StatsPlus client** — `client.py` decoupled from `.env`. Lazy credential resolution: `configure()` > `league_context` > `.env` fallback.
- [x] **1.5 Request-scoped league context** — Flask `before_request` populates `g` with league config. All query modules use `web_league_context` accessors. **LOE: High.** Sub-tasks:
  - [x] 1.5a: `web/web_league_context.py` helper module
  - [x] 1.5b: Refactor `queries.py`
  - [x] 1.5c: Refactor `team_queries.py`
  - [x] 1.5d: Refactor `player_queries.py`
  - [x] 1.5e: Refactor `percentiles.py`
  - [x] 1.5f: Update `app.py` routes and Jinja globals

### Layer 2 — League Structure Generalization
- [x] **2.1 `leagues` array in settings** — `leagues` array in `league_settings.json` with explicit league objects. `config.leagues` property with backward compat synthesis. `config.league_for_team()` helper.
- [x] **2.2 Dynamic standings grouping** — League route iterates `config.leagues` to build `league_groups`. Wild card computation per-league from the array.
- [x] **2.3 Dynamic leader splits** — Leader functions return `{"All": ..., "AL": ..., "NL": ...}` keyed by league short name. Template generates toggle buttons dynamically.
- [x] **2.4 Dynamic division colors and layout** — Inline `border-top` color from league config. Grid columns from division count. Removed `div-al`/`div-nl` CSS classes.

### Layer 3 — Settings & Onboarding UI
- [x] **3.1 Expanded settings page** — 6 sections: My Team, League Identity, League Structure (with JSON editor), Financial, Connection, Data. All settings readable and writable.
- [x] **3.2 Division structure editor** — JSON textarea editor under a `<details>` toggle. Validates JSON, rebuilds flat `divisions` for backward compat. Error display on invalid input.
- [x] **3.3 Onboarding wizard** — 4-step flow: Connect (slug + cookie verify) → Pull Data (runs refresh.py) → Configure (name + team) → Done. Creates league directory, writes initial config.
- [x] **3.4 League switcher** — Nav dropdown when >1 league exists. `/switch-league/<slug>` updates `app_config.json`. Hidden for single-league setups.
- [x] **3.5 Dynamic page title** — `<title>` and `<h1>` show league name from config. Context processor provides `league_name`.

### Layer 4 — Refresh Pipeline Updates
- [x] **4.1 League-aware refresh** — `refresh.py` uses `get_league_dir()` for DB, state, and league_averages paths. Year defaults to `config.year`. `ORG_ID` resolved dynamically.
- [x] **4.2 League-aware analysis scripts** — `fv_calc.py`, `farm_analysis.py`, `roster_analysis.py` use `get_league_dir()` for all data paths (DB, meta, history, tmp). Remaining scripts (`free_agents.py`, `player_utils.py`) work via symlinks.

### Layer 5 — Hardening
- [x] **5.1 Error handling for incomplete leagues** — `before_request` checks for `league.db` + `league_averages.json`; data routes redirect to `/settings` if missing. No-league state redirects to `/onboard`. Settings page shows warning banner. All `league_averages.json` reads use safe loader. Record count query guarded.
- [x] **5.2 Credential refresh flow** — Split Session ID / CSRF Token fields. "Test Connection" button tests protected endpoint. `CookieExpiredError` detection in client + refresh pipeline. Cookie instructions with DevTools walkthrough.
- [x] **5.3 Data validation after refresh** — Post-refresh table count checks. Warnings surfaced in refresh status message. Intermediate commit before ratings to preserve data on partial failure.

### Backlog — Post-Alpha
- [ ] **3.6 Settings page hardening** — Confirmation dialogs, input validation, backup before edits, team ID mismatch handling, read-only derived settings, undo support. **Deferred.**
- [ ] **3.7 Onboarding wizard resilience** — Step 2 GET-capable (resume on browser refresh), `beforeunload` warning during refresh, detect existing league directory on re-onboard and skip to appropriate step, `setup_complete` sentinel in state.json. **Deferred.**
- [ ] **3.8 Data wipe from settings** — Button in settings to wipe league data (delete `league.db`, clear config/history/tmp/reports) with confirmation dialog. Option for full wipe (all leagues + `app_config.json`) vs single-league wipe. After wipe, redirect to `/onboard`. **Deferred.**
- [x] **5.4 Ratings data integrity** — Two bugs found and fixed:
  - (a) `_upsert_ratings()` `row()` tuple order didn't match DB schema — 30 columns (positions 70-99) were rotated, putting character fields where numeric fields belonged and vice versa. Fixed `row()` order and switched to explicit named-column INSERT (immune to column order differences between fresh and migrated DBs).
  - (b) API sends duplicate `Ctrl_L` column (positions 70 and 73). Position 73 is actually overall Ctrl, mislabeled. Python's DictReader silently dropped the real Ctrl_L (position 70) and kept overall Ctrl. Fixed by renaming the duplicate to `Ctrl` in `_fix_ratings_header()`.
  - Added `ctrl` column to DB schema (overall control). Added 7 more previously-unstored API columns: `p`, `pot_p`, `stl_rt`, `run`, `sac_bunt`, `bunt_hit`, `hold`. DB migration via `_migrate_ratings()` in `init_schema()`.
  - Added header validation: `_fix_ratings_header()` compares the corrected header against `_RATINGS_EXPECTED_COLS` and prints a WARNING if the API adds, removes, or reorders columns.
  - All 14,960 ratings rows re-imported from saved CSV with correct column mapping. Verified: 38 fields spot-checked across 5 players (pitchers + hitters), all match API exactly. Zero bad bats/throws values, zero unexpected NULLs.
- [x] **5.5 Hardcoded path and data audit** — Fixed 3 hardcoded `BASE` paths: `free_agents.py` (league_averages.json), `player_queries.py` (scouting summaries), `queries.py` (prospects.json) — all now use `get_league_dir()` or `get_cfg().league_dir`. Added `Ctrl` (overall) to all ratings queries (`data.py`, `fv_calc.py`, `player_queries.py`, `percentiles.py`, `queries.py`). Updated all `ctrl = avg(ctrl_r, ctrl_l)` computations to prefer real `ctrl` column with fallback. Removed hardcoded "Anaheim Angels" from `farm_analysis.py` and `roster_analysis.py` docstrings/headers. Removed hardcoded team ID 44 fallback from `league_config.py`.
- [x] **5.6 Auto-populate league structure on onboard** — `_detect_league_structure()` in `refresh.py` auto-detects divisions and leagues from game history (pairwise game frequency clustering) and team stats API (division-grouped ordering, proper abbreviations). Detects 2 leagues (AL/NL), 6 divisions, assigns correct AL/NL labels using traditional team membership heuristic. Handles expansion teams with few games by assigning them based on API ordering position. Also populates `team_abbr` (from API, e.g. "ANA" not "ANG") and `team_names` (from API + teams table). Runs automatically at end of every `refresh_league()`. Fixes B.3, B.5, B.6.

---

## Bugs

- [x] **B.1 Prospect top-30 shows non-MLB teams** — Root cause: `mlb_team_ids` was derived from `team_abbr_map.keys()` which contained all 378 teams (including Korean, SA, Mexican, Cuban). Fixed by querying DB for teams with level=1 players. Centralized in `league_config.mlb_team_ids`.
- [x] **B.2 Top 100 prospects includes non-affiliated orgs** — Same root cause as B.1. Fixed by the same centralized `mlb_team_ids` change.
- [x] **B.3 Power rankings team abbreviations incorrect** — Root cause: onboarding generated abbreviations as `Nickname[:3].upper()` (e.g. "ANG" instead of "ANA") and stored all 378 teams. Fixed by 5.6: `_detect_league_structure()` now populates `team_abbr` from the team stats API which provides correct abbreviations (ANA, NYY, CWS, etc.), scoped to MLB teams only.
- [x] **B.4 League leaders highlight alignment shift** — Root cause: `.leader-hl` had `border-left: 2px solid var(--green)` which added 2px width to highlighted rows, shifting content right. Fixed by adding `border-left: 2px solid transparent` to all `.leader-row` and `.leader-hero` elements so highlighted and non-highlighted rows have identical box models.
- [x] **B.5 Batting/pitching leaders missing NL/AL toggles** — Root cause: empty `leagues` array in league_settings.json meant `_build_league_team_sets()` returned no league-specific sets, so only "All" was generated. Fixed by 5.6 auto-populating the leagues array.
- [x] **B.6 Team page shows full standings instead of division** — Root cause: empty `divisions` dict meant `team_div_map` was empty, so all teams had `div=""` and `get_division_standings()` returned nothing. Fixed by 5.6 auto-populating divisions.
- [x] **B.7 Leader card stat spacing** — Increased horizontal padding on `.leader-hero` and `.leader-row` from 10px to 12px for better breathing room between stat labels/values and the card edges, especially visible on highlighted rows.

---

## Model & Data

- [x] **ETA gap investigation** — ✅ Root cause: `_ETA` map used `.5` values with Python's `round()` (banker's rounding). `round(0.5)=0` collapsed AAA into 2033 (same as MLB), `round(1.5)=2` pushed AA to 2035, skipping 2034 entirely. Fixed by replacing with integer values (AAA=1, AA=2, A=3, etc.) across all 3 occurrences in `queries.py`. Now: AAA→2034 (40), AA→2035 (13), A→2036 (47).
- [ ] **Projection model reuse** — `projections.py` now has calibrated OPS+, ERA/FIP, WAR, and ratings interpolation models. Explore using these in: (1) prospect pages — show projected MLB stat lines at current and future development stages, (2) draft evaluation — project draft prospect ratings into expected MLB production, (3) trade calculator — replace or supplement surplus model with projected stat lines for more intuitive valuation, (4) farm analysis — add projected stat context to scouting summaries. **LOE: Varies per integration.**
- [ ] **Payroll Adjusted Performance (PAP) score** — rate MLB players on a 1-10 scale (two decimal places) measuring current-year value efficiency. Scale: 0-2 negative returns, 3-4 below market, 5 market neutral, 6-7 above average, 8-9 elite, 10 generational efficiency. Related to surplus but single-year and condensed to a digestible score. Likely non-linear — needs investigation into the right curve shape (log, sigmoid, piecewise, etc.) to make the scale feel right across the full range. **LOE: Medium.**
- [ ] **Career outcome probability chart (prospects)** — on prospect pages, show a distribution chart with buckets for prime WAR/season outcomes and the player's probability of landing in each. Include a confidence meter indicating projection reliability (driven by age, level, scouting accuracy, rating spread). Builds on existing FV/surplus projection model but presents a more granular probabilistic view. **LOE: Medium-High.**
- [x] **Two-way player WAR** — ✅ `stat_peak_war()` now combines batting + pitching WAR per year for two-way players. `load_stat_history()` already detected them; now the set flows through `contract_value()` and `fv_calc.py`. Cowgill surplus: $170.8M → $210.1M.
- [ ] **RP WAR calibration review** — investigate whether replacement-to-average level relievers are being overvalued in projections. The current model uses `ip / 70` scaling which may be too generous for middle relievers who accumulate innings without high leverage. Consider adjusting for leverage, role (setup vs mop-up), or applying a steeper WAR discount for sub-replacement-level stuff. **LOE: Medium.**
- [x] **Two-way player display** — ✅ Player page uses Pitcher/Hitter toggle that swaps the entire view (ratings, stats snapshot, percentiles) between pitcher and hitter modes. Reuses existing macros via `tw-pit`/`tw-hit` CSS wrappers. Popup shows batting tools + stat line for two-way pitchers. Roster hitters tab includes two-way pitchers (PA≥30) with fielding position. TW badge on roster tabs. Depth chart two-way support deferred (playing time model).
- [ ] **Org overview scaffold** — automate the org overview report template pulling farm summary, roster summary, contracts, surplus rankings, extension priorities. Lower priority — report structure changes between evaluations.

## Web UI — Team Page

- [x] **Roster rework** — ✅ Replaced single Roster tab with separate Hitters and Pitchers tabs. Split toggle (Overall/vs L/vs R), rich stat columns, conditional formatting vs league avg, column separators, tooltips. Organization tab deferred.
- [ ] **Organization tab** — new tab on team page for cross-level org data: surplus leaders (MLB + farm combined), position depth summary (MLB starter + top prospect per bucket), payroll overview. Deferred from roster rework. **LOE: Medium.**
- [ ] **Depth chart** — visual MLB depth chart by position with 3-year projections. Tasks: (1) ✅ OPS+/ERA/FIP regression models, (2) ✅ projection utilities, (3) ✅ roster availability, (4) ✅ query function `get_depth_chart()`, (5) ✅ template + CSS, (6) ✅ route wiring, (7) ✅ visual polish (inline stats, age, year tabs, backup trimming, RP roles, departed chips, legend). Remaining: SVG/card alignment (see Visual Overhaul). **LOE: Low.**
- [ ] **Playing time model edge cases** — current model is 77% within 100 PA, 92% within 200 PA across 4 test teams. Known gaps: (1) two-way players (role=11 pitchers who bat/field, e.g. Cowgill) excluded from hitter query — need to detect from fielding/batting data regardless of role; (2) utility players with <3 games at every position get sprayed across the diamond via ratings fallback (e.g. Meza on NYY); (3) DH-primary detection uses 50% batting-fielding gap threshold — teams that rotate DH duties without a primary DH leave the slot empty; (4) bench players squeezed below realistic PA when starter is a multi-position player claiming the slot (e.g. Ransaw behind Gentry); (5) **global position optimization** — model assigns positions per-player, not globally. Doesn't consider moving a starter to a different position to make room for a better overall lineup (e.g. Rockwell LF→RF to open LF for Pettit, gaining ~0.5 WAR total). Would require a constraint-satisfaction or linear-programming approach to maximize total team WAR across all positions simultaneously. **LOE: Low-Medium per item, High for #5.**
- [ ] **Positional strength/weakness map** — starter Ovr + surplus vs league average at each position. **LOE: Medium.**
- [ ] **Pipeline view** — MLB starter → AAA depth → top prospect chain per position bucket. **LOE: Medium.**
- [ ] **Division rival comparison** — side-by-side surplus/farm/record for division teams. **LOE: Medium.**
- [ ] **Roster projection** — project next year's roster from contracts, arb estimates, FA departures. **LOE: High.**

## Web UI — League Page

- [x] **League overview page overhaul** — ✅ Two-column layout (standings+power left, leaders right). Standings as 2×3 division card grid with PCT bars, 1st/WC badges, AL/NL color-coded top borders, muted eliminated teams. Power rankings scrollable with score heatmap bars. Hero leader cards with #1 featured. League vitals KPI cards (AVG, ERA, OPS, $/WAR). User team highlighted globally. Responsive breakpoint at 1100px.
- [ ] **Power rankings trend indicators** — store historical rank snapshots (per eval_date or game_date) and show ▲/▼/— movement arrows next to rank. Needs: new DB table or JSON file for rank history, delta calculation. **LOE: Medium.**
- [ ] **League news / milestone ticker** — horizontal strip between standings and power rankings showing notable milestones (e.g. "Player X: 3 HR from 50"). Needs: milestone detection logic from stats. **LOE: Medium-High.**
- [x] **Prospects tab** — ✅ dedicated tab on the league page. Top 100 with search + team filter (preserves original ranks), Top 30 by Team, Top 10 by Position (merged OF bucket). Level dots, FV color coding, full team names, conditional columns. Dropdown-as-tab pattern for team/position views.
- [x] **Stat leaders overhaul** — ✅ Panel layout + MLB/AL/NL toggle. Remaining: improve selector UI — buttons need clearer visual association with the panels they control. Fold into UI overhaul. **LOE: Low.**
- [x] **Prospects tab polish** — ✅ Filter bar moved inside `prospect-table-wrap` so right edge aligns with table. ETA styling (current year bold white, far-future muted).

## Web UI — Game History

(Record breakdown complete. No remaining items.)

## Data & Research

- [ ] **Team vs team history** — head-to-head record lookup from the `games` table. Could be a standalone query function or CLI tool. Useful for beat reporter articles and rivalry context. **LOE: Low.**
- [ ] **Transaction log** — track trades, callups, DFA, waiver claims over time. StatsPlus API may not expose this directly; needs feasibility research. Would enable narrative context in articles and roster analysis. **LOE: Unknown — research needed.**

## Web UI — Player Page

- [ ] **Similar players / prospect comps** — "Find Similar" button on player page. Two modes: (1) match any player's current ratings against others with similar profile (same bucket, similar Ovr, tool shape) for trade target identification; (2) match a prospect's Pot ratings against MLB players' current Ovr ratings to find ceiling comps with real stat lines, giving concrete production expectations. Uses ratings table league-wide. **LOE: Medium.**

## Web UI — Navigation

- [ ] **Minor league team pages** — extend `/team/<id>` to affiliate team IDs (AAA/AA/A/etc.). Show notable prospects as player cards with at-a-glance overview (FV, key tools, age, level). Include a promotion/demotion indicator based on age-vs-level norms, ratings, and development trajectory — flag players who should be moving up or down the system. Stats data will be limited (API returns empty for minors), so lean on ratings and prospect data. **LOE: Medium-High.**

## Web UI — Visual Overhaul

- [x] **Player popup on hover** — ✅ Lightweight tooltip on any player-link hover. Shows bio, ratings snapshot (color-coded grades), stats, surplus. AJAX with client-side cache. Works on all pages.
- [x] **Prospect side panel** — ✅ slide-out panel with grade bars, pitches, defense, velocity, scouting summaries. Click player name → AJAX fetch → panel renders.
- [ ] **Depth chart SVG alignment** — position cards overlap base markers on the diamond SVG. The SVG coordinate system and CSS pixel positions don't map 1:1. Needs investigation with browser dev tools to find correct offsets. **LOE: Low.**
- [ ] **Team logos** — add team logos to team pages and player pages. Source or generate logo assets for all 34 MLB teams. Display in page headers, standings, and anywhere team identity appears. **LOE: Low-Medium.**
- [ ] **UI overhaul exploration** — current layout is functional but generic. Investigate alternative visual styles, layouts, and design patterns to give the app more personality. Areas to explore: card-based layouts, data visualization (sparklines, heat maps, radar charts), typography, color palette refinement, dashboard density vs whitespace tradeoffs, inspiration from sports analytics sites (FanGraphs, Baseball Savant, etc.). No specific direction yet — this is an open-ended exploration task. **LOE: Medium-High.**

## Long-term

- [ ] **Phase 2 — Interactive tools** — trade workbench, prospect explorer, free agent planner.
- [ ] **Phase 3 — AI assistant** — chat interface with league/team context.
- [ ] **Multi-league support** — ✅ Core implementation complete (Layers 1-5). Remaining: backlog items 3.6, 3.7, 3.8, 5.5, 5.6.
- [ ] **Code architecture cleanup** — connection context manager, consistent row_factory, route-level error handling, test suite. Ongoing incremental work.
- [ ] **Stat/ratings divergence flag** — surface confidence signal when `stat_peak_war` and `peak_war_from_ovr` differ by >1.5 WAR in trade calculator output. Player page already shows over/underperformance; this extends it to trade evaluation context.
