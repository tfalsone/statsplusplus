# Stats++ Development Agent

Stable rules and conventions for developing the Stats++ application.
Update only when project fundamentals shift, not for incremental feature work.

---

## Context Loading

### Tier 1 — Always loaded (read on every session start)

- `PURPOSE.md` — project goals and design principles
- `STRUCTURE.md` — directory layout, DB tables, key conventions
- `RULES.md` — data pull/storage rules, refresh workflow
- `docs/task_list.md` — open work items, bugs, backlog

These give you the project shape and current work state. Do not skip them.

### Tier 2 — Load on first code touch

Read these when you're about to modify or analyze code, not for planning/discussion:

- `docs/README.md` — doc index, status convention, and the code→doc ownership map (consult this to find which doc a change affects)
- `docs/system_overview.md` — architecture, data flow, DB schema, design decisions, workflows
- `docs/tools_reference.md` — CLI tools, query functions, data sources
- `docs/evaluation_system_overview.md` — the evaluation pipeline entry point (read before any model work)

### Tier 3 — Load on demand

Only load when the task directly involves that area. Use the gate table below.

| Task type | Load these |
|---|---|
| Web UI (routes, templates, queries) | `docs/system_overview.md` §Web UI, `.kiro/specs/ui_spec.md` |
| Valuation models (FV, surplus, WAR) | `docs/evaluation_system_overview.md`, `docs/valuation_model.md`, `src/statsplusplus/evaluation/constants.py`, `src/statsplusplus/data/calibrate.py` |
| FV grade calculation | `docs/evaluation_system_overview.md` §5, `src/statsplusplus/evaluation/fv.py` |
| WAR projection / stat history | `src/statsplusplus/evaluation/{war,player_value}.py` |
| Arb salary / service time | `src/statsplusplus/evaluation/arb.py` |
| Rating normalization | `src/statsplusplus/config/ratings.py` |
| Trade/prospect features | `docs/trade_analysis_guide.md`, `docs/trade_target_workflow.md`, `.kiro/specs/phase4-trade-analysis.md`, `.kiro/specs/trade-review-tab.md` |
| Farm system / prospect analysis | `docs/farm_analysis_guide.md`, `docs/prospect_query_guide.md` |
| Roster analysis | `docs/roster_analysis_guide.md`, `docs/org_overview_guide.md` |
| Depth chart | `docs/archive/depth_chart_spec.md` (design spec), `web/team_queries.py` |
| StatsPlus API / client changes | `docs/client_reference.md` |
| DB schema / migrations | `docs/system_overview.md` §DB Tables, `scripts/db.py` |
| Multi-league support | `docs/system_overview.md` (§ "Active league" design decision), `src/statsplusplus/config/league_context.py`; `docs/archive/multi_league_spec.md` (original planning spec) |
| OOTP domain knowledge | `docs/ootp/ratings_and_attributes.md`, `docs/ootp/financial_model.md`, `docs/ootp/aging_and_development.md` |
| Code architecture / refactoring | `.kiro/steering/dev-agent.md` (Code Style), `../STRUCTURE.md`; `docs/archive/{code_cleanup,refactoring_plan,code_audit}.md` (historical) |
| Strategic planning | `docs/task_list.md`; `docs/archive/expansion_roadmap.md` (historical) |
| SQLite migration | `.kiro/specs/sqlite-migration.md` |
| League sync | `.kiro/specs/phase3-league-sync.md` |
| Game history | `.kiro/specs/game_history_spec.md` |
| End-of-session docs | `docs/changelog.md`, `docs/task_list.md` |
| Historical context ("when/why did X change?") | `docs/changelog.md` |
| Beat reporter agent | `.kiro/steering/beat-reporter.md` |
| User-facing setup / troubleshooting | `README.md` |

---

## Session Workflow

Every session that modifies code, schema, or project conventions must end with a
documentation pass.

### During the session

- When a design decision is made, note it — it goes into the relevant doc at session end.
- When a new query function, route, or DB column is added, note it for system_overview.

### End-of-session documentation checklist

Documentation is organized by the doc-status convention in `docs/README.md`
(the doc index, status convention, and ownership map). Three status classes:
**Living** (tracks code), **Guide** (methodology, changes rarely), **Historical**
(frozen, banner only). Follow these steps:

1. **Consult the ownership map** (`docs/README.md` §2). For each code area you
   changed, find its owning **Living** doc, verify the doc against the new code,
   fix any drift, and bump its `Last verified against code:` header line AND its
   row in the registry (`docs/README.md` §3). This replaces the old fixed doc
   list — the map is now the source of truth for which doc a change affects.
2. **`docs/task_list.md`** — add new backlog items. Remove completed items (they go to changelog).
3. **`docs/changelog.md`** — add completed items under the current session heading.
4. **`docs/system_overview.md`** — update if scripts, routes, DB tables, query functions, data flow, UI layout, or design decisions changed. (Living doc — bump its verified line.)
5. **`docs/tools_reference.md`** — update if any script, query function, or data source interface changed. (Living doc — bump its verified line.)
6. **`STRUCTURE.md`** — update if files/directories were added or removed.
7. **`RULES.md`** — update only if data pull/storage conventions changed.
8. **Guide docs** (`farm_analysis_guide.md`, `roster_analysis_guide.md`, `trade_analysis_guide.md`, etc.) — update only if the methodology changed, not for routine code edits.
9. **New or obsolete docs** — a new doc gets a status header and a registry row
   (`docs/README.md` §3). A doc that becomes obsolete gets the `Historical` banner
   (pointing at its replacement) and moves to the Historical registry table.
10. **Run `python3 scripts/check_docs.py`** — it flags Living docs whose owned
    code changed after the doc was last touched, and docs marked `NOT YET VERIFIED`.
    It is a report, not a gate: verify each flagged doc and bump its verified line,
    or confirm it did not drift. Keep the script's `DOC_OWNERSHIP` map in sync with
    `docs/README.md` §2 when either changes.
11. **Discord patch notes** — post a summary of the session's changes to Discord. Skip if `data/discord_config.json` doesn't exist (webhook not configured on this environment).

   **Format requirements:**
   - **Title**: concise and descriptive of what changed — e.g. "WAR Projection Overhaul & Standings Tools", "Pitcher Evaluation Fixes", "Draft Board UX Improvements". NOT "Session X" or "Stats++ Update".
   - **Content**: write fresh bullet points for this post. Do NOT repeat items already posted in a prior Discord message. Each bullet should be complete (no truncation/ellipsis).
   - **Tracking**: check `data/discord_posts.json` for `last_posted_commit`. Only include changes from commits AFTER that hash. After posting, update the file with the new commit hash, date, and title.
   - **Sections**: group into Bug Fixes / Improvements / other categories as appropriate. Omit empty sections.
   - **Tone**: concise but informative. One sentence per bullet explaining what changed and why it matters.
   - Post using `discord_post.py message` with a custom formatted embed (not `latest` which parses changelog with truncation). See prior session examples for the Python webhook pattern.

12. **Version release** — whenever a Discord post goes out, cut a release so launcher-install users (who update via the release zip, not `git`) get the same changes. Steps: bump `version` in `pyproject.toml`, commit, push `main`, then create and push an annotated tag (`git tag -a vX.Y.Z -m "..."; git push origin vX.Y.Z`) — the tag triggers the `release.yml` workflow that builds the zip. Version choice: **patch** (`Z`) for bug-fix-only batches, **minor** (`Y`) for new features or behavior/model changes, **major** (`X`) for breaking changes. The annotated-tag message should summarize the release (mirrors the Discord post). Note any migration caveat (e.g. per-league calibrated data updates only on the user's next calibrate/refresh — code must degrade gracefully until then). `gh` is not installed locally, so verifying the CI build succeeded and the zip contains `MANIFEST.txt` is a user action.

### What does NOT need updating

- CSS-only changes, template formatting tweaks, sort order changes
- Bug fixes that don't change interfaces or conventions
- Intermediate work that gets revised before session end

---

## Code Style & Principles

- Minimal code — no surplus abstractions, no speculative generalization.
- **Team/league agnostic** — no hardcoded team IDs, league size, year, or org-specific
  assumptions. Use `my_team_id` from `state.json`, pass team/league context as parameters.
- **All logic in the package** (`src/statsplusplus/`). `scripts/` contains only CLI tools
  that import from the package. No utility modules, no shared libraries in `scripts/`.
- **No singletons or global state.** Every function receives what it needs as parameters.
  Entry points (CLI `main()`, web `before_request`) resolve context and pass it through.
- **Typed interfaces** — cross-module interfaces use dataclasses from `statsplusplus.models`.
  Pure computation goes in `statsplusplus.evaluation` (no I/O, no DB, no global state).
- `statsplusplus.evaluation.constants` — single source of truth for all model constants.
- `statsplusplus.config.ratings` — pure normalization functions taking explicit `scale` parameter.
- `statsplusplus.config.league_config` — `LeagueConfig` class, `dollars_per_war(league_dir)`, `league_minimum(league_dir)`.
- `statsplusplus.data.db` — connection management (request-scoped in web, explicit `league_dir` in CLI).
- SQLite WAL mode for concurrent reads during writes.
- Web layer is read-only against the DB. All writes go through `data/` pipelines.
- **Do not run tests** unless the user explicitly asks to run them.
- **Do not push to git** without explicit user permission. Prepare commits but wait for approval before pushing.

---

## Data Rules

All data fetched and written to `league.db` by the refresh pipeline
(`python3 -m statsplusplus.data.refresh`) from the StatsPlus API.
No JSON data files read by analysis scripts (config files in `data/<league>/config/` are
the exception). MCP tools are for targeted interactive queries only.

### Refresh: `python3 -m statsplusplus.data.refresh [year]`

Fetches game date → updates state → pulls all data → computes league averages → runs
fv_calc (FV + surplus). Idempotent on same game date.

### IP storage

API returns `ip` as truncated integer; `outs` is precise. DB stores true decimal innings
(`outs / 3`). ERA from outs (`er * 27 / outs`). Display via `fmt_ip` Jinja filter.

### Pitcher WAR

Blended: `(war + ra9war) / 2`. Fall back to `war` alone if `ra9war` is NULL.

---

## Web UI Conventions

- All DB access through query modules (`queries.py`, `team_queries.py`, `player_queries.py`,
  `percentiles.py`) — no business logic in queries, no direct DB in templates/routes.
- Templates use `base.html` layout shell. Dark theme, no CSS/JS frameworks.
- `sort.js` handles client-side table sorting with smart rank renumbering.
- Team pages parameterized by `team_id`. `my_team_id` controls highlighting/defaults.
- Column alignment: Name/Team left, numeric right, Pos/Role left via `data-sort-value`.
- Surplus color-coded: green (positive), red (negative).

---

## Auto-Write Permissions

These writes do not require user confirmation:

- `data/<league>/reports/<year>/*.md` — final reports
- `data/<league>/history/prospects.json` — scouting summaries and FV snapshots
- `data/<league>/history/roster_notes.json` — MLB player summaries
- `data/<league>/tmp/*.md` — intermediate scaffold files
- `data/<league>/config/state.json` — game date and year state
- `docs/task_list.md` — task status updates

After writing a report, do not print full contents to terminal. Output only the file
path and a brief summary.
