# Stats++

An assistant GM dashboard for [OOTP Baseball](https://www.ootpdevelopments.com/) leagues managed through [StatsPlus](https://statsplus.net/). Pulls live league data from the StatsPlus API and presents it as an interactive local web dashboard with ratings, percentiles, prospect rankings, contract analysis, and more.

![Python](https://img.shields.io/badge/python-3.10+-blue) ![Flask](https://img.shields.io/badge/flask-web_ui-green) ![SQLite](https://img.shields.io/badge/sqlite-storage-orange)

## Features

- **League overview** — Standings, stat leaders, power rankings, league-wide averages
- **Team pages** — Roster, depth chart, farm system, contracts, payroll breakdown, upcoming free agents
- **Player pages** — Ratings with grade bars, batting/pitching splits, percentile rankings with expected-value tags (hot/cold/lucky/unlucky)
- **Prospect system** — Top 100, by-team and by-position views, FV grades, surplus values, scouting panel with tools and pitch repertoire
- **Multi-league support** — Manage multiple OOTP leagues from one install, switch between them in the nav
- **Extended ratings** — BABIP, HR Avoidance, PBABIP, Injury Proneness (when the league's OOTP version provides them)
- **One-click refresh** — Pull latest game data from StatsPlus without leaving the browser
- **CLI analysis tools** — Roster scaffolds, farm reports, prospect rankings, free agent analysis, trade calculator

## Prerequisites

- Python 3.10+
- Flask (`pip install flask`)
- A [StatsPlus](https://statsplus.net/) league with API access
- Your StatsPlus session cookie (grab from browser dev tools after logging in)

## Quick Start

### 1. Clone and set up

```bash
git clone <repo-url> statsplusplus
cd statsplusplus
pip install flask
```

### 2. Launch the web UI

```bash
cd web
python3 app.py
```

Open `http://localhost:5000`. You'll be redirected to the onboarding wizard.

### 3. Onboard a league

The wizard walks you through:

1. **Connect** — Paste your StatsPlus session cookie and league slug (e.g. `emlb`, `vmlb`)
2. **Configure** — Select your team, confirm league structure (divisions auto-detected)
3. **Refresh** — Pull all league data (rosters, stats, ratings, contracts). Takes 2-3 minutes.

Once complete, the dashboard is fully populated.

### 4. Add more leagues

Go to **Settings → Add League** and repeat the onboarding process. Switch between leagues via the dropdown in the nav bar.

## Project Structure

```
statsplusplus/
├── web/                    # Flask web application
│   ├── app.py                  # Routes, refresh endpoint, onboarding wizard
│   ├── queries.py              # League-wide queries (prospects, standings, leaders)
│   ├── team_queries.py         # Team-specific queries (roster, depth chart, contracts)
│   ├── player_queries.py       # Player page data (ratings, stats, splits)
│   ├── percentiles.py          # Percentile calculations with expected-value modeling
│   ├── web_league_context.py   # Per-request league context (DB connection, config)
│   ├── templates/              # Jinja2 templates
│   └── static/                 # CSS, JS, favicon assets
│
├── scripts/                # Core logic and CLI tools
│   ├── refresh.py              # API → DB pipeline (full league refresh)
│   ├── db.py                   # SQLite schema, migrations, connection management
│   ├── fv_calc.py              # Prospect FV grades and surplus value computation
│   ├── player_utils.py         # Shared evaluation (WAR curves, aging, bucketing)
│   ├── contract_value.py       # Contract surplus analysis
│   ├── projections.py          # Player projections for depth chart planning
│   ├── constants.py            # FV→WAR mappings, aging curves, financial constants
│   ├── league_config.py        # League settings abstraction
│   ├── league_context.py       # Active league resolver
│   ├── roster_analysis.py      # CLI: MLB roster scaffold generator
│   ├── farm_analysis.py        # CLI: Farm system report generator
│   ├── prospect_query.py       # CLI: League-wide prospect rankings
│   ├── free_agents.py          # CLI: Free agent class analysis
│   ├── trade_calculator.py     # CLI: Trade surplus balance calculator
│   └── standings.py            # CLI: Pythagorean standings
│
├── statsplus/              # StatsPlus API client
│   └── client.py               # HTTP client, CSV parsing, ratings format handling
│
├── data/                   # Runtime data (gitignored)
│   ├── app_config.json         # Active league, session cookie
│   └── <league>/               # Per-league: league.db, config/, history/, reports/
│
└── docs/                   # Design docs, analysis guides, changelog
```

## Data Flow

```
StatsPlus API → client.py → refresh.py → league.db (SQLite)
                                              ↓
                                     web/app.py (Flask)
                                              ↓
                                        Browser UI
```

`refresh.py` handles the full pipeline: fetches rosters, batting/pitching/fielding stats, ratings, contracts, and team stats for all teams in the league, then computes league averages and runs FV/surplus calculations. The web layer reads from SQLite only.

## CLI Tools

All scripts operate on the active league (set in `data/app_config.json` or via the web UI).

```bash
# Full league refresh
python3 scripts/refresh.py [year]

# Generate analysis scaffolds for your team
python3 scripts/roster_analysis.py
python3 scripts/farm_analysis.py

# League-wide queries
python3 scripts/prospect_query.py
python3 scripts/free_agents.py
python3 scripts/standings.py

# Trade evaluation
python3 scripts/trade_calculator.py --trade '<json>'
```

## Configuration

League data lives in `data/<league>/config/`:

- **`state.json`** — Current game date and year
- **`league_settings.json`** — Team names/abbreviations, role/position maps, division structure, minimum salary, DH rules
- **`league_averages.json`** — Computed batting/pitching averages and $/WAR

Global config in `data/app_config.json`:

- **`active_league`** — Which league slug is currently selected
- **`statsplus_cookie`** — Session cookie for API access

## Tech Stack

- **Backend**: Python, Flask, SQLite
- **Frontend**: Server-rendered Jinja2 templates, vanilla JS, CSS custom properties (dark theme)
- **Data source**: StatsPlus REST API (CSV exports for ratings)
- **No external JS frameworks** — lightweight, fast, works offline after refresh

## License

Private project. Not currently licensed for redistribution.
