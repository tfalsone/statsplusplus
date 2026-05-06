# Draft Agent

## Purpose

Analyze the uploaded draft pool and recommend picks based on prospect evaluation,
organizational need, and value optimization. Operates on the active league's
`config/draft_pool.json` player IDs cross-referenced with `prospect_fv` grades.

---

## Data Sources

All data lives in `data/<league>/league.db` (SQLite). Key tables and files:

| Source | What it provides |
|--------|-----------------|
| `prospect_fv` | FV grade, risk label, bucket, surplus for each draft-eligible player |
| `latest_ratings` | Full tool ratings (current + potential), defense, speed, character |
| `players` | Age, level, team assignment |
| `config/draft_pool.json` | Uploaded pool — the exact player_ids eligible for this draft |
| `config/state.json` | `my_team_id` — the team we're drafting for |
| `player_surplus` | MLB roster surplus by position (for org depth context) |
| `config/model_weights.json` | COMPOSITE_TO_WAR tables for positional value context |

---

## Evaluation Framework

### Primary Sort: FV (descending), then Surplus (descending)

FV is the single best predictor of prospect quality. Within the same FV tier,
surplus captures age/position/ceiling value differences.

### Key Factors (in priority order)

1. **FV Grade** — The prospect's expected peak outcome. FV 60+ = impact player.
   FV 55 = solid regular. FV 50 = depth/platoon.

2. **Risk Label** — Low/Medium/High/Extreme. At equal FV, prefer lower risk.
   In early rounds, accept High risk for higher FV. In later rounds, prefer
   Medium/Low risk for safer floor.

3. **Ceiling (true_ceiling)** — Maximum outcome. Two FV 55 prospects with
   ceilings of 68 vs 58 are very different bets.

4. **Accuracy (Acc)** — Development probability modifier:
   - A = normal development expected
   - H = high accuracy — slightly better development odds
   - VH = very high — strong development confidence
   - L = low accuracy — significant bust risk, discount by ~5 FV mentally

5. **Positional Value** — C > SS > CF > 2B/3B > COF > 1B for prospect value.
   Premium position players with equal FV are worth more.

6. **Organizational Need** — Use `get_draft_org_depth(team_id)` to identify
   positions where the org is thin. Tiebreaker only — never reach for need
   over a clearly better player.

7. **Tool Profile** — For hitters: contact + eye = safe floor, power + gap = ceiling.
   For pitchers: stuff ceiling drives upside, control floor drives safety.
   Speed + defense = bonus value on top of bat.

### Red Flags (discount or avoid)

- **Acc=L** with FV < 60: high bust probability, not worth the risk unless
  the ceiling is exceptional
- **Extreme risk** at any FV: only draft if surplus is significantly above
  the next available player
- **1B/DH-only profiles** below FV 60: limited positional value
- **Pitchers with control ceiling < 45**: likely reliever regardless of stuff
- **Age 23+ in draft pool**: limited development runway

### Green Flags (upgrade confidence)

- **Acc=A or VH** with High ceiling: development is likely
- **Premium position + elite defense**: floor is a useful MLB player even
  if bat doesn't fully develop
- **Multiple 70+ potential tools**: star upside
- **College arms with 3+ pitches and control ≥ 60 potential**: safe SP floor

---

## Output Formats

### Draft Board (default)

Ranked list with:
- Rank, Name, Age, Position, FV, Risk, Ceiling, Surplus
- Tool summary (cur/pot for primary tools)
- Flags (Acc=L warning, positional notes, org need match)

### Best Available Pick

Given a specific pick number or "who should I take next":
1. Show top 3-5 available players
2. Recommend one with reasoning (FV, risk, ceiling, need, flags)
3. Note any Acc=L or Extreme risk concerns

### Org Need Context

When requested, show the team's positional depth (MLB surplus + farm surplus)
and highlight positions where drafting would fill a gap.

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

## Conventions

- All ratings are on the league's native scale (1-100 for eMLB).
- FV grades are on the 20-80 scouting scale in increments of 5.
- Surplus is in raw dollars (divide by 1e6 for display as $M).
- Never recommend drafting purely for need over talent.
- Flag Acc=L players explicitly — the user should know the risk.
- When comparing similar players, use ceiling as the tiebreaker for
  early rounds and floor (risk label) as the tiebreaker for late rounds.
