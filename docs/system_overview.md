# EMLB Analytics Platform — System Overview

## Purpose

League-wide analytics platform for managing the Anaheim Angels (org ID 44) in the EMLB
StatsPlus simulation. Supports farm system evaluation, MLB roster analysis, trade
target identification, standings tracking, and free agent analysis across all 34 MLB teams.

---

## Data Flow

```
StatsPlus API
     │
     ▼
refresh.py ─────────────────────────────────────────────────────────────────────┐
  Writes: players, teams, ratings, contracts, batting_stats, pitching_stats,    │
          team_batting_stats, team_pitching_stats,                              │
          league_averages.json, state.json                                      │
     │                                                                          │
     ▼                                                                          │
fv_calc.py ─────────────────────────────────────────────────────────────────── │
  Reads:  players, ratings, batting_stats, pitching_stats, contracts            │
  Writes: prospect_fv, player_surplus                                           │
     │                                                                          │
     ├──► farm_analysis.py         (prospect_fv → tmp/farm_scaffold)            │
     ├──► roster_analysis.py       (ratings, stats, contracts → tmp/roster_scaffold)
     ├──► prospect_query.py        (prospect_fv, players, teams — read-only)    │
     ├──► contract_value.py        (players, ratings, contracts — read-only)    │
     ├──► prospect_value.py        (prospect_fv, players — read-only)           │
     ├──► trade_calculator.py      (contract_value + prospect_value)            │
     ├──► standings.py             (pitching_stats, team_*_stats — read-only)   │
     └──► free_agents.py           (contracts, player_surplus — read-only)      │

                    ┌──────────────────────────────────────────────────────────┐
                    │  web/app.py (Flask)                                      │
                    │  Reads: all DB tables via queries.py (read-only)         │
                    │  Routes: /, /team/<id>, /league, /player/<id>, /settings  │
                    └──────────────────────────────────────────────────────────┘
```

**Rule:** `fv_calc.py` is the sole writer of `prospect_fv` and `player_surplus`.
All other analysis scripts are read-only against the DB.

---

## Scripts

| Script | Lines | Purpose |
|---|---|---|
| `refresh.py` | 280 | Pulls data from StatsPlus API into DB (all teams). |
| `fv_calc.py` | 142 | Computes FV for all prospects + surplus for all MLB players. ~8s runtime. |
| `farm_analysis.py` | 691 | Angels farm scaffold — ranked prospects, grade tables, FV history, dev signals. |
| `roster_analysis.py` | 515 | Angels MLB roster scaffold — player cards, stat lines, contract info, surplus. |
| `prospect_query.py` | 220 | League-wide prospect rankings and farm system comparisons. |
| `contract_value.py` | 344 | MLB contract surplus/deficit with year-by-year projection. CLI + library. |
| `prospect_value.py` | 240 | Prospect trade surplus with option value model. CLI + library. |
| `trade_calculator.py` | 200 | Trade package evaluation — surplus balance with sensitivity ranges. |
| `standings.py` | 115 | League-wide standings — W/L, run differential, pythagorean expected record. |
| `free_agents.py` | 105 | Upcoming free agent class — expiring contracts with surplus data. |
| `player_utils.py` | 324 | Shared evaluation logic — bucketing, FV calc, WAR/aging curves, normalization. |
| `league_config.py` | 120 | Single abstraction for league-specific settings. Loads from `league_settings.json` + `state.json`. |
| `constants.py` | 82 | Valuation tables — FV→WAR, OVR→WAR, aging curves, arb %, discount rates. |
| `db.py` | 142 | DB connection, schema init, WAL mode, busy timeout. |
| `data.py` | 103 | Data access helpers (used by farm_analysis.py). |

---

## DB Tables

| Table | Owner | Description |
|---|---|---|
| `players` | `refresh.py` | All players across all orgs and levels |
| `teams` | `refresh.py` | Team ID → name mapping (34 MLB orgs) |
| `ratings` | `refresh.py` | Scouting ratings — my-team history preserved (`INSERT OR IGNORE`), others overwritten. Includes L/R splits, defensive tools (IFR/OFR/IFE/OFE/TDP), GB%, personality (Int/WrkEthic/Greed/Loy/Lead) |
| `contracts` | `refresh.py` | Active contracts league-wide |
| `batting_stats` | `refresh.py` | MLB batting stats by player/year/split (32 cols, 2020-2033) |
| `pitching_stats` | `refresh.py` | MLB pitching stats by player/year/split (52 cols, 2020-2033) |
| `team_batting_stats` | `refresh.py` | Team-level batting aggregates (34 teams × 3 splits) |
| `team_pitching_stats` | `refresh.py` | Team-level pitching aggregates (34 teams × 3 splits) |
| `games` | `refresh.py` | Game results (23K+ games, 2024-2033). runs0=away, runs1=home |
| `fielding_stats` | `refresh.py` | Player fielding stats by position (G, IP, TC, E, ZR, framing, arm) |
| `prospect_fv` | `fv_calc.py` | FV grades for all non-MLB prospects, keyed by player+eval_date |
| `player_surplus` | `fv_calc.py` | Surplus value for all MLB players, keyed by player+eval_date |

---

## Key Design Decisions

**Two-tier ratings storage** — my-team org ratings use `INSERT OR IGNORE` (history preserved
across snapshots). All other teams use `INSERT OR REPLACE` (current snapshot only). Demographics
(height/bats/throws) are backfilled on existing rows via UPDATE.

**FV calculation** — `calc_fv()` in `player_utils.py`. Inputs: Ovr, Pot, age vs. level norm,
bucket, work ethic, scouting accuracy. Key rules:
- RP FV hard cap at 50 (≤2.0 WAR/season ceiling)
- `Acc=L` applies -2 FV penalty + bust-only risk shift
- Critical tool penalties: Pot Control ≤35 or Pot Movement ≤35 (pitchers), Pot Contact ≤35 (hitters)
- Pitcher arsenal ceiling override: 3+ pitches Pot ≥80 → effective Pot ≥55
- Positional versatility bonus: +1/+2 FV for multi-position viability
- Unified defensive bonus: composite-driven base + weighted score modifier for all defensive positions (C/SS/CF/2B/3B/COF). Comp ≥ 70 + wt ≥ 65 → +3, comp ≥ 70 + wt 55-64 → +2, comp ≥ 70 + wt < 55 → +1, comp 60-69 + wt ≥ 65 → +2, comp 60-69 + wt 55-64 → +1. Position-weighted scores use position-specific tool importance.
- Platoon split penalty: -2/-3 FV for severe L/R splits (weak-side Contact < 30 for hitters, Stuff < 30 for pitchers)
- Knuckleball pitchers (`PotKnbl ≥ 45`) bucketed as SP regardless of supporting arsenal

**Contract surplus model** — `contract_value()` in `contract_value.py`:
- Pre-arb control estimation from service time (AB≥300/IP≥100 qualifying seasons)
- Arb salary projection: Ovr-based exponential model (MAE $0.53M/yr)
- RP arb salary discount (0.80x)
- Non-tender gate: control truncated when projected arb salary exceeds market value
- WAR floor at 0 (teams can release/DFA)
- Pre-arb age gate: age ≥28 on league minimum treated as 1yr FA deal

**Prospect surplus model** — `prospect_surplus_with_option()` in `prospect_value.py`:
- Probability-weighted surplus across base/mid/ceiling FV scenarios
- Age-adjusted development discount (bust probability only, not time value)
- Certainty multiplier from Ovr/Pot realization ratio
- Time-value discounting at 5%/yr
- Replacement WAR floor + zero surplus floor

**$/WAR** — $8.62M (2033). Calibrated from 70 multi-year MLB contracts (salary ≥$5M, years >1).
Stored in `config/league_averages.json`, recalculated each league refresh.

**IP storage** — the API returns `ip` as a truncated integer; `outs` is precise. All IP
values in the DB are stored as true decimal innings (`outs / 3`). ERA computed from outs
(`er * 27 / outs`). Display uses `fmt_ip` Jinja filter (33.333 → "33.1").

**SQLite WAL mode** — `db.py` enables WAL journal mode with 30s busy timeout. Allows
concurrent reads during writes so the web UI stays browsable during background refreshes.

**League configuration** — all league-specific settings (team IDs, divisions, mappings,
year, pyth exponent) live in `config/league_settings.json` and are accessed via
`league_config.config`. No hardcoded team IDs or league assumptions in scripts or web code.

**Summary reuse** — Both scaffold scripts support summary reuse from history files:
- `farm_analysis.py` reads `history/prospects.json` — dev signals (FV movement, stagnation, new season)
- `roster_analysis.py` reads `history/roster_notes.json` — Ovr movement ±5 and season-based refresh triggers

---

## Standard Workflows

### Full evaluation cycle (new game date)
```bash
python3 scripts/refresh.py 2033                  # all teams — auto-fetches date, updates state, runs fv_calc
python3 scripts/farm_analysis.py                 # farm scaffold
python3 scripts/roster_analysis.py               # roster scaffold
# Read scaffolds, write/update summaries, assemble reports
```

### Angels-only refresh (faster, active session)
```bash
python3 scripts/refresh.py 2033                  # Angels only — same auto-state + fv_calc
python3 scripts/farm_analysis.py
python3 scripts/roster_analysis.py
```

### Standings and free agents
```bash
python3 scripts/standings.py                     # from DB
python3 scripts/standings.py --refresh           # fresh from API
python3 scripts/free_agents.py --bucket SP       # upcoming FA starters
python3 scripts/free_agents.py --angels          # Angels expiring contracts
```

### Prospect queries
```bash
python3 scripts/prospect_query.py top --bucket SP --fv-min 50 --age-max 23
python3 scripts/prospect_query.py systems
python3 scripts/prospect_query.py team "Texas"
```

### Contract / trade evaluation
```bash
python3 scripts/contract_value.py "McClanahan"
python3 scripts/prospect_value.py --player 52392
python3 scripts/trade_calculator.py --trade '{"angels_send": [...], "angels_receive": [...]}'
```

---

## Web UI

Local Flask app at `web/`. Dark theme, monospace font, no CSS/JS frameworks.

### Routes

| Route | Template | Description |
|---|---|---|
| `/` | redirect | Redirects to `/team/<my_team_id>` |
| `/dashboard` | redirect | Redirects to `/team/<my_team_id>` |
| `/team/<id>` | `team.html` | Team page — division standings, team stats with league rankings, MLB roster, contracts with surplus, farm top 15, summary bar (payroll, surplus, FV 50+ count) |
| `/league` | `league.html` | League overview (vitals KPIs, 2×3 division standings grid with WC badges, scrollable power rankings with score heatmap, hero leader cards with MLB/AL/NL toggle), top 100 prospects with side panel |
| `/player/<id>` | `player.html` | Player detail — ratings, stats, percentiles, contract, surplus projection |
| `/settings` | `settings.html` | Team selector (`my_team_id` in `config/state.json`) |
| `/refresh` | JSON | POST — starts background refresh (`refresh.py`). Returns 409 if already running. |
| `/refresh/status` | JSON | GET — returns `{running, result, message}` for polling. |

### Team Page Features

Four-tab layout (Main / Roster / Contracts / Player Development) with client-side JS tab switching. Page title (`<h1>`) shows full team name. Summary bar persists across all tabs.

- **Summary bar** — game date, MLB surplus, farm surplus, FV 50+ count, payroll, roster composition (SP/RP/Pos counts)
- **Main tab** — division standings (pythagorean W/L, viewed team highlighted, team names linked) and team batting/pitching stats side-by-side with league rank out of 34 (top-5 bright green, bottom-5 red). Record breakdown panel (Overall/Home/Away/vs Division/1-Run/L10/Streak). Recent games panel (last 10 with linked opponents and pitchers with running records).
- **Roster tab** — position players and pitchers sorted by WAR (Pos/Role first column), surplus leaders (MLB + farm combined, top 15 by surplus)
- **Contracts tab** — MLB contracts only (`is_major=1`) sorted by salary with surplus/option flags, upcoming free agents (multi-year deals expiring within 2 years, or age 30+ on 1-year deals — excludes pre-arb/arb players with team control)
- **Finances tab** — committed payroll table with 6-year horizon. Per-player salary by year with TO/PO option markers and NTC badges. Arb/pre-arb projections shown in italics with `est` superscript. Pre-arb summary row for min-salary players with no projected future. Total committed row in footer.
- **Player Development tab** — farm top 15 (sorted by FV with surplus), farm depth (by position bucket and level, with total surplus, league average, and league rank), age distribution (MLB and farm FV 40+ with horizontal bars and league average markers)
- All queries parameterized by `team_id` — any team's page viewable via `/team/<id>`

### Player Page Features

MLB players use a three-tab layout (Overview / Stats / Contract). Prospects display all content on a single page without tabs.

- **Ratings panel** — overlaid current/potential grade bars (20-80 scale, color-coded by tier). Sections: Hitting tools → Running (Speed/Steal) → Positions → Defense. Defense ordered by position type (infielders: Range/Error/Arm/Turn DP; outfielders: Range/Error/Arm; catchers: Blocking/Framing/Arm). Pitchers show GB% as raw percentage.
- **L/R split toggles** — on Ratings, Percentile Rankings, and Overview stats snapshot. Split percentile expected values use split-specific ratings (e.g. `cntct_l` for vs-L).
- **Stats tab split selector** — 3-button selector (Overall / vs L / vs R) on batting and pitching stats tables. Each view shows full year-by-year history for that split (2020-2033).
- **Stats snapshot** — compact current-year stats on Overview tab between scouting report and percentiles. Pitchers show pitching stats, hitters show batting stats. L/R toggle for current year.
- **Percentile rankings** — Baseball Savant style with fill bars, dots, blue-to-red gradient. Performance tags for rating-to-stat divergence (Hot/Cold/Lucky/Unlucky). Scaled threshold (25 at midrange, 15 at extremes). Unqualified players shown in grey with "(small sample)" label. BABIP expected uses regression model (cntct + speed, R²=0.23) plus historical residual adjustment from 2+ prior qualifying seasons.
- **Fielding percentiles** — per-position FPCT/ZR (all), +Arm (OF), +Framing (C). ZR expected from rating composites (IF: IFR/IFE, OF: OFR, C: IFR/CArm/CBlk). Framing expected from CFrm/CBlk. Qualifier: 1.0 IP per team game.
- **Fielding stats** — Year/Pos/G/IP/TC/A/E/DP/FPCT/ZR/Arm table.
- **Contract panel** — year-by-year salary with NTC badge on header, TO/PO badges on final year row.
- **Surplus projection** — year-by-year breakdown (MLB: WAR/market/salary/surplus; prospects: control years/ETA/dev discount). Pessimistic/optimistic range.
- **Stats tables** — Batting: Year/G/PA → slash/ISO → BB%/SO%/BABIP → HR/RBI/SB-CS → OPS+/WAR. Pitching: Year/G/GS/IP → ERA/ERA+/FIP/SIERA → K%/BB%/K-BB%/GB%/BABIP → W/L/SV/HLD → WAR.
- **Header** — Ovr/Pot color-coded by tier. StatsPlus external link. Prospects show FV; MLB players omit redundant Ovr display.

### Key Files

| File | Purpose |
|---|---|
| `web/app.py` | Flask routes |
| `web/queries.py` | State helpers, league queries (prospects, leaders), re-exports from extracted modules (141 lines) |
| `web/team_queries.py` | Team-level queries — standings, roster, farm, contracts, surplus, age distribution, farm depth (494 lines) |
| `web/player_queries.py` | Player detail query — ratings, stats, splits, contract, surplus, personality, scouting summary (329 lines) |
| `web/percentiles.py` | Percentile rankings — hitter + pitcher, with expected range markers and performance tags (264 lines) |
| `web/templates/team.html` | Team page — standings, stats, roster, contracts, farm |
| `web/templates/player.html` | Player detail template with macros (`grade`, `pctile_grid`) and `toggleSplits()` JS |
| `web/templates/league.html` | League page — vitals KPIs, 2×3 standings grid, power rankings, hero leader cards, prospects tab |
| `web/static/style.css` | Dark theme, grade bar tiers, percentile styling, rank coloring, split toggle styles |
| `web/static/sort.js` | Client-side table sorting (numeric, string, positional spectrum) with smart rank renumbering |

---

## Reference Docs

| Doc | Purpose |
|---|---|
| `docs/farm_analysis_guide.md` | FV methodology, bucketing rules, report format, checklist |
| `docs/roster_analysis_guide.md` | Roster analysis process, player card format, checklist |
| `docs/trade_analysis_guide.md` | Trade evaluation process, surplus model, calibration log |
| `docs/trade_target_workflow.md` | Trade target search workflow (6-step process) |
| `docs/org_overview_guide.md` | Org overview report template |
| `docs/prospect_query_guide.md` | prospect_query.py usage and examples |
| `docs/client_reference.md` | StatsPlus API client reference |
| `docs/ootp/ratings_and_attributes.md` | OOTP ratings system reference |
| `docs/ootp/financial_model.md` | OOTP financial mechanics |
| `docs/ootp/aging_and_development.md` | Aging curves and development factors |
| `RULES.md` | Data pull/storage rules, refresh workflow |
| `STRUCTURE.md` | Directory layout and file conventions |
| `PURPOSE.md` | Goals and affiliates |
