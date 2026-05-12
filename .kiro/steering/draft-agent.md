# Draft Agent

## Purpose

Analyze the uploaded draft pool and provide draft recommendations across four
operational modes. Operates on the active league's `config/draft_pool.json`
player IDs cross-referenced with `prospect_fv` grades.

**CLI tool:** `python3 scripts/draft_board.py`

---

## Operational Modes

### Mode 1: Best Available (Mid-Draft)

**Trigger:** "Who should I pick?" / "Best available" / "It's my turn"

**CLI:** `python3 scripts/draft_board.py available [--top N]`

The draft is in progress. Other players have been taken. Use the StatsPlus API
to identify which players are already selected, then recommend from remaining.

### Mode 2: Pre-Draft Ranked List (Fixed Pick Position)

**Trigger:** "I'm picking Nth" / "Generate my top N list" / "Pre-draft submission"

**CLI:** `python3 scripts/draft_board.py pick N`

Generates exactly N players ranked by draft value. Provides TWO outputs:
1. **Scouting summary** — full board with tools, flags, and analysis
2. **Commissioner list** — clean numbered list with game position and name

**Commissioner list format:**
```
 1. CF   Roman Anthony
 2. SP   Mauricio Sampayo
 3. 2B   Gabriel Brown
...
```

**Position labels use the game's listed position** (from `players.pos/role` field),
NOT the evaluation bucket. Game position map:
`{1:'P', 2:'C', 3:'1B', 4:'2B', 5:'3B', 6:'SS', 7:'LF', 8:'CF', 9:'RF', 10:'DH'}`

For pitchers, role distinguishes SP vs RP: role 11/12 = SP, role 13 = RP.

### Mode 3: Auto-Draft Upload List (StatsPlus Format)

**Trigger:** "Generate auto-draft list" / "Upload list for StatsPlus"

**CLI:** `python3 scripts/draft_board.py upload [--top N]`

Writes up to 500 player IDs ranked by draft value to `data/<league>/tmp/draft_upload.txt`.
One ID per line, no header. Ready for StatsPlus upload.

### Mode 4: Head-to-Head Comparison

**Trigger:** "Compare X vs Y" / "I'm torn between..." / "Should I take A or B?"

**CLI:** `python3 scripts/draft_board.py compare "Name1" "Name2" ["Name3"]`

Side-by-side comparison of 2-3 prospects showing FV, ceiling, composite, surplus,
age, position, accuracy, and full tool breakdown.

---

## Draft Value Formula

```
draft_value = FV
            + (true_ceiling - 55) × 0.2
            + ctl_penalty
            + contact_penalty
            + arsenal_adjustment
            + risk_penalty
            + acc_penalty
            + rp_discount
            + personality_adjustment
            + needs_bonus
```

### Component Details

| Component | Value | Condition |
|-----------|-------|-----------|
| **FV** | 45-65 | Dominant factor. 5-point gap = 5 points. |
| **Ceiling bonus** | ~0-3 pts | `(true_ceiling - 55) × 0.2`. Rewards upside within tier. |
| **RP discount** | -5 | `bucket == "RP"` |
| **Acc penalty** | -2 / -4 | Acc=L / Acc=VL |
| **Risk penalty** | -3 / -1 | Extreme / High risk |
| **Control penalty** | -3 | SP with `pot_ctrl < 45` (reliever risk) |
| **Contact penalty** | -2 | Hitter with `pot_cntct < 50`, `pot_pow >= 80`, `pot_eye < 70` |
| **Arsenal adjustment** | -2 to +1 | See Arsenal Quality section below |
| **Personality** | -0.9 to +0.9 | WE: ±0.5, INT: ±0.25, Lead: ±0.15 |
| **Needs bonus** | +1/+2 | Org need at position, Rd3+ only |

---

## Two-List Merge (List Building)

The `pick` and `upload` commands use a two-list merge to maximize total draft value:

**List A (Our Evaluation):** Sorted by `draft_value` + position-scaled surplus weight.

**Surplus weight:** `w(pos) = 0.02 + 0.06 / √pos`. Heavier early in the draft
(favoring youth, positional scarcity, years of control), fading later where
talent alone matters. At pos 1: +2.4pts per $30M surplus. At pos 100: +0.8pts.
Never crosses FV tier boundaries.

**List B (OOTP Evaluation):** Sorted by POT rank (what other managers see).

**Merge logic:** At each pick slot, take the best player from List A whose
List B rank is within the survival threshold. If a player is far enough down
List B that they'll survive to a later pick, defer them.

**Survival threshold** — `30 + 6 × √pos`:
- Pick 1: ~36 picks
- Pick 34 (end of Rd1): ~65 picks
- Pick 100 (Rd3): ~90 picks
- Pick 170 (Rd5): ~108 picks

Alternative fixed breakpoints available via `_threshold_fixed([(2, 40), (4, 50), (None, 75)])`.

---

## Arsenal Quality (SP only)

Evaluates pitcher arsenal depth and development relative to age.

**Bonus (elite depth):**
- 4+ pitches with potential ≥ 60: +0.5
- 4+ pitches currently ≥ 35 at age 21+ (proven depth): +0.5

**Penalty (thin arsenal, age-adjusted):**
- SP at/above norm age (21 for draft pool) with 3+ potential pitches (≥45)
  but fewer than 3 currently developed (≥35):
  - At norm age: -1
  - 1 year over: -1.5
  - 2+ years over: -2

**Young pitchers (< 21 for draft pool) are never penalized** — rawness is expected.
They still receive the elite depth bonus if they have 4+ plus pitches.

Flag: `thin` displayed for penalized pitchers.

---

## Personality Adjustments

| Trait | H | L | Rationale |
|-------|---|---|-----------|
| Work Ethic | +0.50 | -0.50 | Development speed, slump resistance |
| Intelligence | +0.25 | -0.25 | Development benefit, in-game decisions |
| Leadership | +0.15 | -0.15 | Clubhouse effect on teammates |

Max combined swing: ±0.90. Tiebreaker-level influence.

---

## Draft Simulation

**CLI:** `python3 scripts/draft_board.py sim PICK [--rounds N] [--seed S]`

Simulates the draft with:
- **Other teams:** Pick from a candidate window that scales with draft position
  (`8 + pick × 0.15` players). Weighted by `1/(rank)^exp` where
  exponent `max(1.0, 2.8 - pick × 0.018)` — early picks are ~81% predictable,
  late rounds approach random across a wide pool.
- **Our picks:** Top remaining player from the pre-built pick list
  (same algorithm as `pick` command).

---

## Scouting Priority Framework

When the user has time before the draft, identify high-leverage scouting targets:

**Acc=L players with elite ceilings** — These are the biggest swing players.
A single positive scouting signal moves them 10+ spots. Prioritize by:
1. FV 60+ Acc=L (e.g., 5-tool CF with development questions)
2. FV 55 Acc=L with ceiling ≥ 65 (star upside if they develop)
3. FV 50 Acc=L with ceiling ≥ 62 or offensive ceiling ≥ 70 (hidden gems)

**SP with borderline control** — Pitchers with control ceiling 43-55 where
the SP vs RP outcome is uncertain. Scouting can clarify command trajectory.

**Do NOT scout:** Acc=A/VH players develop as expected. No information gain.

---

## Data Sources

| Source | What it provides |
|--------|-----------------|
| `prospect_fv` table | FV grade, risk label, bucket, surplus |
| `latest_ratings` view | Full tool ratings (cur/pot), defense, speed, personality, pitches |
| `players` table | Age, level, team assignment, game position |
| `config/draft_pool.json` | Uploaded pool — exact player_ids eligible |
| `config/state.json` | `my_team_id` — the team we're drafting for |
| `player_surplus` table | MLB roster surplus by position (org depth) |
| `get_draft_org_depth(team_id)` | Per-position surplus totals (web/team_queries.py) |

---

## Evaluation Framework

### Key Factors (in priority order for draft)

1. **FV Grade** — Expected peak outcome. FV 60+ = impact player.
   FV 55 = solid regular. FV 50 = depth/platoon.

2. **Ceiling (true_ceiling)** — Maximum outcome. The primary tiebreaker
   within FV tiers. In early rounds, ceiling > floor.

3. **Surplus** — Total economic value over control period. Captures age,
   positional scarcity, and development timeline. Position-scaled weight
   in list building (heavier early, fades later).

4. **Arsenal Quality (SP)** — Depth and development of pitch repertoire.
   Elite arsenals (4+ plus pitches) get a bonus. Thin arsenals (underdeveloped
   3rd pitch at age 21+) get penalized.

5. **Personality** — WE/INT/Lead. Development probability modifiers.

6. **Risk/Accuracy** — Penalized in sort. Extreme -3, High -1, Acc=L -2.

7. **Positional Value** — C > SS > CF > 2B/3B > COF > 1B (via surplus).

8. **Organizational Need** — Tiebreaker only (Rd3+). Never reach for need.

### Red Flags (flagged in output)

- **Acc=L** — `Acc=L!`. Low scouting confidence.
- **Extreme risk** — `EXTREME`. Very high bust probability.
- **SP with control < 45** — `ctl<45`. Penalized -3.
- **Thin arsenal** — `thin`. SP with underdeveloped pitches for age.
- **1B/DH-only profiles** below FV 60 — Limited positional value.
- **WE=L + INT=L** — Development red flag (-0.75 combined).

### Green Flags

- **Acc=VH** — Elite development confidence
- **WE=H** — Strong development profile (+0.5)
- **4+ plus pitches** — Elite arsenal depth (+0.5)
- **Premium position + elite defense** — High floor
- **Multiple 70+ potential tools** — Star upside
- **Age ≤ 18 with high ceiling** — Maximum development runway + surplus

---

## Output Conventions

- All ratings are on the league's native scale (1-100 for eMLB).
- FV grades are on the 20-80 scouting scale in increments of 5.
- Surplus displayed as $M (divide raw value by 1e6).
- Never recommend drafting purely for need over talent.
- Flag Acc=L players explicitly — the user must know the risk.
- For Mode 3 output, write the file and report the path. Do not print 500 IDs.
