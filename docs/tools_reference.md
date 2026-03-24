# Tools Reference

Quick-reference catalog of all CLI tools, importable libraries, and data sources available
in the EMLB analytics platform. Intended for agent context — keeps tool discovery out of
the conversation window.

**Maintenance rule:** Update this file whenever a script, query function, or data source
is added, removed, or has its interface changed. Add this to the end-of-session
documentation checklist in `.kiro/steering/emlb-agent.md`.

---

## CLI Tools

All scripts run from the project root: `cd ~/statsplusplus`

### `scripts/standings.py`

League-wide standings with pythagorean expected records.

```bash
python3 scripts/standings.py [--year 2033]
```

Output: Ranked table of all 34 MLB teams — W, L, Pct, GB, RS, RA, Diff. User's team
marked with `◄`. Uses pythagorean expectation (exponent from league settings).

### `scripts/prospect_query.py`

League-wide prospect rankings and farm system comparisons.

```bash
# Top prospects league-wide (filterable)
python3 scripts/prospect_query.py top [--n 20] [--bucket SP] [--age-max 22] [--fv-min 50] [--level AA] [--sort {fv,surplus}]

# Farm system rankings (total surplus, FV tier counts)
python3 scripts/prospect_query.py systems [--n 10]

# Single team's prospect list
python3 scripts/prospect_query.py team ANA [--n 15] [--fv-min 40] [--sort {fv,surplus}]
```

Output: Ranked prospect tables with FV, surplus, level, position, age. Systems view
shows aggregate farm value with tier breakdowns.

### `scripts/contract_value.py`

Contract surplus/deficit breakdown for any MLB player.

```bash
python3 scripts/contract_value.py <player_id or "player name">
```

Output: Year-by-year projection — salary, projected WAR, dollar value, surplus/deficit.
Shows contract flags (NTC, options), total surplus, peak WAR estimate.

### `scripts/prospect_value.py`

Prospect trade surplus calculator.

```bash
# By player ID (looks up FV/level from DB)
python3 scripts/prospect_value.py --player <id>

# Manual parameters
python3 scripts/prospect_value.py --fv 50 --age 21 --level AA --bucket SP
```

Output: Surplus value in dollars with option value model breakdown.

### `scripts/trade_calculator.py`

Trade package surplus balance evaluator.

```bash
python3 scripts/trade_calculator.py --trade '{"side_a": [{"type":"mlb","id":232}], "side_b": [{"type":"prospect","id":12345}]}'
```

Output: Surplus balance between two trade packages with sensitivity ranges.

### `scripts/free_agents.py`

Upcoming free agent class analysis.

```bash
# My team's expiring contracts
python3 scripts/free_agents.py --my-team

# League-wide by position
python3 scripts/free_agents.py [--bucket SP] [--min-war 2.0] [--years 1]
```

Output: Players approaching free agency with age, position, salary, surplus, option flags.

### `scripts/farm_analysis.py`

Generates the Angels farm system scaffold for report writing.

```bash
python3 scripts/farm_analysis.py
```

Output: Writes `tmp/farm_scaffold_<date>.md` — ranked prospect cards with grade tables,
FV history, development signals, and rewrite flags. **Read the scaffold, don't read the
script source.**

### `scripts/roster_analysis.py`

Generates the Angels MLB roster scaffold for report writing.

```bash
python3 scripts/roster_analysis.py
```

Output: Writes `tmp/roster_scaffold_<date>.md` — player cards with stat lines, ratings,
contract info, surplus, and summary rewrite flags.

### `scripts/refresh.py`

Data pipeline — pulls all data from StatsPlus API into the DB. Runs calibration
and FV/surplus computation automatically after data pull.

```bash
python3 scripts/refresh.py [year]    # Full refresh, all teams
python3 scripts/refresh.py state <game_date> [year]  # Manual state override
```

**Do not run during article writing.** Only run when the game date has advanced.

### `scripts/calibrate.py`

Derives league-specific valuation tables from actual data. Produces
`config/model_weights.json` with position-specific OVR→WAR, FV→WAR, arb
percentages, and scarcity curve. Runs automatically during refresh.

```bash
python3 scripts/calibrate.py           # Write model_weights.json
python3 scripts/calibrate.py --dry-run # Show results without writing
```

---

## Importable Libraries

These scripts double as importable modules. Use from Python when you need structured
data rather than CLI text output.

### `contract_value`

```python
from contract_value import get_contract_summary
summary = get_contract_summary(player_id)
# Returns dict: name, age, pos, ovr, pot, salary, years_remaining, total_surplus,
#               year_by_year (list of dicts), contract_flags
```

### `prospect_value`

```python
from prospect_value import calc_prospect_surplus
surplus = calc_prospect_surplus(fv=50, age=21, level="AA", bucket="SP")
# Returns float: surplus in dollars
```

### `player_utils`

Shared evaluation utilities — bucketing, FV calculation, WAR projection, normalization.

```python
from player_utils import (
    bucket_position,      # Determine positional bucket from ratings
    normalize_grade,      # Raw 1-100 → 20-80 scale
    display_pos,          # Numeric pos → display string
    fmt_height,           # cm → feet/inches string
)
```

### `league_config`

Single source of truth for league settings.

```python
from league_config import config
config.my_team_id        # 44
config.year              # 2033
config.team_abbr(44)     # "ANA"
config.team_name(44)     # "Anaheim Angels"
config.team_abbr_map     # {44: "ANA", 48: "NYY", ...}
config.level_map         # {"1": "MLB", "2": "AAA", ...}
config.settings          # Full league_settings.json dict
```

### `constants`

Valuation tables and curves.

```python
from constants import FV_TO_WAR, OVR_TO_WAR, AGING_CURVES, ARB_PCT, DISCOUNT_RATE
```

---

## Web Query Functions

These are in `web/queries.py`, `web/team_queries.py`, and `web/player_queries.py`.
Import with `sys.path.insert(0, 'web')`. All are read-only against the DB.

### League-Level (`queries.py`)

| Function | Returns |
|---|---|
| `get_state()` | `{game_date, year, my_team_id}` |
| `get_my_team_id()` | int |
| `get_my_team_abbr()` | str (e.g. "ANA") |
| `get_top_prospects(n)` | List of top N prospects league-wide |
| `get_all_prospects()` | All FV≥40 prospects with ratings |
| `get_prospect_summary(pid)` | Full prospect detail for side panel |
| `get_batting_leaders(year, min_pa)` | Top 5 per stat, MLB/AL/NL |
| `get_pitching_leaders(year, min_ip)` | Top 5 per stat, MLB/AL/NL |

### Team-Level (`team_queries.py`)

| Function | Returns |
|---|---|
| `get_summary(team_id)` | KPI summary — game date, surplus, FV50 count |
| `get_standings()` | All 34 teams — W/L, pct, RS/RA, pythagorean, division |
| `get_division_standings(team_id)` | Division-only standings for a team |
| `get_power_rankings()` | Composite rankings — pyth, L10, RD/G, surplus |
| `get_roster(team_id)` | Full MLB roster with ratings, contract, surplus |
| `get_roster_hitters(team_id)` | Hitters with full stat lines and ratings |
| `get_roster_pitchers(team_id)` | Pitchers with full stat lines and ratings |
| `get_farm(team_id)` | Minor league prospects with FV, level, surplus |
| `get_team_stats(team_id)` | Team batting/pitching aggregates with league ranks |
| `get_contracts(team_id)` | All contracts with year-by-year salaries |
| `get_payroll_summary(team_id)` | Payroll breakdown by category |
| `get_upcoming_fa(team_id)` | Players approaching free agency |
| `get_surplus_leaders(team_id)` | Top surplus contributors (MLB + farm) |
| `get_age_distribution(team_id)` | Roster age breakdown |
| `get_record_breakdown(team_id)` | W/L by month, home/away, vs division, etc. |
| `get_recent_games(team_id, n)` | Last N games with scores, pitchers, opponents |
| `get_stat_leaders(team_id)` | Team-internal stat leaders by category |
| `get_depth_chart(team_id)` | Positional depth with WAR projections |
| `get_org_overview(team_id)` | Cross-level org summary: position depth, surplus leaders, retention priorities, payroll shape |
| `get_farm_depth(team_id)` | Farm system depth by positional bucket |

### Player-Level (`player_queries.py`)

| Function | Returns |
|---|---|
| `get_player(pid)` | Full player detail — bio, ratings (current/potential), stat history, contract, surplus, splits, percentiles |
| `get_player_popup(pid)` | Lightweight popup data — bio, key ratings, current stats, surplus |

---

## Data Files (Read-Only Context)

| File | Contents |
|---|---|
| `config/state.json` | Current game date, year, my_team_id |
| `config/league_settings.json` | Division structure, team maps, rating thresholds |
| `config/league_averages.json` | League-wide batting/pitching averages, $/WAR |
| `history/prospects.json` | Scouting summaries + FV history by player_id |
| `history/roster_notes.json` | MLB player summaries by player_id |
| `reports/<year>/*.md` | Published farm reports, roster analyses, org overviews |

---

## DB Tables (league.db)

All accessed via the query functions above. Direct SQL is rarely needed.

| Table | Key Contents |
|---|---|
| `players` | All players — name, age, team, level, position, role |
| `teams` | Team ID → name mapping |
| `ratings` | Scouting ratings — all attributes, L/R splits, defensive tools |
| `contracts` | Active contracts — salary schedule, options, NTC |
| `batting_stats` | MLB batting by player/year/split |
| `pitching_stats` | MLB pitching by player/year/split |
| `team_batting_stats` | Team-level batting aggregates |
| `team_pitching_stats` | Team-level pitching aggregates |
| `fielding_stats` | Fielding by player/position |
| `games` | Game results — scores, WP/LP/SV, dates |
| `prospect_fv` | FV grades for all non-MLB prospects |
| `player_surplus` | Surplus value for all MLB players |

---

## Known Data Limitations

- **No minor league stats** — the StatsPlus API returns empty for minor league player IDs.
  Farm analysis relies on ratings + age-vs-level context only.
- **No play-by-play or box scores** — game results include final score and pitchers only.
- **No injury data** — StatsPlus doesn't expose DL/IL status.
- **No transaction log** — trades, callups, DFA are not tracked historically.
- **Ratings are scouted** — accuracy varies by scout quality. `Acc` field indicates
  reliability (VH/H/A/L). Only mention low accuracy when `Acc = L`.
