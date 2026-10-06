# Player Evaluation System — High-Level Overview

> **Status:** Living · **Owns:** evaluation pipeline (`src/statsplusplus/evaluation/`, `src/statsplusplus/data/{evaluation_engine,fv_calc,calibrate}.py`)
> **Writing standard:** ASD-STE100 · **Last verified against code:** Session 95

This document explains how the evaluation system works today. It is the single
entry point for the evaluation pipeline. It replaces the out-of-date
`archive/evaluation_model.md` and `archive/evaluation_engine_assessment.md`. See the
"Document Status" section at the end for which older documents are still accurate
and which are historical. The doc index and ownership map are in `docs/README.md`.

This document uses ASD-STE100 Simplified Technical English: short sentences, active
voice, present tense, and one idea per sentence. Each term has one meaning.

---

## 1. What The System Does

The system gives each player a value. It does not use the game's OVR and POT
ratings as the final answer. Instead it computes its own scores from the
individual tool ratings.

The system produces four numbers for every player:

| Output | Meaning | Scale |
|---|---|---|
| Composite | The player's current ability. | 20-80 |
| Ceiling | The player's peak ability if the tools develop. | 20-80 |
| FV (Future Value) | The expected peak outcome as a scouting grade. | 20-80, steps of 5 |
| Surplus | The dollar value above the player's salary cost. | US dollars |

The FV grade also carries a risk label: Low, Medium, High, or Extreme.

---

## 2. The Core Idea: Value In Runs, Not Grades

The most important design change is how the system combines tools.

The old model combined tools in **grade space**. It took a weighted average of
20-80 grades. This method had a flaw. A "70" in one tool was treated as equal in
value to a "70" in a different tool. This is not true. A 70 power tool and a 70
fielding tool do not add the same number of wins.

The current model combines tools in **run space**. It converts each group of
tools into runs. Runs are the common unit of baseball value. The system adds the
runs together, then converts the total to wins (WAR), and then to a 20-80
composite.

This change is the foundation of the hitter model. It makes a weak bat show its
true cost. A glove-first player with a very poor bat now scores low, because a
bad bat produces negative runs that good defense cannot cover.

**Note on scope:** The run-space model applies to hitters only. Pitchers still use
the older grade-space composite. This is a known limit (see Section 9).

---

## 3. The Four Stages

The system has four stages. Data flows from raw ratings to a dollar value.

```
   RAW TOOL RATINGS (from the game, 20-80 scale)
            │
            ▼
   ┌─────────────────────────┐
   │  STAGE 1: COMPOSITE      │   Current ability. Run-space for hitters.
   │  and CEILING             │   Ceiling = same math on potential tools.
   └─────────────────────────┘
            │
            ▼
   ┌─────────────────────────┐
   │  STAGE 2: FV GRADE       │   Project WAR from the ceiling.
   │  (hitters: WAR-anchored) │   Discount by the chance to develop.
   └─────────────────────────┘   Read the grade off the FV→WAR ladder.
            │
            ▼
   ┌─────────────────────────┐
   │  STAGE 3: WAR            │   Blend tool-WAR and stat-WAR.
   │  PROJECTION              │   Confidence grows with the MLB sample.
   └─────────────────────────┘
            │
            ▼
   ┌─────────────────────────┐
   │  STAGE 4: SURPLUS        │   WAR × $/WAR − salary, over team control.
   │  (dollars)               │   Apply discounts and scarcity.
   └─────────────────────────┘
```

The next sections explain each stage.

---

## 4. Stage 1 — Composite And Ceiling

### 4.1 The Composite (current ability)

The composite is the player's current ability on the 20-80 scale. The hitter
composite uses the run-space method.

```
   HITTER COMPOSITE (run space)

   contact, gap, power, eye ──► projected wOBA ──► bat runs
   speed, steal             ─────────────────────► baserunning runs
   range/arm (by position)  ─────────────────────► fielding runs
   position                 ─────────────────────► positional runs
                                                      │
                                                      ▼
                                      total runs above average
                                                      │
                                   convert to WAR, then map to 20-80
                                                      │
                                                      ▼
                                               COMPOSITE (20-80)
```

The four facets are:

- **Bat runs.** The system projects the player's wOBA from the hitting tools. wOBA
  is a plate-production metric. The system then converts wOBA to runs above
  average (wRAA) over a 600 plate-appearance baseline.
- **Baserunning runs.** A calibrated curve maps speed and steal grades to runs.
- **Fielding runs.** A per-position curve maps the range grade to runs. First base
  and designated hitter get zero fielding runs, because the range tool shows little
  spread there.
- **Positional runs.** Each position gets a fixed run adjustment. A shortstop gets
  a positive adjustment. A first baseman gets a negative one.

For an MLB hitter with a track record, the system blends each facet with the
player's **observed** career runs. Each facet blends at its own speed, because each
statistic becomes reliable at a different sample size:

| Facet | Statistic | Becomes reliable at |
|---|---|---|
| Bat | wRAA | ~600 PA (slow) |
| Baserunning | UBR | ~250 PA (fast) |
| Fielding | ZR | ~900 IP (slowest) |

For a minor-league hitter, the system blends the bat and baserunning facets with
level-adjusted minor-league stats. Minor-league fielding stats are not available,
so defense stays tool-based.

**Pitcher composite.** The pitcher composite uses the older grade-space method. It
takes a weighted average of stuff, movement, and control (plus HRA and PBABIP when
the league supplies them). It adds a bonus for arsenal depth and starter stamina.
It subtracts penalties for a weak tool floor, tool imbalance, and poor platoon
balance.

### 4.2 The Ceiling (peak ability)

The ceiling uses the same math as the composite. The one difference is the input:
the ceiling uses the player's **potential** tool ratings, not the current ones.

The system then blends the ceiling toward the current composite by age. A young
player keeps most of the potential. An older player keeps less.

| Age | Weight on potential | Weight on current |
|---|---|---|
| 16-17 | 0.95 | 0.05 |
| 20 | 0.80 | 0.20 |
| 25 | 0.55 | 0.45 |
| 30+ | 0.30 | 0.70 |

The ceiling can never fall below the current composite.

### 4.3 Minor-league performance signals (prospects)

For a prospect, minor-league stats feed the evaluation in three ways. They never
replace the tools; they refine confidence in them.

- **Composite blend (run-space).** The bat and baserunning facets blend with
  level-adjusted minor-league runs, as described in Section 4.1. Minor-league
  fielding is not available, so defense stays tool-based.
- **Performance-adjusted ceiling (PAC).** The system adjusts the ceiling up or
  down (at most ±6 points) based on how the player's level-relative production
  compares to his tools. A young player who dominates a level gets a boost; an old
  player who struggles gets a penalty. The adjustment scales with sample size.
- **Stat risk modifier.** The same signal nudges the development-confidence number
  used for the risk label (at most ±0.12). Outperforming the tools lowers risk;
  underperforming raises it.

Level discounts weight each level's stats by how well they translate (AAA counts
more than A-ball). The code is in `evaluation/fv.py`
(`compute_performance_adjusted_ceiling`, `compute_stat_risk_modifier`) and
`data/milb.py` (stat loading and level-relative normalization).

---

## 5. Stage 2 — The FV Grade

The FV grade is a scouting grade for the player's expected peak outcome. The
hitter FV model changed in Session 94. It is now **ceiling-anchored**.

### 5.1 How The Hitter FV Works

The old method read the FV grade off the current composite. This gave too many
average grades. A role player with a modest ceiling could ride a good glove to an
FV 55. This was wrong.

The new method projects a WAR from the ceiling, then discounts it by the chance
that the player develops. The steps are:

```
   HITTER FV (ceiling-anchored)

   ceiling score ──► project peak WAR (run-space, tail-capped)
                                     │
                                     ▼
                     ceiling_WAR  = the WAR if fully developed
                                     │
   p = chance to develop  (empirical gap-closure rate for the age)
                                     │
                                     ▼
   expected_WAR = p × ceiling_WAR + (1 − p) × (−0.3)
                                     │
                     read the grade off the FV→WAR ladder
                                     │
                                     ▼
                             FV GRADE (20-80)
```

Three points explain the design:

- **The WAR is tail-capped.** A raw projection from an elite ceiling gives an
  absurd WAR (13 to 18). The system compresses the tails toward the league's real
  WAR distribution. The top cap is the 98th percentile of real WAR; the bottom cap
  is the 2nd percentile.
- **A player who does not develop lands near replacement.** The fallback WAR is
  −0.3, not a deep negative. A prospect who fails is sent down, not played every
  day at a loss.
- **The ladder goes below FV 40.** The industry role scale uses grades below 40 for
  bench, depth, and organizational players. The ladder now reaches 35, 30, 25, and
  20. Marginal players spread into these grades instead of piling up at 40.

### 5.2 How The Pitcher FV Works

The pitcher FV uses the older composite-anchored method. It projects a peak
composite from the gap between the composite and the ceiling, discounts it, and
blends in some ceiling credit. This method is also the fallback for any league
without run-space calibration.

### 5.3 The Risk Label

The risk label is separate from the grade, but it uses the same inputs. The system
computes a development-confidence number from the age, the tool gap, the gap-closure
rate, and the character traits. A minor-league stat signal can adjust it.

| Development confidence | Risk label |
|---|---|
| Gap is small, or confidence ≥ 0.40 | Low |
| Confidence ≥ 0.25 | Medium |
| Confidence ≥ 0.15 | High |
| Confidence < 0.15 | Extreme |

So risk appears twice: once as the development discount in the grade, and once as
the variance label for the user.

---

## 6. Stage 3 — The WAR Projection

The surplus model needs a peak WAR for every player. The system uses one model for
all players, from a raw prospect to an established veteran. It blends two WAR
sources by a confidence number.

```
   WAR PROJECTION (one model for all players)

   tool-WAR  (from FV and composite)  ─┐
                                        ├──► blend by stat_confidence ──► peak WAR
   stat-WAR  (from MLB stat history)  ─┘
```

**stat_confidence** grows with the MLB sample. It controls the blend.

| Career MLB sample | stat_confidence | Meaning |
|---|---|---|
| 0 PA / 0 IP | 0.00 | Pure prospect. Tools only. |
| ~150 PA / ~50 IP | ~0.25 | Stats inform, tools lead. |
| ~250 PA / ~80 IP | ~0.50 | Balanced blend. |
| ~400 PA / ~120 IP | ~1.00 | Established. Stats lead. |

This design removes the hard border between a "prospect" model and an "MLB"
model. A player moves smoothly from one to the other as the sample grows.

The system also projects the WAR for each future year. It ages each facet on its
own curve. Baserunning declines first and fastest. The bat declines last. Defense
is in the middle. For a prospect, the system also projects growth toward the
ceiling along the bat development curve.

---

## 7. Stage 4 — The Surplus

The surplus is the dollar value of a player above the cost to employ him.

```
   For each year of team control:
       market value = WAR × $/WAR          (what the WAR is worth)
       salary       = pre-arb / arb / contract estimate
       surplus      = market value − salary
       discount for time value

   total surplus = sum of the yearly surplus
   total surplus × development discount × certainty × scarcity
```

Key rules:

- **$/WAR** is the league's open-market price for one win. The system calibrates it
  per league from real free-agent contracts.
- **Salary** comes from the real contract when one exists. Otherwise the system
  estimates it: the league minimum for pre-arb years, then an arbitration model.
- **Scarcity** raises the value of hard-to-fill positions (shortstop, catcher,
  center field) and lowers easy ones (first base, corner outfield, reliever).
- **The surplus floor is zero.** A player's talent can project below replacement
  (a negative WAR for the FV grade). But the trade value cannot go below zero. You
  do not pay a negative price. You release the player instead.

This is a deliberate split: the WAR can be negative for the FV grade, but it is
floored at zero for the dollar value.

---

## 8. How The Pipeline Runs

All of the above runs in a batch during the data refresh. The order matters,
because later stages read the output of earlier stages.

```
   refresh (pull data from the StatsPlus API)
       │
       ▼
   calibrate — pass 1
       Derive per-league tool weights and the run-space parameters.
       Write to tool_weights.json.
       │
       ▼
   evaluation_engine.run()
       Compute composite, ceiling, and component scores for every player.
       Write to the ratings table.
       │
       ▼
   calibrate — pass 2
       Regress composite against WAR. Write COMPOSITE_TO_WAR to model_weights.json.
       │
       ▼
   fv_calc.run()
       Compute FV, risk, and surplus for every player.
       Write player_evaluation (and the prospect_fv / player_surplus views).
       Compute the dev_speed metric.
```

**Rule:** `fv_calc` is the only writer of the final value tables. Every other
script and the whole web layer read these tables. They never recompute value.

### The Code Map

| Concept | File |
|---|---|
| Run-space facet spine (hitters) | `evaluation/facet_runs.py` |
| wOBA from tools | `evaluation/woba.py` |
| Composite and ceiling math | `evaluation/composite.py`, `evaluation/ceiling.py` |
| FV grade and risk | `evaluation/fv.py` |
| MiLB stat loading / normalization | `data/milb.py` |
| Surplus, FV↔WAR ladder | `evaluation/surplus.py` |
| WAR projection and blend | `evaluation/player_value.py`, `evaluation/war.py` |
| All model constants | `evaluation/constants.py` |
| Per-league calibration | `data/calibrate.py` |
| Batch composite/ceiling | `data/evaluation_engine.py` |
| Batch FV and surplus | `data/fv_calc.py` |

All files in `evaluation/` are pure. They have no database access and no global
state. The files in `data/` do the input and output.

---

## 9. What Depends On This System

Many features read the value tables. A change to the model changes all of them.
This is the source of the "opaqueness" concern.

```
                         player_evaluation
                      (fv, surplus, peak_war, risk)
                                 │
     ┌───────────────┬──────────┼──────────┬────────────────┐
     ▼               ▼          ▼          ▼                ▼
  Web player     Trade       Draft      Farm /          Offseason
  and team      tools       board      prospect        page (FA, arb,
  pages        (targets,   (value,    reports          options, Rule 5)
               assets,     merge)
               calculator)
```

Every box above trusts the value tables. None of them recomputes the model. So
the model is the single point of truth, and also the single point of risk.

---

## 10. Known Limits And Open Questions

These are the main areas that are not yet clean. The project backlog has the full
detail.

1. **Pitchers do not use the run-space model.** They still use the grade-space
   composite and the composite-anchored FV. A pitcher run-spine is a later project.

2. **The composite-WAR fit differs by league.** The hitter composite tracks real
   WAR well in one league (correlation 0.62) but less well in two others (~0.47).
   The gap comes mostly from compressed source ratings, not a model fault. The
   same-year number is near a data ceiling. The next-year projection is strong.

3. **One league (PPL) runs hot on the FV grade.** The league assigns high ceiling
   scores. This is an upstream calibration difference, not an FV-logic fault.

4. **The dev_speed metric can show a false signal during the migration window.**
   Older rating snapshots used the grade-space composite. The newest uses run-space.
   A window that straddles the change can read the model change as development. This
   self-heals as new snapshots accumulate.

5. **The composite and the stat projection can tell different stories.** For some
   proven MLB players, the ranking (composite) and the production (projection) do
   not agree. A plan exists to converge them, driven by data.

6. **Several older research documents are now historical.** They describe prototype
   stages, not the shipped model. See the next section.

---

## 11. Document Status

The authoritative registry is `docs/README.md`. This table is a quick reference
for the evaluation-related docs specifically.

| Document | Status | Note |
|---|---|---|
| `evaluation_system_overview.md` (this file) | **Living — current** | Single entry point for the pipeline. |
| `system_overview.md` — Key Design Decisions | **Living — current** | Reflects Sessions 92-94. Detailed and accurate. |
| `valuation_model.md` | **Living — current** | Updated Session 94 for the ceiling-anchored FV + surplus model. |
| `evaluation_model_findings.md` | **Living** | Current, but the accuracy tables are a Session 79 baseline (pre-run-space). |
| `archive/fv_war_pipeline_diagnosis.md` | **Historical** | Research trail for the Session 94 FV reframe. Final section matches shipped code; earlier sections are superseded prototypes. |
| `archive/evaluation_model.md` | **Historical** | Pre-run-space grade blend and old composite-anchored FV. |
| `archive/evaluation_engine_assessment.md` | **Historical** | Session 48 snapshot; predates the run-space work. |
| `archive/unified_evaluation_design.md` | **Historical** | The stat_confidence blend (Stage 3) shipped; the FV section is superseded. |

---

## 12. Where To Start A Simplification Review

The system is sound but has grown in layers. These are good places to look for
simplification, in order of likely value. All of these are tracked in
`docs/task_list.md` under "Findings Surfaced By The Session 95 Doc Audit".

1. **Retire or merge the stale documents** (Section 11). This alone removes most of
   the confusion. (Done Session 95 — docs classified and archived.)
2. **Decide the pitcher path.** The two FV paths (run-space for hitters,
   grade-space for pitchers) are a split that adds complexity. Decide whether to
   build the pitcher run-spine or to accept the split and document it clearly.
3. **Review the surplus multipliers.** Stage 4 applies several multipliers
   (development discount, certainty, scarcity, option value, RP discount). Confirm
   each one still earns its place and does not double-count another.
4. **Review the near-maxed blend in `player_value.py`.** The research trail shows it
   was once over-firing. Confirm the current guard is correct and still needed now
   that the FV is ceiling-anchored.
5. **Confirm the composite's role.** The composite now feeds the ranking and the
   WAR floor, but the hitter FV no longer reads off it. Make sure every remaining
   use of the composite is intentional.
