# Multi-League Support — Alpha/Beta Readiness Spec

## Goal

Transform the application from a single-user, single-league tool into a
multi-league application that any StatsPlus user can onboard with their own
league. No code changes should be required to add a new league — all
configuration happens through the UI or config files.

---

## 1. Current Hardcoded Assumptions

### 1.1 League Identity

| Item | Where | Current Value |
|---|---|---|
| DB filename | `scripts/db.py` | `emlb.db` (hardcoded path) |
| App title | `web/templates/base.html` | "EMLB Dashboard" (hardcoded) |
| StatsPlus slug | `web/app.py` | `emlb` (fallback), parsed from `.env` |
| League name | `config/league_settings.json` | `"EMLB"` |
| Default year | `scripts/refresh.py`, `league_config.py` | `2033` (fallback) |

### 1.2 League Structure

| Item | Where | Assumption |
|---|---|---|
| Two leagues (AL/NL) | `queries.py` (`_AL_TEAMS`/`_NL_TEAMS`), `app.py` (standings grouping) | Division names start with "AL" or "NL" |
| Division color coding | `league.html` | `div-al` (blue) / `div-nl` (red) based on `startswith("AL")` |
| Leader splits | `queries.py` (`get_batting_leaders`, `get_pitching_leaders`) | MLB/AL/NL three-way split |
| Leader toggle buttons | `league.html` | Hardcoded "MLB", "AL", "NL" buttons |
| Standings layout | `app.py` league route | Assumes exactly 2 leagues, sorts into `al_divs`/`nl_divs` |
| Wild card computation | `app.py` league route | Per-league WC, assumes 2 leagues |
| 34 MLB teams | `league_settings.json` | 34 teams in divisions, 102 total with affiliates |

### 1.3 Team/Org Identity

| Item | Where | Assumption |
|---|---|---|
| My team ID | `config/state.json` | `44` (Anaheim Angels) |
| Default team ID | `league_settings.json` | `44` |
| Team abbreviations | `league_settings.json` | 34 hardcoded abbreviations |
| Team names | `league_settings.json` | 34 hardcoded names |
| Affiliate mapping | `PURPOSE.md` | Angels affiliate IDs hardcoded |
| Division membership | `league_settings.json` | 6 divisions with specific team IDs |

### 1.4 Financial Model

| Item | Where | Assumption |
|---|---|---|
| Minimum salary | `league_settings.json`, `league_config.py` | `825000` |
| $/WAR | `config/league_averages.json` | Computed from league contracts |
| Arb percentages | `scripts/constants.py` | `{1: 0.20, 2: 0.22, 3: 0.33}` — calibrated to OOTP arb |
| Pythagorean exponent | `league_settings.json` | `1.83` |

### 1.5 Ratings & Evaluation Model

| Item | Where | Assumption |
|---|---|---|
| Ratings scale | `league_settings.json` | 20-80 scouting scale |
| Ovr/Pot encoding | `client_reference.md`, `refresh.py` | Stars × 2 (e.g. 3.5 stars = 7) |
| FV methodology | `farm_analysis_guide.md`, `fv_calc.py` | Full FV calc with bucketing, bonuses, penalties |
| Aging curves | `scripts/constants.py` | Calibrated to OOTP aging model |
| OVR→WAR tables | `scripts/constants.py` | Calibrated to OOTP |
| Positional adjustments | `scripts/player_utils.py` | Standard baseball positional values |
| Percentile models | `web/percentiles.py` | BABIP regression from 2028-2032 data |

### 1.6 StatsPlus API

| Item | Where | Assumption |
|---|---|---|
| Session cookie | `statsplus/.env` | Single `STATSPLUS_COOKIE` — user-level, not league-specific |
| League URL slug | `statsplus/.env` | Single `STATSPLUS_LEAGUE_URL` — this is the league-specific part |
| API base URL | `statsplus/client.py` | `https://statsplus.net/{slug}/api` |
| External links | `app.py` | `https://statsplus.net/{slug}` |

### 1.7 File System Layout

| Item | Assumption |
|---|---|
| Single DB | One `emlb.db` for everything |
| Single `config/` | One `state.json`, one `league_settings.json`, one `league_averages.json` |
| Single `history/` | One `prospects.json`, one `roster_notes.json` |
| Single `reports/` | Reports for one league |
| Single `.env` | One cookie + one league slug bundled together |

---

## 2. League Structure Generalization

### 2.1 The AL/NL Problem

The current code assumes exactly two leagues with divisions prefixed "AL" and
"NL". This is the most pervasive structural assumption and affects:

- Standings grouping (two columns on league page)
- Leader splits (MLB/AL/NL toggle)
- Division color coding (blue/red)
- Wild card computation (per-league)
- Team set partitioning (`_AL_TEAMS`/`_NL_TEAMS`)

**Proposed model:**

Leagues should be defined in settings as a list of league objects:

```json
{
  "leagues": [
    {
      "name": "American League",
      "short": "AL",
      "color": "#4a90d9",
      "divisions": {
        "East": [48, 34, 33, 57, 59],
        "Central": [38, 35, 47, 43, 40, 992],
        "West": [58, 44, 54, 931, 42, 50]
      }
    },
    {
      "name": "National League",
      "short": "NL",
      "color": "#e74c3c",
      "divisions": {
        "East": [60, 32, 41, 51, 49, 932],
        "Central": [37, 46, 52, 36, 56, 991],
        "West": [45, 53, 39, 55, 31]
      }
    }
  ]
}
```

This supports:
- Any number of leagues (1, 2, 4, etc.)
- Any number of divisions per league
- Custom league names and colors
- Single-league setups (no AL/NL split at all)

The standings page, leader splits, and wild card logic all derive from this
structure dynamically. Division display names become `"{league_short} {div_name}"`
(e.g. "AL East") or just `"{div_name}"` for single-league setups.

### 2.2 Standings Layout

Currently hardcoded as a 2×3 grid (2 leagues × 3 divisions). Needs to be
dynamic:
- 1 league with 4 divisions → 1×4 or 2×2 grid
- 2 leagues with 3 divisions → 2×3 grid (current)
- 2 leagues with 4 divisions → 2×4 grid
- Single league, no divisions → just a single standings table

The grid layout should adapt to `len(leagues) × max(divisions_per_league)`.

### 2.3 Leader Splits

Currently MLB/AL/NL with hardcoded buttons. Should dynamically generate one
button per league plus an "All" button. Single-league setups show no toggle.

### 2.4 Wild Cards

Currently computed per league. The `wild_cards_per_league` setting already
exists but the computation assumes exactly 2 leagues. Generalize to iterate
over the `leagues` array.

### 2.5 Playoff Structure

Not currently modeled but relevant for phase display and postseason context.
Consider adding to settings:
- `playoff_teams_per_league` (or derive from division winners + wild cards)
- `playoff_format` (optional, informational)

---

## 3. Data Isolation — Per-League Storage

### 3.1 Option A: Separate DB per League

Each league gets its own directory:

```
data/
├── emlb/
│   ├── league.db
│   ├── config/
│   │   ├── state.json
│   │   ├── league_settings.json
│   │   └── league_averages.json
│   ├── history/
│   └── reports/
├── another-league/
│   ├── league.db
│   ├── config/
│   │   └── ...
│   └── ...
└── app_config.json          # Global: active league, StatsPlus cookie
```

Pros:
- Clean isolation — no cross-contamination
- Easy to back up, delete, or share a single league
- No schema changes needed
- Simpler queries (no league_id filter everywhere)

Cons:
- Need a league switcher in the UI
- All code paths need to resolve paths relative to the active league directory
- `league_config.py` and `db.py` need to accept a league context

### 3.2 Option B: Single DB with League ID

Add `league_id` column to every table. Single DB, single directory.

Pros:
- Simpler file management
- Cross-league queries possible (if ever needed)

Cons:
- Every query needs a `WHERE league_id=?` filter
- Schema migration for existing data
- Risk of data leakage between leagues
- Larger DB file over time

### 3.3 Recommendation: Option A (Separate DB per League)

Option A is cleaner for this use case. Leagues are fully independent — there's
no cross-league analysis need. The isolation makes onboarding and teardown
trivial. The main cost is plumbing a league context through the code, but
`league_config.py` already centralizes most of this.

---

## 4. Onboarding Flow

### 4.1 First-Time Setup

New users need:
1. A StatsPlus account with access to their league
2. The league URL slug (from their StatsPlus league URL)
3. Their StatsPlus session cookie (for API auth)

### 4.2 Add League Wizard (UI)

A multi-step onboarding flow accessible from the settings page:

**Step 1 — Connect to StatsPlus**
- Input: StatsPlus session cookie (if not already saved globally)
- Input: League URL slug
- Action: Validate by calling `get_date()` API with the slug + cookie
- Output: Confirmation of connection, current game date

**Step 2 — Initial Data Pull**
- Action: Run full refresh (roster, stats, ratings, contracts)
- Show progress indicator
- Output: Team count, player count, confirmation

**Step 3 — League Structure**
- Auto-detect from data where possible:
  - Team list (from `get_teams()`)
  - Team count
  - Current year (from `get_date()`)
- User provides or confirms:
  - League name
  - Division structure (which teams in which divisions, which league)
  - Or: import from a template if common formats exist
- This is the hardest step — division/league structure is not available from
  the StatsPlus API and must be user-configured

**Step 4 — Financial Settings**
- Minimum salary (default: auto-detect from lowest contract, or user input)
- Wild cards per league
- DH rule
- These could have sensible defaults with an "Advanced" toggle

**Step 5 — Select My Team**
- Dropdown of all MLB-level teams
- Sets the default team for the dashboard

**Step 6 — Done**
- Redirect to the league dashboard
- Prompt to run first analysis (FV calc, etc.)

### 4.3 Auto-Detection Opportunities

Some settings can be inferred from the data:
- **Team list + names**: from `get_teams()` API
- **Team abbreviations**: from team names (first 3 chars of city, or standard MLB abbrs)
  - Better: let the user edit these in settings after auto-generation
- **Current year**: from `get_date()` API
- **Minimum salary**: lowest salary in contracts data
- **$/WAR**: already computed by `refresh.py`
- **League averages**: already computed by `refresh.py`
- **Number of teams**: count from teams API
- **Affiliate structure**: `parent_team_id` relationships from roster data

Cannot be auto-detected:
- **Division structure**: which teams are in which divisions/leagues
- **League names**: "American League" vs "National League" vs custom
- **Wild cards per league**: league-specific rule
- **DH rule**: league-specific rule
- **Pythagorean exponent**: could default to 1.83 (standard)

### 4.4 Division Structure Input

This is the most complex onboarding step. Options:

**Option A — Manual drag-and-drop**
UI shows all teams. User creates leagues, creates divisions within each league,
and drags teams into divisions. Most flexible but most work.

**Option B — Template + customize**
Offer common templates:
- "2 leagues, 3 divisions each (MLB standard)"
- "2 leagues, 4 divisions each"
- "1 league, 4 divisions"
- "1 league, no divisions"
Then let user assign teams to slots.

**Option C — Paste/import**
Let user paste a JSON structure or import from a file. Power-user option.

Recommendation: Option B as primary, with Option C as an advanced fallback.
Option A is nice but high UI effort for alpha.

---

## 5. Settings Page Expansion

### 5.1 Current Settings

The settings page currently has one control: "My Team" dropdown.

### 5.2 Required Settings Sections

**League Identity**
- League name (displayed in header, page title)
- Current year (auto-updated by refresh, but editable)
- StatsPlus URL slug (for external links)

**League Structure**
- Leagues and divisions (the structure from §2.1)
- Teams per division (editable)
- Wild cards per league
- DH rule (informational, affects depth chart)

**Team Identity**
- My team (current — the team highlighted throughout the UI)
- Team abbreviations (editable table)
- Team names (editable table, auto-populated from API)

**Financial**
- Minimum salary
- Pythagorean exponent (advanced, with default)

**Connection**
- StatsPlus credentials (league slug + cookie)
- Connection status indicator
- Last refresh timestamp
- "Test Connection" button

**Data Management**
- Last refresh date
- Record counts (players, ratings, stats)
- "Full Refresh" button (already exists in nav)
- "Reset League" (delete all data, start over)

### 5.3 Settings Storage

Currently split across:
- `config/state.json` — game_date, year, my_team_id
- `config/league_settings.json` — everything else
- `statsplus/.env` — credentials

For multi-league:
- Each league directory has its own `config/state.json` and `config/league_settings.json`
  (including the league's StatsPlus URL slug)
- The StatsPlus session cookie is stored globally in `data/app_config.json`
  (it's user-level auth, shared across all leagues)
- The settings page reads/writes to the active league's files for league-specific
  settings, and to the global config for the cookie

---

## 6. Code Changes Required

### 6.1 League Context Plumbing

**`scripts/db.py`**
- `DB_PATH` must be dynamic, not hardcoded
- Accept a league directory path, resolve `league.db` within it
- `get_conn()` needs to know which league

**`scripts/league_config.py`**
- `_SETTINGS_PATH` and `_STATE_PATH` must be dynamic
- `LeagueConfig` should accept a base directory
- The global `config` singleton needs to be replaceable or scoped

**`statsplus/client.py`**
- League URL slug must come from the active league's config
- Session cookie is global (user-level auth, not league-specific)
- `LEAGUE_URL` and `COOKIE` loaded at module level — needs to be deferred
  or accept parameters. Cookie can remain global; slug must be per-league.

**`web/app.py`**
- Needs a concept of "active league"
- All routes must resolve data from the active league's DB/config
- League switcher in the nav

**`web/queries.py`, `team_queries.py`, `player_queries.py`**
- All import `db` and `league_config` at module level
- Need to use the active league's connection and config
- Module-level constants (`TEAM_ABBR`, `_AL_TEAMS`, etc.) must be
  per-league, not global

### 6.2 League Structure Generalization

**`web/queries.py`**
- Replace `_AL_TEAMS`/`_NL_TEAMS` with dynamic league→team mapping
- `get_batting_leaders()` / `get_pitching_leaders()` — dynamic league splits
- Leader toggle buttons generated from league list

**`web/app.py` (league route)**
- Standings grouping: iterate over `leagues` array, not hardcoded AL/NL
- Wild card computation: per-league from the array
- Division color: from league config, not `startswith("AL")`

**`web/templates/league.html`**
- Division card classes: dynamic from league color config
- Leader buttons: generated from league list
- Standings grid: adapt columns to number of leagues/divisions

**`web/templates/base.html`**
- Page title: from league config, not hardcoded "EMLB"
- League switcher in nav (if multiple leagues configured)

### 6.3 Refresh Pipeline

**`scripts/refresh.py`**
- Must target the active league's DB and config
- Year default from league config, not hardcoded `2033`
- `_refresh_dollar_per_war()` writes to league-specific `league_averages.json`

**`scripts/fv_calc.py`**
- Reads from league-specific DB and config
- Writes to league-specific `prospect_fv` / `player_surplus` tables

### 6.4 Analysis Scripts

**`scripts/farm_analysis.py`, `roster_analysis.py`**
- Read from league-specific DB
- Write scaffolds to league-specific `tmp/`
- Read settings from league-specific config

### 6.5 Constants

**`scripts/constants.py`**
- `ARB_PCT`, `AGING_HITTER`, `AGING_PITCHER`, `OVR_TO_WAR` — these are OOTP
  engine constants, not league-specific. They should remain global.
- `FV_TO_PEAK_WAR`, `DEVELOPMENT_DISCOUNT`, `YEARS_TO_MLB` — also engine
  constants, global is fine.
- `REPLACEMENT_WAR`, `RP_WAR_CAP` — could theoretically vary but are engine
  constants in practice. Keep global.

### 6.6 Percentile Models

**`web/percentiles.py`**
- BABIP regression model was calibrated on EMLB 2028-2032 data
- For other leagues, the model coefficients may not be accurate
- Options: (a) use the same model (good enough for OOTP), (b) recalibrate
  per league (requires historical data), (c) disable percentiles until
  sufficient data exists
- Recommendation: use the same model for alpha — OOTP engine is consistent
  across leagues, so the coefficients should transfer reasonably well

---

## 7. Migration Path

### 7.1 Existing EMLB Data

The current EMLB installation needs to be migrated into the new directory
structure without data loss:

1. Create `data/emlb/` directory
2. Move `emlb.db` → `data/emlb/league.db`
3. Move `config/` → `data/emlb/config/`
4. Move `history/` → `data/emlb/history/`
5. Move `reports/` → `data/emlb/reports/`
6. Extract cookie from `statsplus/.env` → `data/app_config.json` (global)
7. Move league slug from `statsplus/.env` → `data/emlb/config/league_settings.json`
8. Create `data/app_config.json` with `{"active_league": "emlb", "statsplus_cookie": "..."}`
9. Update `league_settings.json` to new `leagues` array format

### 7.2 Settings Migration

Current `league_settings.json` `divisions` format:
```json
{
  "divisions": {
    "AL East": [48, 34, ...],
    "NL West": [45, 53, ...]
  }
}
```

New format (§2.1). A migration script should convert automatically.

---

## 8. Onboarding UX Flow

### 8.1 No League Configured (First Launch)

If no leagues exist in `data/`, the app shows a welcome/setup page instead of
redirecting to a team page. This page explains what the app does and has a
"Set Up Your League" button that starts the wizard (§4.2).

### 8.2 League Switcher

If multiple leagues are configured, the nav bar shows a league selector
(dropdown or pill buttons). Switching leagues:
- Updates the active league in `app_config.json`
- Reloads config and DB connection
- Redirects to the new league's default team page

### 8.3 Credential Management

StatsPlus uses a session cookie for auth, shared across all leagues. The cookie
expires periodically. The app should:
- Store the cookie globally (not per-league)
- Show connection status on the settings page
- Surface a clear error when a refresh fails due to auth
- Make it easy to update the cookie without re-running any league wizard
- When adding a second+ league, skip the cookie step entirely if one is
  already saved and valid

---

## 9. Decisions Log

Decisions made during spec review, prior to implementation.

| # | Decision | Rationale |
|---|---|---|
| D1 | **Request-scoped league context** (not singleton reload) | Singleton reload breaks under concurrent requests, creates stale-state bugs, and treats "active league" as global mutable state. Request-scoped context is the pattern that scales — each request carries its league context and all data access flows from it. Higher upfront cost but no tech debt. |
| D2 | **Full `leagues` array model** (not division naming convention) | Inferring league membership from `startswith("AL")` is fragile and breaks for non-standard structures (single league, conferences, custom names). Explicit league objects with nested divisions is the right data model — build it once, never revisit. |
| D3 | **UI onboarding wizard** (not CLI init script) | Target alpha/beta users are OOTP players, not engineers. If we want real feedback, onboarding must work in the browser. Doesn't need to be fancy — plain HTML forms with minimal JS — but it must exist. |
| D4 | **Multi-league `data/<league>/` from day one** (not league-agnostic flat layout first) | Building league-agnostic on a flat layout then retrofitting multi-league later means a second migration, second round of path plumbing, second round of testing. The marginal cost of doing it now is small; the cost of doing it twice is real. |
| D5 | **Full settings page expansion** (not minimal + JSON editing) | Same principle — build the real configuration surface area once. Division structure editor included, even if it's a simple form rather than drag-and-drop. |
| D6 | **StatsPlus cookie is global** (not per-league) | Cookie is user-level auth tied to the StatsPlus session, not league-specific. One login gives access to all leagues. Only the league URL slug is per-league. Simplifies onboarding for second+ leagues. |

---

## 10. Implementation Plan

Ordered sequence of implementation tasks. Each task is a self-contained unit
of work that can be completed and verified independently. Tasks are ordered by
dependency — later tasks depend on earlier ones.

### Layer 1 — Data Layer Refactor

These tasks restructure how the app finds and connects to data. No UI changes.
Everything continues to work for the existing EMLB league after each task.

#### Task 1.1 — `data/<league>/` directory structure + migration script

Create the new directory layout and a migration script that moves existing
EMLB data into it.

**Creates:**
- `data/emlb/league.db` (moved from `emlb.db`)
- `data/emlb/config/` (moved from `config/`)
- `data/emlb/history/` (moved from `history/`)
- `data/emlb/reports/` (moved from `reports/`)
- `data/emlb/tmp/` (moved from `tmp/`)
- `data/app_config.json` — `{"active_league": "emlb", "statsplus_cookie": "<from .env>"}`

**Changes:**
- `scripts/migrate_to_multi_league.py` — one-time migration script
- Symlinks or compatibility shims so nothing breaks mid-refactor

**Verification:** All existing routes return 200 after migration.

#### Task 1.2 — Dynamic DB path

Make `scripts/db.py` resolve the DB path from a league directory instead of
hardcoded `emlb.db`.

**Changes:**
- `db.py`: `get_conn()` accepts an optional `league_dir` parameter, defaults
  to resolving from active league in `app_config.json`
- `DB_PATH` becomes a function, not a constant

**Verification:** All scripts and web routes still work, hitting `data/emlb/league.db`.

#### Task 1.3 — Dynamic league config

Make `league_config.py` resolve settings/state from a league directory.

**Changes:**
- `LeagueConfig.__init__()` accepts a `base_dir` parameter
- `_SETTINGS_PATH` and `_STATE_PATH` derived from `base_dir`
- Global `config` singleton initializes from active league
- Add helper to resolve active league dir from `data/app_config.json`

**Verification:** `config.my_team_id`, `config.year`, `config.divisions` all
return correct values from `data/emlb/config/`.

#### Task 1.4 — Dynamic StatsPlus client

Decouple the client from the hardcoded `.env` file.

**Changes:**
- `client.py`: `LEAGUE_URL` and `COOKIE` no longer loaded at module level
- New pattern: `client.configure(slug, cookie)` or pass per-call
- Cookie read from `data/app_config.json`, slug from active league's settings
- Remove `statsplus/.env` dependency (migration moves cookie to app_config)

**Verification:** `client.get_date()` works with credentials from new locations.

#### Task 1.5 — Request-scoped league context

Introduce a Flask context pattern so each request knows which league it's
serving.

**Changes:**
- `web/app.py`: `@app.before_request` resolves active league from
  `app_config.json` (or URL parameter / session — TBD)
- Store league context in Flask `g`: `g.league_dir`, `g.config`, `g.db_conn`
- All query modules access league context from `g` instead of module-level
  globals

**This is the largest single task.** It touches every query function that
currently references `_cfg`, `_db`, `TEAM_ABBR`, `TEAM_NAMES`, etc.

Sub-tasks:
- 1.5a: Create `web/league_context.py` with helper functions that read from `g`
- 1.5b: Refactor `queries.py` to use league context
- 1.5c: Refactor `team_queries.py` to use league context
- 1.5d: Refactor `player_queries.py` to use league context
- 1.5e: Refactor `percentiles.py` to use league context
- 1.5f: Update `app.py` routes and Jinja globals

**Verification:** Full regression — all routes return 200, content unchanged.

### Layer 2 — League Structure Generalization

Replace hardcoded AL/NL assumptions with dynamic league structure.

#### Task 2.1 — `leagues` array in settings

Define the new settings format and update `league_config.py` to parse it.

**Changes:**
- `league_settings.json`: add `leagues` array (§2.1 of spec)
- `league_config.py`: new properties — `config.leagues`, `config.league_for_team(tid)`,
  `config.divisions_for_league(league_short)`
- Backward compat: if `leagues` key missing, synthesize from old `divisions`
  format (parse "AL East" → league "AL", division "East")

**Verification:** `config.leagues` returns correct structure for EMLB.

#### Task 2.2 — Dynamic standings grouping

Replace `al_divs`/`nl_divs` hardcoding in the league route.

**Changes:**
- `app.py` league route: iterate over `config.leagues` to group divisions
- Pass `league_groups` (list of `{league, divisions}`) to template instead
  of separate `al_divs`/`nl_divs`
- Wild card computation: per-league from the array

**Verification:** League page renders identical standings for EMLB.

#### Task 2.3 — Dynamic leader splits

Replace hardcoded MLB/AL/NL leader toggle.

**Changes:**
- `queries.py`: `get_batting_leaders()` / `get_pitching_leaders()` build
  team sets dynamically from `config.leagues`
- Return dict keyed by league short name + "All" (not hardcoded "MLB"/"AL"/"NL")
- `league.html`: generate toggle buttons from league list

**Verification:** Leader panels show correct splits for EMLB.

#### Task 2.4 — Dynamic division colors and layout

Replace `div-al`/`div-nl` CSS classes and 2×3 grid assumption.

**Changes:**
- `league.html`: division card class uses league color from config
- CSS: parameterize league colors (CSS custom properties or inline styles)
- Grid layout adapts to `len(leagues) × max(divisions_per_league)`

**Verification:** League page renders correctly for EMLB with same visual appearance.

### Layer 3 — Settings & Onboarding UI

#### Task 3.1 — Expanded settings page

Full settings UI for an existing league.

**Sections:**
- League identity (name, year, StatsPlus slug)
- My team selector (existing, keep)
- League structure (leagues + divisions — read-only display initially)
- Team names and abbreviations (editable table)
- Financial settings (minimum salary, wild cards, pyth exponent, DH rule)
- Connection (cookie, connection status, last refresh)
- Data management (record counts, refresh button, reset)

**Changes:**
- `web/templates/settings.html`: full rebuild
- `web/app.py`: new POST handlers for each settings section
- Settings writes update the active league's JSON files

**Verification:** All settings readable and writable through UI.

#### Task 3.2 — Division structure editor

UI for creating/editing leagues and divisions.

**Changes:**
- Settings page section: list of leagues, each with list of divisions
- Add/remove leagues, add/remove divisions
- Assign teams to divisions (dropdown or multi-select from team list)
- Writes to `leagues` array in `league_settings.json`

**Verification:** Can modify EMLB division structure through UI and see
changes reflected on league page.

#### Task 3.3 — Onboarding wizard

Multi-step flow for adding a new league.

**Steps (from §4.2):**
1. Connect (cookie if needed + slug → validate)
2. Initial data pull (full refresh → progress indicator)
3. League structure (template selection + team assignment)
4. Financial settings (with auto-detected defaults)
5. Select my team
6. Done → redirect to dashboard

**Changes:**
- `web/templates/onboard.html`: multi-step form
- `web/app.py`: wizard routes (`/onboard/step1` through `/onboard/done`)
- Backend: create league directory, write initial config, run refresh

**Verification:** Can onboard a new league from scratch through the browser.

#### Task 3.4 — League switcher

Nav-level control for switching between leagues.

**Changes:**
- `web/templates/base.html`: league dropdown in nav (if >1 league exists)
- `web/app.py`: `/switch-league/<slug>` route — updates `app_config.json`,
  redirects to new league's default team
- Active league shown in nav

**Verification:** Can switch between two leagues and see correct data for each.

#### Task 3.5 — Dynamic page title and branding

League name in header and `<title>`.

**Changes:**
- `base.html`: `<title>{{ league_name }} Dashboard</title>`, header shows league name
- `app.py`: pass `league_name` to all templates via Jinja globals (from league context)

**Verification:** Page title and header show league name, not "EMLB".

### Layer 4 — Refresh Pipeline Updates

#### Task 4.1 — League-aware refresh

Make `refresh.py` target the active league's DB and config.

**Changes:**
- `refresh.py`: resolve DB path, settings path, and client credentials from
  league directory (passed as argument or resolved from app_config)
- Year default from league config, not hardcoded `2033`
- `_refresh_dollar_per_war()` writes to league-specific `league_averages.json`
- Comment in docstring updated (no more "102 teams" assumption)

**Verification:** `python3 scripts/refresh.py` refreshes data into
`data/emlb/league.db`.

#### Task 4.2 — League-aware analysis scripts

Make `fv_calc.py`, `farm_analysis.py`, `roster_analysis.py` target the active
league.

**Changes:**
- Each script resolves paths from league directory
- Scaffold output goes to league-specific `tmp/`
- Reports go to league-specific `reports/`

**Verification:** `python3 scripts/fv_calc.py` writes to `data/emlb/league.db`.

### Layer 5 — Hardening

#### Task 5.1 — Error handling for incomplete leagues

Graceful degradation when league data is missing or stale.

**Changes:**
- Routes check for missing DB, missing settings, empty tables
- Meaningful error pages instead of 500s
- Settings page shows warnings for incomplete configuration

#### Task 5.2 — Credential refresh flow

Easy cookie update without re-onboarding.

**Changes:**
- Settings page: "Update Cookie" field with test button
- Clear error message when refresh fails due to expired cookie
- Cookie update writes to global `app_config.json`

#### Task 5.3 — Data validation after refresh

Verify data integrity after each refresh.

**Changes:**
- Post-refresh checks: expected table counts, no orphaned records
- Surface warnings in UI if validation fails

---

## 11. Open Questions

1. **Team abbreviations**: Auto-generate from team names, or require manual
   input? Auto-generation is error-prone for non-standard names. Could offer
   editable defaults.

2. **Affiliate detection**: The API provides `parent_team_id` relationships.
   Should we auto-build the affiliate tree, or let users configure it? Auto
   is probably fine — affiliates are structural, not subjective.

3. **Multi-user**: Is this ever multi-user (shared server), or always
   single-user (local install)? This affects auth, data isolation, and
   deployment. For alpha, assume single-user local install.

4. **OOTP version differences**: Different OOTP versions may have different
   rating scales, position codes, or API responses. Do we need a version
   setting? For alpha, assume OOTP 26.

5. **League format edge cases**: Some StatsPlus leagues have unusual formats
   (single league, no divisions, unbalanced divisions, independent leagues
   mixed with affiliated). How much do we support in alpha? Recommendation:
   support the common cases (1-2 leagues, 2-4 divisions each) and document
   limitations.

6. **Historical data**: When a user onboards mid-season, they have no
   historical stats for percentile models or trend analysis. What degrades
   gracefully vs. what breaks? Need to audit all features that depend on
   multi-year data.

7. **Cookie auth UX**: StatsPlus uses session cookies, not API keys. These
   expire and are awkward to extract from a browser. Is there a better auth
   flow? This may be a StatsPlus platform limitation we can't solve, but we
   should make the cookie update process as painless as possible (browser
   extension? bookmarklet? clear instructions with screenshots?).

8. **Refresh rate limits**: The ratings endpoint has a ~4 min rate limit.
   With multiple leagues, users might hit this more often. Document the
   limitation and consider queuing refreshes.

---

## 12. Risk Assessment

| Risk | Impact | Mitigation |
|---|---|---|
| League structure variety | High — unusual formats break assumptions | Support common cases, document limitations, fail gracefully |
| Cookie expiration UX | Medium — users get stuck on auth | Clear error messages, easy update flow, setup instructions |
| Module-level globals | High — `TEAM_ABBR`, `_AL_TEAMS`, DB connection all loaded at import time | Refactor to lazy loading or request-scoped context |
| Migration breaks existing data | High — EMLB data loss | Migration script with backup, tested thoroughly |
| Percentile model accuracy | Low — OOTP engine is consistent | Use shared model for alpha, revisit if users report issues |
| Scope creep | High — this is a large refactor | Strict phase boundaries, alpha ships with Phase 1 only |

---

## 13. Out of Scope for Alpha

- Multi-user / shared server deployment
- Cross-league analysis or comparison
- OOTP version auto-detection
- Per-league percentile model calibration
- League format auto-detection from StatsPlus
- Mobile-responsive onboarding wizard
- Internationalization / localization
