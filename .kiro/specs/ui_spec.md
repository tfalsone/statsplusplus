# Web UI Specification — Phase 1 Dashboard

## Overview

A local web application providing an at-a-glance dashboard for EMLB league management. Phase 1 is a read-only dashboard surfacing data that already exists in the DB.

**Stack:** Flask (Python) backend, Jinja2 server-rendered templates, minimal JS. Reads from `league.db`. Single process, runs locally.

**Design principle:** The UI is a view layer over the existing data and valuation engine. No business logic in the web layer — all valuation, FV calculation, and surplus math stays in the existing scripts. The Flask app queries the DB only.

---

## Scope

Phase 1 displays only data that is already computed and stored in `league.db`. No new data pipelines, no new DB tables, no new API calls on page load.

The current team is hardcoded to Anaheim Angels (team_id=44). Team-agnostic configuration is a separate future task.

---

## Dashboard Panels

### Panel 1: Team Summary Bar

**Source:** `config/state.json`, `player_surplus`, `prospect_fv`

**Display:** Key metrics across the top of the dashboard:
- Game Date, "Anaheim Angels", Total MLB Surplus ($M), Farm System Surplus ($M), # of FV 50+ Prospects

### Panel 2: Standings

**Source:** `team_batting_stats` + `team_pitching_stats` (split_id=1 for current year)

**Display:** League-wide standings table ranked by pythagorean win%. Columns:
- Rank, Team, W, L, Pct, GB, RS, RA, Run Diff

**Behavior:**
- Angels highlighted in the table
- Games derived from `IP / 9` (rounded)
- Pythagorean exponent: 1.83
- GB computed from win% differential × games vs leader

### Panel 3: MLB Roster Overview

**Source:** `players` (level='1', parent_team_id=44) joined with `player_surplus` (latest eval_date) and `batting_stats`/`pitching_stats` (current year, split_id=1)

**Display:** Two sub-tables — position players and pitchers.

Position players columns:
- Name, Age, Pos, Ovr, WAR, Surplus ($M), AVG/OBP/SLG

Pitcher columns:
- Name, Age, Role (SP/RP/CL), Ovr, WAR, Surplus ($M), ERA, IP, K

**Behavior:**
- Sorted by surplus descending within each sub-table
- Role derived from `role` field in `players` table (11=SP, 12=RP, 13=CL)
- Surplus and WAR from `player_surplus` for latest `eval_date`

### Panel 4: Farm System Top Prospects

**Source:** `prospect_fv` (latest eval_date) joined with `players` (parent_team_id=44, level != '1')

**Display:** Top 15 prospects by FV. Columns:
- Rank, Name, FV (with + notation), Bucket, Level, Age, Prospect Surplus ($M)

**Behavior:**
- Sorted by FV descending (FV+ ranks above same base FV), then age ascending
- Level displayed as human-readable string (AAA, AA, A, etc.)

---

## App Structure

```
web/
├── app.py              # Flask app, routes, config
├── queries.py          # All DB queries (thin wrappers, no business logic)
├── templates/
│   ├── base.html       # Layout shell (header, nav, footer)
│   └── dashboard.html  # Dashboard page with all panels
└── static/
    └── style.css       # Minimal styling
```

The `web/` directory sits alongside `scripts/`, `statsplus/`, etc.

### Routes

| Method | Path | Description |
|---|---|---|
| GET | `/` | Dashboard (redirect to `/dashboard`) |
| GET | `/dashboard` | Main dashboard page |

### Configuration

Flask app reads `config/state.json` for:
- `game_date` — displayed on dashboard, used for queries
- `year` — current season year

Angels team_id (44) is hardcoded in Phase 1.

---

## Design Notes

- No external CSS frameworks. Clean, minimal table-based layout. Dark theme (easier on the eyes for long sessions).
- No JavaScript frameworks. Vanilla JS only if needed (e.g. sortable tables later).
- All monetary values displayed in $M with 1 decimal place.
- All queries filter to the latest `eval_date` in `prospect_fv`/`player_surplus`.
- The dashboard should load fast — all data comes from SQLite, no API calls on page load.

---

## Out of Scope (Phase 1)

- Game history / recent games panel (separate spec: `game_history_spec.md`)
- Refresh button / data pipeline triggers
- Team-agnostic configuration / team selector
- Player detail cards
- Trade workbench
- AI assistant
