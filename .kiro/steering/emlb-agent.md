# EMLB Agent Steering

This file contains stable rules and conventions that rarely change. It is not a living
document — update only when project fundamentals shift, not for incremental feature work.

For architecture, data flow, and script details → `docs/system_overview.md`
For open work items → `docs/task_list.md`
For completed work history → `docs/changelog.md`

---

## Session Startup

Read `docs/system_overview.md` in full before doing any work. It defines the data flow,
script ownership, DB schema, key design decisions, and standard workflows.

---

## Session Workflow

Every session that modifies code, schema, or project conventions must end with a
documentation pass. This keeps the project navigable across sessions.

### During the session

- When a design decision is made (e.g. "surplus belongs on contracts, not roster"), note
  it — it will go into the relevant doc at session end.
- When a new query function, route, or DB column is added, note it for system_overview.

### End-of-session documentation checklist

1. **`docs/task_list.md`** — add new backlog items discovered during the session.
   Remove items that are completed (they go to `docs/changelog.md`).

1b. **`docs/changelog.md`** — add completed items under the current session heading
   with a one-line description of what was done.

2. **`docs/system_overview.md`** — update if any of these changed:
   - New or removed scripts, routes, DB tables/columns
   - New query functions in `web/queries.py`
   - Changes to data flow (new writers, new readers)
   - Web UI layout changes (new tabs, panels, pages)
   - Key design decisions that affect multiple files

3. **`STRUCTURE.md`** — update if files/directories were added or removed.

4. **Guide docs** (`farm_analysis_guide.md`, `roster_analysis_guide.md`,
   `trade_analysis_guide.md`) — update only if the methodology or process changed,
   not for implementation details.

5. **`docs/tools_reference.md`** — update if any script, query function, or data source
   was added, removed, or had its interface changed.

6. **`RULES.md`** — update only if data pull/storage conventions changed.

### What does NOT need updating

- CSS-only changes, template formatting tweaks, sort order changes
- Bug fixes that don't change interfaces or conventions
- Intermediate work that gets revised before session end

---

## Data Rules

All data is fetched and written to `league.db` by `scripts/refresh.py` from the StatsPlus API.
No JSON data files are read by analysis scripts. MCP tools are for targeted interactive
queries only — not bulk data pulls.

### Refresh sequence (run when game date advances)

```bash
python3 scripts/refresh.py 2033              # all teams — auto-fetches date, updates state, runs fv_calc
```

Single command handles everything: fetches game date from API → updates `state.json` →
pulls all data → computes league averages → runs `fv_calc.py` (FV + surplus).

The `state` subcommand still exists for manual overrides but is not needed in normal use.

After refresh, validate row counts:
- `players` and `ratings`: ~14,000+ after refresh
- `contracts`: should cover all teams
- `batting_stats` / `pitching_stats`: should have current year rows

### IP storage convention

The API returns `ip` as a truncated integer. The `outs` field is precise. All IP values
in the DB are stored as true decimal innings (`outs / 3`), not baseball display format.
ERA is computed from outs (`er * 27 / outs`). Display formatting uses the `fmt_ip` Jinja
filter which converts back to baseball notation (e.g. 33.333 → "33.1").

---

## Farm Analysis Rules

- **Never read raw data files during farm analysis.** The scaffold script processes all
  raw data — the agent's input is `tmp/farm_scaffold_<date>.md` only.
- **Do not perform FV calculations manually.** `fv_calc.py` handles all bucketing,
  normalization, and FV math. `farm_analysis.py` reads its output.
- **Do not read `farm_analysis.py` or `fv_calc.py` source code** during an analysis run.
  They are black boxes — run them, read their output.
- If `scripts/farm_analysis.py` is not found, stop and report it.

---

## Pitcher WAR Methodology

Pitcher WAR is blended: `(war + ra9war) / 2` for all pitcher evaluations. This applies in:
- `fv_calc.py` — `_load_stat_history` aggregation
- `contract_value.py` — `estimate_peak_war` stat path

`ra9war` is stored in `pitching_stats` alongside `war`. If `ra9war` is NULL, fall back
to `war` alone.

---

## History Files

Scouting summaries and FV tracking live in `history/`, keyed by string player_id:
- `history/prospects.json` — prospect summaries + FV history snapshots
- `history/roster_notes.json` — MLB player summaries + Ovr tracking

Both scaffold scripts (`farm_analysis.py`, `roster_analysis.py`) read these files to
surface reuse flags and dev signals. After writing or updating summaries in a report,
update the corresponding history file.

---

## Auto-Write Permissions

The following writes do not require user confirmation:

- `reports/<year>/*.md` — final reports (farm, roster, org overview)
- `history/prospects.json` — scouting summaries and FV snapshots
- `history/roster_notes.json` — MLB player summaries
- `tmp/*.md` — intermediate scaffold files
- `config/state.json` — game date and year state
- `docs/task_list.md` — task status updates

## Report Output Behavior

After writing a report, do **not** print the full contents to the terminal. Output only:
the file path and a brief summary (prospect count, FV range, notable flags).

---

## Web UI Conventions

- All DB access goes through `web/queries.py` — no business logic in queries, no direct
  DB access in templates or routes.
- Templates use `base.html` layout shell. Dark theme, no CSS/JS frameworks.
- `sort.js` handles client-side table sorting with smart rank renumbering.
- Team pages are parameterized by `team_id` — any of the 34 MLB teams is viewable.
- `my_team_id` (from `config/state.json`) controls highlighting and default redirects.
- Column alignment: Name/Team left-aligned, numeric columns right-aligned, Pos/Role
  left-aligned via `data-sort-value`.
- Surplus values color-coded: green (positive), red (negative).
- IP displayed via `fmt_ip` Jinja filter (true decimal → baseball notation).

---

## Code Style

- Minimal code — no surplus abstractions, no speculative generalization.
- **Team/league agnostic** — new and refactored code must not hardcode team IDs, league
  size, year, or org-specific assumptions. Use `my_team_id` from `state.json`, pass
  team/league context as parameters, and keep constants configurable. Existing hardcoded
  values (e.g. `ANGELS_ORG_ID`, year 2033, 34-team league size) are tech debt being
  addressed incrementally — do not add new ones.
- Scripts are both CLI tools and importable libraries where noted (contract_value,
  prospect_value, trade_calculator).
- `constants.py` is the single source of truth for valuation tables (FV→WAR, OVR→WAR,
  aging curves, arb percentages, discount rates).
- `player_utils.py` holds shared evaluation logic (bucketing, FV calc, WAR projection,
  normalization, height formatting).
