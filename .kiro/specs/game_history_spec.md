# Game History & Recent Games Specification

## Overview

Add game history storage and a recent games dashboard panel. This is a separate effort from the Phase 1 dashboard — it requires a new DB table, a new API integration in the refresh pipeline, and a new dashboard panel.

---

## New DB Table: `games`

```sql
CREATE TABLE IF NOT EXISTS games (
    game_id     INTEGER PRIMARY KEY,
    date        TEXT NOT NULL,
    home_team   INTEGER NOT NULL,
    away_team   INTEGER NOT NULL,
    runs_home   INTEGER NOT NULL,
    runs_away   INTEGER NOT NULL,
    innings     INTEGER DEFAULT 9,
    winning_pitcher INTEGER,
    losing_pitcher  INTEGER,
    save_pitcher    INTEGER,
    game_type   INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_games_date ON games(date);
CREATE INDEX IF NOT EXISTS idx_games_home ON games(home_team);
CREATE INDEX IF NOT EXISTS idx_games_away ON games(away_team);
```

---

## Refresh Pipeline Changes

On data refresh:
1. Read the most recent `date` from the `games` table (or use start-of-season if empty)
2. Call `client.get_game_history()`
3. Upsert all games with `date > last_stored_date`
4. First run backfills all historical games (~24K rows)

The `game_history` endpoint has a ~4 min rate limit. If rate-limited, skip game history and log a warning — don't block the rest of the refresh.

---

## Dashboard Panel: Recent Games

**Source:** `games` table filtered to team_id=44 (home or away), ordered by date descending, limit 10.

**Display:** List of recent games:
- Date, Opponent, Score (W/L indicator), Home/Away

**Behavior:**
- Win/loss derived from comparing runs
- Opponent name resolved from `teams` table

---

## Refresh Button

**Endpoint:** `POST /api/refresh`

**Behavior:**
1. Runs `refresh.py --league [year]` + `fv_calc.py`
2. Includes game history pull (with rate-limit tolerance)
3. Updates `config/state.json` with new game date
4. Returns status and new game date
5. Dashboard auto-reloads on completion

Runs in a background thread. UI shows a spinner. Non-blocking — user can view stale dashboard while refresh runs.

---

## Dependencies

- Phase 1 dashboard (from `ui_spec.md`) should be built first
- Game history panel slots into the existing dashboard layout
