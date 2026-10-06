# Value Grade Research — Findings

> **Status:** Living · **Owns:** research findings for a WAR-anchored value grade (`scripts/analyze_grade_divergence.py`, `scripts/proto_value_grade.py`)
> **Writing standard:** prose · **Last verified against code:** Session 95

Research into whether composite/ceiling grades mislead users on non-prospect
players, and whether a separate WAR-anchored "value grade" should be added.
Prompted by the concern that an established player can show a high ceiling (e.g.
55) while his true value is a 40-45 player — and because established players show
no FV, the user has no corrective lens. Read-only analysis, no model changes.

Scripts: `scripts/analyze_grade_divergence.py` (quantifies the gap),
`scripts/proto_value_grade.py` (prototypes the value grade).

---

## The Concern

- **Composite** = current ability (our answer to OOTP OVR). For hitters it is
  run-space and lightly stat-blended, so it is reasonably honest for veterans.
- **Ceiling** = peak potential (our answer to OOTP POT). It is a pure
  potential-tools projection with **no production grounding at any age**.
- **FV** = risk-discounted value grade — but it is computed **only for players
  under the rookie threshold** (career < 130 AB / < 50 IP).

Once a hitter crosses the threshold he loses his FV and is judged by
composite/ceiling alone. The ceiling never walks down to meet production, so a
proven replacement-level hitter can keep a mid-50s ceiling indefinitely.

---

## Finding 1 — The overvaluation trap is real, systematic, and one-directional

Measured on established hitters (no FV, ≥130 PA, `stat_confidence ≥ 0.8` — i.e.
genuinely proven, `peak_war` is stat-anchored). Gap = ceiling grade − `peak_war`
grade, both on the FV ladder. Positive = ceiling flatters.

| League | n | median gap | % flattered ≥1.5 tiers | % understated |
|---|---|---|---|---|
| eMLB | 371 | **+4.9** | 31% | 1% |
| vMLB | 355 | **+6.4** | 43% | 1% |
| PPL  | 184 | **+8.9** | 58% | 0% |

The entire established-hitter distribution is shifted optimistic by ~5-9 grade
points, with a long flattering tail; the understatement direction is ~0-1%. This
is not an outlier tail — it is a structural lean.

Clear cases (large sample, `sc` 1.0, so no "still developing" excuse):

- **Mac Powerz** (C, 1266 PA): ceiling 60, produced −0.03 peak_war → value ~35.
- **Keiran Donnelly** (SS, 422 PA): ceiling 61, −0.64 WAR → value ~30.
- **Jaime Decanter** (1B, 872 PA): ceiling 55, 0.03 WAR → value ~35.
- **Chris Pugh** (PPL SS, 1284 PA): ceiling 55, −0.38 WAR → value ~32.

These are proven, large-sample, replacement-level bats carrying mid-to-high-50s
ceilings with no FV to contradict them. The concern is confirmed; real cases are
often worse than "55 ceiling / 40-45 value."

**Recent graduates** (just over the threshold) are the most-affected group
(56-81% flattered), but many are low-`stat_confidence` young players where a high
ceiling over thin production is *correct* (they graduated early, haven't
developed). The genuinely misleading graduates are the high-`sc` ones, which are
the same cases as the established cohort.

---

## Finding 2 — Prospects are NOT misgraded (cohort cleared)

Near-ready / "maxed" prospects (FV ≥ 40, small composite→ceiling gap) show
essentially no FV-vs-ceiling disagreement in eMLB (2%) or vMLB (1%). The large
numbers in an earlier, looser pass were an FV-20 vs ceiling-grade-35 floor
artifact (FV floors at 20, the WAR ladder bottoms at 35), not real divergence.

PPL is the exception (62%), but that is the already-tracked "PPL runs hot on
ceiling scores" calibration issue, not a new finding.

**Conclusion:** the problem is localized to established/graduated players. The
prospect FV system works; do not touch it.

---

## Finding 3 — `peak_war` and FV are coherent (the model is sound)

The value-grade prototype first appeared to show a 52% prospect disagreement
between a `peak_war`-derived grade and the stored FV. Investigation showed this
is **not** a model inconsistency:

- `peak_war − FV_implied_WAR` for hitter prospects: median **−0.20**, and **40%
  of prospects sit below their FV-implied WAR, 0% above.** So `peak_war` is
  slightly *more conservative* than the FV grade — never more optimistic.
- Stratified by FV band, the value-grade-vs-FV gap is: **FV ≤ 35 → +9.2**
  (floor-compression artifact), **FV 36-45 → +0.2**, **FV 46-55 → −1.3**,
  **FV 56-65 → −0.8**, **FV > 65 → 0.0**.

So for every prospect that matters (FV 36+), a `peak_war`-derived value grade
reproduces FV within ~1 point. The apparent disagreement was entirely in the
FV ≤ 35 org-filler band, where both numbers say "fringe" anyway and the gap is a
scale-floor artifact of inversion, not a talent disagreement.

**This removed the main objection to a value grade:** there is no deep
`peak_war` ↔ FV incoherence to fix first.

---

## Finding 4 — Value grades must stay POSITION-RELATIVE (the RP lesson)

The prototype inverted `peak_war` through the per-position FV→WAR ladder. For
relievers this pins almost everyone at 80: the RP ladder tops out at ~1.5 WAR
(FV 80), because an elite reliever's peak WAR genuinely is ~1.5 (60-70 IP). So
any decent reliever inverts to the top.

This is **not a bug — it is the point.** FV grades are position-relative: an RP
80 means "best-in-class reliever," an SS 80 means "~8 WAR superstar." They are
not the same absolute value and were never meant to be.

**Decision (user, Session 95): keep the value grade position-relative.** A
cross-position absolute-WAR scale would flatten exactly the distinctions that let
us separate elite relievers from good/average ones — in real baseball there are
clear-tier "80" relievers, and a WAR-generation scale erases that tier structure.
The grade should read like an FV that keeps going after prospect status, not like
a universal WAR number.

Consequence: a value grade must **never** be presented as a cross-position
absolute ("80 = elite, period"). It is read within a position, like FV and like
OOTP's own ratings.

---

## Design Implications

1. **Do not change what composite/ceiling mean.** They are the OOTP current/
   potential frame of reference and are correct for prospects. Ceiling is
   *supposed* to be optimistic/tool-driven; for a 20-year-old that optimism is
   right. The gap is the missing corrective lens for established players, not the
   ceiling itself.

2. **The honest number already exists.** `peak_war` (stored per player in
   `player_evaluation`) is tool-based for prospects and stat-dominated for
   veterans. A value grade is `fv_from_peak_war(peak_war, bucket)` — it needs no
   new model, only surfacing.

3. **Scope and framing (if surfaced):**
   - Works cleanly today for **established / graduated hitters** — the target
     population.
   - Must be **position-relative** (per Finding 4) — labeled/read within a bucket.
   - Prospects already have FV; a value grade for them is redundant (they agree).
   - For the low-WAR floor (FV ≤ 35) the inversion compresses — acceptable since
     those players are all "fringe/org" regardless.

4. **The value grade's job for the user:** separate *tool/potential* (composite/
   ceiling) from *realized value* (value grade). The **gap between ceiling and
   value is the signal** — a large gap flags a player whose scouting read and
   production have diverged (over- or under-performer). This is the "playing
   above/below his ratings" lens the user asked for.

---

## Status / Next Steps

- Research complete; model confirmed sound. **No code changes made.**
- Decision locked: **position-relative** value grade (not cross-position absolute).
- **Not yet decided:** whether to surface the value grade (and where — player page,
  roster, prospect lists) or keep it internal. Tracked in `task_list.md`.
- Both scripts retained as validation tools:
  - `scripts/analyze_grade_divergence.py` — re-run to measure the ceiling-flatters
    gap after any ceiling/surplus change (success = Cohort 1 median gap → ~0).
  - `scripts/proto_value_grade.py` — prototype the value grade per bucket/class.
