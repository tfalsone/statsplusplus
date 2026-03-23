# OOTP Game Engine Reference
## Relevant to Player and Farm System Analysis

---

## Ratings Scale

- All individual ratings (batting, pitching, fielding) are on **1-100** in the raw data
- `Ovr` and `Pot` are on **20-80** (or displayed as stars; 5 stars = 80)
- Ratings above the scale maximum are possible (e.g. 120 on a 1-100 scale) — treat as the max

---

## Batting Ratings

| Field | What it measures | Game effect |
|---|---|---|
| `Cntct` | Contact / BABIP hybrid | Batting average, hits on balls in play |
| `Gap` | Gap power | Doubles and triples per hit in play |
| `Pow` | Home run power | Home runs per at bat |
| `Eye` | Eye / Discipline | Walks per at bat |
| `Ks` | Avoid K's | Strikeouts per at bat (higher = fewer K's) |
| `Speed` | Running speed | Base advancement, triples; correlated with defensive Range |

**Key notes:**
- `Gap` and `Pow` are independent — a player can have high gap power and low HR power
- `Eye` and `Ks` are independent — a player can walk a lot and still strike out a lot
- Speed does **not** directly affect stolen base attempts or success — that's `Steal`/`StlRt`
- Speed correlates with defensive Range; as Speed declines with age, Range likely declines too
- Lefty/righty splits exist (`Cntct_R`, `Cntct_L`, etc.) but overall ratings are the primary signal

---

## Pitching Ratings

| Field | What it measures | Game effect |
|---|---|---|
| `Stf` | Stuff | Strikeouts; calculated from pitch ratings + velocity; relievers get a bonus |
| `Mov` | Movement | Limits hard contact / home runs; based on GB% and pitcher BABIP |
| `Ctrl_R` / `Ctrl_L` | Control vs RHB / LHB | Walks per batter faced |
| `Vel` | Velocity (mph range string) | Factors into Stuff; important for fastball-dependent pitches |
| `Stm` | Stamina | How deep a pitcher can go; minimum 25 to start, most starters need 50+ |
| `GB` | Ground ball % | Higher = more ground outs and DPs; factors into Movement |

**Key notes:**
- `Stf` is a composite — it reflects the full arsenal quality including velocity. Relievers receive a stuff bonus because batters get fewer looks; this bonus is tied to the top two pitches.
- `Mov` is a composite of GB% and pitcher BABIP — it's about limiting hard contact, not pitch movement per se. This is what we label **Command** in reports.
- `Ctrl` is split by batter handedness (`Ctrl_R`, `Ctrl_L`) — average them for an overall control grade.
- Stamina minimum to start: **25** raw. Practical starter threshold: **50+**. Our RP flag uses `Stm < 40` as a conservative threshold.
- Arm slot affects L/R splits: lower arm angle = more pronounced platoon split.

### Individual Pitch Ratings
- Each pitch has a current and potential rating
- Higher rating = more likely to get hitters out with that pitch
- Velocity factors into pitch ratings, especially fastball-dependent pitches (fastball, cutter, sinker)
- Knuckleball is **not** velocity-dependent
- A pitcher typically needs **3+ solid pitches** to be an effective MLB starter
- Pitchers can learn new pitches over time, most likely in the minors or spring training; less likely as they age
- The game has a "Projected Role" indicator (Starter / Borderline Starter / Emergency Starter / Bullpen) — our viable pitch check approximates this

---

## OVR and POT

- `Ovr` = current overall rating **relative to other players at the same position/role in the league**
- `Pot` = potential overall rating, same basis
- **Position-specific:** A 60 Ovr shortstop is above-average among shortstops, not among all players. If the league is weak at SS, a 60 Ovr SS may not be as impressive as it looks.
- For pitchers, `Ovr` is calculated using current role; `Pot` may use projected future role — so a pitcher currently used as a reliever who projects as a starter may show Pot > Ovr even if his current stuff is good.
- These are scouting assessments, not absolute values — subject to scouting accuracy (`Acc`)

---

## Defensive Ratings

| Field | What it measures |
|---|---|
| `IFR`/`OFR` | Infield/Outfield Range — ability to reach batted balls |
| `IFE`/`OFE` | Infield/Outfield Error — inverse of error rate (higher = fewer errors) |
| `IFA`/`OFA` | Infield/Outfield Arm — arm strength and accuracy |
| `TDP` | Turn Double Play |
| `CArm` | Catcher arm — affects stolen base attempts and success |
| `CBlk` | Catcher blocking — prevents passed balls |
| `CFrm` | Catcher framing — gets called strikes on borderline pitches |
| `C`, `SS`, `2B`, etc. | Positional composite rating — overall defensive ability at that position |

**Key notes:**
- Positional composite ratings (`C`, `SS`, `CF`, etc.) increase toward their maximum as the player gains experience at the position — they are **not** purely skill-based
- A player can lose a positional rating if underlying skills (Range, Arm, etc.) fall below a minimum
- Defensive spectrum (easiest to hardest to learn): DH → 1B → LF → RF → 3B → CF → 2B → SS → C
- Position players can learn catcher but it takes a very long time

---

## Player Development

Key factors affecting development:

| Factor | Notes |
|---|---|
| Age | Younger players develop; older players decline. Not all players decline at the same rate. |
| Potential | High-potential players often (not always) develop faster |
| Playing time | Minor leaguers need playing time to develop; MLB/reserve players develop without it |
| Challenge | Players challenged at the right level develop faster; overmatched or unchallenged players may stagnate |
| Work Ethic (`WrkEthic`) | High WE = positive clubhouse effect, better development, less prone to slumps |
| Intelligence (`Int`) | High Int = positive clubhouse effect, better in-game decisions, development benefit |
| Injuries | Can slow or regress both current ratings and potential |
| Chance (TCR) | Random rating jumps (positive or negative) can occur at any time |
| Coaching | GM, manager, hitting/pitching coach ratings all affect development |

**Implications for prospect analysis:**
- A player who is "too comfortable" at their level may not be developing — challenge matters
- `WrkEthic` H/VH is a genuine development signal, not just a character note
- High `Int` is a secondary development positive worth noting
- Injuries in a player's history may have suppressed current ratings below true ability

---

## Personality Ratings (relevant fields)

| Field | Scale | Notes |
|---|---|---|
| `WrkEthic` | VL/L/N/H/VH | Development, clubhouse, slump resistance |
| `Int` | VL/L/N/H/VH | Development, in-game decisions, clubhouse |
| `Loy` | VL/L/N/H/VH | Extension likelihood |
| `Greed` | VL/L/N/H/VH | Lower = better for contract negotiations |
| `Lead` | VL/L/N/H/VH | Clubhouse effect on other players |

---

## Scouting Accuracy (`Acc`)

- Scouts are **less accurate on younger players**, especially high school amateurs
- `Acc` = L means the ratings shown may not reflect true ability — the uncertainty is symmetric in reality, but from an analysis standpoint it increases bust risk (we don't know if the player is better or worse than shown)
- `Acc` = VH/H: treat grades as reliable

---

## Stamina Thresholds (practical)

| Stm (raw) | Profile |
|---|---|
| < 25 | Cannot start at any level per game engine |
| 25–39 | Borderline; our analysis flags as RP |
| 40–49 | Can start at lower levels; borderline at MLB |
| 50+ | Viable starter |
| 70+ | Workhorse starter |
