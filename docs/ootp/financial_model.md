# OOTP — Financial & Contract Model Reference
## Relevant to Contract Valuation and Trade Analysis

---

## Overview

The OOTP financial model governs player contracts, free agency, salary arbitration, and service time. It does not precisely match real-world MLB rules in all cases — use this document, not real-world baseball references, when reasoning about contract and transaction mechanics in the EMLB.

---

## Player Contracts

### Two contract types

| Type | Cost | Duration | Notes |
|---|---|---|---|
| Minor league | $0 | Indefinite | No salary cost. Player remains under team control until free agency, promotion, or trade. |
| Major league | Fixed per year | Fixed years | Guaranteed. Releasing a player requires immediate payment of all remaining salary. |

**Key points:**
- No split contracts — a player is either on a major league contract or a minor league contract, never both
- Major league contracts are fully guaranteed — there is no non-guaranteed money or buyout structure beyond what is explicitly in the contract
- Players who retire void the remaining portion of their contracts
- Contract expiration occurs the day after the last day of the playoffs

### Contract components

- **Salary:** Fixed dollar amount per year, set at signing. Can vary year-to-year within a contract (escalating or declining).
- **No-trade clause (NTC):** Player must consent to any trade. Makes the player effectively immovable unless they agree to waive.
- **Options:** Team options or player options on the final year. Team option = team decides whether to extend; player option = player decides.
- **Incentives:** Can be included but are not a primary analysis factor.

### Contracts at league creation

Initial contracts are generated based on player quality relative to positional average, service time (randomly assigned), age, and randomness. Most starting contracts are 1–2 years. Arbitration-eligible players receive less than market value; league-minimum players receive the minimum.

---

## Service Time

Service time drives free agency and arbitration eligibility. Three types are tracked:

| Type | Accrues when... |
|---|---|
| Professional service time | Player is on any roster (MLB or minor league) or on the 15-day IL, from Opening Day through last day of regular season |
| Major league service time | Player is on an active MLB roster or on the 15-day IL |
| Time on secondary roster | Player is on a team's secondary (minor league) roster or on the 15-day IL |

**Standard year = 172 days** of service time.

### Service time thresholds (default OOTP settings)

| Threshold | Result |
|---|---|
| < 3 years MLB service | Contract auto-renewed at league minimum |
| 3–5 years MLB service | Eligible for salary arbitration |
| Top 17% of players with 2+ years service | "Super 2" — eligible for arbitration one year early |
| ≥ 6 years MLB service, contract expired | Free agent |
| Professional − Secondary ≥ 6 years | Minor league free agent (if not on secondary roster or under extension) |

**Implication for roster management:** Keeping a player in the minors delays their service time clock. A player who spends the first ~20 days of the season in AAA before being called up loses roughly one year of service time accumulation toward free agency — the same "Super 2" manipulation that exists in real baseball.

---

## Salary Arbitration

### Who is eligible

- Players with 3–5 years of MLB service time as of the day after the playoffs end
- "Super 2" players: top 17% of service time among players with 2+ years of service

### Process

1. **Arbitration Offer Period** opens the day after the final playoff game
2. Teams submit a one-year contract offer for each player they wish to take to arbitration
3. Teams can negotiate directly with arbitration-eligible players during this period — if a deal is reached, the player is no longer subject to arbitration
4. **Salary Arbitration Hearings** are typically held in November
5. Arbitrators rule on each case, choosing between the team's offer and the player's demand
6. **If a team fails to offer arbitration**, the player becomes a free agent — the team loses them and forfeits draft pick compensation rights

### Player morale impact

- Player morale drops slightly any time they go to arbitration
- Losing the arbitration case causes a further morale drop
- Settling before hearings avoids the morale penalty

### Practical implications

- Arbitration-eligible players are underpaid relative to market value — this is the source of surplus value for pre-arb and arb-year players
- A player in their first arb year typically earns 40–60% of market value; by their third arb year they approach 80–90%
- Teams should generally prefer to extend players before arbitration to lock in below-market rates and avoid annual salary uncertainty

---

## Free Agency

### Who is a free agent

- Any player with ≥ 6 years of MLB service time whose contract has expired
- Any player released from their contract
- Any player not currently under contract (undrafted amateurs, etc.)

### Draft pick compensation for lost free agents

If enabled, teams that lose free agents receive compensatory draft picks:

| Free agent type | Compensation |
|---|---|
| Type A | Signing team's first-round pick + sandwich pick after round 1 (or second-round pick if the first-round pick is in the top half) |
| Type B | Sandwich pick after round 2 only |
| No compensation | Nothing |

**Requirements:** Team must offer salary arbitration to the pending free agent before they file. Failure to offer arbitration forfeits all compensation rights.

---

## Minor League Free Agency

A minor league player becomes a free agent at the end of the season if:

```
Professional Service Time − Time on Secondary Roster ≥ 6 years
```

**Exceptions:** Players currently on the secondary roster or who have accepted a minor league contract extension are not eligible.

**Implication:** Players who spend significant time on the active minor league roster (not the secondary/40-man equivalent) accumulate professional service time faster and reach minor league free agency sooner. Managing which players are on the secondary roster vs. the active minor league roster affects how long the team retains control.

---

## Financial Model — Team Finances

### Revenue sources
Gate revenue, media revenue, merchandising, playoff revenue, revenue sharing (if applicable), owner cash infusion, cash from trades.

### Expense categories
Player salaries, staff salaries, cash given in trades, scouting, player development, draft expenditures, international amateur free agency, revenue sharing.

### Spending limits
Either owner-set budget or full revenue available, depending on league configuration. GMs can be fired for financial irresponsibility even without a hard budget cap.

### Draft budget
Operates independently from the main budget. Unused draft budget does not carry over ("use it or lose it"). Exceeding the draft budget impacts overall finances by the excess amount.

---

## Implications for Contract Valuation

### Surplus value by contract status

| Status | Typical salary vs. market | Surplus |
|---|---|---|
| Pre-arb (0–2 yrs service) | League minimum (~$825K) | Very high — player earning a fraction of market value |
| Arb year 1 (3 yrs service) | ~40–60% of market | High |
| Arb year 2 (4 yrs service) | ~60–75% of market | Moderate |
| Arb year 3 (5 yrs service) | ~75–90% of market | Low-to-moderate |
| Free agent contract | Market rate | Near zero (or negative if overpaid) |

### NTC contracts

A no-trade clause makes a player effectively immovable without their consent. When valuing a player with an NTC for trade purposes:
- The player must agree to waive — factor in their likely willingness based on situation, morale, and contract remaining
- Even if willing, the NTC gives the player leverage to demand favorable destination or additional compensation
- NTC contracts on declining players are the highest-risk long-term commitments — the team cannot shed the contract without the player's cooperation

### Releasing a player

Releasing a player requires immediate payment of all remaining guaranteed salary. There is no "eating" salary over time — the full obligation is due immediately. This makes releasing expensive veterans a significant one-time financial hit rather than a gradual payroll reduction.

### Extensions

Signing a player to an extension before they reach free agency is the primary lever for locking in below-market rates. The earlier the extension, the greater the potential surplus — but also the greater the uncertainty about the player's future value. Extensions signed during pre-arb years carry the most upside and the most risk.
