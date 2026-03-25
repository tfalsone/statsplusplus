# Trade Review Tab — Spec

## Overview

New **Trade** tab on the league page (`/league`), alongside the existing Overview and
Prospects tabs. An interactive trade builder where the user adds players to each side,
sees live surplus valuations, and gets a balance verdict. Reuses the existing
`contract_value` and `prospect_value` engines server-side — no new valuation logic.

---

## User Flow

1. User navigates to `/league` and clicks the **Trade** tab.
2. Tab shows two columns: **Side A** and **Side B** (team-neutral labels — no hardcoded team assumption).
3. Each side starts with an **org picker** dropdown (all 34 MLB orgs, sorted alphabetically).
   Side A defaults to the user's team (`my_team_id` from `state.json`) and auto-loads
   that org's roster on tab open. Side B starts empty (no org selected).
   Either side can be changed to any org at any time.
4. After selecting an org, the side shows a **player roster table** for that org:
   all MLB players + farm system prospects, with key value columns visible.
5. A **level filter** (All / MLB / AAA / AA / A / etc.) narrows the roster.
6. A **name search** input filters the roster table further (client-side text filter).
7. User scans the roster — Ovr, Pot, FV, surplus, age, position are all visible
   in the table so they can evaluate before committing.
8. User clicks a player row (or a "+" button) to add them to that side's trade package.
9. Selected players appear as **cards** above the roster table. Cards show the full
   valuation (surplus breakdown, contract flags, career outcome summary for prospects).
10. For MLB contract players, an optional salary retention slider (0-100%) appears on the card.
11. Each side has an optional **cash consideration** input (dollar amount). Cash is
    face value — adds directly to that side's total value.
12. A **Trade Balance** panel between the two sides updates live, showing net surplus
    for each side with pessimistic/base/optimistic scenarios.
13. User can remove players (× button on card), change org, or clear all.

---

## Page Layout

```
┌─────────────────────────────────────────────────────────────┐
│  Overview | Prospects | Trade                               │
├────────────────────────────┬────────────────────────────────┤
│  SIDE A                    │  SIDE B                        │
│  [▼ Select Organization]   │  [▼ Select Organization]       │
│                            │                                │
│  ┌──────────────────────┐  │  ┌──────────────────────────┐  │
│  │ Selected Players     │  │  │ Selected Players         │  │
│  │ ┌──────────────────┐ │  │  │ ┌──────────────────────┐ │  │
│  │ │ Player Card      │ │  │  │ │ Player Card          │ │  │
│  │ │ Name/Pos/Age/Ovr │ │  │  │ │ Name/Pos/Age/FV     │ │  │
│  │ │ Surplus: $X.XM   │ │  │  │ │ Surplus: $X.XM      │ │  │
│  │ │ [retention] [×]  │ │  │  │ │                 [×]  │ │  │
│  │ └──────────────────┘ │  │  │ └──────────────────────┘ │  │
│  │ Side A total: $XX.XM │  │  │ Side B total: $XX.XM     │  │
│  └──────────────────────┘  │  └──────────────────────────┘  │
│  Cash: [$______]           │  Cash: [$______]               │
│                            │                                │
│  [All|MLB|AAA|AA|A|...]    │  [All|MLB|AAA|AA|A|...]        │
│  [🔍 Filter by name...]    │  [🔍 Filter by name...]        │
│  ┌──────────────────────┐  │  ┌──────────────────────────┐  │
│  │ Org Roster Table     │  │  │ Org Roster Table         │  │
│  │ Pos Name  Age Ovr ..│  │  │ Pos Name  Age Ovr ..     │  │
│  │ SP  Smith  27  65   │  │  │ SS  Doe    21  --        │  │
│  │     Pot WAR  Surp   │  │  │     Pot FV  Lvl  Surplus │  │
│  │     68  3.2  +22M   │  │  │     62  55  AA   +61M    │  │
│  │ [+ click to add]    │  │  │ [+ click to add]         │  │
│  └──────────────────────┘  │  └──────────────────────────┘  │
├────────────────────────────┴────────────────────────────────┤
│  TRADE BALANCE                                              │
│  Side A net: +$X.XM  │  Side B net: -$X.XM                 │
│  Pessimistic / Base / Optimistic                            │
│  Verdict: [one-line summary]                                │
└─────────────────────────────────────────────────────────────┘
```

---

## API Endpoints

### `GET /api/player-search?q=<query>`

Autocomplete endpoint. Returns up to 15 matching players (MLB + prospects) across
all orgs. Used by the name filter within the roster table (client-side filtering
handles most cases, but this endpoint exists for the future global search bar).

Query: fuzzy name match against `players` table (LIKE `%query%`).

Response:
```json
[
  {
    "pid": 12345,
    "name": "John Smith",
    "team": "LAA",
    "age": 27,
    "pos": "SP",
    "level": "MLB",
    "ovr": 65,
    "fv": null
  }
]
```

### `GET /api/org-players/<int:team_id>`

Full org roster for the trade tab. Returns all MLB players + farm prospects for
the given org, with enough data to populate the roster table.

Response:
```json
[
  {
    "pid": 12345,
    "name": "John Smith",
    "pos": "SP",
    "age": 27,
    "level": "MLB",
    "ovr": 65,
    "pot": 68,
    "fv": null,
    "fv_str": null,
    "surplus": 22400000,
    "war": 3.2
  },
  {
    "pid": 67890,
    "name": "Jane Doe",
    "pos": "SS",
    "age": 21,
    "level": "AA",
    "ovr": 48,
    "pot": 62,
    "fv": 55,
    "fv_str": "55",
    "surplus": 61200000,
    "war": null
  }
]
```

Logic:
- MLB players: join `player_surplus` + `players` + `latest_ratings` + current year
  `batting_stats`/`pitching_stats` for WAR.
- Prospects: join `prospect_fv` + `players` + `latest_ratings`.
- Rookie-eligible players (in both tables) appear in the prospect section only,
  deduplicated by player_id.
- Combined, sorted: MLB first (by surplus desc), then prospects (by FV desc, surplus desc).
- Org membership: `team_id = ?` for MLB, `parent_team_id = ?` for farm.

### `POST /api/trade-value`

Compute valuation for a single player. Called when a player is added to a side
or when retention % changes.

Request:
```json
{
  "player_id": 12345,
  "retention_pct": 0.15
}
```

Response:
```json
{
  "player_id": 12345,
  "name": "John Smith",
  "type": "contract",
  "team": "LAA",
  "age": 27,
  "pos": "SP",
  "ovr": 65,
  "years_left": 3,
  "salary": "$12.5M",
  "flags": ["NTC"],
  "surplus": {
    "pessimistic": 15200000,
    "base": 22400000,
    "optimistic": 29600000
  },
  "breakdown": [
    {"year": 2033, "age": 27, "war": 3.2, "market": 27600000, "salary": 12500000, "surplus": 15100000},
    ...
  ]
}
```

Response:
```json
{
  "player_id": 67890,
  "name": "Jane Doe",
  "type": "prospect",
  "team": "NYY",
  "age": 21,
  "pos": "SS",
  "level": "AA",
  "fv": 55,
  "fv_str": "55",
  "surplus": {
    "pessimistic": 52000000,
    "base": 61200000,
    "optimistic": 70400000
  },
  "outcome": {
    "thresholds": {"Contributor": 0.82, "Regular": 0.54, "All-Star": 0.21},
    "likely_range": [1.5, 2.75],
    "confidence": 0.72
  }
}
```

Logic:
- Reuse `contract_value()` from `scripts/contract_value.py` for MLB players.
- Reuse `prospect_surplus_with_option()` + `find_player()` from `scripts/prospect_value.py`
  for prospects.
- Detection: if player has a row in `player_surplus` with level="MLB", treat as contract.
  Otherwise check `prospect_fv`. If in neither, return error.
- Apply the same sensitivity multipliers as `trade_calculator.py` (0.85/1.00/1.15).
- This is essentially `value_player()` from `trade_calculator.py` adapted for web.

---

## Backend Implementation

### New file: `web/trade_queries.py`

Thin web adapter that calls into the existing scripts. Functions:

- `get_org_players(team_id)` — full org roster (MLB + farm) with Ovr, Pot, FV, surplus,
  WAR, salary. Single query per player type (MLB / prospect), combined and sorted.
  Used to populate the roster table on each side.
- `get_trade_value(player_id, retention_pct=0.0)` — returns valuation dict.
  Wraps `trade_calculator.value_player()` with web-friendly formatting.
  For prospects, also calls `career_outcome_probs()` and includes threshold
  summary + likely range + confidence in the response.

### Addition to `web/queries.py`

- `search_players(query)` — league-wide player search, returns list of dicts.
  Lives in `queries.py` (not `trade_queries.py`) because it's a general-purpose
  function reused by both the trade tab and the future global search bar in `base.html`.

This keeps the web layer read-only against the DB (valuations are computed on the fly
from existing precomputed data in `player_surplus` and `prospect_fv`, plus on-demand
`contract_value()` calls for the year-by-year breakdown).

### Route additions in `web/app.py`

- `GET /api/player-search?q=` — JSON, calls `queries.search_players()`.
- `GET /api/org-players/<int:team_id>` — JSON, calls `trade_queries.get_org_players()`.
- `POST /api/trade-value` — JSON, calls `trade_queries.get_trade_value()`.

The trade tab content is rendered as part of the existing `/league` route template.
No new page route needed — it's a client-side tab like Overview and Prospects.

### Template: `web/templates/league.html`

New **Trade** tab added to the existing tab bar (Overview | Prospects | **Trade**).
Tab content is a `<div id="tab-trade">` with the two-column trade builder layout.
JS-driven interactivity:
- Search inputs with debounced autocomplete (fetch on 2+ chars, 300ms debounce).
- Dropdown results list below search input.
- Player cards rendered client-side from JSON response.
- Retention slider (range input, 0-100, step 5) on contract player cards.
  Changing retention re-fetches valuation via `/api/trade-value`.
- Trade balance panel computed client-side from the surplus values already
  returned by the API (sum each side, diff).
- All state lives in JS — no server-side session. Page is stateless.

---

## Org Roster Table

Each side shows a sortable table of the selected org's players. Two sections:

### MLB Players
| Pos | Name | Age | Ovr | Pot | WAR | Surplus |
Sorted by surplus descending. Surplus color-coded green/red.

### Prospects (FV 40+)
| Pos | Name | Age | Pot | FV | Level | Surplus |
Sorted by FV desc, then surplus desc. FV badges reuse existing coloring.
Level badges reuse existing `.lvl-badge` styles.

Clicking a row adds the player to the selected cards above and greys out / marks
the row in the table (prevents double-adding). Players already in the trade show
a checkmark or highlighted background.

The level filter tabs (All / MLB / AAA / AA / A / ...) and name search input
filter the table client-side — no additional API calls. The full org roster is
fetched once when the org is selected via `/api/org-players/<tid>`.

---

## Player Card Content

### MLB Contract Player
- Name (linked to `/player/<pid>`), Team, Age
- Position, Ovr
- Years remaining, annual salary (current year)
- Contract flags: NTC, team option, player option, estimated control
- Surplus: base case, formatted as $X.XM (green/red coloring)
- Retention slider (if on a side)
- Year-by-year breakdown expandable (collapsed by default):
  Year | Age | WAR | Market Value | Salary | Surplus

### Prospect
- Name (linked to `/player/<pid>`), Team, Age
- Position, FV (with badge coloring), Level (with badge)
- Surplus: base case, formatted as $X.XM
- No retention slider (minor league contracts have no salary to retain)
- Career outcome probability summary (expandable, collapsed by default):
  Threshold probabilities (Contributor/Regular/All-Star for hitters+SP; Contributor/Quality/Elite for RP),
  most likely outcome range (mid-50% WAR band), confidence meter.
  Reuses `career_outcome_probs()` from `prospect_value.py` — already built in Session 35.
  Does NOT render the full bar chart (too heavy for a card) — just the summary numbers.
  Full chart available on the player page via the name link.

---

## Client-Side Logic

All in `league.html` inline `<script>` within the trade tab div (consistent with
existing pages — no separate JS files beyond `sort.js`).

### State
```js
const sides = {
  a: { teamId: null, players: [], roster: [], cash: 0 },
  b: { teamId: null, players: [], roster: [], cash: 0 }
};
// roster: full org player list from /api/org-players (cached)
// players: selected trade package entries with full valuation data
// cash: dollar amount (face value, added to side total)
```

### Functions
- `selectOrg(side, teamId)` — fetch `/api/org-players/<tid>`, store in `roster`, render table.
- `filterRoster(side)` — client-side filter by level tab + name input, re-render table.
- `addPlayer(side, pid)` — fetch `/api/trade-value`, push to `players`, render card,
  mark row in roster table, update balance.
- `removePlayer(side, pid)` — splice from `players`, unmark roster row, re-render, update balance.
- `updateRetention(side, pid, pct)` — re-fetch `/api/trade-value` with new retention, update card + balance.
- `updateCash(side, amount)` — parse input, store in `sides[side].cash`, update balance.
- `renderBalance()` — sum surplus + cash for each side, compute net, render verdict.

### Verdict Logic (client-side)
Same as `trade_calculator.py` `verdict()`:
- All three scenarios positive for one side → "Side A wins in all scenarios"
- Base positive, pessimistic negative → "Side A wins in base/optimistic"
- Base negative, optimistic positive → "Side A wins only in optimistic"
- All negative → "Side A loses in all scenarios"

---

## Styling

Reuses existing dark theme from `style.css`. New classes:

- `.trade-page` — two-column grid layout
- `.trade-side` — each column
- `.trade-search` — search input + dropdown container
- `.trade-card` — player card (reuse `.panel` styling)
- `.trade-balance` — bottom balance panel
- `.trade-verdict` — verdict text with conditional coloring
- Retention slider styled to match dark theme
- Surplus coloring: green positive, red negative (existing convention)
- FV badges and level badges reuse existing `.fv-badge` and `.lvl-badge` classes

---

## Design Decisions

### Org change clears selected players
If the user changes the org dropdown on a side that already has selected players,
the selected players are cleared with a brief confirmation ("Changing team will
clear selected players. Continue?"). A trade side represents one org — mixing
players from different orgs on the same side is not a valid trade.

### Rookie-eligible deduplication
Players who appear in both `player_surplus` (MLB) and `prospect_fv` (rookie-eligible
prospect) are shown once in the **prospect section** of the roster table so that
prospect-specific evaluation data (FV, career outcome probabilities, development
context) is surfaced. The `/api/org-players` endpoint deduplicates by player_id,
preferring the prospect row. When added to a trade, they are valued via the prospect
path (`prospect_surplus_with_option` + `career_outcome_probs`).

### Salary column — deferred
Salary is not shown in the v1 org roster table. May be added after initial usage
reveals whether it's needed for the selection workflow.

### Pot shown for all players
Both MLB and prospect rows in the org roster table show Pot. MLB players can still
have room to grow — Pot gives the user ceiling context alongside Ovr.

---

## What This Does NOT Include

- Saving/loading trade proposals (stateless — refresh clears the page)
- Multi-team trades (two sides only)
- Draft pick valuation

---

## Future Enhancements

Ideas for subsequent iterations of the trade tool. Not in scope for v1 but
documented here so nothing is lost.

### Buy/Sell Mode Detection
Automatically classify each team as buyer, seller, or neutral based on a composite
of signals: current record and playoff proximity (standings + games back), farm system
strength (total prospect surplus, FV 50+ count), MLB roster age profile (core player
ages, years of control remaining), payroll situation (committed $ vs budget, expiring
contracts), and power ranking trajectory. Surface this as a badge or indicator on
player cards ("Seller team — likely available") and potentially as a standalone
league-wide view showing all 34 teams on a buy/sell spectrum. Would help users
quickly identify realistic trade partners without manually checking standings +
farm + payroll for every team.

### Consolidation/Distribution Tax (N-for-1 Adjustments)
Real trades where one side receives fewer, better players require the consolidating
side to overpay. A 2-for-1 trade where surplus is "even" on paper actually favors
the side getting the single elite player — talent consolidation has inherent value
(one roster spot vs two, higher individual WAR ceiling, etc.). Needs calibration:
analyze completed league trades to determine the typical overpay percentage for
2-for-1 (~10-15%?), 3-for-1 (~20-25%?), and larger packages. Display as an
adjustment line in the trade balance panel: "Consolidation adjustment: +$X.XM to
Side B (receiving 1 player for 3)." The multiplier likely scales with the quality
gap — swapping two FV 45s for one FV 55 requires more overpay than two FV 50s for
one FV 55.

### Prospect Comparison Panel
When both sides include prospects, show a side-by-side comparison: FV, surplus,
career outcome thresholds (Contributor/Regular/All-Star probabilities), age, level,
position, ceiling. Helps the user evaluate whether two FV 50 prospects on one side
are truly equivalent to one FV 60 on the other — the outcome probabilities make
this concrete (e.g. "55% chance of 2+ WAR vs 35% chance of 3+ WAR").

### Full Career Outcome Chart in Trade Context
v1 shows the summary numbers (thresholds + likely range) on prospect cards. A future
enhancement could render the full horizontal bar chart inline on the trade page when
a prospect card is expanded, or in a comparison overlay when two prospects are
selected. The rendering code already exists in `player.html` — would need to be
extracted into a reusable component.

### Trade History / Saved Proposals
Persist trade proposals to a JSON file or DB table so users can save, name, and
revisit trade scenarios. Would enable "what if" exploration across sessions and
comparison of multiple package options for the same target.

### Automated Trade Suggestions
Given a positional need and budget, suggest trade packages that balance surplus.
Requires buy/sell detection + roster gap analysis + package generation. This is
the "trade workbench" item from the Phase 2 long-term backlog.

### Guided Target Search
Let the user describe what they're looking for and filter/rank the available
player pool accordingly. Example queries:
- "I want an MLB 3B" → filter org rosters to 3B-eligible MLB players, rank by surplus.
- "I need a SP prospect who can enter my rotation in 2 years" → filter to SP prospects
  with ETA ≤ 2 years, FV 50+, rank by FV then surplus.
- "I'm willing to take on a salary dump alongside prospects" → surface high-salary
  negative-surplus MLB players who could be packaged with prospects to balance value
  (the receiving team absorbs the bad contract in exchange for better prospect return).
- "Show me controllable arms under 27" → SP/RP, age ≤ 27, 3+ years control, rank by WAR.

Implementation could be a structured filter panel (position dropdown, level range,
age range, ETA range, min FV/Ovr, contract type) rather than natural language parsing.
The filter panel narrows the org roster table or shows a cross-org results view.
Natural language interpretation is a Phase 3 (AI assistant) feature.

### Multi-Team Trades
Extend beyond two sides. Significantly more complex UI and balance calculation.

---

## Implementation Order

1. `web/trade_queries.py` — org roster + valuation functions; `search_players()` in `queries.py`
2. `GET /api/player-search` + `GET /api/org-players` + `POST /api/trade-value` routes in `app.py`
3. Trade tab content in `league.html` (layout, org picker, roster table, cards, balance)
4. CSS additions in `style.css`

---

## Files Changed

| File | Change |
|---|---|
| `web/trade_queries.py` | **New** — get_org_players(), get_trade_value() |
| `web/queries.py` | Add search_players() — league-wide player search (shared with future global search) |
| `web/app.py` | Add 3 API routes: /api/player-search, /api/org-players, /api/trade-value |
| `web/templates/league.html` | Add Trade tab to existing tab bar + trade builder content |
| `web/static/style.css` | Trade tab styles |

No new templates. No changes to scripts/, DB schema, or valuation logic.

---

## Implementation Status

| Task | Description | Status |
|---|---|---|
| 1 | `search_players()` in `queries.py` | ✅ Done (Session 37) |
| 2 | `get_org_players()` in `trade_queries.py` | ✅ Done (Session 37) |
| 3 | `get_trade_value()` in `trade_queries.py` | ✅ Done (Session 37) |
| 4 | API routes in `app.py` | ✅ Done (Session 37) |
| 5 | Trade tab HTML structure in `league.html` | ✅ Done (Session 37) |
| 6 | Client-side JS (state, org picker, roster, balance) | ✅ Done (Session 37) |
| 7 | Player card rendering (MLB + prospect cards) | ✅ Done (Session 37) |
| 8 | CSS in `style.css` | ✅ Done (Session 37) |
