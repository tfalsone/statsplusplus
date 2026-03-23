# Depth Chart Feature Spec

## Overview

A new "Depth Chart" tab on the team page showing a visual baseball diamond with 3-5 players listed at each position, including MLB starters, backups, and organizational prospects who project to contribute. Stat projections are selectable via dropdown. Pitchers displayed separately with their own stat selector.

The depth chart supports a 3-year window (current year through current+2) navigable via forward/back arrows. Future years account for contract expirations, aging, and prospect development — showing how the roster is expected to evolve.

---

## Design

### Layout

```
┌─────────────────────────────────────────────────────────────────────┐
│  ◀ 2033 ▶    [Stat selector: PT% | PA | WAR | OPS+]               │
│                                                                     │
│                         ┌─────────┐                                 │
│                         │   CF    │                                 │
│                         │ Allen   │                                 │
│                         │ Greer   │                                 │
│                         │ DeLuca  │                                 │
│                         └─────────┘                                 │
│                                                                     │
│          ┌─────────┐                  ┌─────────┐                   │
│          │   LF    │                  │   RF    │                   │
│          │ Rockwell│                  │ Kelenic │                   │
│          │ Wanza   │                  │ Cabarrus│                   │
│          └─────────┘                  └─────────┘                   │
│                                                                     │
│                         ┌─────────┐                                 │
│                         │   SS    │                                 │
│              ┌─────────┐│Kazansky │┌─────────┐                     │
│              │   3B    ││ French  ││   2B    │                     │
│              │ Shuey   │└─────────┘│ Ransaw  │                     │
│              │ O'Conner│           │ Gentry  │                     │
│              └─────────┘           │ Gelof   │                     │
│                                    └─────────┘                     │
│                         ┌─────────┐                                 │
│                         │   1B    │                                 │
│                         │Thornton │                                 │
│                         │ Thomas  │                                 │
│                         └─────────┘                                 │
│                                                                     │
│                         ┌─────────┐                                 │
│                         │    C    │                                 │
│                         │ Pethel  │                                 │
│                         │ Farmer  │                                 │
│                         └─────────┘                                 │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  DH                                                          │   │
│  │  Acuna Jr.  .808 OPS+                                        │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  SP  [Stat selector: PT% | IP | WAR | ERA | FIP]            │   │
│  │  1. Crochet     28.7 IP  1.4 WAR                            │   │
│  │  2. McClanahan  26.7 IP  0.7 WAR                            │   │
│  │  3. Briggs      30.3 IP  0.7 WAR                            │   │
│  │  4. Jimm        28.3 IP  0.3 WAR                            │   │
│  │  5. Rohnson     33.3 IP -0.0 WAR                            │   │
│  │  6. Starks (AAA)                                             │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  RP                                                          │   │
│  │  CL  Grimaldo   20.0 IP  0.1 WAR                            │   │
│  │  SU  Leclerc    15.3 IP -0.0 WAR                            │   │
│  │  MR  Rasmussen  10.3 IP -0.0 WAR                            │   │
│  │  ...                                                         │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### Diamond Rendering

CSS-positioned cards on a relative container. No SVG or canvas — pure HTML/CSS. The diamond shape is achieved by positioning cards at appropriate coordinates within a fixed-aspect-ratio container. A subtle diamond outline (4 lines connecting 1B-2B-SS-3B positions) drawn with CSS borders or a lightweight inline SVG background.

### Position Cards

Each card shows:
- Position label (C, 1B, 2B, 3B, SS, LF, CF, RF)
- 3-5 players ranked by projected playing time
- Player name (linked to `/player/<pid>`)
- Selected stat value
- Level badge for non-MLB players (e.g. `AAA`, `AA`)
- Starter (row 1) visually distinguished from backups (slightly dimmed)

### Stat Selectors

**Position players** (single selector for all positions + DH):
| Label | Column | Source | Format |
|---|---|---|---|
| PT% | Playing time share | Projected from Ovr/age/role | `XX%` |
| PA | Plate appearances | PT% × team total PA | `XXX` |
| WAR | Wins above replacement | Projected from Ovr/bucket/age | `X.X` |
| OPS+ | OPS relative to league | Projected from ratings | `XXX` |

**Pitchers** (separate selector):
| Label | Column | Source | Format |
|---|---|---|---|
| PT% | Playing time share | Projected from Ovr/role/stm | `XX%` |
| IP | Innings pitched | PT% × team total IP | `XXX.X` |
| WAR | Wins above replacement | Projected from Ovr/bucket/age | `X.X` |
| ERA | Earned run average | Projected from ratings | `X.XX` |
| FIP | Fielding independent pitching | Projected from ratings | `X.XX` |

Default selection: WAR for both.

### Year Navigation

```
◀  2033  ▶
```

Arrow buttons cycle through current year → current+1 → current+2 (2033 → 2034 → 2035). Left arrow disabled on year 1, right arrow disabled on year 3. Year label displayed prominently. Switching years swaps the entire depth chart — all position cards, pitcher lists, and stat values update.

All three years are computed server-side and rendered into the HTML. JS toggles visibility by year (same pattern as stat selectors — no AJAX).

---

## Multi-Year Projection Model

The 3-year window is the defining feature. Year 1 (current) is a standard depth chart. Years 2-3 project roster evolution.

### Roster Availability by Year

For each future year, determine which players are still under team control:

1. **Contracted players** — check `contracts` table. A player with `years=N` and `current_year=C` is under contract for `N - C` more years. If their contract expires before the projected year, they are **removed** from the depth chart (treated as departed FA).
2. **Team/player options** — `last_year_team_option` and `last_year_player_option` flags. For projections, assume team options are exercised for players with positive surplus, declined otherwise. Player options are assumed exercised (conservative — player keeps the guaranteed money).
3. **Estimated control players** (1-year contracts, pre-arb/arb) — use `_estimate_control` logic from `contract_value.py` to determine how many years of control remain. Apply the non-tender gate: if projected arb salary exceeds market value in a future year, the player is removed (non-tendered).
4. **Prospects** — always available (team controls them through their pre-arb + arb window). Their level and Ovr change with development projections.

### Aging and Development

For year offsets +1 and +2:

- **Age**: `current_age + offset`
- **Ovr (veterans, age ≥ peak)**: stays at current Ovr — aging is captured by `aging_mult` on WAR, not by changing Ovr
- **Ovr (pre-peak, Pot > Ovr)**: apply development ramp — `proj_ovr = ovr + (pot - ovr) × min(offset / years_to_peak, 1.0)` where `years_to_peak = peak_age - current_age`. Same formula as `contract_value.py`.
- **WAR**: recalculated from (possibly ramped) Ovr with `aging_mult(age + offset, bucket)`
- **OPS+ / ERA / FIP**: recalculated from projected ratings. For pre-peak players, interpolate offensive/pitching ratings toward potential at the same rate as Ovr.

### Prospect Promotion Logic

For future years, prospects move up the depth chart:

- **Year 1**: prospects shown at their current level with level discount on PT%
- **Year 2**: prospects who were at AAA in year 1 are treated as MLB-ready (no level discount). AA prospects move to AAA discount (0.5×).
- **Year 3**: one more level promotion. Former AA prospects are now MLB-ready.

This is a simple heuristic — advance one level per year for players at A or above. Players below A stay at 0.1× discount regardless.

### Replacement Players

When a player departs (contract expiration, non-tender), their slot opens up. The depth chart doesn't invent free agent signings — it shows what the org has internally. This naturally surfaces:
- Holes where the org has no replacement (position shows only 1-2 players, or only low-WAR options)
- Positions where a prospect is projected to step into a starting role
- The overall trajectory of the roster (improving farm pushing out aging vets, or a talent cliff when contracts expire)

---

## Projection Engine

The depth chart needs a projection engine that doesn't exist yet. This is the core new work.

### Player Pool

For each position, gather candidates from:
1. **MLB roster** — players on the 26-man roster (`level=1`) for this team
2. **Upper minors** — players at AAA/AA (`level` 2-3) in the org (`parent_team_id=tid`) with FV ≥ 40
3. **Top prospects** — any org prospect with FV ≥ 50 regardless of level

Position assignment uses:
- **MLB players (year 1)**: `fielding_stats` for the current year — a player appears at every position where they have ≥3 games. PT% split proportional to games at each position. Falls back to `players.pos` if no fielding data.
- **MLB players (years 2-3)**: positional ratings determine viability (same thresholds as bucketing: SS ≥ 50, CF ≥ 55, etc.). PT% split weighted toward highest-rated position.
- **Prospects**: `prospect_fv.bucket` mapped to specific diamond positions via ratings (COF → best of LF/RF by positional grade). Multi-position viability from ratings, same as MLB future years.
- Multi-position players appear at every viable position with PT% distributed across them.

For future years, the pool is filtered by roster availability (see Multi-Year Projection Model above). Departed FAs are removed; prospects are promoted per the level advancement heuristic.

### Playing Time Model

Playing time is the foundation — PA, IP, WAR, and rate stats all derive from it.

**Position player PT%:**
1. Each player has a total PT% budget (100% max = everyday player)
2. Multi-position players split their budget across positions proportional to fielding games (year 1) or positional ratings (years 2-3)
3. At each position, rank candidates by projected WAR
4. Starter gets base 85% of that position's PA allocation
5. Remaining 15% split among backups proportional to WAR
6. A player's contribution at a position = their positional share × their overall PT% budget
7. Non-MLB players get a level discount (see prospect promotion logic for future years):
   - Year 1: AAA = 0.5×, AA = 0.25×, lower = 0.1×
   - Year 2+: prospects advance one level per year, discounts shift accordingly

**Pitcher PT%:**
- SP: rank by projected WAR. Top 5 split ~90% of SP innings (each ~18%). 6th starter / swingman gets remainder.
- RP: rank by projected WAR. Closer gets ~70 IP, setup ~65 IP, middle relief ~55 IP, mop-up ~45 IP. Scale to team total RP innings.

**Team total PA/IP baselines:**
- Year 1: current-year team stats extrapolated to 162 games (floor denominator at 40 games to avoid early-season noise)
- Years 2-3: league average (~6,200 PA, ~1,450 IP) — no team-specific extrapolation for future seasons

### WAR Projection

Reuses existing infrastructure from `player_utils.py`:
- `peak_war_from_ovr(ovr, bucket)` — maps Ovr to WAR by bucket
- `aging_mult(age, bucket)` — age curve multiplier
- `stat_peak_war()` — 3-year weighted actual WAR (MLB players with 2+ seasons)
- Development ramp — Ovr→Pot interpolation for pre-peak players

For the depth chart:
- **MLB players with 2+ seasons (year 1 only)**: use `stat_peak_war`
- **All other cases**: use `peak_war_from_ovr` with aging curve and development ramp
- **Future years**: always use Ovr-based projection (stat_peak_war is current-year only — it becomes stale for +1/+2 projections where Ovr and age have shifted)
- Scale WAR by PT%: `projected_war = full_season_war × pt_pct`

### OPS+ Projection

Derive from Ovr using the existing Ovr→WAR curve, then convert WAR to OPS+ via a simplified relationship:
- League average OPS+ = 100 (by definition)
- Each 1.0 WAR above replacement ≈ +15 OPS+ above baseline (~80 for replacement level)
- Formula: `ops_plus = 80 + (projected_war / full_season_pa_share) × 15 × (600 / 600)`
- This is approximate but directionally correct and consistent with the WAR model

Alternative (more accurate): use the ratings directly:
- `cntct` → AVG component, `pow` → SLG component, `eye` → OBP component
- Map to OPS via regression on existing player data, then OPS+ = OPS / lg_OPS × 100
- This is better but requires calibrating a ratings→OPS model

**Decision: use ratings-based approach.** We already have league averages and the raw ratings. A simple model mapping (cntct, pow, eye, gap) → OPS is more accurate than WAR→OPS+ back-conversion and gives us a stat that's independent of the WAR projection.

### ERA / FIP Projection

Similar approach — derive from pitcher ratings:
- `stf` → K rate, `ctrl` (avg of ctrl_r, ctrl_l) → BB rate, `mov` → GB% / HR rate
- Map to ERA/FIP components using existing league averages as baseline
- FIP = `fip_const + (13×HR + 3×BB - 2×K) / IP` — project the components from ratings
- ERA ≈ FIP adjusted by mov (high mov → ERA < FIP due to BABIP/GB suppression)

---

## Data Flow

```
team_queries.py::get_depth_chart(team_id)
  ├── Query MLB roster + ratings + current stats + fielding
  ├── Query org prospects (AAA/AA with FV≥40, any level FV≥50)
  ├── Query contracts for roster availability
  ├── For each year in [current, current+1, current+2]:
  │     ├── Filter player pool by roster availability
  │     ├── Age players, apply development ramp to Ovr
  │     ├── Promote prospects one level per year offset
  │     ├── Assign positions
  │     ├── Project WAR for each player
  │     ├── Compute PT% allocation per position
  │     ├── Derive PA/IP from PT% × team totals
  │     ├── Project OPS+ from (projected) ratings (hitters)
  │     └── Project ERA/FIP from (projected) ratings (pitchers)
  └── Return dict keyed by year

app.py
  └── Pass depth_chart to template

team.html
  └── New "Depth Chart" tab with diamond layout + stat selectors + year nav
      └── JS toggles year visibility and stat column visibility
```

Output structure (one entry per year):
```python
{
  "years": [2033, 2034, 2035],
  "by_year": {
    2033: {
      "positions": {
        "C":  [{"pid": ..., "name": ..., "level": "MLB", "pt_pct": 85, "pa": 520, "war": 2.1, "ops_plus": 108}, ...],
        "1B": [...], "2B": [...], "3B": [...], "SS": [...],
        "LF": [...], "CF": [...], "RF": [...], "DH": [...]
      },
      "sp": [{"pid": ..., "name": ..., "level": "MLB", "pt_pct": 18, "ip": 180, "war": 3.5, "era": 3.20, "fip": 3.15}, ...],
      "rp": [{"pid": ..., "name": ..., "level": "MLB", "rp_role": "CL", "pt_pct": 8, "ip": 65, "war": 1.0, "era": 2.80, "fip": 2.95}, ...],
      "team_pa": 6200,
      "team_ip": 1450,
      "total_war": 38.5
    },
    2034: { ... },
    2035: { ... }
  }
}
```

---

## Implementation Tasks

### Task 1: Calibrate OPS+ and ERA/FIP models
One-time analysis to find regression coefficients.

- Pull all qualified MLB hitters (PA ≥ 200) with ratings and actual OPS+
- Regress OPS+ ~ cntct + pow + eye + gap + speed
- Pull all qualified MLB pitchers (IP ≥ 40) with ratings and actual ERA/FIP
- Regress ERA ~ stf + ctrl + mov (and FIP separately)
- Hardcode coefficients in `projections.py`
- Validate R² and spot-check known players

**LOE: Low-Medium.** Same approach as the BABIP regression.

### Task 2: Projection utilities (`scripts/projections.py`)
New module with pure projection functions. No DB access — takes player dicts as input.

- `project_war(ovr, pot, age, bucket, year_offset=0, stat_war=None)` — full-season WAR projection
  - year_offset=0: uses stat_war if available, else Ovr-based with dev ramp + aging
  - year_offset>0: always Ovr-based, applies dev ramp for pre-peak, aging for post-peak
- `project_ovr(ovr, pot, age, bucket, year_offset)` — projected Ovr for future years (dev ramp)
- `project_ops_plus(cntct, pow, eye, gap, speed)` — ratings → OPS+
- `project_era(stf, ctrl, mov)` — ratings → ERA
- `project_fip(stf, ctrl, mov)` — ratings → FIP
- `project_ratings(ratings_dict, year_offset, age, bucket)` — interpolate offensive/pitching ratings toward potential for pre-peak players. Returns adjusted ratings dict for use in OPS+/ERA/FIP projections.
- `allocate_playing_time(players_by_pos)` — PT% allocation algorithm

**LOE: Medium.** Core new logic. WAR projection reuses existing functions. Ratings interpolation is new but follows the same dev ramp pattern.

### Task 3: Roster availability (`scripts/projections.py` or `web/team_queries.py`)
Determine which players are available in each future year.

- Parse contracts: remaining years, option handling (exercise TO if surplus > 0, assume PO exercised)
- For 1-year contracts: use `_estimate_control` to determine pre-arb/arb control window
- Apply non-tender gate: if projected arb salary > market value in year N, player removed from year N+
- Return per-year player availability list

**LOE: Medium.** Reuses `_estimate_control` and non-tender logic from `contract_value.py`, but needs to be restructured for batch use across years.

### Task 4: Depth chart query (`web/team_queries.py::get_depth_chart`)
Assembles the data for one team across 3 years.

- Query MLB roster with ratings, current-year stats, fielding positions
- Query org prospects (FV ≥ 40 at AAA/AA, FV ≥ 50 anywhere)
- Query contracts for all org players
- For each year offset (0, 1, 2):
  - Filter pool by roster availability (Task 3)
  - Age players, project Ovr and ratings (Task 2)
  - Promote prospects per level heuristic
  - Assign positions, compute PT%, derive all stats
- Return structured dict keyed by year

**LOE: Medium-High.** The per-year loop with roster filtering and prospect promotion is the most complex assembly step.

### Task 5: Template and CSS (`web/templates/team.html`, `web/static/style.css`)
The visual layer.

- Add "Depth Chart" tab button
- Year navigator: `◀ 2033 ▶` with JS to toggle year containers
- Diamond container with CSS-positioned cards (one container per year, only active year visible)
- Position cards with player lists, level badges, starter/backup distinction
- Stat selector dropdowns (JS toggles stat columns within the active year)
- SP/RP sections below the diamond
- DH section between diamond and pitchers
- `total_war` summary line per year (shows overall roster WAR trajectory)

**LOE: Medium.** CSS positioning + two layers of JS toggling (year + stat).

### Task 6: Wire up route (`web/app.py`, `web/queries.py`)
- Add `get_depth_chart` to `queries.py` exports
- Call it in the team route, pass to template

**LOE: Low.**

---

## Execution Order

1. **Task 1** — calibrate regression models (coefficients needed by Task 2)
2. **Task 2** — projection utilities (testable standalone)
3. **Task 3** — roster availability (testable standalone)
4. **Task 4** — depth chart query (combines Tasks 2+3, testable from CLI)
5. **Task 6** — route wiring (trivial, alongside Task 4)
6. **Task 5** — template/CSS (last, once data shape is finalized)

Tasks 1-3 can be validated from the command line before touching the web layer.

---

## Open Questions

1. **DH assignment** — who goes in the DH slot? No "DH fielding stats" exist — DH is identified by inference:
   - Players with poor defensive ratings who are in the lineup for their bat (e.g. Acuna at DH full-time)
   - Teams with excess talent at a position may rotate players through DH
   → **Decision: DH candidates are identified by elimination.** After assigning all field positions, any MLB player with significant PA but minimal fielding games is a DH candidate. Additionally, if a player's best positional rating is below the viability threshold at every position (or they're clearly the worst defender among starters), they're a DH. Rank DH candidates by projected WAR. This is a heuristic — doesn't need to be perfect.

2. **Multi-position players** — a player like Gentry (2B/3B/SS) appears at multiple positions. Do we:
   - Show them at their primary position only?
   - Show them at all positions they've played?
   → **Decision: players appear at every position where they have a realistic claim to playing time.** The model works in two layers:

   **Year 1 (current season):** Use `fielding_stats` to determine positions. A player appears at a position if they have ≥3 games there this season. PT% at each position is proportional to their fielding games at that position relative to their total fielding games. Example: Gentry with 11G at 2B, 7G at 3B, 6G at SS → appears at all three, weighted ~46%/29%/25%.

   **Years 2-3 (future, no fielding data):** Use positional ratings to determine viability. A player appears at a position if their rating meets the bucketing viability threshold (SS ≥ 50, 2B ≥ 50, 3B ≥ 45, C ≥ 45, CF ≥ 55, LF/RF ≥ 45, 1B ≥ 45). PT% split proportional to positional rating among viable positions, weighted toward the primary (highest-rated) position.

   **Locked-in starters:** A player who plays 90%+ of their fielding games at one position (Allen at CF, Thornton at 1B) is effectively single-position — they'll appear at that position only with near-100% of their PT% there. The model handles this naturally without special-casing.

3. **Prospect position mapping** — `prospect_fv.bucket` uses broad categories (COF, not LF/RF). For the diamond we need specific positions.
   → **Decision: prospects use positional ratings for placement, same as MLB future-year logic.** A COF prospect appears at LF/RF/CF based on which ratings clear viability thresholds. An infield prospect viable at 2B/3B/SS appears at all three — they contribute as a utility player rotating through when starters rest, same as MLB versatility players. Multi-position prospects are not forced into a single slot.

4. **Season extrapolation early in the year** — at 26 games, extrapolating to 162 may be noisy.
   → **Decision: use max(games_played, 40) as denominator for extrapolation to avoid extreme early-season swings. Below 40 games, blend with league average baselines.**

5. **Future year team totals** — years 2-3 don't have actual team stats to extrapolate from.
   → **Decision: use league average baselines (~6,200 PA, ~1,450 IP) for all future years. Team-specific extrapolation only for year 1.**

6. **Option exercise assumptions** — team options and player options affect roster availability in future years.
   → **Decision: team options exercised if player's projected surplus > 0 at option year. Player options always assumed exercised (conservative — player keeps guaranteed money). Options shown with a marker on the depth chart card.**

7. **Departed player indicators** — when viewing year 2 or 3, it's useful to see who left.
   → **Decision: defer. Keep it simple for v1 — departed players just don't appear. Could add a "departed" ghost row later if useful.**
