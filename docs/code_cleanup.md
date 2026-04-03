# Code Architecture — Cleanup Tracker

Status: `[ ]` open · `[x]` done · `[-]` deferred · `[~]` in progress

---

## Principles

- Incremental — each item is a standalone change that doesn't break anything
- No speculative abstraction — only extract when duplication or confusion is real
- Tests follow refactors — add coverage for the code you just moved/changed
- **Team/league agnostic by default** — new and refactored code should not hardcode team IDs, league size, year, or org-specific assumptions. Use `my_team_id` from state, pass team/league context as parameters, and keep constants configurable. This reduces future complexity when multi-league support is added.

---

## Phase 1 — Low-Hanging Fruit

Quick wins that reduce duplication and clarify boundaries without restructuring.

### Consolidate shared mappings

- [x] **`league_config.py` — single settings abstraction** — created `scripts/league_config.py` with a `LeagueConfig` class that loads all league-specific settings from `config/league_settings.json` + `config/state.json`. Exposes: `my_team_id`, `year`, `game_date`, `pos_map`, `role_map`, `level_map`, `pos_order`, `pyth_exp`, `divisions`, `team_abbr_map`, `team_names_map`, `team_div_map`, `mlb_team_ids`, plus helper methods (`team_name()`, `team_abbr()`, `division()`). Lazy-loads on first access, `reload()` for post-refresh. `league_settings.json` expanded with divisions, team names/abbr, pos_order, pyth_exp.
- [x] **Wire `queries.py` through `league_config`** — replaced ~50 lines of hardcoded mappings (DIVISIONS, TEAM_ABBR, TEAM_NAMES, LEVEL_MAP, POS_MAP, POS_ORDER, PYTH_EXP) with imports from `league_config.config`. `get_my_team_id()` and `get_my_team_abbr()` now read from config. `set_my_team()` calls `config.reload()`. `app.py` uses `config.year` for refresh and reloads config on completion.
- [x] **Migrate remaining scripts to `league_config`** — `refresh.py`, `farm_analysis.py`, `roster_analysis.py`, `fv_calc.py`, `prospect_query.py`, `free_agents.py`, `standings.py`, `player_utils.py` all migrated. `ANGELS_ORG_ID` removed from `constants.py`. `ANGELS_TEAM_ID` removed from `prospect_query.py`. `--angels` flag renamed to `--my-team` in `free_agents.py`. Scaffold title in `roster_analysis.py` uses `config.team_name()`. All direct `league_settings.json` / `state.json` reads replaced with config properties.
- [x] **Centralize `_norm()`, `_height_str()`, `_display_pos()`** — canonical versions in `player_utils.py` with None/string/<=0 handling. `queries.py` imports from `player_utils` instead of defining its own. Duplicate `height_str` removed from lower in `player_utils.py`.

### Split `queries.py`

- [x] **Extract `web/percentiles.py`** — 264 lines extracted from `queries.py`. Includes `get_hitter_percentiles()`, `get_pitcher_percentiles()`, helpers (`_pctile`, `_tag_threshold`), and all stat/tag constants. `queries.py` imports from it. Uses `_cfg.year` instead of `get_state()`.
- [x] **Extract `web/player_queries.py`** — 329 lines extracted. `get_player()` with all ratings, stats, splits, contract, surplus, and scouting summary logic. `queries.py` re-exports via import. Dead `PITCH_FIELDS` constant removed. Unused `_norm`/`_height_str` imports cleaned from `queries.py`.
- [x] **Extract `web/team_queries.py`** — 494 lines extracted. All team-specific queries: `get_summary`, `get_standings`, `get_division_standings`, `get_roster`, `get_farm`, `get_team_stats`, `get_contracts`, `get_roster_summary`, `get_upcoming_fa`, `get_surplus_leaders`, `get_age_distribution`, `get_farm_depth`. `queries.py` re-exports all. Fixed duplicate `return` in `get_age_distribution`. Dead `_team_names()` removed. `queries.py` now 141 lines (was 1294).
- [ ] **Remaining in `queries.py`** — state/config functions, standings, roster, farm, league leaders. ~400 lines. Manageable as a "core" module.

### Reduce hardcoded values

- [x] **Consolidate magic numbers into `constants.py`** — All model levers, salary thresholds, service time denominators, arb coefficients, and default fallbacks extracted to named constants in `constants.py` under clearly labeled sections. Replaced across `contract_value.py`, `projections.py`, `team_queries.py`, `player_utils.py`, `prospect_value.py`, `calibrate.py`, `free_agents.py`, `app.py`, `league_config.py`. **Done Session 41.**
- [x] **Standardize `norm`/`_n80`** — `_n80()` wrapper removed from `queries.py`. `norm_floor()` added to `ratings.py` for call sites that require a numeric result. All `norm(x or 0)` patterns replaced with `norm_floor(x)`. **Done Session 41.**
- [x] **Standardize `dollar_per_war` and `minimum_salary`** — `DEFAULT_DOLLARS_PER_WAR` and `DEFAULT_MINIMUM_SALARY` added to `constants.py`. All inline fallback values replaced. Web layer uses `dollars_per_war()` function instead of duplicating `_load_la().get(...)`. **Done Session 41.**
- [ ] **Read year from `state.json` instead of hardcoding 2033** — `app.py` `_run_refresh()` hardcodes `"2033"`. Several scripts default to 2033. Should read from state or accept as parameter.

---

## Phase 2 — Structural Improvements (Session 41)

### File restructuring — Done

- [x] **Extract `scripts/ratings.py`** — `norm()`, `norm_floor()`, `get_ratings_scale()`, `init_ratings_scale()` extracted from `player_utils.py`. Eliminates circular import between `player_utils` and `fv_model`. **Done Session 41.**
- [x] **Extract `scripts/fv_model.py`** — `calc_fv()`, `dev_weight()`, `effective_pot()`, `versatility_bonus()`, `defensive_score()`, `DEFENSIVE_WEIGHTS`, `LEVEL_NORM_AGE` extracted from `player_utils.py`. **Done Session 41.**
- [x] **Extract `scripts/war_model.py`** — `peak_war_from_ovr()`, `aging_mult()`, `load_stat_history()`, `stat_peak_war()` extracted from `player_utils.py`. **Done Session 41.**
- [x] **Extract `scripts/arb_model.py`** — `estimate_service_time()`, `estimate_control()` extracted from `contract_value.py`. New `arb_salary()` function consolidates the arb formula previously duplicated across `contract_value.py`, `team_queries.py`, and `projections.py`. **Done Session 41.**
- [x] **`player_utils.py` reduced** — now contains only bucketing, display helpers, league settings accessors, PAP, and re-exports from the new modules for backward compatibility. **Done Session 41.**

### DB access patterns

- [ ] **Connection context manager** — many query functions open a connection, do work, close it. A `with db.get_conn() as conn:` pattern or a helper that auto-closes would reduce boilerplate and prevent leaked connections.
- [ ] **Standardize `row_factory`** — web query layer uses `conn.row_factory = None` (tuple rows, positional indexing) consistently. Scripts layer uses `sqlite3.Row`. Documented in module docstrings. Consider unifying in a future pass.

### Script boundaries

- [ ] **`refresh.py` — separate fetch from transform** — currently each `_upsert_*` function fetches from API and writes to DB in one step. Separating fetch (returns raw data) from upsert (writes to DB) would make the pipeline testable and allow dry-run mode.

### Web layer

- [ ] **Route-level error handling** — no try/except on routes. A bad player ID or DB error returns a raw 500. Add a simple error template.
- [ ] **Template macro extraction** — `team.html` and `player.html` have repeated table patterns. Extract common table macros (stat table, grade bar) into a shared `_macros.html`.

---

## Phase 3 — Testing (Session 41)

- [x] **Model unit tests** — `tests/test_player_utils.py` (21 tests: norm, calc_fv, peak_war_from_ovr, aging_mult), `tests/test_prospect_value.py` (12 tests: prospect_surplus, option value, invariants), `tests/test_arb_model.py` (11 tests: arb_salary known values and invariants). 63 tests total, all passing. **Done Session 41.**
- [ ] **Query integration tests** — verify key queries return expected shapes against a minimal SQLite fixture. Inline import errors in web layer are invisible until a page is hit. **Tracked in task_list.md.**
- [ ] **Refresh dry-run test** — verify `refresh.py` transform functions produce correct output from sample API responses without hitting the real API.

---

## Not Planned (rationale)

- **ORM / SQLAlchemy** — overkill for read-heavy SQLite with simple schemas. Raw SQL is fine.
- **Flask blueprints** — only 6 routes + 2 API endpoints. Not worth the indirection yet.
- **Type hints everywhere** — add incrementally where they aid comprehension, not as a blanket pass.
- **Config file framework** — `state.json` + `league_settings.json` + `constants.py` is sufficient. No need for YAML/TOML/env frameworks.
