# Spring Training Page — Opening Day Roster Builder

Status: Shipped (Session 108). This spec documents the design; the living
description of the built feature is `docs/system_overview.md` §Web UI (Offseason
page) + the query/engine docstrings.
Owner doc: `docs/system_overview.md` §Web UI
Scope: the final `spring` sub-phase panel of the offseason page.

---

## 1. Purpose & reasoning

Spring Training is the last gate before the games count. Every earlier offseason
phase is about *acquiring and shedding control* (arbitration, options, free
agency, Rule 5, trades). Spring is different — the roster is largely fixed, and
the GM is now **deploying** it. The decisions are allocation decisions, not
transactions:

1. **Who are my 26?** The 40-man is set; the Opening Day active roster is a
   subset. Only ~4-6 spots are genuinely contested (last bench bat, 5th starter,
   final 2-3 bullpen arms, a Rule 5 carry). The other ~20 are locks.
2. **How do the contested spots resolve?** Framed per-opening — "for THIS slot,
   who are the candidates and what separates them" — not a global leaderboard.
3. **How do I deploy them?** Lineup vs RHP and vs LHP, rotation order, bullpen
   roles, platoon pairings, DH, playing-time shares for role/utility players.
4. **Is this the best configuration?** Did a choice leave a position below
   replacement? Did I bury a better option? Is there a platoon hole vs lefties?

The page is a **comparison engine**: build an Opening Day 26-man, then stress-
test it — see projected team output respond live to every roster/deployment
change. The valuable loop is *see the contested decisions → make calls → watch
team output respond → adjust.*

This is deliberately NOT the 3-year depth chart (read-only, auto-optimized,
every-player). It is one-season, interactive, user-overridable, contested-spots-
first. It reuses the depth chart's projection *math* (position assignment,
playing-time allocation, per-player WAR) but not its framing.

---

## 2. The projection model (settled & data-grounded)

Validated in `data/vmlb/tmp/spring_projection_mockup.py` + `spring_projection_notes.md`.

### 2.1 The cascade

```
Projected record  (true-talent point estimate)   ← leads
    Run differential   (+N, with RS / RA)
        Hitting       +X runs above avg
        Baserunning   +X runs
        Fielding      +X runs
        Pitching      +X runs prevented
```

### 2.2 Anchoring — the honest identity (NO double-counting)

Record comes from the **WAR identity**, then run diff is **derived from the
record** (not summed independently), guaranteeing the two always agree and both
match league history:

```
team_wins = REPL_WINS + total_team_WAR
run_diff  = (team_wins − GAMES/2) × RUNS_PER_WIN
RS / RA   = LG_TEAM_RUNS ± run_diff, split by offense-vs-pitching WAR share
```

- `total_team_WAR` = playing-time-weighted sum of per-player current-age WAR
  (`player_evaluation.peak_war × aging_mult(age, bucket)`), over a fixed slot
  budget (starters ≈ 0.92 of a slot, bench ≈ 0.10; SP ≈ 0.90, RP ≈ 0.55 of
  their innings — tuned to the real allocator on build).
- Facet runs (hitting/baserunning/fielding) are scaled to sum to the offensive
  half of the derived diff, split by the run-space facet components per player
  (bat wRAA / UBR / ZR); pitching runs = the pitching half via the ERA/FIP→runs
  path (the run-space pitcher spine is deferred backlog — accepted).
- **Display wOBA (stat selector):** the pool surfaces the EXACT model projected
  wOBA, not an OPS+-derived estimate. The evaluation engine computes it from the
  calibrated tool→wOBA fit (`composite.project_woba_hitter`, the same value the
  run-space composite uses internally) and stores it in `ratings.proj_woba`;
  `_spring_pool` reads it via `latest_ratings`, falling back to the OPS+ × league-
  wOBA estimate for leagues not yet re-run on this model version.

### 2.3 Calibration constants — PER LEAGUE, from history

Computed from each league's own team RS/RA/record history (the way
`calibrate.py` derives its other constants), with sane defaults for thin-history
leagues. Measured on vMLB 2033-2034 (60 team-seasons):

| Constant | vMLB value | Meaning |
|---|---|---|
| `LG_TEAM_RUNS` | 770 | league-avg team RS == RA |
| `RUNS_PER_WIN` | 8.29 | regressed through origin (wins-above-.500 vs run diff) |
| `WIN_BAND_SD` | 9.5 | stdev of (actual − pythag-expected) wins |
| `REPL_WINPCT` | 0.294 | replacement-level win% (→ ~48 wins) |
| `pyth_exp` | 1.83 | existing league setting |

Validation: derived run diff lands inside the historical run-diff bands across
75-100 wins; 86-win projection → +39 diff, matching real 84-88 win teams
(+3/+78/−16/+79/+73/+30).

### 2.4 Uncertainty & display philosophy (the key UX decision)

Two different questions, answered differently:

- **"How many games will I win?"** → wide band (±`WIN_BAND_SD` ≈ ±9-10 wins).
  Season luck, not actionable. Shown as ONE quiet context line.
- **"Is roster A better than roster B?"** → the season-luck term **cancels**
  between two configs, so the win/run-diff **delta is PRECISE**. This is THE
  decision signal and is visually prominent.

Therefore: **point-estimate record leads**, the **delta vs the prior config**
is the loud signal (green strip), and the luck band is demoted to one muted
line — explicitly noting the band does NOT apply to the delta. Mirrors
`standings.py` (pythag expectation is THE number; luck is commentary). Sensitivity
is honest — a bench swap is correctly small (~+0.7 wins); real forks (5th
starter 1.8 vs 0.6 WAR, glove-vs-bat at a weak spot, platoon vs weak-side
exposure) are multi-win swings.

---

## 3. Page layout — sticky projection header + multi-view roster

**Decision (locked):** rather than one roster layout, the page offers a **view
switcher** over a shared roster state — all four views, **defaulting to Board**.
Confirmed against the mockups (`data/vmlb/tmp/spring_multiview.html`, and the
earlier `spring_page_mockup.html` / `spring_ui_*.html`).

### The projection header (always visible, the payoff) — persistent
A **sticky header** above the view switcher, identical across all views:
- Left: record big point estimate; run diff (+N, RS/RA, team WAR muted); one
  quiet ±WIN_BAND_SD variance line.
- Middle: four facet mini-stats (Hitting / Baserunning / Fielding / Pitching
  run contributions vs league avg).
- Right: a green **change-preview delta strip** (the loudest comparison
  element) — the last/pending edit's Δwins · Δrun-diff · Δfacet, with the "band
  does not apply to the delta" note. This is the decision signal.

### Architecture — one state, N renders (the reason multi-view is cheap)
The **config is the single source of truth** (`lineup`/`bench`/`rotation`/
`bullpen` + out-of-options). Each view is a pure RENDER of that config; every
edit in ANY view mutates the same config and calls the same `/api/spring-project`
→ re-projects → updates the shared header + delta. Adding a view is "another
render + a tab," not another feature. All the built backend (projection, delta,
contested detection, persistence) is shared unchanged.

### The four views (each a distinct JOB)
1. **Board** (default) — dense depth grid: Lineup (with vs-RHP / vs-LHP platoon
   toggle), Rotation, Bullpen columns + bench line. A contested slot is flagged
   and expands its candidate pool inline on click (reuses the contested-spot
   pools). The working view where slots get resolved. Click-to-swap, no drag
   library. WAR color-coded (green ≥2.5 / neutral ≥1.2 / dim).
2. **Decisions** — just the contested-spot cards (Layer-1 distillation): slot ·
   "N in the mix" · candidates with the **model pick** highlighted, evidence
   (WAR · FV/composite · age), level-push tag, **out-of-options** flag (user
   toggle). Locks hidden. The "here are my ~5 calls" shortlist.
3. **Field** — diamond diagram, positions laid out spatially so an empty
   position reads as a visible hole; staff listed below. **Read-mostly**
   (coverage glance) — editing concentrated in Board/Table to sidestep vanilla
   drag-drop cost while keeping the field's spatial value.
4. **Table** — the full candidate pool as a sortable table (WAR / FV / age /
   level / bucket), reusing `sort.js`. Comparison/ranking across the whole pool;
   row-click slots a player.

**Default landing = Board** (the home base where most time is spent). A "⚙
Recommend my 26" action resets to the auto allocation; "Save plan" persists.
Edits funnel through one config mutation so all views stay in sync — the one
discipline point to keep the views consistent.

---

## 4. Editable levers (v1)

Highest-value for THIS phase, per the scoping discussion:

1. **Roster inclusion** — who's on the 26 (toggle contested candidates in/out).
2. **Position / role assignment** — override a slot (CF→corner, SP→pen, name DH).
3. **Deployment** — platoon pairing (vs-L / vs-R), rotation order, bullpen roles.
4. **Playing time — PLATOON-ASSIGNMENT + START-SHARE model (locked, supersedes
   the earlier flat-tier idea).** Modeled the way OOTP actually works and
   grounded in historical data (vMLB 2033-34), NOT flat "tier → %" shares.

   **Per position, the user assigns deployment by handedness:**
   - A **vs-RHP player** and a **vs-LHP player** (usually the same everyday
     player; a platoon splits them — strong-side bat vs the hand he mashes,
     weak-side partner vs the other). Batting *order* is NOT modeled (hitting
     2nd vs 6th is ~0 WAR — out of scope for a projection tool).
   - Each position also has a **backup** with a realistic start-share.

   **PA is DERIVED, not asserted:**
   `PA(player) = team_PA_share × Σ over handedness of
       (lineup_presence vs that hand) × (that hand's PA frequency)`
   with the hand frequency from data: **71% vs RHP / 29% vs LHP**. A true
   everyday player (both lineups) gets ~full share; a strong-side platoon bat
   (vs-LHP only) gets ~29%; his weak-side partner ~71%.

   **Realistic start-shares (from historical GS data, vMLB 2034):**
   | Position | Primary starts |
   |---|---|
   | C | **67%** (teams carry **2.7 catchers**; a backup C is REQUIRED) |
   | 1B | 79% · RF 81% · LF/CF 76% · 2B/3B 73% · SS 71% |
   The starter never plays 100% — the remainder flows to the backup. These
   anchor the auto start-shares; the platoon assignment redistributes within a
   position.

   **Backup catcher is a hard requirement.** A C starts ~67% of games — you
   physically cannot cover 162 with one. The model warns/flags a config that
   carries only one catcher and routes the ~33% to a second C.

5. **Pitching roles (OOTP-style).** Rotation 1–5 order + bullpen Primary Role
   (Closer / Setup / Middle / Long / **Specialist vs-L**), IP share derived from
   the role. The vs-L specialist is the LOOGY nuance from the OOTP staff screen.

Every lever feeds the same projection engine; the delta strip reports the effect.

Deferred: full OOTP ordered 1-9 batting lineups (order ≈ 0 WAR); per-pitch usage
rules ("every Nth game" granularity — we use realistic start-shares instead);
FA/waiver/trade recommendations (future add-on).

### Historical grounding (vMLB 2033-34, measured)
- Primary start-share by position: C 67 · 1B 79 · RF 81 · LF 76 · CF 76 · 2B 73
  · 3B 73 · SS 71 (%). Catchers used per team: 2.7.
- Opponent-handedness PA split: **71% vs RHP, 29% vs LHP.**
- These are the model's default start-shares + platoon weights; recomputed per
  league in calibration where sample allows, else these defaults.

---

## 5. Candidate pool

- **Full 40-man** + **AA/AAA players who could realistically push** for a spot
  (`player_evaluation` rows at level 2/3 with a WAR projection).
- AA/AAA push candidates carry a not-yet-MLB-proven readiness discount
  (mockup: AAA ×0.80, AA ×0.65 — tune on build).
- Org membership via `ORG_ID_SQL` (NOT `contract_team_id`, which goes stale
  after trades — established convention).

---

## 6. Out-of-options — user toggle (API gap, confirmed)

Minor-league options remaining is **NOT available from the StatsPlus API**
(audited both `/players` 62-col and `/contract` 41-col live headers; the only
"option" fields are contract/vesting options, unrelated to the 3-option rule).
Options status is a hard Spring constraint (out-of-options → make the 26 or
clear waivers), so it is a **per-player user toggle** on contested-spot
candidates — consistent with other user-supplied offseason inputs (injuries,
untouchables, recent moves). When flagged, the recommend logic treats the player
as a must-decide. We do NOT fabricate an options-exhaustion estimate (no
unevidenced mechanisms).

Related roster-status we DO have and use: `is_on_secondary` (40-man),
`designated_for_assignment`, `is_on_waivers`, `injury_*`, `free_agent`.

---

## 7. "Recommend my 26" button

One click generates the model's optimal Opening Day 26 + deployment (best-WAR
roster subject to position needs, platoon value, and any out-of-options
constraints the user has flagged). It's the starting point the user then
overrides; the delta strip then reads against this auto baseline.

---

## 8. Persistence

Opening Day plans are **saved per team** (revisitable as camp progresses,
comparable to auto). A small per-league state artifact keyed by team (shape TBD
on build — likely `data/<league>/config/` or a plans JSON, following the
auto-write-permitted config pattern). Distinct from the FA-cart localStorage
pattern because a Spring plan is a deliberate saved artifact, not a scratch cart.

---

## 9. Implementation plan (high-value first)

1. **`get_spring_projection(team_id, config)`** — pure-ish query/eval function
   returning the full cascade for a given roster configuration. Reuses
   `projections.allocate_playing_time` / `allocate_pitcher_time` for PT, the
   run-space facet components for the breakdown, Pythagenpat + per-league
   calibration for the record/band. Prove against the auto config first.
2. **Per-league calibration** — derive `RUNS_PER_WIN`, `LG_TEAM_RUNS`,
   `WIN_BAND_SD`, `REPL_WINPCT` from team history in `calibrate.py` (or a spring-
   specific calibration step), with defaults for thin-history leagues.
3. **Auto config + "Recommend my 26"** — the optimal-26 allocator.
4. **Contested-spot detection** — surface slots with top-2 within ~1 WAR;
   candidate cards with evidence + pick + out-of-options toggle.
5. **Opening Day team view** — editable lineup (dual platoon) / rotation /
   bullpen / bench; wire edits → re-project → delta strip.
6. **Persistence** — save/load/compare plans per team.
7. **Wire into `offseason.html`** replacing the `spring` placeholder; gate via
   `panels_for_phase`.

Layer A (projection + cascade + delta) is the novel core and ships first; each
later layer feeds a trusted projection.

---

## 10. Honesty guardrails (carry into the UI)

- Record is a **true-talent expectation**, full-health full-season — no injury/
  availability/schedule modeling. The **delta** of an edit is the decision-grade
  signal; the absolute band is wide and quiet.
- Pitching runs come through the ERA/FIP→runs path (same caveats as our pitcher
  WAR); hitting/fielding/baserunning from the native run-space facets.
- Calibration is per-league from that league's history; converges as history
  accumulates (document the degrade-gracefully behavior for new leagues).

---

## 11. Known rough edges in the mockups (NOT blockers)

- The mockup allocator is a crude greedy-by-bucket placeholder (thin bullpen
  WARs, a catcher carrying too much). Real version uses the proper allocator.
- RS/RA ran slightly high vs the record's Pythagenpat before the derive-from-
  record fix; the real engine solves them jointly (done in §2.2).
- Facet split currently a proportional prior; real engine pulls true per-player
  run-space facet components.

---

## 12. Reference artifacts

Design-phase mockups and calibration-notes scaffolds (`data/vmlb/tmp/spring_*`,
`shot_*.png`) were removed at ship (Session 108); the logic they prototyped now
lives in `team_projection.py`, `offseason_queries.py`, `calibrate.py`, and
`offseason.html`. Reused production machinery:

- `web/team_queries.py get_depth_chart`,
  `scripts/projections.py` (allocate_playing_time / allocate_pitcher_time /
  assign_diamond_positions), `scripts/standings.py` (Pythagenpat),
  `src/statsplusplus/evaluation/facet_runs.py`, `.../war.py aging_mult`.


---

## 13. Lineup & roster construction — first principles (Session 108)

Added after a "step back" discussion. Two DISTINCT optimization problems that
were being conflated; the tool treats them differently:

**(A) Roster construction** — which 26, who plays each position, how to platoon.
This moves WAR MEANINGFULLY and is the projection's real job (the auto-platoon,
Phase 4 of `_spring_auto_config`, lives here). Runs actually live here.

**(B) Batting order** — the 1–9 sequence of a GIVEN nine. Worth only ~5–15
runs/season (~0.5–1.5 wins) at the extreme, ~0 if the order is already sane. So
order is a PRESENTATION / VALIDATION lens, NOT a WAR lever — the projection is
order-independent. But it's the thing the user LOOKS AT to sanity-check the
roster, so it should read like a lineup a smart manager would actually write.

### Batting-order research (The Book: Playing the Percentages; FanGraphs/Sky
Kalkman "Optimizing Your Lineup"; BP). Established, stable findings:

- **Top-of-order gets the most PA** (~18 more PA/slot going up) → put your best
  ON-BASE guys early; don't waste PA on outs.
- **Slot value ordering of the top: #1 ≈ #2 ≈ #4 > #3 > #5.** #2 is one of the
  three MOST valuable spots (high PA + often men on) — the modern "best hitter
  bats 2nd" (Trout). #3 is OVERRATED by tradition (comes up with 2 outs / bases
  empty most) — slightly de-prioritized. #4 = best power (most men on base).
- **OBP weighted slightly more at #1/#2; SLG slightly more at #4/#5.**
- **Speed/steals at leadoff is OVERRATED** — real but small, must NOT override
  OBP. A high-OBP slow runner > a low-OBP burner at leadoff. Speed is a
  TIEBREAKER among similar-OBP bats, not a driver.
- **Caveat:** optimal vs worst *realistic* order ≈ 1 win; any sane ordering
  captures nearly all of it. Don't over-engineer; don't claim WAR from order.

### Implementation (`_spring_lineup_cards`, component-aware, per hand)

Per-hitter, per-hand component scores derived from STORED model data (no web /
no new pull): on-base proxy from `eye`+`cntct` (walks + contact reach base) and
`proj_woba`; power proxy from `pow`+`gap`; run score from `baserunning_value`
(`stats.bsr`) + `speed`/`steal`; overall = the vs-hand bat wRAA
(`facets.bat_R/bat_L`). Slot assignment (research "modern" default):

    1 (leadoff) = best ON-BASE  (run score breaks near-ties)
    2           = best OVERALL remaining
    4           = best POWER remaining
    3           = best OVERALL remaining
    5           = best POWER remaining
    6-9         = remaining by OVERALL, descending

### User preferences (`config.lineup_prefs`, optional)

A small lever so the generated order can match a GM's philosophy without
re-plumbing: `{"style": "modern"|"traditional", "leadoff": "obp"|"speed"}`.
`traditional` puts the best overall hitter at #3 (not #2); `leadoff:"speed"`
weights the run score more heavily at #1 (the user's stated preference) vs the
research-default `obp` (on-base dominant, speed as tiebreaker). Defaults to
`modern` + `obp`. Batting order remains projection-neutral regardless.
