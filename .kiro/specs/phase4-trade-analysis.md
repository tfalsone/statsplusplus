# League-Wide Trade Analysis — Phase 4

## Overview

Build a query layer on top of the fully populated DB to support trade target identification, positional need/supply matching, and surplus-balanced trade package generation. The Angels remain the workflow focus — this phase enables informed decisions about other teams, not management of them.

---

## Prerequisites

- Phase 3 complete: `--league` refresh has run, all teams in DB
- Two-tier ratings storage implemented (see Phase 3 spec) before first `--league` refresh
- League-wide FV estimates populated in `prospect_fv` table

---

## Architecture Decisions

### FV calculation scope
Full league FV calculation runs against all players in the DB. Two paths:
- **Prospects** (non-MLB, age ≤ 25): FV from the prospect model (`calc_fv` logic extracted from `farm_analysis.py`)
- **MLB players**: surplus value from the contract value model (already implemented)

Both are stored in `prospect_fv` with `eval_date = game_date`. The table already supports this — no schema change needed.

### Ratings history — two-tier storage
Angels org players: full snapshot history retained (`INSERT OR IGNORE` by `(player_id, snapshot_date)`).
All other teams: current ratings only, overwritten on each `--league` refresh (`INSERT OR REPLACE`).

This keeps the ratings table flat at ~30,000 rows regardless of refresh cadence. See Phase 3 spec for implementation details.

### `prospect_fv` at league scale
18,000 players × N eval dates. At weekly evals: ~936,000 rows/year — trivial for SQLite. No special handling needed; the existing schema is sufficient.

### Motivated seller detection — deferred
Determining which teams are motivated sellers requires org-level analysis (roster surplus, payroll pressure, rebuild status) for all teams. This is deferred — Phase 4a focuses on the query layer only. Motivated seller signals can be added in Phase 4b once the query layer is validated.

### Query interface
CLI scripts for structured queries; agent interprets results and drives the conversation. No hardcoded Angels assumptions in query scripts — all filters are parameters.

---

## Implementation Plan

### Task 1 — Extract FV calculation into shared utility
- Move `calc_fv()`, `dev_weight()`, `effective_pot()`, `versatility_bonus()` from `farm_analysis.py` into `player_utils.py`
- `farm_analysis.py` imports from `player_utils` — no behavior change

### Task 2 — League-wide FV calculation script
- Add `scripts/fv_calc.py`: iterates all non-MLB players in DB (age ≤ 25), computes FV using shared utility, upserts into `prospect_fv`
- Runs as a post-step after `--league` refresh: `python3 scripts/fv_calc.py`
- Angels org players already have FV from `farm_analysis.py` — `fv_calc.py` skips them or overwrites (TBD)

### Task 3 — Surplus value for MLB players
- Extend `fv_calc.py` to also compute surplus value for all MLB players using `contract_value` logic
- Store result in a new `player_surplus` table (see schema below)

### Task 4 — Trade target query script
- Add `scripts/trade_targets.py`: query DB for players matching position, age, contract, and FV/surplus criteria
- Output: ranked list with player name, team, age, FV/surplus, contract status
- Parameters: `--bucket`, `--age-max`, `--fv-min`, `--surplus-min`, `--exclude-team`
- **Filter requirement:** All queries against `player_surplus` must include `ovr >= 30`. The game engine places raw international signees (age 16-18, Ovr 20) on the MLB roster with `level=1`, so they appear in `player_surplus` alongside real MLB players. Without this filter they pollute results.

### Task 5 — Trade package calculator (cross-team)
- Extend `trade_calculator.py` to accept players from any team (currently Angels-centric)
- Given a target player and Angels assets to move, compute surplus balance on both sides

---

## New Schema

```sql
CREATE TABLE IF NOT EXISTS player_surplus (
    player_id   INTEGER,
    eval_date   TEXT,
    bucket      TEXT,
    age         INTEGER,
    ovr         INTEGER,
    fv          INTEGER,
    fv_str      TEXT,
    surplus     INTEGER,   -- base case surplus over remaining control
    level       TEXT,
    team_id     INTEGER,
    parent_team_id INTEGER,
    PRIMARY KEY (player_id, eval_date)
);
```

This consolidates FV (prospects) and surplus (MLB) into one queryable table, avoiding a join between `prospect_fv` and a separate MLB surplus table for most queries.

---

## Out of Scope (Phase 4)

- Motivated seller detection (Phase 4b)
- Automated trade proposal generation (Phase 4b)
- UI (Phase 5)
- Prose org reports for non-Angels teams

---

## Known Limitations

### Two-way player surplus — resolved
Two-way players (meaningful batting AND pitching stats in the same season) now sum batting WAR + pitching WAR as their combined peak WAR input in `fv_calc.py`. 7 two-way players identified in the 2033 dataset.

### Traded player incomplete stat lines — resolved
PK changed to `(player_id, year, split_id, team_id)` — all per-team rows now stored. `stint` field added to both stat tables. `_load_stat_history` aggregates across teams via `GROUP BY player_id, year`. Incomplete seasons (single `stint=1` row with no matching team row) are flagged and downweighted by 0.5 in the WAR average. Historical stats re-pulled for 2031/2032/2033.

### Batch surplus limited to signed contract only — by design
`player_surplus` (computed by `fv_calc.py`) only projects value over the player's remaining **signed** contract years. Pre-arb and arb years beyond the signed deal are not inferred.

**Reason:** Veteran players on league-minimum deals ($825K) are indistinguishable from pre-arb players in the contract data. Projecting additional team-control years for all short contracts would significantly overstate surplus for veterans. Example: Austin Franklin (age 35, $825K) would be incorrectly treated as a pre-arb player with 5 years of control.

**Implication:** Batch surplus for pre-arb players (e.g. Cowgill, $83M for 1 signed year) understates true trade value. For trade analysis involving pre-arb or arb-eligible players, use `contract_value.py` on-demand where the player's actual status is known.

**Future improvement:** If the API exposes service time or arb eligibility status, this constraint can be lifted.
