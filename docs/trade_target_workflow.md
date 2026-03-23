# Trade Target Search Workflow

## Purpose

Repeatable process for identifying trade targets that address specific organizational needs.
Uses `prospect_query.py`, `free_agents.py`, `contract_value.py`, and `trade_calculator.py`.

---

## Step 1 — Define the Need

Before searching, articulate what you're looking for:
- **Position bucket** (SP, RP, C, SS, 2B, 3B, 1B, CF, COF)
- **Role** (everyday starter, platoon bat, bullpen arm, rotation depth)
- **Timeline** (need now vs. next season vs. 2-3 years out)
- **Contract preference** (controllable/cheap, expiring rental, doesn't matter)
- **Minimum quality** (Ovr floor, WAR floor)

Example: "We need a controllable SP with Ovr 60+ to slot into the rotation for the next 3 years."

---

## Step 2 — Search for MLB Targets

### Surplus-positive players on bad teams (buy low)

Check standings to identify sellers:
```bash
python3 scripts/standings.py
```

Teams 8+ games back with negative run differential are likely sellers. Cross-reference with their surplus players:

```bash
# Find high-surplus players on a specific team
python3 scripts/contract_value.py "<player name>"
```

### Upcoming free agents on contenders (rental targets)

Contenders sometimes trade expiring contracts they can't re-sign:
```bash
python3 scripts/free_agents.py --bucket SP
python3 scripts/free_agents.py --bucket SP --years 2   # Also check 2-year window
```

Look for players with high Ovr but low surplus (expensive contract expiring soon = team might sell).

### Direct DB query for specific criteria

```sql
-- Example: SP Ovr 60+, age ≤ 30, on teams with losing records
SELECT s.name, s.bucket, s.ovr, s.age, s.surplus, t.name as team
FROM player_surplus s
JOIN teams t ON t.team_id = s.parent_team_id
WHERE s.bucket = 'SP' AND s.ovr >= 60 AND s.age <= 30
  AND s.eval_date = (SELECT MAX(eval_date) FROM player_surplus)
ORDER BY s.surplus DESC;
```

---

## Step 3 — Search for Prospect Targets

When the need is future-oriented (2-3 year window), search prospect databases:

```bash
# Top SP prospects league-wide
python3 scripts/prospect_query.py top --bucket SP --fv-min 50 --age-max 23

# Specific org's farm system
python3 scripts/prospect_query.py team "Texas"

# Farm system rankings (find prospect-rich orgs to trade with)
python3 scripts/prospect_query.py systems
```

Prospect-rich teams that are contending now are natural trade partners — they have surplus prospects they'd trade for MLB help.

---

## Step 4 — Evaluate Contract Fit

For each candidate, run the contract breakdown:
```bash
python3 scripts/contract_value.py "<player name or id>"
```

Key questions:
- How many years of control remain?
- Is the salary manageable within our payroll?
- Does the surplus justify the acquisition cost?
- Is there a no-trade clause?

---

## Step 5 — Build and Evaluate Trade Packages

Use the trade calculator to test packages:
```bash
python3 scripts/trade_calculator.py --trade '{
  "angels_send": [
    {"player_id": 48517},
    {"player_id": 52392, "is_prospect": true}
  ],
  "angels_receive": [
    {"player_id": 99999}
  ]
}'
```

Guidelines for fair trades:
- **Net surplus should be close to zero** — both sides should gain roughly equal value
- **Prospect sensitivity range matters** — if the pessimistic scenario makes the trade a loss, it's risky
- **Controllable years are king** — a player with 4 years of control at $2M/yr is worth far more than the same player on a 1-year $15M deal
- **Don't trade top-5 farm prospects for rentals** — the surplus math rarely works

---

## Step 6 — Document the Proposal

For any trade worth proposing, write up:
1. What need it addresses
2. The surplus balance (from trade calculator)
3. What we give up (prospect capital, MLB depth)
4. Risk factors (injury, regression, contract)
5. Alternative options if this trade falls through

---

## Common Search Patterns

### "Find me a #2 starter"
```bash
python3 scripts/free_agents.py --bucket SP
python3 scripts/standings.py  # identify sellers
# Then for each candidate:
python3 scripts/contract_value.py "<name>"
```

### "Find me a controllable SS"
```bash
python3 scripts/prospect_query.py top --bucket SS --fv-min 50
# Or MLB players with years of control:
# Look for SS with high surplus (= underpaid relative to production)
```

### "What can we get for Player X?"
```bash
python3 scripts/contract_value.py <player_id>  # know their value
python3 scripts/prospect_query.py systems       # find prospect-rich partners
# Then build packages with trade_calculator.py
```

### "Should we buy or sell at the deadline?"
```bash
python3 scripts/standings.py                    # where do we stand?
python3 scripts/free_agents.py --angels         # who's expiring?
# If competing: buy rentals. If out of it: sell expiring contracts for prospects.
```
