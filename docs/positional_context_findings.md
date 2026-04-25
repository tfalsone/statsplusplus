# Positional Context & Carrying Tool Findings

*Generated: 2026-04-20 | Data: EMLB + VMLB combined (2033 season)*

---

## Summary

The evaluation engine's composite and component scores measure raw tool quality but lack positional context. A 51 offensive grade means "average hitter" regardless of whether the player is a SS or 1B — but a SS who hits at a 120 OPS+ level is one of the best players in baseball, while a 1B at the same level is merely good. This document captures the empirical findings that should inform a positional context enhancement.

---

## Finding 1: Offensive Tool Scarcity Varies Dramatically by Position

Elite hitting tools (65+ grade) are rare at premium defensive positions and common at bat-first positions:

| Position | % with 65+ Contact | % with 65+ Power | % with 65+ Eye |
|---|---|---|---|
| SS | 11% | 5% | 11% |
| C | 4% | 6% | 9% |
| CF | 8% | 5% | 5% |
| 2B | 3% | 3% | 10% |
| 3B | 6% | 11% | 10% |
| COF | 6% | 9% | 8% |
| 1B | 8% | 15% | 13% |

**Implication:** A 65+ contact tool at SS (11% scarcity) is far more impactful than a 65+ contact tool at 1B (8% scarcity, and 1B are expected to hit). The model should reward elite tools more at positions where they're rare.

---

## Finding 2: WAR Premium for Elite Offensive Tools is Position-Dependent

Players with 65+ grade in a tool produce significantly more WAR than the position average — but only for certain tool/position combinations:

### High-premium carrying tools (65+ grade WAR premium > +1.0):

| Position | Tool | Scarcity | WAR Premium | Assessment |
|---|---|---|---|---|
| SS | Power | 5% | **+1.89** | Elite carry tool |
| SS | Contact | 11% | **+1.56** | Elite carry tool |
| C | Power | 6% | **+2.16** | Elite carry tool |
| C | Contact | 4% | **+1.97** | Elite carry tool |
| C | Speed | 4% | **+2.10** | Elite carry tool (rare at C) |
| CF | Power | 5% | **+1.61** | Elite carry tool |
| CF | Contact | 8% | **+1.24** | Carry tool |
| SS | Eye | 11% | **+1.19** | Carry tool |

### Moderate-premium tools (+0.5 to +1.0):

| Position | Tool | Scarcity | WAR Premium |
|---|---|---|---|
| 2B | Power | 3% | +0.96 |
| 1B | Contact | 8% | +0.87 |
| COF | Contact | 6% | +0.71 |
| 3B | Contact | 6% | +0.69 |
| 3B | Eye | 10% | +0.68 |
| 3B | Gap | 6% | +0.67 |
| 1B | Eye | 13% | +0.55 |
| 3B | Power | 11% | +0.51 |

### Non-carrying tools (premium < +0.3 or negative):

| Position | Tool | Scarcity | WAR Premium | Note |
|---|---|---|---|---|
| SS | Speed | 29% | **-0.30** | Common, no value |
| CF | Speed | 28% | +0.27 | Common, minimal value |
| 2B | Speed | 16% | -0.63 | Negative premium |
| 3B | Speed | 12% | -0.78 | Negative premium |
| COF | Speed | 18% | -0.31 | Negative premium |
| COF | Power | 9% | +0.23 | Weak despite scarcity |
| 1B | Power | 15% | +0.44 | Moderate (common at 1B) |

**Key insight:** Speed is almost never a carrying tool. At every position, 65+ speed produces zero or negative WAR premium. The only exception is C (4% scarcity, +2.10 premium) — but this likely reflects that fast catchers tend to be athletic players who also hit well.

---

## Finding 3: Defensive Tools Are NOT Scarce at Premium Positions

Unlike hitting tools, elite defensive tools (65+) are common among MLB players at their position:

| Position | % with 65+ Range | % with 65+ Error | % with 65+ Arm |
|---|---|---|---|
| SS | 50% (IFR) | 51% (IFE) | 46% (IFA) |
| CF | 50% (OFR) | 42% (OFE) | 27% (OFA) |
| C | 37% (CFrm) | 40% (CBlk) | 28% (CArm) |
| 2B | 28% (IFR) | 34% (IFE) | 23% (IFA) |
| 3B | 20% (IFR) | 26% (IFE) | 43% (IFA) |

**Implication:** Players who make the majors at premium defensive positions are *selected* for defense. Elite defense at SS isn't scarce — it's the baseline. A carrying tool bonus for defense would reward the norm, not the exceptional.

---

## Finding 4: Raw Defensive WAR Premium is Near Zero

The WAR premium for 65+ defensive tools is minimal or negative at most positions:

| Position | Best Defensive Tool | 65+ WAR Premium |
|---|---|---|
| SS | IFR | +0.10 |
| C | CBlk | +0.29 |
| CF | OFA | +0.18 |
| 2B | IFR | -0.17 |
| 3B | IFR | +0.18 |
| COF | OFR | -0.43 |

**Why:** Elite defenders tend to be weaker hitters (selection effect). The raw correlation is confounded.

---

## Finding 5: Defense DOES Matter When Controlling for Offense

Among players with similar offensive grades (45-55), elite defense adds significant WAR:

| Position | Elite Def WAR | Avg Def WAR | Defense Premium |
|---|---|---|---|
| C (off 45-55) | 1.83 | 0.73 | **+1.10 WAR** |
| CF (off 45-55) | 2.28 | 1.00 | **+1.28 WAR** |

**Implication:** Defense doesn't need a carrying tool bonus (it's not scarce), but it does need proper credit in the FV/value calculation. A SS with average offense + elite defense is significantly more valuable than a SS with average offense + average defense. The current model gives defense only 5% weight at SS — this may be too low for the *value* calculation even though it's correct for the *composite* (which measures tool quality, not positional value).

---

## Finding 6: The Hudson Problem — Positional Context in Interpretation

Jeff Hudson (SS, age 23): Offensive Grade=51, Defensive Value=63, Composite=56, OVR=60.

The model flags him as a "landmine" (-8 divergence). But he produced 6.0 WAR with a consistent 115-142 OPS+ over 4 seasons. The model is wrong because:

1. A 51 offensive grade at SS is **above the SS median** (most SS have offensive grades of 40-50)
2. Combined with 63 defense at a premium position, this profile produces elite WAR
3. The composite of 56 doesn't capture that "average bat + great glove at SS = star player"

**The fix:** The divergence detection and FV calculation need positional context. A SS with a 51 offensive grade shouldn't be flagged as a landmine — that's a good SS bat. The comparison should be against position-specific expectations, not the league-wide average.

---

## Finding 7: The Read Problem — Ceiling Doesn't Capture Positional Upside

Joe Read (SS prospect, age 20): Potential Contact=80, Power=35, Eye=40. Offensive Ceiling=43. FV=45.

The model sees "43 offensive ceiling = below-average hitter" and assigns FV 45. But:

1. An 80 contact tool at SS is in the top 3% — it's a franchise-defining skill
2. A SS who can hit .300+ with elite defense is a perennial All-Star
3. The ceiling formula averages the 80 contact with the 35 power and 40 eye, producing 43
4. The game's POT=65 correctly values the combination of elite contact + premium position

**The fix:** The ceiling calculation needs a carrying tool bonus for elite tools at positions where they're scarce. An 80 contact at SS should boost the ceiling beyond what the weighted average produces.

---

## Proposed Model Enhancements

### 1. Carrying Tool Bonus (Offensive)

For each position's high-premium tools (from Finding 2), apply an additive bonus when the tool grades 65+. The bonus scales with the tool's grade (rarer = bigger bonus) and the position-specific WAR premium.

**Proposed formula:**
```
bonus = premium_factor × (tool_value - 60) × scarcity_multiplier
```

Where:
- `premium_factor` is derived from the WAR premium data (higher for SS/C, lower for COF/1B)
- `scarcity_multiplier` accelerates with grade (e.g., 1.0 at 65, 1.5 at 70, 2.0 at 75, 3.0 at 80)

**Which tools get the bonus by position:**

| Position | Carrying Tools | Premium Factor |
|---|---|---|
| SS | Contact, Power, Eye | High (1.5-1.9 WAR premium) |
| C | Contact, Power | High (2.0-2.2 WAR premium) |
| CF | Contact, Power | Moderate-High (1.2-1.6) |
| 2B | Power, Contact | Moderate (0.6-1.0) |
| 3B | Power, Contact, Eye, Gap | Moderate (0.5-0.7) |
| COF | Contact | Moderate (0.7) |
| 1B | Contact | Moderate (0.9) |

**Speed and defense do NOT get carrying tool bonuses.**

### 2. Positional Context in Divergence Detection

Instead of comparing composite vs OVR raw, compare the offensive grade against the **position-specific median**. A SS with a 51 offensive grade is above the SS median (~45) — that's not a landmine, it's a good SS.

**Proposed approach:**
- Compute position-specific offensive grade percentiles from the league data
- Flag divergence only when the player's offensive grade is below the position's 25th percentile (true weakness) or above the 75th percentile (hidden strength)
- Include positional context in the divergence report: "51 offensive grade = 70th percentile for SS"

### 3. Defense as Positional Access in FV

Defense's role in the FV calculation should be:
- **Positional access:** Can this player hold a premium position? (defensive_value >= 55 at SS/C/CF = yes)
- **Value multiplier:** When a player can hold a premium position AND has adequate offense, the FV should reflect the positional value premium
- **Not a carrying tool:** Defense doesn't get the scarcity bonus because it's not scarce at premium positions

### 4. Ceiling Enhancement for Carrying Tools

When computing the offensive ceiling, apply the carrying tool bonus to potential tools that qualify. Joe Read's potential Contact=80 at SS should produce a ceiling bonus that reflects the +1.56 WAR premium of elite contact at SS.

---

## Data Limitations

- Sample sizes are small at some positions (C: 93, CF: 74, 3B: 88). Findings at these positions should be treated as directional, not definitive.
- The analysis uses a single season (2033). Multi-year pooling would produce more stable estimates.
- WAR includes defensive value, so the "offensive tool → WAR" correlation partially captures defense through the positional adjustment. This is a feature, not a bug — it means the carrying tool premium already accounts for positional context.
- Speed's negative WAR premium may be confounded: fast players are often selected for premium defensive positions where they're expected to hit less, depressing their WAR relative to slower players at bat-first positions.
