# OOTP — Aging & Development Reference
## Relevant to Player Valuation and Contract Analysis

---

## Development Factors

The following factors affect how a player's current and potential ratings change over the course of a season or career. Some are controllable; others are not.

| Factor | Impact |
|---|---|
| Coaching / management | GM, manager, bench coach, hitting coach, and pitching coach ratings all affect development. Higher coaching ratings = faster development. |
| Playing time | Minor league players who get little playing time may develop more slowly. MLB players and reserve roster players develop normally without playing time. |
| Potential / individual qualities | High-potential players often (not always) develop more quickly. Some players simply develop faster or slower than their potential suggests — variance is real. |
| Age | Younger players mature; older players decline. Rate and timing vary by individual — some players remain productive into their 40s, others decline earlier than expected. |
| Challenge | Players challenged at the right level develop faster. A player dominating AA without being promoted may stagnate. An overmatched rookie in the MLB lineup may regress. |
| Injuries | Injuries slow development and can cause ratings to regress. More severe injuries carry higher risk of permanent ratings loss, including potential ratings. |
| Spring training | Players can improve during spring training outside the regular season. |
| Chance (TCR) | Random rating jumps — positive or negative — can occur at any time. A player can suddenly break out or unexpectedly decline regardless of other factors. Effect is most pronounced among the most skilled players. |
| Player development modifiers | League-level settings that scale the speed of development and aging globally. See league settings below. |

---

## EMLB League Development & Aging Settings

| Setting | Value | Meaning |
|---|---|---|
| Batter Development Speed | 1.030 | Hitters develop slightly faster than the OOTP baseline |
| Batter Aging Speed | 0.930 | Hitters age slightly slower than the OOTP baseline |
| Pitcher Development Speed | 1.030 | Pitchers develop slightly faster than the OOTP baseline |
| Pitcher Aging Speed | 0.930 | Pitchers age slightly slower than the OOTP baseline |
| Talent Change Randomness | 100 | Average randomness — standard distribution of breakouts and busts |

### Modifier definitions

- **Development Speed:** Higher = faster skill development. 1.030 means players reach their potential slightly ahead of the default pace.
- **Aging Speed:** Lower = slower skill decline. 0.930 means players retain their skills longer than the default model. A modifier of 0.500 would roughly halve the rate of decline.
- **Talent Change Randomness:** Controls the magnitude of random rating changes. At 100 (average), breakouts and busts occur at a normal rate. Above 100 = larger swings; below 100 = more stable careers.

---

## Implications for Player Valuation

### Aging curves are shallower than real-world baseball

The 0.930 aging modifier means players in the EMLB hold their value longer than real-world MLB comps would suggest. When projecting WAR decline for contract valuation:

- **Do not use real-world aging curves directly.** A typical real-world pitcher declines ~0.3–0.5 WAR/year from age 30. In the EMLB, that decline is approximately 7% slower — closer to 0.28–0.47 WAR/year.
- **Peak age is effectively extended by ~1 year** relative to the OOTP baseline for both hitters and pitchers.
- **Long-term contracts carry less aging risk** than equivalent real-world deals. A 5-year deal for a 30-year-old is less risky here than in real baseball.

### Development is slightly accelerated

The 1.030 development modifier means prospects reach their potential a bit faster than the default model. Implications:

- **Development timelines for prospects should be compressed slightly** relative to default OOTP expectations.
- A prospect projected to reach the majors in 3 years under default settings may arrive in 2.5–3 years in the EMLB.
- This modestly increases the surplus value of near-MLB prospects, since the time-to-value is shorter.

### Randomness is average

At TCR 100, the distribution of breakouts and busts is standard. No adjustment needed relative to default OOTP expectations. High-potential players still carry meaningful bust risk; low-potential players can still surprise.

---

## Practical Aging Curve Estimates (EMLB-adjusted)

These are the calibrated aging curves used in contract and prospect valuation.
Source: `scripts/constants.py` (`AGING_HITTER`, `AGING_PITCHER`).
Calibrated 2033-04-25 from Marcel/BP/FanGraphs consensus aging research,
adjusted for the EMLB's 0.930 aging modifier.

### Position players — WAR multiplier vs. peak

| Age | Multiplier | Decline rate |
|---|---|---|
| 27–28 | 1.00 | Peak |
| 29 | 0.97 | -3%/yr |
| 30 | 0.94 | -3%/yr |
| 31 | 0.91 | -3%/yr |
| 32 | 0.85 | -6%/yr |
| 33 | 0.79 | -6%/yr |
| 34 | 0.76 | -3% (plateau) |
| 35 | 0.67 | -9%/yr |
| 36 | 0.58 | -9%/yr |
| 37 | 0.49 | -9%/yr |
| 38 | 0.37 | -12%/yr |
| 39 | 0.26 | -11% |
| 40 | 0.16 | -10% |
| 42 | 0.08 | terminal |

### Pitchers — WAR multiplier vs. peak

| Age | Multiplier | Decline rate |
|---|---|---|
| 27–28 | 1.00 | Peak |
| 29 | 0.97 | -3%/yr |
| 30 | 0.94 | -3%/yr |
| 31 | 0.91 | -3%/yr |
| 32 | 0.84 | -7%/yr |
| 33 | 0.77 | -7%/yr |
| 34 | 0.65 | -12% (steeper — injury/velocity risk) |
| 35 | 0.55 | -10%/yr |
| 36 | 0.45 | -10%/yr |
| 37 | 0.35 | -10%/yr |
| 38 | 0.25 | -10%/yr |
| 39 | 0.16 | -9% |
| 40 | 0.09 | terminal |

Pitchers decline faster than hitters from age 32+, reflecting injury and velocity risk.
Intermediate ages are linearly interpolated by `aging_mult()` in `player_utils.py`.

---

## Notes

- These curves are calibrated from consensus aging research, adjusted for the EMLB modifier. Individual players deviate significantly — high Work Ethic, high Intelligence, and favorable TCR rolls can extend careers; injuries and low TCR rolls can accelerate decline.
- As evaluation cycles accumulate, empirical EMLB-specific curves may replace these estimates.
- Intermediate ages are linearly interpolated by `aging_mult()` in `scripts/player_utils.py`.
