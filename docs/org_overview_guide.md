# Organizational Overview Guide

## Purpose

The org overview report synthesizes the MLB roster and farm system into a single
picture of the Anaheim Angels organization. It answers questions the farm report
and MLB analysis cannot answer in isolation:

- Where is the roster strong vs. thin by position, accounting for both current
  production and pipeline depth?
- Which roster spots have contract clarity vs. upcoming holes?
- Which farm prospects have a clear path to the roster vs. a blocked path?
- What does the roster look like in 1–3 years given current contracts and
  prospect timelines?

This report is **not** generated on a fixed cadence. Run it when there is enough
new information from both the MLB analysis and the most recent farm report to
make it meaningful — typically after a full MLB roster analysis has been completed.

---

## Inputs Required

Both of the following must be current before running this report:

1. **Farm report** — `reports/<year>/farm_report_<game_date>.md` for the current game date
2. **MLB roster analysis** — completed analysis of the current 25-man roster,
   including performance, roles, contract status, and positional depth

Do not run this report using a stale farm report or without a completed MLB
roster analysis. The action items will be wrong.

---

## Report Structure

### Section 1 — Roster Positional Map

For each position bucket (C, SS, 2B, CF, COF, 3B, 1B, SP, RP):

- **MLB incumbent:** Who currently holds the spot, their role, contract status,
  and whether they are performing to expectation
- **Near-term pipeline (0–2 years):** Farm prospects at FV 45+ who could
  realistically contribute at this position within 2 seasons
- **Long-term pipeline (3+ years):** FV 40+ prospects with a realistic path
  to this position on a longer timeline
- **Gap flag:** If there is no MLB incumbent with contract security AND no
  near-term pipeline option, flag the position as a gap

Keep each position to 2-3 sentences. This is a map, not a deep dive.

### Section 2 — Contract Outlook

Summarize the org's contract situation over the next 3 seasons:

- Players under contract through the current season only (expiring)
- Players with multi-year deals providing roster stability
- Positions where expiring contracts create roster holes with no internal solution
- Any notable options (team or player) that affect planning

### Section 3 — Prospect Path Analysis

For each top-15 farm prospect, one sentence on their path to the MLB roster:

- **Clear path:** Position is a need, prospect is on track, timeline aligns
- **Blocked path:** Position is covered by a long-term contract or established
  incumbent — prospect may need to be traded or moved to a new position
- **Uncertain:** Timeline or role is unclear pending MLB roster decisions

### Section 4 — Organizational Assessment

3-4 paragraphs synthesizing the full picture:

- Overall system health (strong, average, thin) and why
- The 1-year outlook: what the roster looks like next season
- The 3-year outlook: where the org is headed if current prospects develop
- The single biggest organizational risk (one position, one contract, one gap)

### Section 5 — Action Items

3-5 specific, prioritized actions with timelines. Each action must be grounded
in both the MLB roster state and the farm system state — not just one or the other.

Format:
```
[Priority]. [Action] (Timeline: X months)
Rationale: [One sentence connecting MLB need + farm gap/asset]
```

---

## Output

Write the completed report to `reports/<year>/org_overview_<game_date>.md`.

No scaffold script is required — this report is written directly from the
farm report and MLB analysis already on disk.

---

## Notes

- Do not run this report without a completed MLB roster analysis. The positional
  map and action items require MLB context that the farm report alone cannot provide.
- The farm report's System Snapshot (Section 3) is the primary farm input for
  this report — use it as the starting point for pipeline depth by position.
- Contract data is in the `contracts` table in `league.db`. Decode `salary_0`–`salary_14` as
  years 0–14 from the contract start; `years` is total contract length;
  `current_year` is the year index the player is currently in.
