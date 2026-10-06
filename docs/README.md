# Documentation Index & Registry

This file is the single entry point to the Stats++ documentation. It tells you
which document to read for a given system, and whether that document is current.

It also holds the **doc-status convention** and the **ownership map** that the
end-of-session documentation checklist and the staleness-check script both use.

**Folder layout:** living and guide docs (plus the logs and this index) sit at the
top level of `docs/`. Historical/archived docs live in `docs/archive/`. If a doc is
in `archive/`, it is frozen — do not update it; read it for history only.

---

## 1. Doc-Status Convention

Every substantive document in `docs/` carries a status header directly below its
title. The header has one standard form:

```
> **Status:** Living · **Owns:** evaluation pipeline (`src/statsplusplus/evaluation/`)
> **Writing standard:** ASD-STE100 · **Last verified against code:** Session 95
```

Fields:

- **Status** — one of `Living`, `Guide`, or `Historical` (defined below).
- **Owns** — the code area the document describes, with the primary path(s). Omit
  for `Historical` docs.
- **Writing standard** — `ASD-STE100` for new/rewritten living docs, else `prose`.
- **Last verified against code** — the session in which a human or agent last read
  the document against the code and confirmed it is accurate. This is NOT the last
  edit; it is the last *verification*. Bump it only after an actual check.

### Status values

| Status | Meaning | Maintenance rule |
|---|---|---|
| **Living** | Describes a system that changes. Must track the code. | Verify whenever the owned code area changes. Bump *Last verified*. |
| **Guide** | A repeatable process or methodology. Changes rarely. | Verify only when the methodology changes, not for routine code edits. |
| **Historical** | A frozen snapshot, design doc, or research trail. | Never update. Carries a deprecation banner pointing to the living doc. |

A `Historical` document uses a banner instead of the status line:

```
> **⚠ HISTORICAL — not maintained.** This document is a <design doc / research
> trail / point-in-time assessment> from Session N. It does not describe the
> current system. For the current state, see `docs/<living-doc>.md`.
```

---

## 2. Ownership Map (code area → living doc)

When a code area in the left column changes, verify the document in the right
column and bump its *Last verified* line. This is the authoritative map for the
`dev-agent.md` end-of-session checklist and `scripts/check_docs.py`.

| Code area | Owning living doc |
|---|---|
| `src/statsplusplus/evaluation/` (facet_runs, fv, composite, ceiling, player_value, surplus, woba, war) | `evaluation_system_overview.md` |
| `src/statsplusplus/evaluation/` empirical accuracy, $/WAR, surplus concepts | `valuation_model.md`, `evaluation_model_findings.md` |
| `src/statsplusplus/evaluation/{surplus,player_value,fv}.py` value-grade research | `value_grade_research.md` (`scripts/{analyze_grade_divergence,proto_value_grade}.py`) |
| `src/statsplusplus/data/calibrate.py`, `fv_calc.py`, `evaluation_engine.py` | `evaluation_system_overview.md`, `system_overview.md` |
| `src/statsplusplus/config/league_context.py`, `league_config.py`, multi-league resolution | `system_overview.md` (§ "Active league" design decision; `archive/multi_league_spec.md` is the original planning spec) |
| `src/statsplusplus/data/milb.py`, MiLB stat ingestion/integration | `evaluation_system_overview.md` §4.3 (`archive/milb_stat_integration_spec.md` is the original design spec) |
| `src/statsplusplus/client/`, `src/statsplusplus/data/refresh.py` | `client_reference.md`, `statsplus_api_analysis.md` |
| Depth chart (`web/team_queries.py` depth logic, `team.html`) | `archive/depth_chart_spec.md` (design spec) + `system_overview.md` |
| Any script, query function, route, or data-source interface | `tools_reference.md` |
| `.github/workflows/` (CI + release pipeline) | `testing_pipeline_design.md` |
| Scripts, routes, DB tables, data flow, UI layout, design decisions (index) | `system_overview.md` |
| Directory layout, file add/remove | `../STRUCTURE.md` |
| Data pull/storage conventions, refresh workflow | `../RULES.md` |

Guide docs own a *process*, not a code path. Verify them only when the process changes:

| Process | Owning guide |
|---|---|
| Farm system report methodology | `farm_analysis_guide.md` |
| MLB roster scaffold methodology | `roster_analysis_guide.md` |
| Trade analysis methodology | `trade_analysis_guide.md`, `trade_target_workflow.md` |
| Prospect query usage | `prospect_query_guide.md` |
| Org overview methodology | `org_overview_guide.md` |

---

## 3. Document Registry

### Living — must track the code (top level of `docs/`)

| Document | Owns | Last verified |
|---|---|---|
| `evaluation_system_overview.md` | Evaluation pipeline (the entry point) | Session 95 |
| `system_overview.md` | Architecture, data flow, DB, routes, design decisions | Session 94 |
| `valuation_model.md` | Surplus/valuation model (plain language) | Session 94 |
| `evaluation_model_findings.md` | Model accuracy, empirical WAR drivers (accuracy tables are a Session 79 baseline) | Session 95 |
| `value_grade_research.md` | Value-grade research findings + decisions | Session 95 |
| `client_reference.md` | StatsPlus API client and fields | Session 95 |
| `statsplus_api_analysis.md` | API wiki analysis, endpoint coverage | Session 95 |
| `tools_reference.md` | CLI tools, query functions, data sources | Session 95 |
| `testing_pipeline_design.md` | CI/release pipeline (Stage 1 shipped; 2–4 roadmap) — `.github/workflows/` | Session 95 |

### Guide — methodology, changes rarely (top level of `docs/`)

| Document | Process |
|---|---|
| `farm_analysis_guide.md` | Farm system evaluation and reporting |
| `roster_analysis_guide.md` | MLB roster scaffold generation |
| `trade_analysis_guide.md` | Trade analysis workflow |
| `trade_target_workflow.md` | Trade target search |
| `prospect_query_guide.md` | Prospect query usage |
| `org_overview_guide.md` | Organizational overview reporting |

### Historical — frozen, not maintained (moved to `docs/archive/`)

Archived docs are kept for history. They are NOT maintained and do not describe
the current system. Each carries a banner pointing at its living replacement.

| Document | What it is |
|---|---|
| `archive/evaluation_model.md` | Pre-run-space model reference (superseded Sessions 92-94) |
| `archive/evaluation_engine_assessment.md` | Session 48 engine assessment |
| `archive/unified_evaluation_design.md` | Session 78 design doc (stat_confidence blend shipped; FV section superseded) |
| `archive/unified_evaluation_implementation.md` | Session 78 implementation plan |
| `archive/fv_war_pipeline_diagnosis.md` | Session 94 FV reframe research trail |
| `archive/multi_league_spec.md` | Pre-build multi-league planning spec (feature now shipped) |
| `archive/depth_chart_spec.md` | Depth chart design spec (feature shipped and stable) |
| `archive/milb_stat_integration_spec.md` | MiLB stat integration design spec (shipped Session 74; composite blend superseded by run-space Session 92) |
| `archive/positional_context_findings.md` | Session 46-47 research findings |
| `archive/api_impact_analysis.md` | API integration planning |
| `archive/refactoring_plan.md` | Package refactor plan (done Session 77) |
| `archive/code_audit.md` | Session 76 code audit |
| `archive/code_cleanup.md` | Code cleanup tracker |
| `archive/assistant_gm_requirements.md` | Original requirements draft |
| `archive/expansion_roadmap.md` | Original strategic roadmap |

### Logs and registries (no status header, top level of `docs/`)

| Document | Role |
|---|---|
| `README.md` (this file) | Doc index, status convention, ownership map |
| `changelog.md` | Per-session completed work |
| `task_list.md` | Open backlog |

---

## 4. How To Keep This Current

1. When you change a code area, find its owning living doc in the ownership map
   (Section 2). Verify the doc against the new code. Fix it if it drifted. Bump its
   *Last verified* line in the header AND in the registry table (Section 3).
2. When you add a new document, give it a status header and add it to the registry.
3. When a document becomes obsolete, change its header to the `Historical` banner,
   point it at the replacement, `git mv` it into `docs/archive/`, and move its
   registry row to the Historical table.
4. Run `python3 scripts/check_docs.py` to find living docs whose owned code changed
   after the doc was last touched. The script reports candidates; a human decides.

The end-of-session documentation checklist in `.kiro/steering/dev-agent.md`
enforces steps 1-3. The staleness script supports step 4.
