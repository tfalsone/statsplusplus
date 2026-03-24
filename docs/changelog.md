# Changelog

Completed and deferred work items, organized by session. Moved from `task_list.md` to keep the task list focused on pending work.

---

## Session 33 (2026-03-23)

### Top 100 Prospect Model Tuning
Session 32 audit found four issues: COF flood (34/100), AAA concentration (81/100), inflated surplus values, and safe-over-ceiling bias. This session addressed all four with six changes.

- **Position-specific FV→WAR for hitters** — `calibrate.py` now derives per-bucket hitter tables (`FV_TO_PEAK_WAR_BY_POS`) instead of averaging all hitter positions. COF FV 50 → 3.0 WAR (was 3.3), SS → 3.6, CF → 3.9, C → 2.9. Stored in `model_weights.json`, loaded by `constants.py`, used by `prospect_value.py` `peak_war()`. Directly addresses COF flood and inflated surplus values.
- **Flattened development discount** — AAA: 0.88 (was 0.90), AA: 0.78 (was 0.75), A: 0.68 (was 0.60), Rookie: 0.45 (was 0.38), Intl: 0.35 (was 0.25). Old curve dropped too steeply below AAA, causing 81/100 to be AAA. The AA and A increases are the biggest drivers — high-ceiling A-ball arms were being penalized 33% vs AAA.
- **Certainty multiplier capped at 1.0** — Was up to 1.15x for maxed prospects (Ovr/Pot near 1.0). This double-counted AAA proximity since those players already benefit from higher dev discount and lower time-value discount.
- **Steeper age adjustment** — 4%/yr (was 3%) for young-for-level bonus and old-for-level penalty. Targeted lift for young A-ball prospects without changing AAA values (already at 0.95 cap).
- **Gap-scaled option value** — Upside probabilities now scale with the Pot-FV gap in addition to youth. `gap_factor = min(1.0, (pot - fv) / 25)` boosts p_mid and p_ceil for high-ceiling prospects. Ceiling FV cap removed (was 70, now uncapped). A Pot 80 / FV 50 player gets ~30% base / 45% mid / 25% ceiling probabilities (was 42/40/18).
- **Prospect age cutoff lowered to 24** — 25yo minor leaguers are MLB-bubble players, not prospects. `fv_calc.py` now excludes age 25+. Added `DELETE` before `INSERT` to clear stale rows.

**Results** (VMLB top 100):
| Metric | Before | After |
|---|---|---|
| COF count | 34 | 25 |
| AAA count | 81 | 60 |
| A-ball count | 4 | 19 |
| Age ≤ 20 | 7 | 17 |
| #50 surplus | $94.7M | $81.8M |
| #100 surplus | $75.8M | $65.1M |

Key prospect movement: Ricky Sanchez (A 1B, 18, Pot 80) #29→#4, Honor Lara (A COF, 17, Pot 80) #44→#9, Alex Rodriguez (A SP, 19, Pot 68) >100→#59, Angelo Rivera (AA SP, 20, Pot 55) >100→#87.

### Bug Fixes
- **Refresh button race condition** — Navigating during a refresh showed the green ✓ badge instead of the spinner. Root cause: `/api/game-date` and `/refresh/status` fired in parallel on page load; the game-date response overwrote the spinner because `state.json` updates early in the pipeline. Fix: added `refreshRunning` flag, sequenced the checks so sync badge only renders when no refresh is active.
- **Cross-league stale date indicator** — After switching leagues, the refresh button showed stale (!) because `/api/game-date` was still querying the previous league's StatsPlus API. The client retained the old league's slug. Fix: `api_game_date` now configures the client with the current league's `statsplus_slug` before each call.

---

## Session 32 (2026-03-23)

### League-Calibrated Valuation Model
- Built `scripts/calibrate.py` — derives league-specific valuation tables from actual data instead of hand-tuned constants. Produces `config/model_weights.json` with position-specific `OVR_TO_WAR`, `FV_TO_PEAK_WAR` (hitter/SP/RP), `ARB_PCT`, and `SCARCITY_MULT`.
- **OVR_TO_WAR**: Position-specific Ovr→WAR regression from 3 years of data (2030-2032). 9 buckets (C, SS, 2B, 3B, CF, COF, 1B, SP, RP) with 53-355 seasons each. Falls back to grouped hitter regression when N < 40. Key findings: SS produces 4.44 WAR at Ovr 60 vs C 3.69 vs COF 3.70 — old generic table said 3.2 for all. SP produces 2.96 at Ovr 60 (old: 2.8). RP close to old values.
- **FV_TO_PEAK_WAR**: Derived from OVR_TO_WAR by mapping FV+5 to expected peak Ovr. Now has separate hitter, SP, and RP tables. FV 45 hitter = 2.6 WAR (was 1.2), FV 50 SP = 2.5 (was 2.0). Old table was calibrated for a different league and significantly undervalued mid-tier prospects.
- **ARB_PCT**: Calibrated from 104 arb-eligible players. Arb 1: 21% (was 20%), Arb 2: 18% (was 22%), Arb 3: 34% (was 33%). Minor changes.
- **SCARCITY_MULT**: Sigmoid-based mapping from FA availability rate to scarcity. Uses 2-point Pot bands for smoothing, monotonic enforcement. Mid-season only (offseason FA pool is flooded). Pot 40: 0.0, Pot 42: 0.03, Pot 44: 0.44, Pot 46: 0.97, Pot 50: 1.0.
- `constants.py` now loads from `model_weights.json` when present, falling back to hardcoded defaults. New exports: `FV_TO_PEAK_WAR_SP`, `OVR_TO_WAR_CALIBRATED`.
- `player_utils.py` `peak_war_from_ovr()` uses position-specific calibrated tables when available.
- `prospect_value.py` `peak_war()` uses SP-specific FV→WAR table for starting pitchers.
- `refresh.py` runs calibration before fv_calc in the refresh pipeline. Calibration failure is non-fatal (logs warning, uses defaults).
- Key value changes: Mead $68.2M → $100.5M, Teschler $67.5M → $83.8M, Showalter $49.2M → $86.9M, Jobe $32.6M → $71.6M. Increases driven by calibrated FV→WAR tables showing mid-tier players produce more WAR than old hand-tuned constants assumed.

### Veteran Decline Ratings Blend
- Victor Robles (Ovr 44, age 36, COF) showed $25.9M surplus despite being a clearly declining player. Root cause: his `stat_peak_war` of 3.31 was propped up by a 5.3 WAR season from 2030, and his worst recent season (2032: -0.1 WAR, 125 AB) was excluded for falling below the 130 AB qualifying threshold. The model had no downward blend for veterans — it only blended ratings upward for young players.
- **Fix**: Added declining veteran ratings blend in `contract_value.py`. For players past age 31 (30 for pitchers) where stat WAR exceeds ratings WAR, blends toward ratings. Weight scales with both age past peak and gap size (`age_w × gap_ratio`, capped at 0.75). Small gaps at age 32 get minimal correction; large gaps at age 36+ get aggressive correction.
- Robles: $25.9M → $16.4M (projected WAR: 3.31 → 2.25). Other affected players: Acuna ($2.0M), Julio Rodriguez ($11.2M), Adames ($7.2M) — all now more reasonable.

### Top 100 Prospect Audit (findings only — no code changes)
- **COF flood**: 34 of top 100 are COF (42 total OF). Model doesn't penalize positional replaceability — a Pot 53 COF ranks alongside scarcer positions.
- **AAA concentration**: 81 of 100 in AAA, only 4 in A-ball, 0 in Rookie/Intl. Development discount may be too steep for lower levels, or model over-rewards MLB proximity.
- **Surplus values feel high**: #100 at $75.8M, #50 at $94.7M. Driven by calibrated FV→WAR tables — FV 45 hitters now map to 2.6 WAR peak. Needs validation: do FV 45 prospects actually reach 2.6 WAR?
- **FV 50 clustering**: 48 of 100 are FV 50 with huge surplus spread ($121M to $76M). FV system may not differentiate enough in the middle tier.
- **No RPs**: RP FV discount working as intended — 0 RPs in top 100.
- Added findings to task list for next session.

---

## Session 31 (2026-03-23)

### Surplus Model Validation — Scarcity Recalibration
- Systematic validation revealed the original scarcity curve (from Session 30) was too gradual — didn't reach 1.0 until Pot 65, while FA availability data shows 0% availability at Pot 49+.
- **Fix (iteration 1)**: Steeper ramp: `{40: 0.0, 43: 0.10, 45: 0.30, 47: 0.60, 49: 0.85, 50: 1.0}`. Fixed the bottom end but created a cliff at Pot 48-50 (28% penalty for 2-point Pot difference).
- **Fix (iteration 2)**: Smoothed S-curve: `{40: 0.0, 42: 0.05, 44: 0.20, 45: 0.35, 46: 0.55, 47: 0.75, 48: 0.92, 49: 1.0}`. Reaches 1.0 at Pot 49 to reflect scouting fog of war — 1-2 point Pot differences are within noise. No single-point cliffs anywhere.
- Validated with fog-of-war test: Pot 48 vs 49 is only 8% swing (was 15%+ before). Pot 48 vs 50 is 8% (was 28%).
- Key prospect impact: Jobe (Pot 49) +18%, Donovan (Pot 48) +27%, Neely (Pot 47) +25%. High-ceiling unchanged.

### Surplus Model Validation — Realization Blend
- Crossover analysis showed maxed-out prospects (Ovr ≈ Pot) had a discontinuity: prospect surplus was 0.36x of MLB contract value for hitters and 1.31x for RPs at the same grade.
- Root cause: `FV_TO_PEAK_WAR` assumes further development, but maxed players have already reached their ceiling. Their peak WAR should equal their current production (from `OVR_TO_WAR`).
- **Fix**: When `ovr/pot` realization exceeds 0.7, blend `peak_war(fv)` with `peak_war_from_ovr(ovr)` using a squared weight curve. At realization 1.0 (fully maxed), uses 100% OVR→WAR. At 0.7 (still developing), uses 100% FV→WAR. Only applies when OVR→WAR < FV→WAR (downward adjustment only).
- Crossover ratios now 0.79-0.86x across all positions at Pot 50+ (was 0.36-1.31x). Developing players (realization < 0.7) completely unaffected.

### Trade Scenario Analysis — 3B Upgrade
- Evaluated 3B trade targets for the Rays (team 57, 40-33) from seller/fringe teams.
- Identified key targets: Eric Elwood (CLE, Ovr 64, 3B:65, $130M+ with extension), Andy Tatum (STL fire sale, Ovr 53, 3B:65, $65.5M), Kris Williamson (BAL fringe, Ovr 56, 3B:55, $80.3M), Bobby Butler (LAA, Ovr 58, 3B:45, $47.6M), Pat Clark (MIN rental, Ovr 70, $31.5M).
- Elwood has a 10yr/$136M extension not captured by the API — manually modeled at $261.5M surplus (vs $130.4M without extension). Effectively untradeable.
- Tatum best package: Teschler straight up ($67.5M, 1-for-1 avoids consolidation tax) or Woods + Showalter + filler (~$65-66M, needs ~10-15% overpay for 3-for-1).

### Data Gap — Pending Contract Extensions
- Discovered that the StatsPlus API returns only the current active contract, not pending extensions signed during the season. Elwood showed as 1yr/$610K pre-arb when he actually has a 10yr/$136M extension. Added to task list.

### RP FV Positional Discount
- FV grades were too generous to RPs — 102 RPs earned FV 45+ (23.8% of all ranked prospects), vs ~3-5% in real baseball prospect lists. A Pot 55 RP got the same FV as a Pot 55 COF despite producing far less WAR.
- **Fix**: Before FV calculation, RP Pot is scaled to 80% of raw value. A Pot 55 RP now has effective Pot 44, dropping from FV 45+ to FV 40. Only elite RPs (Pot 70+) reach FV 50.
- League-wide RPs at FV 45+: 102 → 26 (7.4%). Top 100 by FV: 4 RPs → 3 RPs.
- Surplus uses the raw (undiscounted) FV to avoid double-counting with the RP-specific WAR table. `fv_calc.py` computes raw FV separately for RPs and passes it to `prospect_surplus_with_option`.

### Valuation Model Documentation
- Created `docs/valuation_model.md` — plain-language explanation of how FV grades, prospect surplus, and MLB contract surplus work. Covers the full pipeline from ratings to trade value without requiring code reading.

### Positional WAR Regression (investigation only — no code changes)
- Ran Ovr→WAR regression by position bucket using 2031-2033 data (61-491 seasons per bucket).
- Generic hitter table is a poor fit: at Ovr 65, SS produces 5.47 WAR vs COF 3.51 vs C 2.97 — model says 4.5 for all. SS slope (0.217) is 2x COF slope (0.119).
- SP table overestimates at high OVR: actual 3.0 at Ovr 65 (model 4.0), actual 3.5 at Ovr 70 (model 5.5). Likely calibrated against a different league.
- RP table is close (0.86-0.95x across Ovr 50-70).
- Conclusion: constants were likely tuned for a different league. Added league-calibrated valuation model to task list as the proper fix rather than hand-tuning for VMLB.

### RP Service Time Fix
- `_estimate_control()` in `contract_value.py` used IP >= 40 for all pitchers to count qualifying seasons. RPs were being undercounted by 1-4 service years because they rarely reach 40 IP in a season.
- **Fix**: RPs (detected by bucket) now use IP >= 20 threshold. Passed `bucket` parameter to `_estimate_control()`.

### Pitcher Percentile Qualification Thresholds
- Percentile pool used a single IP threshold (0.5 × team_games) for all pitchers. RPs with a full workload (e.g. 34 IP mid-season) were flagged as "small sample."
- **Fix**: Split thresholds — SP uses 0.7 × team_games (55 IP), RP uses 0.35 × team_games (27 IP). RP detected by GS/G ratio < 0.25. SPs below the higher threshold correctly show as small sample even if they're in the broader pool.

### Pitcher BABIP Expected — Regression Model
- Pitcher BABIP expected percentile was using rating percentiles from the MLB pool. The pbabip rating distribution is extremely compressed (stdev 3.3, range 45-70) — a 50 rating showed as 4th percentile because 96% of MLB pitchers have pbabip ≥ 50 (survivorship bias).
- **Fix**: Replaced rating percentile with a regression model: `expected_BABIP = 0.439 - 0.0028 × pbabip` (r=-0.18, from 362 qualifying seasons). Maps the rating to an expected BABIP value, then percentile-ranks that against the stat pool. pbabip 50 → .299 expected (≈44th percentile). McKeever (.333 actual) now correctly tagged "unlucky."

---

## Session 30 (2026-03-23)

### Ratings Scale Support (20-80 / 1-100)
- Leagues using OOTP's 20-80 scouting scale (tools in 5-point increments, OVR/POT in single increments) were being double-normalized by `norm()`, which assumed 1-100 raw input. This compressed tool grades toward the center (80→70, 70→60, 35→40) and caused incorrect defensive bonuses, critical tool floor penalties, and OPS+/BABIP projections.
- **Fix**: `norm()` in `player_utils.py` is now scale-aware via lazy config detection. On 20-80 leagues, it passes values through unchanged (clamp + round to 5). On 1-100 leagues, behavior is unchanged.
- **Fix**: `projections.py` `project_ops_plus()` converts 20-80 inputs to 1-100 equivalent before applying regression coefficients calibrated on 1-100 data.
- **Fix**: `percentiles.py` BABIP expected model handles both scales for direct rating conversion and regression fallback.
- **Fix**: Platoon split thresholds in `calc_fv` now use `norm()` for scale-independent comparison.
- Added `ratings_scale` setting to `league_settings.json`, `league_config.py`, settings page, and onboarding wizard. Defaults to `"1-100"` for backward compatibility.
- FV grades themselves are minimally affected (driven by Ovr/Pot which were already correct) but display grades, OPS+ projections, and BABIP models are now accurate.

### Prospect Scarcity Multiplier
- FV 40-45 prospects (replacement-level depth) were valued at $16-29M surplus despite being freely available on waivers. A FV 45 RP prospect (Fisher, Ovr 43) was valued at $28.9M — on par with Chris Brown (Ovr 75 MLB RP, $28.1M). No GM would make that swap.
- **Fix**: New `SCARCITY_MULT` table in `constants.py` applies a non-linear multiplier to prospect surplus based on Pot (ceiling). Derived from MLB talent distribution data: Ovr 45-49 players comprise 35% of MLB rosters (abundant), while Ovr 65+ are <3% (scarce).
- Table: `{40: 0.0, 45: 0.15, 50: 0.45, 55: 0.70, 60: 0.90, 65: 1.0}` — interpolated for intermediate values.
- Uses Pot rather than FV so developing players (e.g. 40 Ovr / 65 Pot) are valued for their ceiling, not current ability. A maxed-out 43/43 gets 0.09x; a raw 40/65 gets 1.0x.
- Applied in `prospect_value.prospect_surplus()` alongside dev_discount and certainty_mult.
- Prospect surplus breakdown now applies combined multiplier to per-year surplus so rows sum to the total. Market value and salary stay raw. Discount math shown below the table on player pages.
- Fisher: $28.9M → $2.6M. Mead (40/65): $42.5M → $68.2M (Pot-based scarcity + option value).

### Extended Ratings Bug Fix
- Player pages crashed with `no such column: babip` on leagues without extended rating columns (BABIP, HRA, PBABIP, Prone). Root cause: `player_queries.py` hardcoded extended column names in SELECT; `percentiles.py` did the same for BABIP expected model and pitcher percentile ratings.
- **Fix**: `player_queries.py` switched from explicit column list + tuple unpack to `SELECT *` + dict access. Missing columns return `None` via `.get()`. All downstream code already guarded with `if X is not None`.
- **Fix**: `percentiles.py` conditionally includes extended columns using `has_extended_ratings()` helper, falls back to `NULL` when absent.
- **Fix**: `web_league_context.py` added `has_extended_ratings()` — checks `PRAGMA table_info(ratings)` for `babip` column, cached per request.
- **Fix**: `refresh.py` added backfill step in `_upsert_ratings()` — updates extended columns on existing rows when incoming API data has them but DB values are NULL. Fixes leagues where rows were inserted before 126-col format support was added.

### RP Surplus Model Calibration
- Regression analysis on 1,582 qualifying RP seasons (IP≥20, GS≤3) revealed three model problems:
  1. `RP_WAR_CAP=2.0` flattened FV 50–80 RPs to identical surplus ($63.3M each)
  2. `REPLACEMENT_WAR=1.0` threshold created an $8.4M cliff, zeroing out sub-1.0 WAR control years
  3. FV 45 peak WAR (1.2) was too high vs actual data (median 0.5 WAR for Ovr 48 RPs)
- **Data findings**: 80 Ovr RPs average 1.9 WAR vs 0.6 for 50 Ovr (3x ratio). Only 10 RPs league-wide are 70+ Ovr (0.2%). Linear fit: WAR = -1.37 + 0.040 × Ovr (R²=0.15).
- **Fix 1**: New `FV_TO_PEAK_WAR_RP` table in `constants.py` — scales from 0.5 (FV 40) to 3.2 (FV 80). Replaces flat `RP_WAR_CAP`. `prospect_value.peak_war()` selects RP table when `bucket=="RP"`.
- **Fix 2**: Smooth market value ramp in `prospect_value._market_value()` — linear interpolation from league minimum at 0 WAR to full `war × $/WAR` at 1.0 WAR. Replaces binary cliff at `REPLACEMENT_WAR=1.0`.
- **Fix 3**: Removed `RP_WAR_CAP` from `contract_value.py`, `projections.py`, `fv_calc.py`, `player_utils.py`. RP WAR for MLB players was already handled by `OVR_TO_WAR` table's RP column.
- **Result**: FV 50 RP $37M, FV 60 $63M, FV 70 $83M (was all $63M). FV 40 now $16M (was $0). FV 45 stable at $25M.
- Removed `RP_WAR_CAP` and `REPLACEMENT_WAR` constants.

### Young Player Ratings Blend
- `contract_value.py` previously used `stat_peak_war` as the sole WAR projection when stats were available, ignoring ratings entirely. For young players whose Ovr-based WAR significantly exceeds their stat WAR (e.g. Chris Brown: Ovr 75 → 2.0 WAR ratings, 1.28 WAR stats), this undervalued them and triggered premature non-tender via the arb salary gate.
- **Fix**: When `ratings_war > stat_war` and the player is below peak age (27 pitchers, 28 hitters), blend the two projections. Ratings weight fades linearly from 50% at age 21 to 0% at peak age. Only applies upward (ratings > stats) — stat underperformance relative to ratings is treated as unrealized potential, not the other way around.
- Chris Brown: $9.3M → $16.8M (2yr → 3yr control, WAR 1.28 → 1.64).

### RP Arb Salary Model
- The generic arb salary model (exponential in Ovr with 0.80x RP discount) dramatically overprojected RP arb salaries — e.g. Ovr 61 RP 3rd arb: model $12M vs game $3.8M. This triggered premature non-tender, cutting control years short.
- **Fix**: RP-specific arb model calibrated from 35 actual RP arb contracts. Uses separate exponential (`566K × e^(0.0294 × Ovr)`) with 25% annual raises instead of the generic additive raise model. Non-RP arb model unchanged.
- Gaytan (Ovr 61): $22.3M → $35.2M (4yr → 5yr control, 3rd arb $4.3M vs game $3.8M).

---

## Session 29 (2026-03-23)

### Task List Cleanup
- Pruned `task_list.md` to open items only. Removed all completed multi-league tasks (Layers 1–5, hardening 5.1–5.6), all resolved bugs (B.1–B.7), and all shipped web UI features (roster rework, depth chart, league overview, prospects tab, stat leaders, player popup, prospect side panel, two-way player support, ETA gap fix). Removed stale "remaining: 5.5, 5.6" note from long-term multi-league entry. All completed items were already recorded in the changelog from their respective sessions.
- Confirmed depth chart SVG alignment is resolved — card positions and SVG coordinates are well-tuned. Removed from task list.

### Organization Tab
- New **Organization** tab on team page — cross-level org summary in one view.
- **Position Depth table** — rows for C/1B/2B/3B/SS/LF/CF/RF plus SP 1-5 and RP top 3. Each row shows: league rank (color-coded pill on first row per position group), MLB player (name, age, color-coded Ovr, WAR, surplus), and top prospect (pos, name, age, FV badge, level badge, surplus). One prospect per position; SP shows 5, RP shows 3. OF prospects labeled with specific field position (LF/CF/RF) instead of generic OF. Prospects deduplicated across positions (each player appears once). SP/RP sorted by Ovr; prospects sorted by FV then surplus. SP/RP section separated by top border. Level badges reuse league prospects tab styling (AAA blue, AA green, A yellow, lower gray). Reuses `_league_pos_rankings()` from depth chart for rank data.
- **Surplus Leaders** — top 20 combined MLB + Farm players sorted by surplus. Level badges (MLB/AAA/AA/A/etc.) using existing `lvl-badge` styles plus new `lvl-mlb` class.
- **Retention Priorities** — players with ≤2 years of team control and positive surplus. Multi-year contracts use contract years remaining; 1-year contracts use `_estimate_control()` for arb/pre-arb estimation. Shows control years remaining. Positioned alongside position depth in a two-column grid layout.
- **Committed Payroll** — 4-year horizon bar chart showing total committed dollars per year. Reuses `get_payroll_summary()`.
- **Layout**: top row is position depth (wide) + retention priorities (narrow) side by side. Bottom row is surplus leaders + payroll bars in two columns.
- New `get_org_overview(team_id)` query function in `team_queries.py`. Re-exported via `queries.py`.
- **Ovr tier coloring consolidated** — moved duplicated Ovr/Pot tier coloring JS from `player.html` and `team.html` into `base.html`. Now runs globally on all pages. Single source of truth for the color palette.
- CSS: `.org-top` grid, `.org-depth-panel`/`.org-retention-panel`, `.org-depth-table`, `.org-group-top` separator, `.lvl-mlb` badge, `.payroll-bars`/`.payroll-bar-*` bar chart styles. Removed unused `.src-badge` styles.

---

## Session 28 (2026-03-22)

### Multi-League — Layer 5 Hardening + Onboarding Polish

**Layer 5 — Hardening (Tasks 5.1–5.3)**
- `before_request` checks for `league.db` + `league_averages.json`; data routes redirect to `/settings` if missing. When no leagues exist at all, redirects to `/onboard`.
- Settings page shows orange warning banner for incomplete leagues.
- All `league_averages.json` reads replaced with safe `web_league_context.league_averages()` loader (returns zeros when missing) — `app.py`, `player_queries.py`, `team_queries.py`, `percentiles.py`.
- Record count query guarded against missing DB.
- `/api/test-connection` endpoint — tests both public (`/date/`) and protected (`/ratings/`) endpoints. Catches `CookieExpiredError` specifically.
- `statsplus/client.py` — new `CookieExpiredError` exception. `_fetch()` detects "requires user to be logged in" response (StatsPlus returns 200, not 401).
- Refresh error handler detects cookie expiration in stderr and surfaces clear message.
- Post-refresh validation checks table counts (players ≥100, ratings ≥100, teams ≥10, contracts ≥50).

**Settings page improvements**
- DH rule: free text input replaced with constrained dropdown (No DH / Universal DH / AL Only DH) + server-side validation.
- Cookie fields split into separate Session ID and CSRF Token inputs (both settings and onboarding).
- Collapsible "Where do I find these?" instructions with DevTools walkthrough.
- Project root added to `sys.path` in `app.py` so `from statsplus import client` works when Flask runs from `web/`.

**Onboarding wizard improvements**
- Step 2 (Pull Data) is now async: background thread with `Popen` captures stdout stage markers. JS polls `/onboard/refresh-status` every 1.5s. Spinner, progress bar, stage text ("── teams", "── ratings", etc.). Error state shows retry + back buttons.
- Back buttons on steps 2 and 3.
- Step 3 loads team names from API (city + nickname) instead of empty settings file. Filters to MLB teams via `players.level = '1'`.
- Step 3 POST populates `team_names` and `team_abbr` in settings from API data.
- `fv_calc` deferred from refresh to step 3 save (`--no-fv` flag added to `refresh.py`).

**Refresh button staleness indicator**
- `/api/game-date` endpoint returns local and remote game dates.
- JS on every page load checks staleness and shows badge: green ✓ (up to date), yellow ! (stale), gray ? (API unreachable).
- Badge re-checks after refresh completes.

**Bug fixes**
- `db.py` `_resolve_db_path()` — when `league_dir` is explicitly passed, always use it (no legacy fallback). Fixed new leagues writing to `emlb.db` instead of their own `league.db`.
- `refresh.py` — intermediate commit before ratings so roster/stats data survives if ratings fails (cookie expiration).
- `league_config.py` — `_load()` handles missing `league_settings.json` and `state.json` (returns empty dicts). `pos_map`, `role_map`, `level_map` use `.get()` with empty dict fallback.
- `contract_value.py` — `_get_state()` uses `league_context.get_league_dir()` instead of hardcoded `BASE / "meta"` path.
- `player_utils.py` — `dollars_per_war()` uses `league_context.get_league_dir()` instead of hardcoded path.
- `projections.py` — `_int_or()` helper coerces non-numeric rating values (from misaligned CSV) instead of crashing.
- `league.html` — handles missing `dollar_per_war` in league averages (shows "—").
- Removed dangling symlinks at project root (`emlb.db`, `config/`, `history/`, `reports/`, `tmp/`).

---

## Session 27 (2026-03-22)

### Multi-League Implementation — Layers 1-4

Implemented the multi-league spec (`docs/multi_league_spec.md`) across 4 layers, 18 tasks.

**Layer 1 — Data Layer Refactor (Tasks 1.1–1.5)**
- Created `data/emlb/` directory structure with migration script (`scripts/migrate_to_multi_league.py`). Symlinks at old locations for backward compat.
- `data/app_config.json` — global config with `active_league` and `statsplus_cookie`.
- `scripts/league_context.py` — shared resolver for active league directory, cookie, slug.
- `scripts/db.py` — dynamic DB path from `get_league_dir()`, falls back to legacy `emlb.db`.
- `scripts/league_config.py` — accepts `base_dir` parameter, resolves paths dynamically. Added `leagues` property, `league_for_team()`, `state_path`, `league_dir` properties.
- `statsplus/client.py` — lazy credential resolution (no module-level env reads). `configure()` > `league_context` > `.env` fallback.
- `web/web_league_context.py` — request-scoped accessors (`get_db()`, `get_cfg()`, `team_abbr_map()`, etc.).
- `web/app.py` — `@app.before_request` populates Flask `g` with league config. Context processor for template globals.
- `web/queries.py`, `web/team_queries.py`, `web/player_queries.py`, `web/percentiles.py` — all module-level globals (`_cfg`, `_db`, `TEAM_ABBR`, `TEAM_NAMES`, `LEVEL_MAP`, `POS_MAP`, etc.) replaced with `web_league_context` accessors. `conn.close()` calls removed from `queries.py` (shared connection lifecycle). Each `get_db()` call creates a fresh connection scoped to the active league.

**Layer 2 — League Structure Generalization (Tasks 2.1–2.4)**
- `league_settings.json`: Added `leagues` array with explicit league objects (name, short, color, divisions). Old `divisions` dict kept for backward compat.
- `league_config.py`: `leagues` property synthesizes from old format if `leagues` key missing.
- `app.py` league route: Builds `league_groups` from `config.leagues`. Wild card computation per-league.
- `queries.py`: `_build_league_team_sets()` returns `{lg_short: set(tids)}`. Leader functions return `{"All": ..., "AL": ..., "NL": ...}`.
- `league.html`: Division cards use inline `border-top` color. Leader toggle buttons generated dynamically. Grid columns from division count.
- `style.css`: Removed `div-al`/`div-nl` classes.

**Layer 3 — Settings & Onboarding UI (Tasks 3.1–3.5)**
- `settings.html`: Full rebuild — 6 sections (My Team, League Identity, League Structure with JSON editor, Financial, Connection, Data) + "Add Another League" link.
- `app.py`: Expanded settings route with `save_identity`, `save_financial`, `save_cookie`, `save_structure` POST actions. Structure editor validates JSON and rebuilds flat `divisions`.
- `onboard.html` + routes: 4-step wizard (Connect → Pull Data → Configure → Done). Creates league directory, runs refresh, configures team.
- `base.html`: Dynamic `<title>` and `<h1>` from `league_name`. League switcher dropdown (hidden for single league).
- `/switch-league/<slug>` route updates `app_config.json`.
- Backlog item 3.6 added for settings page hardening (data safety, validation, visual editor, etc.).

**Layer 4 — Refresh Pipeline Updates (Tasks 4.1–4.2)**
- `refresh.py`: All paths resolve through `get_league_dir()`. Year defaults to `config.year`. `ORG_ID` resolved dynamically.
- `fv_calc.py`: DB and state path from `get_league_dir()`.
- `farm_analysis.py`: All data paths (prospects, state, scaffold output, tmp) from `get_league_dir()`.
- `roster_analysis.py`: Notes, league averages, scaffold output, tmp from `get_league_dir()`.

---

## Session 26 (2026-03-22)

### ETA Gap Fix
- **Root cause**: `_ETA` map in `queries.py` used `.5` values with Python's `round()` (banker's rounding). `round(0.5)=0` collapsed AAA to 2033 (same as MLB), `round(1.5)=2` pushed AA to 2035, skipping 2034 entirely.
- **Fix**: Replaced with integer values (AAA=1, AA=2, A=3, A-Short=4, USL/DSL/Intl=5) across all 3 occurrences. Removed `round()` calls.
- **ETA pull-forward**: Added `_calc_eta()` helper — prospects with Ovr ≥ 45 (MLB-viable contributor) get ETA pulled forward by 1 year. A AAA prospect who can contribute today shows 2033, not 2034.
- **Result**: Clean distribution — 2033 (10 MLB-ready AAA), 2034 (32), 2035 (13), 2036 (41), 2037 (6).
- `constants.py` `YEARS_TO_MLB` unchanged — `.5` values are correct for NPV discounting in surplus model.

### Multi-League Support Spec
- **`docs/multi_league_spec.md`** — comprehensive spec for transforming the app from single-league to multi-league. Covers:
  - Full audit of hardcoded assumptions (§1) — 25+ items across league identity, structure, team/org identity, financial model, ratings, API, file layout
  - League structure generalization (§2) — `leagues` array model replacing AL/NL hardcoding
  - Data isolation (§3) — `data/<league>/` directory structure (separate DB per league)
  - Onboarding flow (§4) — 6-step browser wizard
  - Settings page expansion (§5) — 6 sections covering full configuration surface
  - Code changes required (§6) — file-by-file breakdown
  - Migration path (§7) — existing EMLB data migration
  - Decisions log (§9) — 6 architectural decisions with rationale
  - Implementation plan (§10) — 5 layers, 18 tasks, ordered by dependency

### Architectural Decisions
- D1: Request-scoped league context (not singleton reload) — scales correctly
- D2: Full `leagues` array model (not naming convention) — explicit over inferred
- D3: UI onboarding wizard (not CLI) — target users are OOTP players
- D4: Multi-league directory structure from day one — avoid double migration
- D5: Full settings page expansion — build real config surface once
- D6: StatsPlus cookie is global, only slug is per-league

---

## Session 24 (2026-03-21/22)

### UI Visual Overhaul — Team Page
- **KPI cards**: Summary bar items restyled as individual cards with borders, lighter background (#1e2530), green left accent on surplus cards, conditional pos/neg coloring. Streak card with win/loss accent border+tint.
- **Rank pills**: 5-tier colored pill badges (elite/good/mid/poor/bad) replacing plain text rank. Blue/orange/red palette for color-deficiency accessibility. Contextual progress bars behind pills — bar width proportional to rank, pill rides at the end.
- **Recent games**: W/L solid color square badges in own column, bold scores, dimmed pitcher names, muted vs/@ indicator. Abbreviated player names via `|short` Jinja filter (handles Jr/Sr/II/III suffixes).
- **Leaders section**: Vertical card layout with category label left + players right. #1 leader bold with gold value. All values soft blue (#7ec8ff). Abbreviated names.
- **Two-column layout**: Main tab restructured into independent left (Standings, Record, Recent Games) and right (Team Stats, Leaders) columns — eliminates dead space gap.
- **Standings highlight**: Team row gets green left border via `td:first-child` border + background tint.
- **Section dividers**: Panel h2 headings get bottom border.
- **Zebra striping**: `tr:nth-child(even)` on all tables.
- **Active tab**: Underline changed from red to green.

### UI Visual Overhaul — Depth Chart
- **SVG cleanup**: Removed filled outfield wedge and thick infield diamond. Replaced with faint arc, subtle dirt circle, very faint basepaths.
- **Control bar**: Year tabs + stat selectors grouped in structured panel bar (years left, stats right).
- **Header contrast**: Forced white text on all colored position headers (elite/good/weak).
- **Sidebar**: DH/SP/RP wrapped in distinct container with dark background and left border.
- **Player grid alignment**: CSS grid (`1fr auto auto auto`) for consistent column alignment. Name+level tag wrapped in single grid cell.
- **Card sizing**: Fixed 210px width, edge cards repositioned to prevent overlap/clipping.
- **Heatmap legend**: Three colored swatches (Elite/Above Avg/Below Avg) in control bar.
- **Departed banner**: Lightened text to soft pink, chips get border for readability.
- **Level badges**: Yellow border + padding upgrade to proper status badge.

### UI Visual Overhaul — League Prospects Page
- **FV badges**: Color-coded pills — gold (65+), blue (55-64), green (50-54), gray (<50).
- **Level badges**: Colored pills by level — AAA blue, AA green, A yellow, lower gray.
- **ETA highlighting**: Current year bold white, 2035+ muted gray.
- **Surplus data bars**: Inline flex track bars scaled relative to #1 prospect.
- **Filter bar**: Search + team filter consolidated into mode tabs bar (pushed right).
- **Compact rows**: Reduced padding for more visible prospects without scrolling.
- **Height column**: Right-aligned with tabular nums.

### Infrastructure
- **`|short` Jinja filter** (`app.py`): `_short_name()` handles Jr/Sr/II/III/IV suffixes. Used on team page (recent games, leaders).
- **Global CSS fix**: `select { width: 100% }` scoped to `form select` only — was breaking all non-form selects site-wide.
- **Duplicate CSS cleanup**: Removed duplicate `.split-btn`, `.prospect-mode-select`, `.prospect-filters` rules.

### UI Visual Overhaul — League Overview Page
- **League vitals KPI cards**: Added Phase, Lg AVG, Lg ERA, Lg OPS, $/WAR cards to summary bar. KPI divider (`<hr>`) separates header from content.
- **Standings 2×3 division grid**: Replaced vertical stack of full tables with compact division cards in a 3-column grid. AL cards get blue top border, NL cards get red. Division leaders get gold "1st" badge, wild card teams get blue "WC" badge. Fixed-width badges + spacer for name alignment. PCT progress bars behind win percentage. Teams 10+ GB get muted opacity. Responsive: collapses to auto-fit below 1100px.
- **Wild card logic**: Computed from standings using `wild_cards_per_league` setting (3). Ties for last WC spot both marked.
- **Two-column layout**: Left column (standings grid + scrollable power rankings), right column (leaders starting at top). `league-main` grid.
- **Power rankings**: Fixed 480px height with internal scroll. Score column has heatmap bar (green, scaled to #1). User team highlighted with green left border.
- **Leader hero cards**: #1 leader featured with bold name + large gold value. 2-5 listed below with muted gold values. 2-column grid layout. Team abbreviations muted to `#8b949e`. User team players get green highlight (border + tint + green value).
- **Batting leaders**: Removed "R" (runs) category — now 6 categories (AVG, HR, RBI, SB, OPS, WAR) matching 6 pitching categories.
- **Prospect tab**: Mode tabs + filters moved inside `prospect-table-wrap` so right edge aligns with table.
- **ETA styling**: Current year bold white (`eta-now`), 2035+ muted gray (`eta-far`).

### Beat Reporter Agent — T.R. Falcone
- **Agent definition**: `.kiro/steering/beat-reporter.md` — standalone steering file with project context, persona, tone/style rules, 8 article type templates, research process, output format (short for Discord, long for Google Docs), and guardrails.
- **Agent config**: `~/.kiro/agents/beat-reporter.json` — registered as Kiro CLI agent with resources pointing to steering file, tools reference, and key project files. Accessible via `/agent swap` or `kiro-cli chat --agent beat-reporter`.
- **Tools reference**: `docs/tools_reference.md` — comprehensive catalog of all CLI tools (8), importable libraries (5), web query functions (20+), data files, DB tables, and known data limitations. Added to end-of-session documentation checklist.
- **Reporter identity**: T.R. Falcone, analytical tone by default (The Athletic style), user-overridable. No OOTP field names in prose — scout language only.

---

## Session 23 (2026-03-21)

### Two-Way Player Support
- **Detection**: `load_stat_history()` already returned a `two_way` set (players with qualifying batting AB≥130 and pitching GS≥10 in the same year). Now consumed by all callers.
- **Surplus fix**: New `_two_way_peak_war()` combines batting + pitching WAR per year (no incomplete adjustment). `stat_peak_war()` gains `two_way` kwarg, flows through `contract_value()` and `fv_calc.py`. Cowgill surplus: $170.8M → $210.1M (+$39.3M).
- **Roster hitters tab**: Two-way pitchers (PA≥30) now appear on the Hitters tab with their fielding position (e.g. Cowgill shows as 1B). `is_two_way` flag and "TW" badge on both tabs.
- **Player page — Pitcher/Hitter toggle**: Two-way players get a "Pitcher | Hitter" button pair in the header. Clicking swaps the entire page view between pitcher mode (pitcher ratings, pitching stats snapshot, pitching percentiles) and hitter mode (hitter ratings with L/R splits + defense + running, batting stats snapshot, batting percentiles). Reuses existing pitcher/hitter macros — no TW-specific template sections. Stats tab always shows both batting and pitching history tables regardless of toggle.
- **Player popup**: Two-way pitchers show batting tools (Con/Pow/Eye/Spd) below pitching tools, plus a batting stat line (slash line + HR + bWAR) below the pitching stat line.
- **Backend**: `get_player()` returns `hit_ratings` dict (full hitter ratings structure) for two-way pitchers, plus `bat_percentiles`/`bat_pctile_splits`. `get_player_popup()` returns `bat_stats` and `ratings.bat` for two-way pitchers.
- **CSS**: `.tw-badge`, `.tw-toggle`, `.tw-btn` styles. `tw-pit`/`tw-hit` CSS classes for view toggling.
- 12 two-way players detected league-wide; 7 with meaningful current-year playing time.

---

## Session 22 (2026-03-21)

### Data Integrity — Intl Complex Level Fix
- **Root cause**: API reports international complex players as `Level=1` (MLB). Only distinguishable by negative `league_id` in ratings. `fv_calc.py` treated them as MLB players → inflated surplus.
- **Fix at source** (`refresh.py`): After ratings ingest, reclassify any player with negative `League` from `level=1` to `level=8` (International) in the `players` table. 1,321 players reclassified.
- **Simplified downstream**: `fv_calc.py` no longer needs `is_intl_complex` special-casing — level=8 flows through normal prospect path via `LEVEL_INT_KEY`. `farm_analysis.py` old workaround (query level=1 then filter by league_id) replaced with standard `get_ratings(org, level=8)`.
- Deleted stale eval_date rows from `player_surplus` (1,844 rows).

### Roster Rework — Hitters & Pitchers Tabs
- Replaced single "Roster" tab with separate **Hitters** and **Pitchers** tabs.
- **Split toggle** (Overall / vs L / vs R) — all 3 splits loaded as JSON, JS swaps displayed values instantly. Split label ("Showing: vs LHP") appears when viewing a split.
- **Hitters columns**: Pos, Name, Age, Ovr | WAR | G, PA, AVG, OBP, SLG, OPS | HR, R, RBI, SB, CS | BB%, K% | Surplus
- **Pitchers columns**: Role, Name, Age, Ovr | WAR | IP, ERA, WHIP | K, BB, K%, BB%, K-BB% | HR, W-L, QS, SV+H, IRS% | Surplus
- Players with missing split data (e.g. no AB vs RHP) still shown with dashes instead of hidden.
- **Column header tooltips** — every stat header has a `title` attribute explaining the abbreviation on hover.
- **Conditional formatting** — rate stats (AVG, OBP, SLG, OPS, BB%, K%, ERA, K%, BB%) colored green/red when >5% above/below league average.
- **Column separators** — subtle left borders between logical stat groups for visual tracking.

### Player Hover Popup
- Hover any player name link for 300ms → tooltip appears with key data.
- **Content**: Name, age, height, bats/throws, position, team, level, Ovr/Pot, FV (prospects), stats (slash line or ERA/IP/K), surplus.
- **Ratings snapshot**: Hitters show Con/Pow/Eye (present/future) + Spd. Pitchers show Stf/Mov/Ctl (present/future) + Stm + Vel + top 4 pitches with grades.
- **Grade coloring**: blue (70+), green (60+), white (50+), orange (40+), red (<40).
- AJAX endpoint `/api/player-popup/<pid>` with client-side caching. Works on all pages (base.html).
- Added `player-link` class to depth chart links that were missing it.

---

## Session 21 (2026-03-21)

### Depth Chart Visual Improvements
- **Inline stats** — position player rows now show OPS+ (or selected stat) prominently with PT% always visible but dimmed; pitchers show ERA by default. Stat selectors default to OPS+ and ERA instead of PT%.
- **Age added** to all player rows (dimmed, after name). Ages increment correctly across projection years.
- **Legend row** — dynamic legend above diamond showing "Player Age [Stat] PT%", updates when stat selector changes.
- **Year tabs** — replaced ◀/▶ arrows with three clickable year buttons (2033/2034/2035) with active underline.
- **Backup trimming** — cards show players until 95% cumulative PT coverage instead of hard cutoff, reducing noise while preserving meaningful depth (e.g. DH rotation).
- **RP role hierarchy** — CL/SU/MR labels now have tiered prominence (CL: larger/bolder, SU: medium, MR: subtle).
- **Departed banner** — reformatted as individual chips sorted by WAR descending, with bold position labels. Much more scannable than the old dot-separated text.
- **DH placement** — moved from diamond to right sidebar above SP/RP, styled as matching section card.

### WAR Projection Model Fix — Stat/Ratings Blending
- **Problem**: Players outperforming their ratings (e.g. Rohnson: 5.2 stat WAR vs 2.6 ratings WAR) had a cliff in projections — year 1 used actual stats, year 2+ dropped to ratings-only.
- **Fix in `projections.py`**: `project_war()` now blends stat_war into future years with 50% exponential decay per year. Year 1 = stat_war, Year 2 = 50/50 blend, Year 3 = 25/75, converging to ratings-only.
- **Fix in `contract_value.py`**: Same blending applied to the `dev_ramp` branch of the surplus model, which had the same cliff for pre-peak players.
- **ERA/FIP alignment**: `project_era()` and `project_fip()` now delegate to `project_war()` instead of computing WAR independently from ratings, ensuring ERA/FIP track with the blended WAR projection.
- Rohnson's curve: 5.2 → 4.0 → 3.4 (was 5.2 → 2.8 → 2.8). ERA: 2.84 → 3.32 → 3.57 (was 3.88 flat).

### Data Integrity Fix — player_surplus Table
- **Problem**: `fv_calc.py` was writing international complex players (negative `league_id`, level=1) into `player_surplus` as MLB players. Inflated team surplus totals with cheap prospects not on the active roster. Sacramento showed $1164M surplus with 67 "MLB" players.
- **Fix**: Added `league_id > 0` guard to the MLB branch in `fv_calc.py`.
- **Cleanup**: Deleted 3,949 bad rows (intl complex) and 1,844 stale eval_date rows. All teams now show 26-28 players (actual MLB rosters).

---

## Session 20 (2026-03-21)

### Depth Chart Fixes
- **Level display bug** — `allocate_playing_time()` was stripping `_level` field; changed filter to only strip `_eff_war`
- **Premium position lock** — lowered WAR threshold from 5.0 to 3.0 for SS/CF/C; increased inertia boost to 4x. Kazansky stays locked at SS all 3 years.

### League Page — Stat Leaders Overhaul
- Replaced batting/pitching leader tables with per-stat panel cards (top 5 per category)
- Added MLB/AL/NL toggle — single query, client-side filtering
- Batting: AVG, HR, RBI, R, SB, OPS, WAR. Pitching: ERA, W, K, SV, WHIP, WAR

### League Page — Prospects Tab
- New tab bar on league page (Overview | Prospects)
- **Top 100** — default view with player search and All Teams filter dropdown; preserves original rank when filtering
- **Top 30 by Team** — dropdown-as-tab pattern, defaults to user's team, shows full team names
- **Top 10 by Position** — dropdown-as-tab, merged OF bucket (CF/LF/RF/COF), ordered C/1B/2B/3B/SS/OF/SP/RP
- Level dots indicator (5-dot scale: Rookie=1, A=2, AA=3, AAA=4, MLB=5)
- FV color coding (65+ blue, 55+ green, 50 white, 45 dim)
- Conditional columns — hides Position on position view, hides Team on team view
- Table capped at 960px max-width

---

## Session 19 (2026-03-20)

### Finances Tab
- **Finances tab on team page** — new tab with committed payroll table showing 6-year horizon (current year + 5 future). Per-player salary by year with TO/PO option markers, NTC badges, and total committed row.
- **Arb/pre-arb salary projections** — 1-year contract players get projected future salaries using the existing `contract_value` arb model. Projected cells shown in italics with `est` superscript. Pre-arb years at league minimum, arb years using OOTP-calibrated exponential + raise model with RP discount.

### Surplus Model Fixes
- **Service year threshold fix** — lowered qualifying thresholds from 300 AB / 100 IP to 100 AB / 40 IP to correctly count relievers and part-time players. Fixes Grimaldo (was missing 4 of 5 qualifying seasons) and other relievers.
- **Pre-arb age gate fix** — changed from blanket `age >= 28` rejection to `age >= 28 AND svc >= 4`. Fixes McClanahan (age 28, 1 qualifying season due to injuries) who was incorrectly treated as a veteran FA.
- **RP bucketing for MLB players** — `assign_bucket` now respects actual deployment role when `use_pot=False`. A reliever is valued as RP regardless of SP-viable ratings. Fixes Franklin ($11.4M → $5.4M surplus) and all other misclassified relievers league-wide.
- **Non-tender gate fix** — compare arb salary against `max(market_value, min_salary)` instead of requiring `market_value > 0`. Zero-WAR players now correctly get non-tendered at arb entry.
- **Removed pw > 0 control gate** — the non-tender gate handles this more precisely. Players with estimated control now always get the full projection.
- **Development ramp for pre-peak players** — `contract_value` now linearly interpolates Ovr toward Pot for players below peak age (27 pitchers, 28 hitters). Edwards went from -$0.8M (1yr, 0 WAR) to $13.7M (6yr, ramping WAR). Only applies when Pot > Ovr and no stat-based WAR override.
- **Re-ran fv_calc.py** — all 918 MLB players recomputed with the above fixes.

### Record Breakdown
- **Record breakdown panel on team page** — Main tab panel showing Overall, Home, Away, vs Division, 1-Run Games, Last 10, and Streak with W-L-Pct for each split.

### BABIP Investigation & Fix
- **BABIP rating investigation** — confirmed hidden BABIP rating is not in the API export. Regression analysis: Contact (r=0.41) and Speed (r=0.21) explain 23% of BABIP variance (R²=0.227). Residuals are stable across years (even/odd correlation r=0.46), confirming a persistent hidden trait.
- **Improved BABIP expected percentile** — replaced contact-only expected BABIP with regression model (cntct + speed) plus historical residual adjustment (avg actual-vs-predicted over 2+ prior qualifying seasons). Players with consistently high/low BABIP no longer falsely flagged as lucky/unlucky.

### Task List Updates
- Payroll summary marked complete, comparable teams dropped, roster rework added (Hitters/Pitchers/Organization tabs), similar players/prospect comps added, BABIP investigation resolved, stat/ratings divergence flag moved to long-term.

## Session 18 (2026-03-20)

- **Stats snapshot bug fix** — `bat_splits`/`pit_splits` changed from single dicts to arrays of rows (for year-by-year splits), but the Overview tab snapshot macro still treated them as single dicts. Fixed by extracting `[-1]` (latest year) from each split array.
- **SV/HLD zero display fix** — Jinja `or` treats `0` as falsy, showing `-` instead of `0`. Removed `or "-"` pattern.
- **Game history API fix** — `get_game_history()` returned empty without `year` param. Added `year` parameter to client. Endpoint has ~4 min rate limit.
- **Games table** — new `games` DB table storing game results (game_id, home/away teams, runs, WP/LP/SV pitchers). 23,694 games loaded (2024-2033). Added to `refresh.py` pipeline.
- **API field mapping: runs0=away, runs1=home** — discovered and documented that the StatsPlus game history API uses `runs0` for away team runs and `runs1` for home team runs (opposite of typical convention).
- **Actual W/L standings** — standings now use real win/loss records from game history instead of pythagorean estimates. Pythagorean W shown as supplementary column with Δ (delta) indicating over/underperformance. Falls back to pythagorean-only if games table is empty.
- **Division-grouped standings** — league page standings broken into 6 division tables under American League / National League headers, with per-division GB.
- **Power rankings** — composite ranking on league page. Score weights: pythagorean W% (50%), last-10 record (25%), run diff/game (25%). Surplus removed from score (display-only). Includes L10 record, streak (color-coded W/L), RD/G, MLB$/Farm$ columns.
- **Recent games on team page** — last 10 games on Main tab with date, vs/@, opponent (linked), W/L result (color-coded), WP/LP/SV pitcher names (linked to player pages) with running season records as of that game date.
- **Task list updates** — power rankings marked complete, game history items partially addressed.

## Session 17 (2026-03-20)

- **Ovr/Pot color box bug fix** — bare `[data-g]` CSS selectors applied background color to `.ovr-color` text spans, creating colored boxes instead of colored text. Scoped selectors to `.grade-cur[data-g]` and `.grade-pot[data-g]`.
- **Team stats leaders** — top 3 players in key batting (HR, RBI, AVG, OPS, SB, WAR) and pitching (ERA, W, SV, K, WHIP, WAR) categories on team Main tab. Stats are per-team so traded players retain their stats. Card grid layout with gold highlight on #1.
- **MLB qualification thresholds** — rate stat leaders (AVG, OPS, ERA, WHIP) use MLB standard qualifiers: 3.1 PA/team game for batters, 1.0 IP/team game for pitchers. Scales automatically with season progress.
- **Saves field fix** — API uses `s` for saves, not `sv`. Fixed in `refresh.py`, re-pulled all pitching stats.
- **Full stats schema expansion** — `batting_stats` expanded from 22→32 columns, `pitching_stats` from 21→52 columns. Now stores every API field including: er, cg, sho, hld, bs, svo, qs, gb, fb, pi, wp, bk, ir, irs, wpa, li, relief_app, md, sd (batting: g, gs, cs, gdp, ibb, pitches_seen, ubr, wpa). Batting avg/obp/slg now computed in upsert.
- **Full stats backfill** — pulled all batting, pitching, and fielding stats for 2020-2033 (14 seasons). 27,223 batting rows, 25,154 pitching rows, 24,529 fielding rows.
- **New batting stats displayed** — added G, ISO (SLG-AVG), SB/CS to player page batting tables.
- **New pitching stats displayed** — replaced K/9 and BB/9 with K%, BB%, K-BB% (superior rate stats). Added GB%, G, HLD. Removed HR/9 from display (captured by FIP).
- **Stats snapshot on Overview tab** — compact current-year stats panel between scouting report and percentiles. Pitchers show pitching stats (not batting). L/R split toggle for current year.
- **Stats tab split selector** — replaced old L/R toggle (current year only) with 3-button selector (Overall / vs L / vs R) showing full year-by-year history for each split.
- **SV/HLD zero display fix** — `0` was showing as `-` due to Jinja `or` treating 0 as falsy.
- **New backlog items added** — PAP score (1-10 value efficiency), career outcome probability chart, UI overhaul exploration.

## Session 16 (2026-03-20)

- **StatsPlus external links** — player and team pages link to StatsPlus web profiles via ↗ icon. League slug read from `statsplus/.env`, exposed as `statsplus_base` Jinja global.
- **Team navigation dropdown** — hover dropdown in nav bar with all 34 teams, accessible from any page. `all_teams` Jinja global. Pure CSS hover, no JS.
- **Fielding stats pipeline** — new `fielding_stats` DB table, `_upsert_fielding()` in `refresh.py`, API pull added to `refresh_league()`. IP stored as decimal (API returns outs). 1245 rows for 2033.
- **Fielding stats on player page** — query in `player_queries.py`, full-width table with Year/Pos/G/IP/TC/A/E/DP/FPCT/ZR/Arm. Pos column left-aligned.
- **Fielding percentile rankings** — `get_fielding_percentiles()` in `percentiles.py`. Position-aware metrics: FPCT+ZR for all, +Arm for OF, +Framing for C. Qualifier: 1.0 IP per team game, floor 15.
- **Fielding expected percentiles** — ZR expected from rating composites (IF: IFR×0.7+IFE×0.3, OF: OFR, C: IFR×0.35+CArm×0.35+CBlk×0.30). Framing expected from CFrm×0.7+CBlk×0.3. FPCT and Arm have no expected (too noisy). Includes expected range band.
- **Player header cleanup** — removed duplicate Ovr display for MLB players (was showing both Ovr/Pot and "MLB Ovr"). Prospects still show FV since FV≠Ovr. Ovr/Pot values color-coded using tier palette via JS.
- **Player page tabbed layout** — MLB players get 3 tabs: Overview (ratings, character, scouting report, percentiles, fielding percentiles), Stats (batting/pitching/fielding), Contract (contract years, surplus projection). Prospects keep single-page layout (no tabs). Reusable Jinja macros for all content blocks.
- **Split-specific expected percentiles** — hitter splits now use `cntct_l/pow_l/eye_l/ks_l` for vs-L and `cntct_r/pow_r/eye_r/ks_r` for vs-R instead of overall ratings. Pitcher splits use `stf_l/mov_l/ctrl_l` and `stf_r/mov_r/ctrl_r`. Verified with Trey Sweeney (cntct: 98 vs L, 49 vs R → expected AVG pctile 100 vs L, 34 vs R).
- **Steering doc update** — references `docs/changelog.md`, documentation checklist updated for task list/changelog split.

## Session 15 (2026-03-20)

- **Ratings CSV header truncation fix** — StatsPlus API truncates the ratings CSV header at 500 chars, dropping the last 17 columns (PotCutt onward including personality, Acc, Ovr, Pot). `client.py` now detects truncation and appends known missing column names. Also renames `Overall`/`Potential` to `Ovr`/`Pot` for downstream compatibility.
- **Ratings column order fix** — `_upsert_ratings()` in `refresh.py` had personality/league/height fields ordered after fielding/splits, but the DB schema has them before. All data from league-wide refreshes was being written to wrong columns (e.g. IFR values in the `int_` column). Reordered `row()` to match DB schema. All ratings data re-pulled.
- **`calc_fv()` None composite guard** — `_pos_composite()` could return `None` for COF players with missing LF/RF grades, crashing the `comp >= 60` comparison. Fixed with `or 0` guard.
- **fv_calc error propagation** — `_run_fv_calc()` in `refresh.py` was swallowing failures (printed error but exited 0). Now writes to stderr and exits non-zero so the web UI reports it.
- **Refresh error display** — web UI was truncating raw tracebacks to 200 chars. Now extracts the last line (actual exception message) and shows it in red in the modal.
- **Rate limit retry** — `get_ratings()` rate limit handling upgraded from single retry to 3-attempt loop.
- **Dynamic percentile qualification** — replaced hardcoded `min_pa=50` / `min_ip=10` with pro-rated thresholds: 2.0 PA per team game (hitters), 0.5 IP per team game (pitchers), with floors of 30 PA / 5 IP. Team games estimated from `max(team PA) / 38`.
- **Expected range band** — percentile expected indicator expanded from a single line to a shaded range band. Width is ±12 percentile points at the qualifier threshold, narrowing as `sqrt(qualifier / sample_size)`. Capped at ±25.
- **Personality text-snapshot workaround** — `player_queries.py` queries the most recent snapshot with text personality values (`WHERE wrk_ethic IN ('VL',...)`) as a safety net against bad numeric data from prior refreshes. Harmless after the column order fix since new snapshots have correct text values.
- **Task list / changelog split** — moved 141 completed items from `task_list.md` to new `docs/changelog.md`. Task list trimmed from 243 to 55 lines (open items only). Updated STRUCTURE.md and steering doc.

## Session 14 (2026-03-20)

- **Centralized `norm()`, `height_str()`, `display_pos()`** — canonical versions in `scripts/player_utils.py`. `queries.py` imports from `player_utils`.
- **Extracted `web/percentiles.py`** (264 lines) — hitter/pitcher percentile functions, helpers, stat/tag constants.
- **Extracted `web/player_queries.py`** (329 lines) — `get_player()` with ratings, stats, splits, contract, surplus, personality, scouting summary.
- **Extracted `web/team_queries.py`** (494 lines) — 12 team-specific query functions.
- **`queries.py` reduction** — 1294 → 141 lines (89% reduction). State helpers + league queries + re-exports.
- **Fix 20-rating grade bar** — minimum 5% width so grade 20 is always visible.
- **Player personality traits** — Character panel showing Intelligence, Work Ethic, Greed, Loyalty, Leadership. Color-coded VL/L/N/H/VH text.
- **Percentile expected range indicator** — white vertical line on each percentile bar showing where ratings predict performance.
- **Overall performance indicator** — "▲ Over" / "≈ Expected" / "▼ Under" in player header bar.
- **Deprecated Angels-only refresh** — removed `refresh()`, `org_ids()`, `org_players()`. League refresh is now the only path.

## Session 13 (2026-03-19)

- **IP storage fix** — API returns truncated integer `ip`; now derived from `outs` field (`outs/3`). ERA computed from outs. `fmt_ip` Jinja filter for baseball display.
- **Single-command refresh** — `refresh.py` auto-fetches game date, updates `state.json`, runs `fv_calc.py`.
- **SQLite WAL mode** — concurrent reads during writes. Web UI stays browsable during refresh.
- **`league_config.py`** — single abstraction for league-specific settings. All scripts migrated from hardcoded values.
- **Refresh button** — trigger full data refresh from web UI with progress indicator and error modal.

## Session 12 (2026-03-19)

- **Tab layout** — team page reorganized into 4 tabs: Main, Roster, Contracts, Player Development.
- **Roster construction summary** — SP/RP/Pos counts in summary bar.
- **Upcoming free agents** — multi-year deals expiring within 2 years on team page.
- **Surplus leaderboard** — top 15 surplus players combining MLB and farm.
- **Age distribution** — MLB roster and farm age brackets with horizontal bars and league average markers.
- **Farm system depth** — FV 40+ prospects by position bucket and level with league rank.
- **Page title header** — `<h1>` with full team name.
- **Rank color fix** — `.rank-top` changed to `#66ff99` for readability.
- [-] **Trade asset inventory** — built then removed. Redundant with contracts table and surplus leaderboard.

## Session 11 (2026-03-19)

- **Team page base migration** — `/team/<id>` renders full dashboard for any team. Dashboard queries parameterized.
- **Team links** — all team names clickable across all views.
- **Team stats with league rankings** — batting/pitching stats with rank out of 34.
- **Contract table** — MLB contracts sorted by salary with surplus and option flags.
- **Payroll in summary bar** — total MLB payroll from `is_major=1` contracts.
- **Surplus moved to contracts** — removed from roster tables, added to contracts table.
- **Pos/Role column first** — moved before Name in all tables.
- **Column alignment** — CSS switched to semantic rules.

## Session 10 (2026-03-19)

- **Platoon split penalty in FV model** — prospects penalized for severe L/R splits. 28 affected league-wide.
- **Position-weighted defensive score** — `defensive_score()` with position-specific tool weights.
- **Unified scaled defensive bonus** — composite-driven + weighted-score system replacing flat bonuses.
- **Scaffold context lines** — GB%, defensive detail, L/R split flags in farm and roster scaffolds.
- **data.py expanded** — `get_ratings()` returns all defensive + split fields.
- **Farm table formatting** — dashboard farm table matches league prospects table format.
- **Smart rank renumbering** — `sort.js` re-numbers `#` column after sort with direction-aware logic.

## Session 9 (2026-03-18)

- **Player page layout improvements** — grade bars fill width, contract option badges inline, surplus alignment fixed.
- **Expanded ratings** — Gap power, Steal, GB%, Defense (Error, Turn DP, Range), position-aware arm rating.
- **L/R split ratings toggle** — overall vs split grades for batting and pitching attributes.
- **L/R split stats and percentiles** — split stats from API, split percentile pools with lower thresholds.
- **Unqualified player percentiles** — grey percentile bars with "(small sample)" label.

## Session 7–8 (2026-03-18)

- **Bug fixes** — intl complex filtered from roster, batting rate stats computed from counting stats, .000 display fix, COF→OF display, non-MLB filtered from top 100, Montreal Expos added.
- **Player detail page** — `/player/<id>` with header bar, grade bars, scouting report, contract, surplus projection.
- **Player links** — all player names clickable to detail page.
- **Surplus projection panel** — year-by-year breakdown for MLB and prospects.
- **Advanced stats** — OPS+, BABIP, BB%, SO%, FIP, SIERA, ERA+, K/9, BB/9, HR/9.
- **Stats column ordering** — grouped by concept.
- **Percentile rankings (Savant style)** — horizontal bars with color gradient.
- **Performance tags** — rating-to-stat divergence indicators.
- **Phase 1 Dashboard (My Team + League)** — Flask web app with standings, roster, farm, leaders, prospects.
- **Team-agnostic configuration** — `my_team_id` in `state.json`, `/settings` page.
- **Division mappings** — all 34 teams mapped.
- **Client-side table sorting** — numeric, string, positional sort types.

## Session 6 (2026-03-18)

- **Standings script** — pythagorean W/L from team RS/RA.
- **Free agent analysis script** — expiring contracts with surplus data and filters.
- **Team stats in DB** — `team_batting_stats` and `team_pitching_stats` tables.
- **Trade target search workflow** — documented in `docs/trade_target_workflow.md`.
- **ERA fix** — computed from `er * 9 / ip`. Backfilled 2031-2033.
- **Height/bats/throws fix** — backfill UPDATE for demographics.
- **Aging docs updated** — exact calibrated values from `constants.py`.
- **STRUCTURE.md and system_overview.md rewritten**.
- **Deduplicated utility functions** — consolidated in `player_utils.py`.

## Session 5 (2026-03-18)

- **Farm report re-run** — Medina entered top 15, Posada rebucketed COF→C, Carrillo to watch list.
- **Fresh roster analysis** — 26 player assessments with contract health table.
- **Fresh org overview** — farm summary, MLB assessment, 1-3 year outlook.
- **Roster summary reuse** — `history/roster_notes.json` with rewrite flags.
- **Season-based refresh for both scaffolds** — new-season triggers rewrite flags.

## Session 4 (2026-03-18)

- **`fv_calc.py` integrated with `contract_value()`** — full control estimation for MLB surplus.
- **Circular import resolved** — `load_stat_history()` and `stat_peak_war()` moved to `player_utils.py`.
- **Batch performance optimization** — optional `_conn`/`_hist` params.
- **Pre-arb age gate** — age ≥ 28 on league minimum treated as 1yr FA.
- **WAR floor at 0** — negative WAR floored to prevent phantom negative surplus.
- **RP arb salary discount (0.80x)** — calibrated against OOTP data.
- **Non-tender gate** — control truncated when projected arb salary exceeds market value.

## Session 3 (2026-03-18)

- **`trade_calculator.py` fixed** — imports, FV+ display, sensitivity range, unified `net_surplus`.
- **Pre-arb/arb control estimation** — `_estimate_control()` validated 7/7 against game data.
- **ARB_PCT recalibrated** — 45/65/80% → 20/22/33% based on 86 OOTP arb players.
- **Arb salary model** — Ovr-based exponential/additive model. MAE $0.53M/yr.
- **DEVELOPMENT_DISCOUNT separated from time value** — bust-only realization rates.

## Session 2 (2026-03-18)

- **Prospect surplus model overhaul** — age-adjusted development discount, certainty multiplier, replacement WAR floor, zero floor, option value.
- **Farm systems ranking: surplus-based** — replaced point scoring with total surplus.
- **Prospect sort: surplus tiebreaker** — within same FV, sorted by surplus.
- **`prospect_query.py` enhancements** — `--sort` flag, `--n`, `--fv-min`.
- **FV model improvements** — critical tool floor penalty, level-adjusted development weight.

## Session 1 (2026-03-18)

- **Full league refresh** — all 102 teams.
- **`$/WAR` methodology fixed** — $6.28M → $8.62M.
- **`contract_value.py` rewritten** — fully team-agnostic.
- **Aging curves recalibrated** — consensus-based.
- **FV→WAR and OVR→WAR tables recalibrated**.
- **Valuation tables consolidated in `constants.py`**.

## Prior Sessions

- Farm report for 2033-04-25 — scaffold, summaries, published report.
- Prospect history + notes merged into `history/prospects.json`.
- Dev signal overhaul — stagnation/developing signals on 180-day baseline.
- Surplus value on farm cards.
- Height/Bats/Throws added to ratings DB.
- Bucket fallback to listed position.
- Intl complex loading fixed.
- Reports reorganized into year subdirectories.
- Prospect surplus model — `prospect_value.py` built and validated.
- Single source of truth for shared constants — `constants.py`.
- `roster_analysis.py` migrated to DB.

## Deferred

- **Marginal cost model for elite players** — flat $/WAR understates value of 5+ WAR players. Deferred until a trade involving a star player makes it necessary.
- **Transaction tracking** — no API endpoint for trades/DFAs/call-ups. Inferring from roster diffs unreliable. Shelved.
- **Starter game log** — requires box score data which the game history API does not have. Blocked.
