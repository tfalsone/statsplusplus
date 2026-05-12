# Evaluation Model Reference

Complete reference for the Stats++ player evaluation pipeline. Covers every
stage from raw tool ratings to FV grade and surplus value.

---

## Pipeline Overview

```
Raw Tool Ratings (20-80)
    │
    ▼
┌─────────────────────────┐
│  1. Tool Transform      │  Non-linear: penalty below 40, bonus above 60
└─────────────────────────┘
    │
    ▼
┌─────────────────────────┐
│  2. Compensation        │  Pull below-average tools toward 50 when
│                         │  a compensating tool is strong
└─────────────────────────┘
    │
    ▼
┌─────────────────────────┐
│  3. Composite Score     │  Weighted average of offense + baserunning + defense
│                         │  with dynamic share scaling and floor penalty
└─────────────────────────┘
    │
    ├──── (potential tools) ────▶ True Ceiling (Step 4)
    │                                    │
    │                                    ▼
    │                            ┌───────────────────┐
    │                            │  5. Ceiling Score  │  Age-blended projection
    │                            └───────────────────┘
    │                                    │
    ▼                                    ▼
┌─────────────────────────┐    ┌───────────────────┐
│  6. MLB Stat Blending   │    │  7. FV Grade      │  Gap closure + bust discount
│  (MLB players only)     │    │  (prospects only) │  → risk label
└─────────────────────────┘    └───────────────────┘
    │                                    │
    ▼                                    ▼
  composite_score                 ┌───────────────────┐
  (stored in DB)                  │  8. Surplus Value  │  FV → WAR → dollars
                                  └───────────────────┘
```

---

## Step 1: Tool Transform

**Function:** `_tool_transform(val)`

Piecewise non-linear transformation applied to each offensive tool before
the weighted average. Reflects empirical WAR data showing non-linear returns.

| Range | Formula | Effect |
|-------|---------|--------|
| val ≤ 40 | `40 - (40 - val) × 1.5` | Penalty: 30 → 25, 20 → 10 |
| 40 < val ≤ 60 | `val` (linear) | No change |
| val > 60 | `60 + (val - 60) × 1.3` | Bonus: 70 → 73, 80 → 86 |

**Rationale:** Sub-40 tools produce sharply negative WAR outcomes (the "cliff").
Above-60 tools produce outsized value that a linear average underestimates.

---

## Step 2: Tool Compensation

**Function:** `_compensated_transform(val, compensators)`

After the tool transform, tools below 50 (league average) get pulled toward
50 when a compensating tool is strong. This captures the empirical finding
that players with one elite tool can partially offset a weakness.

**Formula:**
```
transformed = _tool_transform(val)
deficit = 50 - transformed          # only positive when below average
pull_fraction = min(0.75, Σ(surplus_i × strength_i))
effective = transformed + deficit × pull_fraction
```

Where `surplus_i = compensator_value - 50` (how far above average the
compensator is) and `strength_i` is the per-point pull rate.

**Hitter compensation pairs:**

| Weak Tool | Compensator | Strength |
|-----------|-------------|----------|
| Power | Contact | 0.020/pt |
| Power | Eye | 0.012/pt |
| Eye | Contact | 0.020/pt |
| Contact | (none) | — floor tool, no compensator |

**Pitcher compensation pairs:**

| Weak Tool | Compensator | Strength |
|-----------|-------------|----------|
| Stuff | Movement | 0.020/pt |
| Stuff | Control | 0.012/pt |
| Control | Stuff | 0.018/pt |
| Control | Movement | 0.012/pt |
| Movement | (none) | — floor tool, no compensator |

**Example:** Power=35, Contact=70:
- transformed = 32.5 (1.5× penalty)
- deficit = 50 - 32.5 = 17.5
- surplus = 70 - 50 = 20, fraction = 20 × 0.020 = 0.40
- effective = 32.5 + 17.5 × 0.40 = **39.5**

**Design:** Smooth curve with no cliff at 40. Activates continuously from
compensator=50 upward. Capped at 75% deficit reduction.

---

## Step 3: Composite Score

### Hitter Composite

**Function:** `compute_composite_hitter(tools, weights, defense, def_weights)`

Three components combined with position-specific shares:

**a) Offensive Grade** — weighted average of transformed+compensated hitting tools:
- Tools: contact, gap, power, eye
- Weights vary by position (e.g., 1B weights power 0.32, SS weights contact 0.30)

**b) Baserunning** — weighted average of speed, steal, stl_rt (no transform):
- Contact-scaled boost: when contact > 50, baserunning share increases
- `boost_factor = min(1.0, (contact - 50) / 30)`
- At contact=80, baserunning share doubles its base value

**c) Defense** — weighted average of positional defensive tools:
- Elite defense boost: when primary def > 50, defense share increases
- `boost_factor = min(1.0, (primary_def - 50) / 30)`
- At def=80, defense share doubles its base value

**d) Sub-MLB Floor Penalty:**
- Each offensive tool below 35: penalty = (35 - tool) × 0.25
- Captures the non-linear cost of a disqualifying weakness

**Default tool weights (hitter):**

| Position | Contact | Gap | Power | Eye | Speed | Steal | StlRt | Defense |
|----------|---------|-----|-------|-----|-------|-------|-------|---------|
| C | 0.30 | 0.16 | 0.24 | 0.16 | 0.02 | 0.01 | 0.01 | 0.15 |
| SS | 0.30 | 0.18 | 0.22 | 0.16 | 0.03 | 0.02 | 0.01 | 0.05 |
| 2B | 0.30 | 0.18 | 0.22 | 0.16 | 0.03 | 0.02 | 0.01 | 0.05 |
| 3B | 0.28 | 0.16 | 0.26 | 0.16 | 0.04 | 0.02 | 0.01 | 0.00 |
| CF | 0.26 | 0.16 | 0.20 | 0.16 | 0.04 | 0.03 | 0.02 | 0.10 |
| COF | 0.29 | 0.18 | 0.28 | 0.17 | 0.02 | 0.01 | 0.01 | 0.00 |
| 1B | 0.30 | 0.18 | 0.32 | 0.19 | 0.02 | 0.00 | 0.00 | 0.00 |

### Pitcher Composite

**Function:** `compute_composite_pitcher(tools, weights, arsenal, stamina, role)`

- Core tools: stuff, movement, control (+ HRA, PBABIP when available)
- Tool compensation applied (stuff/control holes softened)
- Arsenal: +1 per pitch ≥45 beyond 3rd (capped +3), +2 if best pitch ≥70
- Stamina: penalty if <40, volume bonus if >45 (SP only, capped +4)
- Platoon penalty: -2 to -3 for severe splits
- Sub-MLB floor penalty on core tools

**Default pitcher weights:**

| Role | Stuff | Movement | Control | Arsenal |
|------|-------|----------|---------|---------|
| SP | 0.35 | 0.25 | 0.30 | 0.10 |
| RP | 0.40 | 0.25 | 0.25 | 0.10 |

---

## Step 4: True Ceiling

**Function:** `compute_true_ceiling(potential_tools, weights, composite, ...)`

Pure potential-driven score: what happens if every tool reaches its potential
rating. Uses the same composite formula applied to potential tools.

- No age blend (unlike ceiling_score)
- Floored at current composite (can't project below current ability)
- Represents the absolute peak outcome

---

## Step 5: Ceiling Score

**Function:** `compute_ceiling(potential_tools, weights, composite, age, ...)`

Age-weighted blend between true ceiling and current composite:

```
potential_weight = max(0.30, min(0.95, 1.0 - (age - 16) × 0.05))
ceiling = true_ceiling × potential_weight + composite × (1 - potential_weight)
```

| Age | Potential Weight | Current Weight |
|-----|-----------------|----------------|
| 16-17 | 0.95 | 0.05 |
| 18 | 0.90 | 0.10 |
| 20 | 0.80 | 0.20 |
| 22 | 0.70 | 0.30 |
| 25 | 0.55 | 0.45 |
| 30+ | 0.30 | 0.70 |

**Modifiers:**
- Work ethic H/VH: +1
- Work ethic L: -1
- Accuracy L: -2
- Floor: never below composite

---

## Step 6: MLB Stat Blending

**Function:** `compute_composite_mlb(tool_score, stat_seasons, peak_age, player_age)`

For MLB players with qualifying seasons (PA≥300 hitters, IP≥40 pitchers):

```
stat_signal = recency-weighted average of last 3 seasons (weights: 3×, 2×, 1×)
blend_weight = {1 season: 0.20, 2 seasons: 0.35, 3 seasons: 0.60}
composite = tool_score × (1 - blend_weight) + stat_signal × blend_weight
```

**Young player discount:** When player_age < peak_age and tools > stats:
```
age_factor = max(0.3, 1.0 - (peak_age - player_age) × 0.1)
blend_weight *= age_factor
```

**Stat conversion:**
- Hitters: OPS+ → `stat_to_2080()` (20 + stat_plus/200 × 60)
- Pitchers: Inverted FIP- → `pitcher_stat_to_2080()` (asymmetric slope)

---

## Step 7: FV Grade

**Function:** `calc_fv_v2(p)` in `fv_model.py`

Uses composite (as OVR) and true_ceiling (as Pot) to compute expected peak:

```
gap = max(0, pot - ovr)
closure = gap_closure_rate[age]     # empirical, by age and pitcher/hitter
bust_discount = age-scaled (0.30 young → 0.60 old)
peak = ovr + gap × closure × bust_discount
ceil_weight = max(0, min(0.5, (pot - 50) / 30))
fv = peak × (1 - ceil_weight) + pot × ceil_weight
```

**Penalties:** Accuracy L (-5), severe platoon splits (-5), RP cap (55)

**Rounding:** `round(fv / 5) × 5`

**Risk label** based on development confidence:
- Low: gap < 3 or confidence ≥ 0.40
- Medium: confidence ≥ 0.25
- High: confidence ≥ 0.15
- Extreme: confidence < 0.15

---

## Step 8: Surplus Value

Computed in `prospect_value.py`. Maps FV grade to peak WAR, projects years
of control, and converts to dollar value using league-calibrated $/WAR.

---

## Carrying Tool Bonus

**Status: DISABLED (Session 57)**

**Function:** `compute_carrying_tool_bonus(tools, position, config)`

Additive bonus for elite offensive tools (≥65) at positions where that tool
is scarce. Was applied to the offensive grade before recombination.

```
bonus = war_premium_factor × (tool_grade - 60) × scarcity_multiplier(grade)
```

Scarcity schedule: 1.0× at 65, 1.5× at 70, 2.0× at 75, 3.0× at 80.

Disabled for composite (Session 56) and ceiling (Session 57). Redundant with
the piecewise tool transform (1.3× above 60) and peak tool bonus (capped +10
in `compute_ceiling`). Was inflating `ceiling_score` by +5 to +31 without
affecting FV or surplus. `true_ceiling` (without bonus) predicts outcomes
better (r=0.912 vs 0.897). Function retained for potential future use.

---

## Known Limitations / Future Work

1. **Score compression** — composite maxes at ~76 on VMLB vs ~80 on eMLB.
   Leagues with tighter tool distributions (1-100 scale) compress more.

2. **RP WAR correlation** — composite predicts RP rate quality (ERA) well
   (r=-0.53 to -0.73) but not counting-stat WAR (driven by IP volume).
   Accepted as design choice: composite measures quality, not usage.

3. **Arsenal bonus** — adds no predictive value beyond stuff/movement/control
   (residual r≈0). Retained at ~10% weight for now; low-priority cleanup.
