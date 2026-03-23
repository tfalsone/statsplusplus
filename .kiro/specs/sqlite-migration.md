# SQLite Migration — Phase 2

## Overview

Migrate the Anaheim Angels data from flat JSON files to a SQLite database (`league.db`). This is a proof-of-concept scoped to the Angels org only. The goal is to validate the schema and query patterns before expanding to the full league in Phase 3.

The JSON files remain on disk during Phase 2 as a fallback. `refresh.py` writes to both JSON and DB. Analysis scripts are updated to query the DB via a new data access layer — they do not read JSON directly after this migration.

JSON files will be deprecated in Phase 3 once league-wide data is in the DB and dual-write is no longer needed. The DB schema and data access layer are designed for all teams from the start — no Angels-specific assumptions.

## Scope Philosophy

The platform is Angels-focused from a workflow perspective — reports, recommendations, and decisions center on the Angels org. However, the data layer and analysis tools must be team-agnostic: any script or query that filters to the Angels by hardcoded ID is a liability once league-wide data exists.

**Practical rule:** The Angels org ID (`44`) may appear in guide docs, session context, and CLI defaults — but never in DB schema, query functions, or script logic. Callers pass `parent_team_id` as a parameter; scripts do not assume which team they're analyzing.

Guide docs and agent instructions that reference "Angels" by name will be updated in Phase 3 to use parameterized team references where the logic is team-agnostic. Workflow-level references (e.g. "you are the GM of the Angels") are intentional and stay.

---



### Functional

1. `league.db` is created and populated by `scripts/refresh.py` on a full refresh
2. All Angels org data is queryable from the DB: players, ratings, contracts, batting stats, pitching stats, prospect FV history
3. Analysis scripts (`contract_value.py`, `prospect_value.py`, `trade_calculator.py`, `farm_analysis.py`) read from the DB instead of JSON where applicable
4. Prospect FV snapshots written to DB on each farm evaluation (replacing or supplementing `config/prospect_history.json`)
5. The DB schema supports future league-wide expansion — no Angels-specific assumptions baked in (team_id foreign keys, not hardcoded filters)

### Non-Functional

1. JSON files are not removed during Phase 2 — DB writes are additive; JSON is a fallback only
2. JSON files are deprecated in Phase 3 — analysis scripts must not re-introduce direct JSON reads after this migration
3. No data loss: every field currently stored in JSON must be present in the DB schema
4. Schema must match the design in `docs/expansion_roadmap.md` exactly unless a deviation is explicitly noted here
5. No Angels-specific hardcoding in the DB layer — all queries filter by `team_id` or `parent_team_id` as parameters

---

## Schema

```sql
CREATE TABLE teams (
    team_id       INTEGER PRIMARY KEY,
    name          TEXT,
    level         TEXT,
    parent_team_id INTEGER,
    league        TEXT
);

CREATE TABLE players (
    player_id     INTEGER PRIMARY KEY,
    name          TEXT,
    age           INTEGER,
    team_id       INTEGER,
    parent_team_id INTEGER,
    level         TEXT,
    pos           INTEGER,
    role          INTEGER
);

CREATE TABLE ratings (
    player_id     INTEGER,
    snapshot_date TEXT,
    ovr           INTEGER,
    pot           INTEGER,
    -- batting
    cntct INTEGER, gap INTEGER, pow INTEGER, eye INTEGER, ks INTEGER,
    speed INTEGER, steal INTEGER,
    -- pitching
    stf INTEGER, mov INTEGER, ctrl_r INTEGER, ctrl_l INTEGER,
    fst INTEGER, snk INTEGER, crv INTEGER, sld INTEGER, chg INTEGER,
    splt INTEGER, cutt INTEGER, cir_chg INTEGER, scr INTEGER,
    frk INTEGER, kncrv INTEGER, knbl INTEGER, stm INTEGER, vel TEXT,
    -- pot pitching
    pot_stf INTEGER, pot_mov INTEGER, pot_ctrl INTEGER,
    pot_fst INTEGER, pot_snk INTEGER, pot_crv INTEGER, pot_sld INTEGER,
    pot_chg INTEGER, pot_splt INTEGER, pot_cutt INTEGER,
    pot_cir_chg INTEGER, pot_scr INTEGER, pot_frk INTEGER,
    pot_kncrv INTEGER, pot_knbl INTEGER,
    -- pot batting
    pot_cntct INTEGER, pot_gap INTEGER, pot_pow INTEGER, pot_eye INTEGER, pot_ks INTEGER,
    -- positional
    c INTEGER, ss INTEGER, second_b INTEGER, third_b INTEGER,
    first_b INTEGER, lf INTEGER, cf INTEGER, rf INTEGER,
    pot_c INTEGER, pot_ss INTEGER, pot_second_b INTEGER, pot_third_b INTEGER,
    pot_first_b INTEGER, pot_lf INTEGER, pot_cf INTEGER, pot_rf INTEGER,
    ofa INTEGER, ifa INTEGER, c_arm INTEGER, c_blk INTEGER, c_frm INTEGER,
    -- character
    int_ INTEGER, wrk_ethic TEXT, greed TEXT, loy TEXT, lead TEXT, acc TEXT,
    PRIMARY KEY (player_id, snapshot_date)
);

CREATE TABLE contracts (
    player_id             INTEGER PRIMARY KEY,
    team_id               INTEGER,
    contract_team_id      INTEGER,
    is_major              INTEGER,
    years                 INTEGER,
    current_year          INTEGER,
    salary_0              INTEGER,
    salary_1              INTEGER,
    salary_2              INTEGER,
    salary_3              INTEGER,
    salary_4              INTEGER,
    salary_5              INTEGER,
    salary_6              INTEGER,
    salary_7              INTEGER,
    salary_8              INTEGER,
    salary_9              INTEGER,
    salary_10             INTEGER,
    salary_11             INTEGER,
    salary_12             INTEGER,
    salary_13             INTEGER,
    salary_14             INTEGER,
    no_trade              INTEGER,
    last_year_team_option INTEGER,
    last_year_player_option INTEGER
);

CREATE TABLE batting_stats (
    player_id INTEGER,
    year      INTEGER,
    team_id   INTEGER,
    split_id  INTEGER,
    ab INTEGER, h INTEGER, d INTEGER, t INTEGER, hr INTEGER,
    r INTEGER, rbi INTEGER, sb INTEGER, bb INTEGER, k INTEGER,
    avg REAL, obp REAL, slg REAL, war REAL,
    PRIMARY KEY (player_id, year, split_id)
);

CREATE TABLE pitching_stats (
    player_id INTEGER,
    year      INTEGER,
    team_id   INTEGER,
    split_id  INTEGER,
    ip REAL, g INTEGER, gs INTEGER, w INTEGER, l INTEGER, sv INTEGER,
    era REAL, k INTEGER, bb INTEGER, ha INTEGER, war REAL,
    PRIMARY KEY (player_id, year, split_id)
);

CREATE TABLE prospect_fv (
    player_id INTEGER,
    eval_date TEXT,
    fv        INTEGER,
    fv_str    TEXT,
    level     TEXT,
    bucket    TEXT,
    PRIMARY KEY (player_id, eval_date)
);

CREATE TABLE org_reports (
    team_id     INTEGER,
    report_date TEXT,
    report_md   TEXT,
    PRIMARY KEY (team_id, report_date)
);
```

## Data Access Layer

Analysis scripts must not issue raw SQL or read JSON directly. All DB access goes through `scripts/data.py`, which exposes typed query functions. This keeps SQL centralized and makes the JSON→DB transition transparent to callers.

Minimum interface needed for Phase 2:

```python
# scripts/data.py
def get_ratings(parent_team_id: int, snapshot_date: str = None) -> list[dict]
def get_contracts(parent_team_id: int) -> list[dict]
def get_batting_stats(parent_team_id: int, year: int, split_id: int = 1) -> list[dict]
def get_pitching_stats(parent_team_id: int, year: int, split_id: int = 1) -> list[dict]
def get_players(parent_team_id: int) -> list[dict]
```

- `snapshot_date=None` returns the most recent snapshot per player
- All functions return list of dicts matching the existing JSON field names where possible (eases migration in callers)
- `parent_team_id` is the filter — never hardcode `44`

---



### Task 1 — DB initialization
- Add `scripts/db.py`: `get_conn()` (creates `league.db` if absent) and `init_schema()` (runs all CREATE TABLE IF NOT EXISTS statements)

### Task 2 — Data access layer
- Add `scripts/data.py` with the query functions defined above
- All callers use this module — no raw SQL outside `db.py`/`data.py`

### Task 3 — Populate teams table
- In `scripts/refresh.py`, after writing `config/teams.json`, upsert all rows into `teams`

### Task 4 — Populate players table
- After writing each `roster.json` (MLB + all farm levels), upsert into `players`
- Replace existing rows by `player_id`

### Task 5 — Populate ratings table
- After writing `ratings.json`, upsert into `ratings` with `snapshot_date = game_date`
- Append-only by `(player_id, snapshot_date)` — do not overwrite prior snapshots

### Task 6 — Populate contracts table
- After writing `angels/contracts.json`, upsert into `contracts`
- Replace existing rows by `player_id`

### Task 7 — Populate batting_stats and pitching_stats
- After writing stat JSON files, upsert into respective tables
- Replace existing rows by `(player_id, year, split_id)`

### Task 8 — Migrate prospect_fv writes
- In `scripts/farm_analysis.py`, after writing to `config/prospect_history.json`, also upsert into `prospect_fv`
- `fv_str` stores display value (e.g. `"45+"`); `fv` stores numeric floor (e.g. `45`)

### Task 9 — Update analysis scripts to use data access layer
- `contract_value.py`: replace JSON reads with `data.get_ratings()` and `data.get_contracts()`
- `prospect_value.py`: replace farm JSON reads with `data.get_ratings()`
- `trade_calculator.py`: no direct JSON reads currently — no change needed
- `farm_analysis.py`: scaffold generation reads raw JSON by design — defer to Phase 3

### Task 10 — Validation
- After a full refresh, spot-check row counts against JSON record counts for players, ratings, contracts, batting_stats, pitching_stats
- Document the validation command in `RULES.md`

---

## Out of Scope (Phase 2)

- League-wide data pull (Phase 3)
- Removing JSON files (Phase 3)
- `org_reports` table population
- UI (Phase 5)
- `fielding_stats` table — low priority for current analysis; add in Phase 3
- `farm_analysis.py` DB reads — scaffold generation stays JSON-based until Phase 3

---

## Open Questions

- Should `refresh.py` drop JSON writes after Phase 3? **Decision: yes — JSON is deprecated in Phase 3. Dual-write is Phase 2 scaffolding only.**
- `ratings` snapshot cadence: the DB preserves history by `snapshot_date`. Is weekly granularity sufficient? **Assumed yes — revisit if FV tracking needs finer resolution.**
