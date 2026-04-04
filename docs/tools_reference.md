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

### `ratings`

Rating normalization — the foundation for all tool grade display and model inputs.

```python
from ratings import norm, norm_floor, get_ratings_scale, init_ratings_scale
norm(75)              # → 65 (1-100 scale) or 75 (20-80 scale)
norm_floor(0)         # → 20 (floor for numeric comparisons)
get_ratings_scale()   # → '1-100' or '20-80'
```

### `fv_model`

Prospect FV grade calculation. Pure functions — no DB access.

```python
from fv_model import calc_fv, dev_weight, defensive_score
fv_base, fv_plus = calc_fv(player_dict)   # player_dict needs Ovr, Pot, Age, _bucket, _norm_age
```

### `war_model`

WAR projection and stat history loading.

```python
from war_model import peak_war_from_ovr, aging_mult, load_stat_history, stat_peak_war
peak_war_from_ovr(60, 'SP')          # → float
aging_mult(33, 'SP')                 # → float (multiplier on peak WAR)
bat_hist, pit_hist, two_way = load_stat_history(conn, game_date)
war = stat_peak_war(pid, 'SP', bat_hist, pit_hist)
```

### `arb_model`

Arb salary estimation and service time calculation.

```python
from arb_model import arb_salary, estimate_service_time, estimate_control
arb_salary(60, 'SS', arb_year=1, prior_salary=825000, min_sal=825000)  # → int
svc = estimate_service_time(conn, player_id)                            # → float (years)
ctrl, sals, pre_arb = estimate_control(conn, player_id, age, salary)   # → (int, list, int) or (None,None,None)
```

### `contract_value`

MLB contract surplus/deficit breakdown.

```python
from contract_value import contract_value
result = contract_value(player_id)
# Returns dict: player_id, name, bucket, age, ovr, years_left, flags,
#               breakdown (list of year dicts), total_surplus {pessimistic, base, optimistic}
```

### `prospect_value`

Prospect trade surplus calculator.

```python
from prospect_value import prospect_surplus, prospect_surplus_with_option
result = prospect_surplus(fv=55, age=21, level='AA', bucket='SP', ovr=50, pot=70)
# Returns dict: total_surplus, dev_discount, certainty_mult, scarcity_mult, breakdown
opt = prospect_surplus_with_option(fv=55, age=21, level='AA', bucket='SP', ovr=50, pot=70)
# Returns int: surplus including option value from upside scenarios
```

### `player_utils`

Shared utilities — bucketing, display helpers, league settings, PAP.
Also re-exports `norm`, `norm_floor`, `calc_fv`, `peak_war_from_ovr`, `aging_mult`,
`load_stat_history`, `stat_peak_war` for backward compatibility.

```python
from player_utils import (
    assign_bucket,    # Determine positional bucket from ratings dict
    display_pos,      # Convert bucket to display string (COF → OF)
    height_str,       # cm → feet/inches string
    fmt_table,        # Format markdown table row
    calc_pap,         # PAP score from WAR, salary, team games, $/WAR
    dollars_per_war,  # Current $/WAR from league_averages.json
    league_minimum,   # League minimum salary from league_settings.json
)
```

### `league_config`

Single source of truth for league settings.

```python
from league_config import config
config.my_team_id        # int
config.year              # int
config.team_abbr(44)     # str e.g. "ANA"
config.team_name(44)     # str e.g. "Anaheim Angels"
config.team_abbr_map     # {int: str}
config.level_map         # {"1": "MLB", "2": "AAA", ...}
config.minimum_salary    # int
config.ratings_scale     # "1-100" or "20-80"
config.settings          # full league_settings.json dict
```

### `constants`

Named constants for all model levers. Sections:
- **Shared identifiers**: `PITCH_FIELDS`, `ROLE_MAP`, `DEFAULT_DOLLARS_PER_WAR`, `DEFAULT_MINIMUM_SALARY`, `PEAK_AGE_PITCHER/HITTER`, `SERVICE_GAMES_*`
- **Prospect model**: `ARB_PCT`, `FV_TO_PEAK_WAR*`, `DEVELOPMENT_DISCOUNT`, `YEARS_TO_MLB`, `PROSPECT_DISCOUNT_RATE`, `LEVEL_AGE_DISCOUNT_RATE`, `PROSPECT_WAR_RAMP`, `NO_TRACK_RECORD_DISCOUNT`, `RP_POT_DISCOUNT`, `SCARCITY_MULT`, `MIN_REGRESSION_N`, `CALIBRATION_YEARS`
- **MLB contract model**: `MLB_SCARCITY`, `ARB_HITTER_BASE/EXP`, `ARB_RP_BASE/EXP`, `ARB_RAISE_*`, `ARB_DEEP_SALARY_THRESHOLD`
- **WAR tables**: `OVR_TO_WAR`, `OVR_TO_WAR_CALIBRATED`
- **Aging curves**: `AGING_HITTER`, `AGING_PITCHER`

---

## Web Query Functions

These are in `web/queries.py`, `web/team_queries.py`, `web/player_queries.py`, and `web/trade_queries.py`.
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
| `search_players(query)` | Up to 15 matching players (MLB + prospects) across all orgs |
| `get_prospect_comps(pid)` | 3-tier MLB comps for a prospect (Upside/Likely/Floor) |
| `get_player_card(pid)` | Side-panel-style data for any player (tools, pitches, defense, stats) |
| `get_draft_pool()` | Draft board: state detection, surplus-ranked pool (via `prospect_surplus_with_option`), outcome probabilities, `$Val` per player |

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
| `get_draft_org_depth(team_id)` | Per-position positive surplus totals (MLB + farm split) for draft needs panel. Returns `{pos: {mlb, farm, total}}` in $M. |
| `get_org_overview(team_id)` | Cross-level org summary: position depth, surplus leaders, retention priorities, payroll shape |
| `get_farm_depth(team_id)` | Farm system depth by positional bucket |

### Player-Level (`player_queries.py`)

| Function | Returns |
|---|---|
| `get_player(pid)` | Full player detail — bio, ratings (current/potential), stat history, contract, surplus, splits, percentiles |
| `get_player_popup(pid)` | Lightweight popup data — bio, key ratings, current stats, surplus |

### Trade-Level (`trade_queries.py`)

| Function | Returns |
|---|---|
| `get_org_players(team_id)` | Full org roster (MLB + farm) with Ovr/Pot/FV/surplus/WAR for trade tab |
| `get_trade_value(player_id, retention_pct)` | Single-player valuation — contract breakdown or prospect surplus + career outcomes |

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
