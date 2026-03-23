# EMLB Project — Expansion Roadmap

**Created:** 2033-04-22 (game date) / 2026-03-17 (real date)
**Scope:** Strategic guidance for expanding the EMLB analytics project from a single-org tool to a league-wide assistant GM platform.

---

## Current State

The project is a single-org analytics system for the Anaheim Angels (org ID 44). It supports:

- MLB roster analysis (performance, ratings, contracts)
- Farm system prospect evaluation (FV rankings, scouting summaries)
- Organizational overview (pipeline depth, contract outlook, roster projection)
- Ad-hoc trade analysis (surplus value, contract valuation, prospect value)

Data lives in flat JSON files under `angels/` and `farm/`. Analysis is driven by a context-aware agent reading guide docs and running Python scripts. The methodology is documented in `docs/farm_analysis_guide.md` and `docs/ootp/` (see `aging_and_development.md`, `financial_model.md`, `ratings_and_attributes.md`).

---

## Goals (in priority order)

### 1. Assistant GM Mode (near-term)
Build structured, repeatable trade analysis tools for the Angels. Currently trade analysis is done ad-hoc in conversation — the math is reconstructed from scratch each session. The goal is a set of scripts and a methodology doc that make trade analysis as repeatable as farm analysis.

### 2. League-Wide Data Sync (medium-term)
Expand the data pipeline to cover all 102 league teams. This enables cross-team queries: trade target identification, surplus value comparisons, positional need/supply matching.

### 3. League-Wide Org Overviews (medium-term)
Generate structured org data (not necessarily full prose reports) for every team — FV distribution, contract commitments, positional needs. This is the input layer for league-wide trade analysis.

### 4. League-Wide Trade Analysis (long-term)
True assistant GM mode: given a need, query the league for matching supply, evaluate trade packages, and generate surplus-balanced proposals. Requires goals 1–3 to be complete.

### 5. Local UI (long-term)
A browser-based local interface for interacting with team and player data, reports, and analysis without requiring a terminal or agent session. The UI is a presentation layer over the SQLite database and generated reports — it does not replace the agent, it complements it.

---

## Key Challenges

### Data Volume
The current JSON architecture works for one org (~150 farm players, ~26 MLB players). At 102 teams that's 15,000+ farm players and 2,600+ MLB players. Problems that emerge at scale:
- Cross-team queries require reading and parsing dozens of files — no indexing, no joins
- Ratings files are already 400KB+ per org; league-wide is 40MB+ of JSON
- The agent context window cannot hold league-wide data — queries must be pre-computed

**Solution:** Migrate to SQLite. This is a prerequisite for goals 2–4, not a stretch goal.

### Ratings Rate Limit
The StatsPlus ratings endpoint enforces a ~4 minute rate limit between requests. A full league refresh (102 teams) takes significant wall-clock time. This makes on-demand league-wide ratings pulls impractical.

**Solution:** Schedule bulk refreshes overnight or between sessions. Cache ratings in the database with a `snapshot_date` field. Accept that league-wide ratings are not real-time — a weekly or bi-weekly refresh cadence is sufficient for strategic analysis.

### Prospect Valuation Methodology
Current prospect surplus value estimates are heuristic (FV tier → dollar bracket). This is defensible for directional analysis but not precise enough for rigorous trade balance calculations.

**Solution:** Build a bottoms-up model: development probability by FV tier × projected WAR curve × market $/WAR − expected salary over control period. Calibrate $/WAR from actual league contract and WAR data rather than estimating from payroll inference.

### League-Calibrated $/WAR
Currently estimated at $9–10M based on Angels payroll inference. This needs to be derived from actual league data to be reliable.

**Solution:** On each refresh, compute total MLB payroll / total MLB WAR across all teams. Store in `config/league_averages.json`. Use this figure in all surplus value calculations.

### Org Report Scale
Generating full prose farm reports for 102 teams is not practical or useful. Most teams only need structured data, not narrative.

**Solution:** Distinguish between structured org data (generated for all teams, stored in DB) and prose reports (generated on demand for specific trade partners or the Angels only). The agent writes prose; the scripts generate structured data.

---

## Recommended Build Sequence

### Phase 1 — Assistant GM Mode (Angels only, current JSON)
Build the trade analysis tooling against the existing architecture. Get the methodology right before scaling the infrastructure.

Deliverables:
- `docs/trade_analysis_guide.md` — methodology, WAR aging curves, development probability table by FV tier, surplus value formula
- `scripts/prospect_value.py` — surplus value by FV, age, level
- `scripts/contract_value.py` — projected WAR and surplus/deficit for MLB contracts
- `scripts/trade_calculator.py` — composes the above; takes two trade sides as input, outputs net surplus exchange per side

### Phase 2 — SQLite Migration (Angels only)
Migrate the Angels data to a SQLite database as a proof of concept. Same data, relational schema. Verify query patterns work before expanding to the full league.

Deliverables:
- `emlb.db` — SQLite database with schema covering teams, players, ratings, contracts, stats, prospect_fv, org_reports
- Updated `scripts/refresh.py` to write to DB in addition to (or instead of) JSON
- Updated analysis scripts to query DB

Schema (core tables):
```sql
teams        (team_id, name, level, parent_team_id, league)
players      (player_id, name, age, team_id, parent_team_id, level, pos, role)
ratings      (player_id, snapshot_date, ovr, pot, [all attribute fields])
contracts    (player_id, team_id, years, current_year, salary_0..14, ntc, options)
batting_stats(player_id, year, team_id, split_id, [stat fields])
pitching_stats(player_id, year, team_id, split_id, [stat fields])
prospect_fv  (player_id, eval_date, fv, level, bucket)
org_reports  (team_id, report_date, report_md)
```

### Phase 3 — League-Wide Data Sync
Expand the refresh pipeline to cover all 102 teams. Populate the full database.

Deliverables:
- `scripts/refresh.py` bulk mode: iterate all parent team IDs, pull rosters and ratings, write to DB
- Scheduled refresh cadence (overnight or between sessions) to work around the ratings rate limit
- `config/league_averages.json` updated to include league-calibrated $/WAR derived from actual contract + WAR data

### Phase 4 — League-Wide Trade Analysis
Build the assistant GM query layer on top of the complete dataset.

Deliverables:
- Trade target queries: "find all SP prospects FV 45+ on teams with rotation surplus"
- Positional need/supply matching: given Angels' needs, surface teams with matching supply
- Full trade package generator: input a need and a player to move, output surplus-balanced proposals

---

## Architecture Principles

- **Scripts are the computation layer; the agent is the interpretation layer.** Scripts handle data retrieval, normalization, and calculation. The agent reads script output and writes prose. Never replicate script logic in conversation.
- **Methodology lives in guide docs.** Every repeatable analysis process gets a guide doc. This makes the analysis consistent across sessions and auditable.
- **Structured data for all teams; prose for the Angels and on-demand trade partners.** Don't generate narrative reports for teams you don't manage — it's wasted compute and context.
- **Calibrate to the league, not the real world.** $/WAR, aging curves, and development probabilities should be derived from EMLB data where possible, not imported from real-world baseball research. The game engine may not match real-world distributions.
- **JSON for single-org interactive work; SQLite for anything cross-team.** The JSON architecture is not a mistake — it's appropriate for the current scope. Migrate when the queries demand it, not before.

---

### Phase 5 — Local UI
A browser-based local interface for browsing team and player data, reading reports, and running analysis without a terminal session. Built on top of the SQLite database populated in Phase 3.

Scope:
- **Roster views** — MLB and farm rosters per org, filterable by level, position, age, FV
- **Player cards** — ratings, contract, stats, prospect history, scouting summary in one view
- **Report browser** — read generated farm and org reports without opening markdown files
- **Trade calculator UI** — input two trade sides, see surplus balance computed in real time
- **Dashboard** — Angels-specific: payroll summary, top prospects, upcoming free agents, contract flags

Tech considerations:
- A lightweight Python web framework (Flask or FastAPI) serving the SQLite database is the simplest path — no separate frontend build step, runs entirely locally
- Reports stored as markdown in `org_reports` can be rendered with a markdown library
- The agent remains the authoring layer — the UI is read-only for reports, interactive only for the trade calculator
- SQLite is a hard prerequisite — the UI should not be built against JSON files

This is a Phase 4/5 deliverable. Do not build the UI before the database is populated with league-wide data — a UI over Angels-only data has limited value compared to a UI over all 102 teams.

---

## Open Questions

- **Development probability by FV tier:** What percentage of FV 45 prospects reach their ceiling in this league? This needs to be empirically derived from historical prospect data once enough evaluation cycles have accumulated in `prospect_history.json`.
- **Aging curves:** Do OOTP engine aging curves match real-world baseball? The engine has its own development and decline model — the trade analysis methodology should be calibrated to observed in-game aging, not MLB research.
- **Multi-team league structure:** The EMLB has 102 teams across multiple leagues. Trade rules, roster limits, and DFA mechanics may differ from real baseball. The trade analysis guide needs to account for any EMLB-specific transaction rules.
