# SQLite Migration — Phase 3: League-Wide Data Sync

## Overview

Expand the data pipeline to cover all 102 league teams. All player, ratings, contract, and stats data is written to `league.db`. Angels JSON files are retained for backward compatibility with `farm_analysis.py`; all other teams are DB-only.

After Phase 3, the DB is the authoritative data source for all cross-team queries. JSON files for non-Angels teams are never written.

---

## Scope Philosophy

Phase 3 does not change the *workflow* — the Angels are still the primary focus. It changes the *data availability*: any team's players, ratings, and contracts become queryable from the DB, enabling trade target identification and org comparisons in Phase 4.

---

## Key Facts (inform implementation)

- `client.get_ratings()` pulls **all players league-wide in one job** — `player_ids` is a client-side filter. A league-wide ratings pull takes the same ~5 minutes as an Angels-only pull. No per-team batching needed.
- `client.get_contracts()` already returns all teams — no change needed.
- `client.get_players()` already returns all teams — no change needed.
- `client.get_player_batting_stats()` and `get_player_pitching_stats()` return all players when called without `pid` — same pattern as ratings.
- The `parent_team_id = 0` issue for MLB-level players (discovered in Phase 2) applies league-wide. The `data.py` `team_id = ? OR parent_team_id = ?` pattern handles this correctly.

---

## Requirements

### Functional

1. `scripts/refresh.py` supports a `--league` flag that pulls all 102 orgs and writes to DB
2. All players, ratings, contracts, batting stats, and pitching stats for all teams are stored in `league.db`
3. Angels JSON files continue to be written on both `refresh.py` (default) and `refresh.py --league` runs
4. Non-Angels teams have no JSON files — DB only
5. `data.py` query functions work for any `parent_team_id`, not just 44
6. League-calibrated `$/WAR` is computed from actual DB data and stored in `config/league_averages.json`

### Non-Functional

1. League-wide refresh is designed to run between sessions (not interactively) due to wall-clock time
2. Ratings pull is a single API call — do not loop per team
3. No Angels-specific hardcoding introduced in Phase 3 code

---

## Implementation Plan

### Task 1 — League-wide player and roster sync
- In `refresh.py --league` mode: write all players from `client.get_players()` to `players` table (no JSON)
- Angels org players still also written to JSON as today

### Task 2 — League-wide ratings sync
- Call `client.get_ratings()` with no `player_ids` filter — returns all ~18,000 players
- Upsert all rows into `ratings` table with `snapshot_date = game_date`
- Angels subset still written to `angels/ratings.json` and farm level `ratings.json` files

### Task 3 — League-wide contracts sync
- `client.get_contracts()` already returns all teams — upsert all rows (currently only Angels are upserted)
- No JSON written for non-Angels contracts

### Task 4 — League-wide stats sync
- Call batting and pitching stat endpoints without `player_ids` filter
- Upsert all rows into `batting_stats` and `pitching_stats`
- Angels subset still written to JSON as today

### Task 5 — League-calibrated $/WAR
- After stats and contracts are populated, compute: `total_mlb_payroll / total_mlb_war` from DB
- Store result in `config/league_averages.json` under `dollar_per_war`
- Update `player_utils.py` `dollars_per_war()` to read from `league_averages.json` if present, fall back to hardcoded `$9,500,000`

### Task 6 — Deprecate Angels JSON reads in `farm_analysis.py`
- Replace `load_level()` JSON reads with `data.get_ratings(parent_team_id, level=...)` calls
- This is the last script reading farm JSON directly
- After this task, JSON files for the Angels are written but not read by any script

### Task 7 — Validation
- After a league-wide refresh, verify: player count ≈ 18,000+, ratings count matches players, contracts count matches league total
- Add league-wide validation command to `RULES.md`

---

## Out of Scope (Phase 3)

- Removing Angels JSON files (can be done after Task 6 is validated)
- Org reports for non-Angels teams (Phase 4)
- Trade target query interface (Phase 4)
- UI (Phase 5)

---

## Refresh Modes After Phase 3

| Command | Scope | Duration | Use case |
|---|---|---|---|
| `python3 scripts/refresh.py` | Angels org only | ~5 min | Active session, quick data update |
| `python3 scripts/refresh.py --league` | All all teams | ~5–10 min | Between sessions, before trade analysis |

Both modes write Angels JSON. Only `--league` populates non-Angels DB rows.

---

## Open Questions

- Should `--league` replace the Angels-only refresh entirely, or remain a separate mode? **Decision: keep both — Angels-only is faster for active sessions where you only need current org data.**
- Stats endpoints: do batting/pitching stats return all teams without a filter, or require pagination? **Resolved: all teams returned without filter. No pagination needed.**

---

## Architecture Decisions

### Ratings history retention (two-tier storage)
Historical ratings snapshots are only retained for Angels org players. All other teams store current ratings only — overwritten on each `--league` refresh.

**Rationale:** At 18,000 players × weekly snapshots, full league ratings history would accumulate ~560MB/year. Non-Angels historical ratings have no analytical value for current use cases — trade analysis only needs current grades.

**Implementation:** The `_upsert_ratings()` function in `refresh.py` uses `INSERT OR IGNORE` for Angels org players (preserves history by `(player_id, snapshot_date)` key) and `INSERT OR REPLACE` for all others (overwrites current row). Schema is unchanged.

**Must be implemented before the first `--league` refresh** — once non-Angels rows accumulate with snapshot dates, they cannot be collapsed without a migration.

