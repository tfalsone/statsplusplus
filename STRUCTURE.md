# Directory Structure

```
statsplusplus/
├── README.md
├── PURPOSE.md              # Project goals and design principles
├── STRUCTURE.md            # This file
├── RULES.md                # Data pull and storage rules
│
├── data/                           # Runtime data (gitignored)
│   ├── app_config.json                 # Global config: active_league, statsplus_cookie
│   ├── logs/                           # Rotating log files
│   └── <league>/                       # Per-league data directory (e.g. data/vmlb/)
│       ├── league.db                       # SQLite database
│       ├── config/
│       │   ├── state.json                      # Current game date, year, my_team_id
│       │   ├── league_settings.json            # Team names/abbr, divisions, role/pos/level maps, financial settings
│       │   ├── league_averages.json            # League-wide batting/pitching averages + $/WAR
│       │   └── model_weights.json              # Calibrated valuation tables (OVR_TO_WAR, FV, ARB, scarcity)
│       ├── history/
│       │   ├── prospects.json                  # Scouting summaries + FV history (keyed by player_id)
│       │   └── roster_notes.json               # MLB player summaries (keyed by player_id)
│       ├── reports/<year>/                     # Published analysis reports
│       └── tmp/                                # Intermediate scaffolds (script output)
│
├── scripts/
│   ├── league_context.py       # Active league resolver (get_league_dir, get_active_league_slug)
│   ├── league_config.py        # Single abstraction for league-specific settings
│   ├── log_config.py           # Centralized logging (rotating file + console)
│   ├── constants.py            # Shared constants (FV→WAR, aging curves, arb %, pitch fields)
│   ├── db.py                   # SQLite schema, migrations, connection management
│   ├── data.py                 # Data access layer (typed query functions)
│   ├── player_utils.py         # Shared evaluation (bucketing, FV calc, WAR curves, aging)
│   ├── refresh.py              # API → DB pipeline (full league refresh)
│   ├── fv_calc.py              # Batch FV + surplus computation (prospect_fv, player_surplus)
│   ├── calibrate.py            # League-specific model calibration (OVR_TO_WAR, FV, ARB, scarcity)
│   ├── projections.py          # Player projections for depth chart planning
│   ├── contract_value.py       # MLB contract surplus/deficit breakdown
│   ├── prospect_value.py       # Prospect surplus calculator
│   ├── farm_analysis.py        # CLI: Farm system report generator
│   ├── roster_analysis.py      # CLI: MLB roster scaffold generator
│   ├── prospect_query.py       # CLI: League-wide prospect rankings
│   ├── trade_calculator.py     # CLI: Trade surplus balance evaluator
│   ├── standings.py            # CLI: Pythagorean standings
│   └── free_agents.py          # CLI: Free agent class analysis
│
├── web/
│   ├── app.py                  # Flask app, routes, onboarding wizard, refresh endpoint
│   ├── web_league_context.py   # Request-scoped league context (DB connection, config)
│   ├── queries.py              # League-wide queries (prospects, standings, leaders)
│   ├── team_queries.py         # Team queries (roster, depth chart, contracts, farm)
│   ├── player_queries.py       # Player detail (ratings, stats, splits, surplus)
│   ├── percentiles.py          # Percentile rankings with expected-value modeling
│   ├── templates/
│   │   ├── base.html               # Layout (header, nav, breadcrumbs, refresh, player hover popup)
│   │   ├── league.html             # League dashboard (standings, leaders, prospects)
│   │   ├── team.html               # Team page (roster, depth chart, contracts, farm)
│   │   ├── player.html             # Player page (ratings, stats, percentiles)
│   │   ├── settings.html           # Settings (team, identity, structure, financial, connection)
│   │   ├── onboard.html            # Onboarding wizard (connect, configure, refresh)
│   │   └── _structure_editor.html  # League structure editor (shared partial)
│   └── static/
│       ├── style.css               # Dark theme CSS
│       ├── sort.js                 # Client-side table sorting
│       └── assets/                 # Favicon and logo files
│
├── statsplus/
│   └── client.py               # StatsPlus API client (HTTP, CSV parsing, ratings format handling)
│
├── tests/
│   └── test_client.py          # API client tests
│
└── docs/                       # Design docs, analysis guides, changelog
    └── valuation_model.md          # Plain-language explanation of FV, surplus, and WAR models
```

## DB Tables (league.db)

| Table | Owner | Description |
|---|---|---|
| `players` | `refresh.py` | All players across all orgs and levels |
| `teams` | `refresh.py` | Team ID → name, level, parent org, league |
| `ratings` | `refresh.py` | Scouting ratings (121 cols). Overall + L/R splits for batting and pitching tools, defensive grades, character traits, demographics. Extended ratings (BABIP, HRA, PBABIP, Prone) populated when the league's OOTP version provides them. PK: `(player_id, snapshot_date)` for history tracking. |
| `contracts` | `refresh.py` | Active contracts league-wide (up to 15 salary years) |
| `batting_stats` | `refresh.py` | MLB batting stats by player/year/split/team |
| `pitching_stats` | `refresh.py` | MLB pitching stats by player/year/split/team |
| `fielding_stats` | `refresh.py` | Player fielding stats by position (G, IP, TC, E, ZR, framing, arm) |
| `team_batting_stats` | `refresh.py` | Team-level batting aggregates by year/split |
| `team_pitching_stats` | `refresh.py` | Team-level pitching aggregates by year/split |
| `games` | `refresh.py` | Game results with scores, WP/LP/SV |
| `prospect_fv` | `fv_calc.py` | FV grades for all non-MLB prospects |
| `player_surplus` | `fv_calc.py` | Surplus value for all MLB players |

| View | Description |
|---|---|
| `latest_ratings` | Most recent snapshot only — used by all web queries to avoid join multiplication |

## Key Conventions

- Each league's data lives in `data/<league>/league.db`. The web layer is read-only.
- `data/<league>/config/` contains JSON configuration and league-level aggregates.
- `data/<league>/history/` contains hand-written scouting summaries and FV tracking.
- `data/<league>/tmp/` contains intermediate scaffolds — script output that feeds report writing.
- `data/<league>/reports/` contains final published reports organized by game-year.
- `data/app_config.json` stores global config: `active_league` slug and `statsplus_cookie`.
- League context resolved via `scripts/league_context.py` (shared) and `web/web_league_context.py` (Flask request-scoped).
