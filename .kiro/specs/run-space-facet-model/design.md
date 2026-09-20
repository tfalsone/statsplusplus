# Run-Space Facet Evaluation Model — Design

**Status:** Investigation / design. No implementation yet.
**Scope:** Core-model redesign of the hitter composite spine (bat/baserunning/
defense). Affects composite → ceiling → FV → WAR estimate → surplus → rankings,
every league. Pitchers out of scope for v1.
**Origin:** Session 91-92. Emerged from the offensive-tool-weight fix (offense
regressed against wOBA instead of total WAR). Once each facet is calibrated on
its own proper target, the old WAR-correlation "shares" that combined them are
orphaned — we need a principled recombination.

---

## 1. Problem statement

The current hitter composite (`compute_composite_hitter`, `composite.py`)
evaluates three facets and blends them in **grade-space (20-80)** using
**shares that sum to 1.0**:

- offense grade (contact/gap/power/eye) — now regressed against **wOBA** ✅
- baserunning grade (speed/steal) — regressed against total WAR (should be **UBR**)
- defense grade (positional D tools) — **hardcoded shares** (`DEFENSE_SHARES`),
  not calibrated at all

Recombination (current):
```
composite = off_grade*offense_share + br_grade*baserunning_share + def_grade*defense_weight
  where offense_share/baserunning_share/defense_weight sum to 1.0
  (defense_weight hardcoded per position; baserunning ~0.06; offense = remainder)
  + a pile of ad-hoc adjustments (contact-scaled baserunning boost, elite-defense
    boost, speed×contact synergy, sub-MLB floor penalty, imbalance penalty)
```

### Why this is broken
A 20-80 grade means **different run values in different facets**. A "70"
baserunner (~+6 runs) is not equivalent to a "70" bat (~+40 runs) or a "70"
defender (~+15 runs), but the share-weighted average treats them as
interchangeable and scales by an arbitrary share. The shares were reverse-
engineered to make the grade-blend roughly track WAR. Now that the facets are
individually de-WAR'd, **the shares have no principled basis.**

### The insight
wOBA, UBR, and fielding/positional value are **all natively in runs**. Runs are
the common currency WAR was badly proxying. Facets should combine **additively
in run-space**, not via grade-space shares:

```
runs_above_avg = wRAA(bat) + UBR(baserunning) + fielding_runs + positional_adj
             → WAR  (÷ runs_per_win, + replacement level)
             → composite (20-80, mapped from runs for display)
             → surplus (via $/WAR)
```

This is literally how WAR is constructed — but from OUR facet evaluations. Each
facet's contribution to the composite then **emerges from its natural run
magnitude** (bat dominates correctly; baserunning is small correctly) with no
hardcoded shares.

---

## 2. Current architecture map (as-is)

### 2.1 Files and responsibilities (`src/statsplusplus/evaluation/`)
| Module | Role | Touched by redesign? |
|---|---|---|
| `composite.py` | Grade-space facet grades + `compute_composite_hitter` recombination | **Heavy** — recombination replaced |
| `woba.py` | Per-player wOBA + per-league/year weight derivation (NEW, this session) | Reused (→ wRAA) |
| `war.py` | `peak_war_from_score` (composite→WAR table), aging curves, `stat_peak_war` (WAR from stat history) | **Medium** — composite→WAR may be superseded by run-spine |
| `player_value.py` | `compute_player_value`: blends tool-WAR vs stat-WAR by `stat_confidence`; surplus | **Medium** — tool-WAR source changes |
| `ceiling.py` | Ceiling scores (uses composite/transform machinery) | Medium — same recombination |
| `fv.py` | FV grade (ceiling vs positional median), risk | Low — consumes composite/ceiling |
| `surplus.py` | Prospect/contract surplus, scarcity, market value | Low — consumes WAR |
| `constants.py` | All constants + `ModelWeights` loader | Add run-conversion tables |
| `dev_speed.py`, `arb.py`, `outcomes.py`, `carrying_tools.py` | Adjacent | Low/none |

### 2.2 The two WAR paths today (KEY to the user's stat-signal question)
The model already blends tools and stats — the redesign must preserve this:

1. **Tool-WAR** (`peak_war_from_score(composite, bucket)`): composite score →
   WAR via a per-league calibrated `COMPOSITE_TO_WAR` table.
2. **Stat-WAR** (`stat_peak_war`): weighted 4-year WAR average from actual MLB
   stat history (weights [3,3,2,1], recency + partial-season scaled).
3. **Blend** (`compute_player_value`):
   `peak_war = (1 - sc)*tool_war + sc*stat_war` where
   `sc = stat_confidence(career_pa, career_ip)` ramps 0→1 (full at 400 PA /
   120 IP, concave exponent 1.4).
   - Prospects (sc≈0): pure tool projection (FV-based, encodes development prob).
   - Veterans (sc≈1): pure stat history.
   - Tool projection itself blends FV-WAR (upside) and composite-WAR (current)
     by sc, with near-maxed and RP caps.
4. **Aging** (`aging_mult`): applies the per-league aging curve to peak WAR over
   the control window; `_UNIFIED_WAR_RAMP` handles pre-peak development years.

**Critical design constraint the user flagged:** the run-space facet model
produces a *tool-based* current-ability run total. It must slot in as the
**tool-WAR source**, and the existing `stat_confidence` blend with stat-history
WAR and the aging/ramp machinery must continue to work. We are replacing HOW
tool-WAR is computed (run-additive facets instead of composite→WAR table), NOT
the stat-blend/age gradient on top of it. This keeps prior-performance and age
handling intact and consistent.

### 2.3 Composite consumers (blast radius)
`compute_composite_hitter` / composite score feeds: ceiling → FV → surplus →
rankings; player page (tool_only + stat-blended composite); prospect lists;
draft board; trade calculator; depth chart; dev_speed (uses composite deltas).
A run-based composite must still emit a **20-80 integer** for all these display/
ranking consumers (map runs → 20-80 via league spread), so the redesign is
internally run-based but externally compatible at the composite-score boundary.

### 2.4 Batch orchestration
`data/evaluation_engine.py` computes composite/ceiling per player in batch;
`data/fv_calc.py` computes FV/surplus/WAR; `data/calibrate.py` derives all
per-league tables into `tool_weights.json` / `model_weights.json`. New run-
conversion tables (grade→runs per facet) get calibrated here.

---

## 3. Proposed model (to-be)

### 3.1 Run-space spine (hitters)
```
bat_runs         = wRAA = (proj_wOBA - lg_wOBA) / wOBA_scale * PA_full
baserunning_runs = f_br(speed, steal)            # calibrated grade→UBR curve
fielding_runs    = f_def(def_tools, position)    # calibrated grade→fielding-runs curve
positional_adj   = POS_ADJ[position]             # runs, standard positional adjustment
------------------------------------------------------------------
runs_above_avg   = bat_runs + baserunning_runs + fielding_runs + positional_adj
peak_war_tool    = runs_above_avg / runs_per_win + replacement_runs/rpw
composite(20-80) = map_runs_to_grade(runs_above_avg, league_spread)
```
Then `peak_war_tool` enters `compute_player_value` exactly where `tool_war` does
today → the `stat_confidence` blend, aging, ramp, surplus all unchanged (in B1).

### 3.1a Per-facet stat-blend / aging / convergence (RESOLVED: adopt; stage as B2)
The facets develop, age, and stabilize on **different curves** — aggregating them
into one whole-player `stat_confidence` + one aging multiplier is a modeling
error the run-spine lets us fix cleanly (facets are already separate run
components, so blend/age each BEFORE summing):
```
bat_runs         = blend(tool_bat_runs, stat_bat_runs; sc_bat)  * age_bat(age)
baserunning_runs = blend(tool_br_runs,  stat_br_runs;  sc_br)   * age_br(age)
fielding_runs    = blend(tool_def_runs, stat_def_runs; sc_def)  * age_def(age)
positional_adj   = POS_ADJ[position]
runs_above_avg   = sum(...) → WAR (OOTP-anchored) → composite/surplus
```
Rationale per facet:
- **Bat:** develops most; ages on classic offensive curve; wRAA stabilizes SLOW
  (~300+ PA) → `sc_bat` ramps slowly. Carries almost all of a prospect's
  projected development.
- **Baserunning/speed:** barely develops (near-fixed physical trait); ages
  EARLIEST/fastest (speed peaks ~23-25); UBR stabilizes FAST (low variance) →
  `sc_br` ramps quickly, near-known even for young players. A prospect's
  baserunning is treated as ~known and roughly flat, NOT as upside.
- **Defense:** develops moderately; own aging shape; fielding runs stabilize
  SLOWEST (noisy) → `sc_def` slowest ramp, leans on tools longest.

Per-facet stat-WAR needs per-facet OBSERVED runs from history (not total `war`):
bat→historical wRAA (from stored counting stats), baserunning→stored `ubr`,
defense→fielding runs from stored `fielding_stats.zr`. All feasible with stored
data; more machinery than reading `war`.

Calibration surface grows: 3 stabilization ramps + 3 aging curves per league.
Mitigation: baserunning/defense aging are more universal (physical decline) →
stronger priors, less per-league wobble; guard small samples (recurring concern).

### 3.2 The three grade→runs conversions (all per-league calibrated)
1. **Bat → runs (wRAA):** already have wOBA (this session) + wOBA_scale + lg_wOBA
   from run-env derivation. Need PA normalization (per-600 or full-season).
2. **Baserunning → runs:** calibrate `speed/steal grade → UBR`. Confirmed signal:
   PPL speed~UBR r=0.34 (vs r=0.08 vs WAR). Regress UBR on speed/steal grades,
   per league. UBR fully populated on PPL.
3. **Defense → runs:** calibrate `def_tools → fielding_runs` per position. Data:
   `fielding_stats.zr` well-populated (15169/17184 nonzero on PPL); framing
   sparse (catcher-only, 3151). Positional adjustment (runs) is standard/
   configurable. This is the hardest/noisiest facet.

### 3.3 What gets retired / reconsidered
- `DEFENSE_SHARES` hardcoded dict → replaced by fielding-runs + positional_adj.
- `BASERUNNING_SHARE` 0.06 → emerges from UBR magnitude.
- Grade-space share recombination in `compute_composite_hitter` → run-additive.
- Ad-hoc adjustments (contact-scaled baserunning boost, elite-defense boost,
  speed×contact synergy): re-evaluate each — some may be redundant once facets
  are in runs (synergy/boosts were partly compensating for grade-space flaws);
  others (sub-MLB floor penalty, imbalance penalty) may still be warranted as
  tool-reliability adjustments. DECISION NEEDED per adjustment.
- `peak_war_from_score` (composite→WAR table): may become redundant for hitters
  if the run-spine produces WAR directly. Keep for pitchers (unchanged) and as
  fallback. DECISION NEEDED.

---

## 4. Design decisions

**Resolved (Session 92):**
- **[R] Anchor to OOTP WAR (decision 2).** Derive runs-per-win / replacement so
  our league-total WAR ≈ OOTP's league-total WAR — self-consistent + built-in
  sanity check, mirroring the wOBA-anchor approach.
- **[R] Fold in composite↔projection convergence (decision 8).** The run-spine
  gives composite and the WAR projection ONE shared run total, naturally
  resolving the long-standing divergence. Retire/replace the weak
  `compute_composite_mlb` stat-blend with the shared run total.
- **[R] Adopt per-facet stat-blend / aging / convergence (§3.1a).** Each facet
  gets its own `sc` (stabilization-driven), aging curve, and tool↔stat
  convergence. Staged as B2 (after the whole-player run-spine milestone B1).
- **[R] Hold the baserunning UBR target swap** — do it directly in the run-space
  redesign (as baserunning→runs), NOT as a separate current-model increment.
  Avoids doing baserunning twice.

**Still open (to resolve before/within implementation):**
1. **PA/playing-time normalization.** *(RESOLVED Session 92.)* Peak = **600 PA
   full-time baseline** for the run projection (consistent with current peak-WAR
   framing; a prospect projects to a full-time role at peak). Playing-time /
   role-scaling (platoon, bench, injury) is applied DOWNSTREAM in the depth-chart
   / surplus layer where PT is already modeled — NOT in the peak-ability run
   spine. Keeps the composite a clean full-time-ability measure.
3. **Defense in runs — how ambitious.** *(RESOLVED Session 92.)* **Option (a):
   regress defensive tools → fielding runs (ZR) per position group.** Confirmed
   viable — IF range→ZR r=0.40, OF range→ZR r=0.39 on PPL (comparable to
   baserunning's 0.34), realistic ZR spreads (±25-40 runs). Catcher framing is
   sparse → positional-prior fallback for framing + small samples. Defense is the
   noisiest facet → strongest prior-shrinkage of the three (ties to the recurring
   small-sample-calibration concern).
   **Calibration detail (RESOLVED in B1 prototyping, Session 92):** fit the
   tool→ZR curve **PER POSITION, not pooled** — per-position signal is far
   stronger (SS r=0.70, LF r=0.86, CF r=0.57) than pooled OF/IF (~0.4-0.51).
   **Center** each curve at the position-average grade (0 runs at avg) and
   **CLAMP** to the position's observed ZR range (±10%) — the steep slopes
   otherwise extrapolate to absurd runs (e.g. −24 to −81) for grades far from the
   sample mean. Use position-appropriate tool: IF range (ifr) for SS/2B/3B, OF
   range (ofr) for CF/COF, arm (c_arm) for C (weak/small — catcher stays near
   prior, value comes from the +11 positional adjustment). ZR is already
   ~position-relative runs (mean~0, weak IP dependence) → NO playing-time
   normalization needed. Slope shrinkage ~0.75. Impact: this single fix took the
   prototype's new-WAR~OOTP-WAR R² from 0.57 → 0.71.
3b. **Multi-position players — best-position, split lives downstream.**
   *(RESOLVED Session 92.)* The ability composite measures peak FULL-TIME ability,
   which is inherently a per-position question (`fielding_runs` and
   `positional_adj` are both position-specific). Resolution:
   - **Ability composite:** evaluate `fielding_runs + positional_adj` at the
     player's **best position** — the position maximizing that sum. Reuse the
     EXISTING `estimate_all_positions` + `assign_bucket` machinery (Session 66
     calibrated positional OLS models already estimate a player's rating at every
     position from his defensive tools). This is NOT "primary position only" — a
     2B/3B utility man who can cover SS gets SS's positional credit, so
     flexibility is rewarded indirectly. One clean, comparable composite number.
   - **Realized value (2B/3B time split):** lives in the depth-chart / surplus
     layer where playing time is already modeled (per decision #1). Fielding runs
     + positional adjustment accrue pro-rated by games at each position there —
     the layer already knows the deployment.
   - **Explicit versatility PREMIUM** (roster flexibility: injury cover, platoons,
     bench-spot savings) is small, uncertain, and GM-judgment — kept as a
     SEPARATE later enhancement (see the open "Positional versatility in depth
     calculations" task). Layers onto the run-spine cleanly once it exists; does
     NOT gate this redesign.
2b. **Runs-per-win / replacement (anchor mechanics).** *(RESOLVED Session 92.)*
   Do NOT derive RPW from a run-environment formula (error-prone — a naive
   Pythag estimate gave a nonsensical 44 in testing). Instead **solve** RPW +
   replacement level so our summed-facet-runs→WAR reproduces OOTP's qualified-
   hitter WAR distribution for the season (1954 PPL anchor: mean 2.49, median
   2.30, max 10.12). The anchor IS the calibration.
4. **Composite (20-80) mapping.** *(RESOLVED Session 92.)* Map runs_above_avg →
   20-80 by **calibrating to the current MLB composite distribution** (mean/sd)
   so the new composite preserves the existing scale and ranking continuity
   (league-avg ≈ 50, elite ≈ 70+). Method: z-score runs vs the qualified-MLB run
   distribution, then affine-map to match the incumbent composite mean/sd. This
   guarantees no compression/expansion surprise for downstream consumers.
   Validate: rank correlation new-vs-old composite; inspect large movers.
5. **Prospect facet-runs.** *(RESOLVED Session 92.)* From tools→runs projection
   (same calibrated curves as MLB tool-WAR). Per §3.1a a prospect's development
   lives almost entirely in bat_runs; baserunning/defense near-known. FV stays
   ceiling-based and unchanged in construction — it consumes the run-derived
   composite/ceiling exactly as it consumes today's composite (20-80 boundary
   preserved), so no FV formula change. Confirm ceiling uses the same run spine.
6. **Where the run-spine lives.** *(RESOLVED Session 92.)* New pure module
   `evaluation/facet_runs.py` (grade+curves→runs per facet, sum→runs/WAR);
   `composite.py` calls it and maps to 20-80; `player_value.py` consumes its
   tool-WAR. facet_runs is the TOOL-WAR source ONLY — no duplication of
   `war.py`'s stat-history-WAR path.
7. **Pitchers.** *(RESOLVED Session 92.)* Out of scope v1 — pitchers stay on the
   current composite→WAR path. Hitter/pitcher composite interfaces already
   diverge cleanly. Revisit a pitcher run-spine (FIP/RA9 components) as a later
   phase.
9. **Ad-hoc adjustments.** *(RESOLVED Session 92 — plan.)* Re-derive each in
   run-space rather than porting blindly:
   - contact-scaled baserunning boost, elite-defense boost, speed×contact
     synergy: **DROP** — these compensated for grade-space share flaws; in
     run-space the additive facets capture the value directly. Verify each adds
     no residual signal before removing (quick regression check during B1).
   - sub-MLB floor penalty, tool-imbalance penalty: **KEEP as run adjustments** —
     these encode tool-RELIABILITY / bust-risk (a sub-35 tool underperforms its
     grade), which is orthogonal to run-conversion. Re-express as run penalties.
10. **`peak_war_from_score` (composite→WAR table).** *(RESOLVED Session 92.)*
   For **hitters**, retire as the primary path — the run-spine produces WAR
   directly. **Keep** for pitchers (unchanged) and as a fallback when facet-runs
   can't be computed (missing tools). The composite→WAR table stays calibrated
   for those uses.

---

## 5. Staging plan

**Banked already (current model, low-risk, validated):**
- Offense → wOBA target swap (done Session 92, full suite green, uncommitted).

**Increment A — DROPPED.** The standalone baserunning UBR target swap in the
current grade-space model is NOT done separately — folded into B1 (baserunning→
runs) to avoid doing baserunning twice. (Resolved Session 92.)

**Increment B — the redesign (own scoped session(s)):**

- **B1 — run-space spine, whole-player blend (safe checkpoint):**
  - Build `evaluation/facet_runs.py` + per-league grade→runs calibration
    (bat→wRAA, baserunning→UBR-runs, defense→fielding-runs + positional_adj).
  - OOTP-anchored runs-per-win / replacement level.
  - Rewire `compute_composite_hitter` to run-additive; map runs→20-80.
  - Slot run-based tool-WAR into `compute_player_value`; keep the EXISTING
    whole-player `stat_confidence` blend + aging + ramp for now.
  - Retire `DEFENSE_SHARES` / `BASERUNNING_SHARE`; re-evaluate ad-hoc adjustments.
  - Validate B1 in isolation before adding per-facet dynamics.

- **B2 — per-facet stat-blend / aging / convergence (§3.1a):**
  - Per-facet observed-runs from history: historical wRAA, `ubr`, fielding-runs.
  - Per-facet `sc` ramps (stabilization-driven) + per-facet aging curves.
  - Fold in composite↔projection convergence (shared run total).
  - Validate the added per-facet dynamics against B1 as the baseline.

  **B2 bat-blend PROTOTYPE VALIDATED (Session 92, prospects):** implemented the
  bat-facet MiLB blend in the prospect harness — observed **level-relative,
  level-discounted MiLB wRAA** (vs the prospect's own MiLB league average wOBA)
  blended with tool-projected wRAA by a bat `stat_confidence` (`(eff_pa/500)^1.2`,
  cap 0.85; eff_pa = level-discount × recency × PA). Confirmed correct behavior:
  - Steve Colley (Cubs CF): tool bat +28 but observed MiLB −6 (.299/.303, 504 PA,
    sc=0.67) → composite 60→53. The over-crediting is FIXED.
  - Luke Drake: observed +87 (elite) but sc=0.10 (254 PA) → stays tool-driven, no
    hot-small-sample overreaction.
  - Small samples (Perez/Camba, 148/197 PA, sc=0.05) barely move — guard works.
  Level-relative is essential (per-MiLB-league wOBA available); MiLB fielding
  empty so defense stays tool-only (correct).

  **B2 MLB per-facet blend + aging PROTOTYPE VALIDATED (Session 92):** each MLB
  facet blends tool-projection with observed CAREER facet runs by a
  facet-specific stabilization `sc` — bat (wRAA, slow, full ~600 PA, cap 0.90),
  baserunning (UBR, FAST, full ~250 PA, cap 0.95 — low variance), fielding (ZR,
  SLOWEST, full ~900 IP, cap 0.80). Per-facet AGING applied separately.
  Confirmed corrections vs whole-player B1: Jeff Vining (CF) batObs +21 vs tool
  +5 → WAR 2.5→4.0 (closer to OOTP 3.5); Tom Myers batObs +29 → 2.4→4.4;
  Joe Phillips tool +16 but batObs −3 (not hitting) → 3.1→2.2 (correct downward,
  the MLB analogue of prospect Colley).
  **Aging-curve decision (RESOLVED):** per-facet aging uses LITERATURE-BASED PRIOR
  curves (`AGING_BAT` classic 26-28 peak; `AGING_BASERUNNING` earliest/steepest
  peak ~23-25; `AGING_DEFENSE` moderate, experience offsets speed decline) — NOT
  freely fit from per-league longitudinal data, which is too thin (PPL YoY
  transitions n=10-19/age) and survivorship-biased (cross-sectional UBR wrongly
  rises at 33+ because only good baserunners keep playing). Per-league shrink-
  adjust only where longitudinal signal is strong.

**Increment B (the redesign, own scoped session(s)):**
- Build `facet_runs.py` + per-league grade→runs calibration (bat/br/def).
- Rewire `compute_composite_hitter` to run-additive; map runs→20-80.
- Slot run-based tool-WAR into `compute_player_value`.
- Retire hardcoded shares; re-evaluate ad-hoc adjustments.
- Validate: hold-out WAR R², composite-ranking continuity, player spot-checks
  (power-first up, correct positional value), cross-league (eMLB/vMLB/PPL),
  full suite. Compare to OOTP WAR at league level (anchor sanity).

---

## 6. Validation strategy (increment B)
- **Anchor check:** our league-total WAR ≈ OOTP league-total WAR (self-consistency).
- **Hold-out:** `model_regression.py --test holdout` — run-spine composite→WAR R²
  vs current, per year. Accept small WAR-R² tradeoffs for correctness (precedent:
  Session 82 pitcher transform).
- **Ranking continuity:** correlation of new vs old composite ranks; flag large
  movers and confirm they move for baseball-sound reasons (position value now in
  runs, not shares).
- **Player spot-checks:** power-first hitters up; premium-D up-the-middle players
  correctly valued; 1B/DH offense not double-penalized.
- **Cross-league:** eMLB, vMLB, PPL all calibrate sensibly (small-sample guards).
