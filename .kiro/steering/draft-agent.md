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

## Draft Value Sort

The `pick` command sorts by draft value:

```
draft_value = FV + (true_ceiling - 55) × 0.2 + ctl_penalty
```

- **FV** is the dominant factor (5-point FV gap = 5 points)
- **Ceiling bonus** rewards upside within the same FV tier (~2-3 points spread)
- **Control penalty** (-3) for SP with control ceiling < 45 (reliever risk)
- **No accuracy penalty** — Acc=L players compete on tools alone; scouting
  reports inform manual adjustments to the final list

This means the tool sorts purely on talent ceiling. The user applies judgment
about development probability (Acc rating) when curating the final submission.

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
| `latest_ratings` view | Full tool ratings (cur/pot), defense, speed, character |
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

3. **Risk Label** — Low/Medium/High/Extreme. Informational — does not
   affect sort but should be noted in analysis.

4. **Accuracy (Acc)** — Development probability. Not penalized in sort
   but flagged for user awareness:
   - VH = very high confidence
   - A = normal development
   - H = high accuracy
   - L = low accuracy — flag prominently, recommend scouting

5. **Positional Value** — C > SS > CF > 2B/3B > COF > 1B

6. **Organizational Need** — Tiebreaker only. Never reach for need.

### Red Flags (flag but don't auto-penalize)

- **Acc=L** — Flag with `Acc=L!` in output. User decides.
- **Extreme risk** — Flag with `EXTREME`. Very high bust probability.
- **SP with control < 45** — Flag with `ctl<45`. Penalized in sort (-3).
- **1B/DH-only profiles** below FV 60 — Limited positional value.
- **Age 23+** — Limited development runway.

### Green Flags

- **Acc=VH** — Elite development confidence
- **Premium position + elite defense** — High floor
- **Multiple 70+ potential tools** — Star upside
- **Acc=A + WE=H** — Strong character profile

---

## Queries

### Load draft pool with FV grades
```sql
SELECT pf.fv, pf.fv_str, pf.risk, pf.bucket, pf.prospect_surplus,
       p.name, p.age, p.player_id,
       r.composite_score, r.true_ceiling, r.offensive_grade,
       r.pot_cntct, r.pot_gap, r.pot_pow, r.pot_eye,
       r.cntct, r.gap, r.pow, r.eye, r.speed,
       r.pot_stf, r.pot_mov, r.pot_ctrl,
       r.stf, r.mov, r.ctrl,
       r.ofr, r.ifr, r.c_frm, r.acc
FROM prospect_fv pf
JOIN players p ON pf.player_id = p.player_id
JOIN latest_ratings r ON r.player_id = p.player_id
WHERE pf.player_id IN (<pool_ids>)
ORDER BY pf.fv DESC, pf.prospect_surplus DESC
```

### Org depth for need context
```python
sys.path.insert(0, 'web')
from team_queries import get_draft_org_depth
depth = get_draft_org_depth(my_team_id)
```

---

## Output Conventions

- All ratings are on the league's native scale (1-100 for eMLB).
- FV grades are on the 20-80 scouting scale in increments of 5.
- Surplus displayed as $M (divide raw value by 1e6).
- Never recommend drafting purely for need over talent.
- Flag Acc=L players explicitly — the user must know the risk.
- For Mode 3 output, write the file and report the path. Do not print 500 IDs.
