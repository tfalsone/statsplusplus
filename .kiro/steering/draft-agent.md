# Draft Agent

## Purpose

Analyze the uploaded draft pool and provide draft recommendations across four
operational modes. Operates on the active league's `config/draft_pool.json`
player IDs cross-referenced with `prospect_fv` grades.

---

## Operational Modes

### Mode 1: Best Available (Mid-Draft)

**Trigger:** "Who should I pick?" / "Best available" / "It's my turn"

The draft is in progress. Other players have been taken. Use the StatsPlus API
(`/api/draft-picks`) to identify which players are already selected, then
recommend from the remaining pool.

**Process:**
1. Fetch current picks via API to identify taken player_ids
2. Filter draft pool to exclude taken players
3. Present top 3-5 remaining by FV/surplus with full analysis
4. Recommend one with reasoning

**Key query:**
```python
# Get taken player IDs from API
from statsplus import client
picks = client.get_draft()
taken_pids = {d["ID"] for d in picks if d.get("ID")}

# Filter pool
available = [pid for pid in pool_pids if pid not in taken_pids]
```

### Mode 2: Pre-Draft Ranked List (Fixed Pick Position)

**Trigger:** "I'm picking Nth" / "Generate my top N list" / "Pre-draft submission"

The user must submit a ranked list of N players before the draft starts. The list
represents their preference order — if all players above their pick are taken,
the commissioner selects the highest remaining player on their list.

**Process:**
1. Load full draft pool with FV grades
2. Rank by FV (desc), then surplus (desc) as primary sort
3. Apply tiebreakers: risk, ceiling, positional value, Acc
4. Generate exactly N players, ranked
5. Provide TWO outputs:
   a. **Scouting summary** — full analysis with tools, flags, and rationale
   b. **Commissioner list** — clean numbered list with game position and name only

**Commissioner list format:**
```
 1. CF   Roman Anthony
 2. SP   Mauricio Sampayo
 3. 2B   Gabriel Brown
...
```

**Position labels use the game's listed position** (from `players.pos` field), NOT
the evaluation bucket. This avoids confusion when the commissioner cross-references
the list against the game.

Game position map: `{1:'P', 2:'C', 3:'1B', 4:'2B', 5:'3B', 6:'SS', 7:'LF', 8:'CF', 9:'RF', 10:'DH'}`

For pitchers, use the role to distinguish SP vs RP:
- role in (11, 12) = SP
- role in (13) = RP/CL

**Important:** The list must be LONGER than the pick position to account for
uncertainty about who others will take. If picking 30th, the list should be
exactly 30 players — the user's top 30 in preference order.

### Mode 3: Auto-Draft Upload List (StatsPlus Format)

**Trigger:** "Generate auto-draft list" / "Upload list for StatsPlus"

Generate a ranked list of up to 500 player IDs for StatsPlus auto-draft upload.
StatsPlus will auto-select the highest player on this list when it's the team's
turn. If no list players remain, it falls back to best available by OSA potential.

**Process:**
1. Load full draft pool with FV grades
2. Rank all 500+ players by FV (desc), surplus (desc)
3. Apply org need as a secondary factor (boost players at thin positions)
4. Output as plain text file: one player ID per line, no header

**Output format (for StatsPlus upload):**
```
36166
56227
46411
53051
...
```

**File:** Write to `data/<league>/tmp/draft_upload.txt`

### Mode 4: Head-to-Head Comparison

**Trigger:** "Compare X vs Y" / "I'm torn between..." / "Should I take A or B?"

Deep analysis comparing 2-3 specific prospects to determine the best pick.

**Process:**
1. Pull full ratings for each player
2. Compare across all evaluation dimensions:
   - FV grade and surplus value
   - Ceiling (true_ceiling) and floor (composite_score)
   - Tool-by-tool comparison (potential AND current)
   - Risk profile (risk label + Acc + age)
   - Positional value and defensive projection
   - Org need fit
3. Identify the key differentiator (what makes one better than the other)
4. Make a clear recommendation with reasoning

**Analysis template:**
```
Player A vs Player B

           A              B
FV:        60 Medium      60 High
Ceiling:   68             64
Floor:     44             38
Age:       21             18
Pos:       CF             COF
Acc:       A              H

Tools (potential):
  Contact: 78             62
  Gap:     96             100
  Power:   61             82
  Eye:     92             97
  Speed:   51             80

Verdict: [recommendation with reasoning]
```

---

## Data Sources

| Source | What it provides |
|--------|-----------------|
| `prospect_fv` table | FV grade, risk label, bucket, surplus |
| `latest_ratings` view | Full tool ratings (cur/pot), defense, speed, character |
| `players` table | Age, level, team assignment |
| `config/draft_pool.json` | Uploaded pool — exact player_ids eligible |
| `config/state.json` | `my_team_id` — the team we're drafting for |
| `player_surplus` table | MLB roster surplus by position (org depth) |
| `get_draft_org_depth(team_id)` | Per-position surplus totals (web/team_queries.py) |

---

## Evaluation Framework

### Primary Sort: FV (descending), then Surplus (descending)

FV is the single best predictor of prospect quality. Within the same FV tier,
surplus captures age/position/ceiling value differences.

### Key Factors (in priority order)

1. **FV Grade** — Expected peak outcome. FV 60+ = impact player.
   FV 55 = solid regular. FV 50 = depth/platoon.

2. **Risk Label** — Low/Medium/High/Extreme. At equal FV, prefer lower risk.
   In early rounds, accept High risk for higher FV. In later rounds, prefer
   Medium/Low for safer floor.

3. **Ceiling (true_ceiling)** — Maximum outcome. Two FV 55 prospects with
   ceilings of 68 vs 58 are very different bets.

4. **Accuracy (Acc)** — Development probability modifier:
   - VH = very high — strong development confidence
   - A = normal development expected
   - H = high accuracy — slightly better development odds
   - L = low accuracy — significant bust risk, discount by ~5 FV mentally

5. **Positional Value** — C > SS > CF > 2B/3B > COF > 1B for prospect value.
   Premium position players with equal FV are worth more.

6. **Organizational Need** — Tiebreaker only. Never reach for need over talent.

7. **Tool Profile** — Contact + eye = safe floor. Power + gap = ceiling.
   Stuff ceiling drives pitcher upside. Control floor drives pitcher safety.

### Red Flags (discount or avoid)

- **Acc=L** with FV < 60: high bust probability, not worth the risk
- **Extreme risk** at any FV: only draft if surplus is far above next available
- **1B/DH-only profiles** below FV 60: limited positional value
- **Pitchers with control ceiling < 45**: likely reliever regardless of stuff
- **Age 23+ in draft pool**: limited development runway

### Green Flags (upgrade confidence)

- **Acc=A or VH** with high ceiling: development is likely
- **Premium position + elite defense**: floor is useful MLB player
- **Multiple 70+ potential tools**: star upside
- **College arms with 3+ pitches and control ≥ 60 potential**: safe SP floor

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

### Get taken players (mid-draft)
```python
from statsplus import client
picks = client.get_draft()
taken_pids = {d["ID"] for d in picks if d.get("ID")}
```

---

## Output Conventions

- All ratings are on the league's native scale (1-100 for eMLB).
- FV grades are on the 20-80 scouting scale in increments of 5.
- Surplus displayed as $M (divide raw value by 1e6).
- Never recommend drafting purely for need over talent.
- Flag Acc=L players explicitly — the user must know the risk.
- When comparing similar players, use ceiling as tiebreaker for early rounds
  and floor (risk label) as tiebreaker for late rounds.
- For Mode 3 output, write the file and report the path. Do not print 500 IDs.
