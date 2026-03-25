# Draft Page Spec

## Overview

A dedicated page for scouting and tracking the annual amateur draft. Provides a ranked, sortable board of draft-eligible prospects with full ratings detail, live pick tracking during the StatsPlus draft, and analysis tools to identify draft targets.

## Value Added

- **Pre-draft scouting**: Evaluate the entire draft pool in one view — rank prospects by FV, filter by position/age/type, identify sleepers and value picks. Currently requires manually browsing individual player pages or external spreadsheets.
- **Live draft tracking**: During the multi-day StatsPlus draft, see which prospects are still available and which have been taken. Eliminates the need to cross-reference the StatsPlus draft board with scouting notes.
- **Draft strategy**: Suggested picks based on team needs, best available by FV, and positional scarcity in the pool. Helps make informed decisions under time pressure.
- **Post-draft review**: Grade team hauls, compare picks against the board, identify steals and reaches.

## Data Sources

### Draft Pool (DB)
- **vMLB-style leagues**: Players at level 10 (college) and level 11 (HS) with age ≥ 18 (HS) or ≥ 19 (college).
- **eMLB-style leagues**: Players at level 0 (amateur) with age ≥ 18.
- Pool size: top 800 by Pot rating (covers ~25 rounds × 32 teams with buffer). Validated against vMLB: captures 99.3% of actual draft picks.
- Full scouted ratings available (Ovr, Pot, all tools, pitches, defense).

### Draft Picks (StatsPlus API)
- Endpoint: `/draftv2/` — returns completed picks only (player ID, round, pick, overall, team, position, age, college/HS flag, timestamp).
- Does not expose draft order or empty slots for future picks.
- Does not expose the draft pool directly — pool must be inferred from DB.

### Level Detection
Amateur levels vary by league configuration. Detection heuristic:
- If levels 10 and/or 11 exist with players whose teams are college/HS (team names containing "HS" or "College", or team_id in a high range with parent_team_id = 0) → use those levels.
- If level 0 has draft-age players → use level 0.
- Store detected amateur levels in league settings or derive at query time.

## Page States

### State 1: Draft In Progress
- Draft API returns picks that reference players still in the amateur pool (college/HS teams in DB).
- **Display**: Full draft board with pick overlay. Drafted players marked with team badge, dimmed or filterable. "Update Picks" button to fetch latest from API. Best Available panel.

### State 2: Draft Complete
- Draft API picks reference players now in MLB org systems (parent_team_id > 0).
- **Display**: Draft results view — picks by round, team haul summaries, grades.

### State 3: Pre-Draft / New Season
- Draft API returns stale picks (from previous draft — player IDs don't match current amateur pool).
- Amateur pool exists in DB for scouting.
- **Display**: Draft board for scouting. No pick overlay. Analysis tools active.

### State 4: No Draft Data
- No amateur-level players in DB and no relevant draft API data.
- **Display**: Message indicating draft pool not yet available.

## Features — Base Implementation

### Draft Board (main table)
- Sortable columns: Rank (by FV), Name, Pos, Age, College/HS, Ovr, Pot, FV, Status (Available/Drafted)
- Key tool columns: hitters get Contact, Power, Speed; pitchers get Stuff, Movement, Control
- Default sort: FV descending (with Pot as tiebreaker)
- Position filter: All / C / IF / OF / SP / RP (or individual positions)
- College/HS filter
- "Hide Drafted" toggle to show only available prospects
- Drafted players show picking team name, round/pick, dimmed styling
- Row click → opens prospect detail panel

### Prospect Detail Panel
- Side panel (same pattern as league prospects tab) triggered by row click
- Full ratings display: tools with grade bars (cur/pot), pitches, defense positions
- Player info: name, age, position, height, bats/throws, college/HS
- FV grade with breakdown context
- Scouting summary: archetype label (e.g., "Power-hitting corner OF", "High-upside HS arm")

### FV Calculation for Draft Prospects
- Extend `fv_calc.py` or create a draft-specific FV function
- Use existing FV model with adjustments for amateur levels:
  - College seniors (age 21-22): closer to current minor league prospects, lower development discount
  - College underclassmen (age 19-20): moderate discount
  - HS players (age 18): highest discount, most volatile — weight Pot more heavily
- Increased uncertainty: wider FV bands for younger/rawer players
- Position bucketing: use same bucket logic as existing prospect system

### Draft Pick Updates (State 1)
- "Update Picks" button in page header
- Fetches `/draftv2/`, diffs against stored picks, updates table in-place
- Status indicator: "Last updated: [time]" and "X new picks" after update
- Newly picked players briefly highlighted
- No continuous polling — manual refresh only

### My Team's Picks
- Sidebar or top section showing the user's team's selections (from draft API)
- Shows round, pick number, player name, position, age, FV
- Visible in States 1 and 2 — during the draft it grows as picks come in, post-draft it shows the full haul
- Quick-click to highlight/scroll to that player in the main board

### Suggested Picks Panel
- "Best Available" section: top 5-10 undrafted prospects by FV
- Positional breakdown: best available at each position group
- "Sleepers" flag: prospects with high Pot-Ovr gap (≥ 20 points) — raw upside plays
- "Value" flag: prospects whose FV suggests they should go higher than current board position

## Features — Future Improvements

- **Team needs integration**: Cross-reference user's farm system to highlight positions where draft picks would fill gaps. "Your system is thin at SS — here are the top SS available."
- **Mock draft / projection**: Estimate where prospects will be picked based on FV and historical draft patterns. Flag "likely available at your pick" prospects.
- **Draft history tab**: Show previous years' draft results (if API retains historical data). Team draft track record — hit rate, average FV of picks, best/worst picks.
- **Comparison tool**: Select 2-3 prospects side-by-side to compare ratings, tools, FV, archetype.
- **Draft pick trade tracker**: If pick trades are visible in the data, show current pick ownership.
- **Export**: Download draft board as CSV for offline use during the draft.
- **Archetype classification**: Auto-label prospects (e.g., "Contact-first SS", "Power arm with control risk", "Toolsy OF") based on tool shape analysis.
- **Post-draft grades**: After draft completes, grade each team's haul by total FV, positional balance, and value relative to pick position.
- **Mobile-friendly compact view**: Condensed layout for phone/tablet use (lower priority — desktop is primary).

## Technical Considerations

### Amateur Level Detection
Need a reliable way to identify which DB levels represent the amateur draft pool across different league configurations. Options:
1. Check for levels 10, 11, or 0 with players whose teams have no parent org (parent_team_id = 0) and team names matching college/HS patterns.
2. Store the amateur level(s) in `league_settings.json` during onboarding or first detection.
3. Derive at query time — scan for levels not in the standard MLB→Rookie chain that have draft-age players.

Option 1 is most robust for auto-detection. Option 2 is simplest if we can detect once and cache.

### FV Model Adjustments
The current FV model (`calc_fv` in `fv_calc.py`) is calibrated for minor league prospects (Rookie through AAA). Draft prospects are further from MLB and have higher variance. Adjustments needed:
- Development discount: steeper for HS players (further from MLB debut)
- Certainty: lower for all draft prospects, especially HS
- Age normalization: HS 18yr-old is not the same as a Rookie-ball 18yr-old
- The FV calculation should produce reasonable grades (FV 30-70 range) that are comparable to existing prospect FVs

### Draft Pick Storage
Options:
1. Store in a `draft_picks` DB table during refresh (like contract_extensions)
2. Fetch live from API at page load / on button click, no DB storage
3. Hybrid: cache in DB, refresh on demand

Option 2 is simplest for base implementation — the draft page fetches from the API when needed. Option 1 is better long-term for historical tracking.

### Page Route
- New tab on the league page (`/league`): Overview | Prospects | Trade | **Draft**
- Follows existing tab-switching pattern (client-side JS)
- No separate route — draft data loaded with the league page

## Implementation Task List

### Phase 1: Draft Board (static scouting view)
1. **Amateur level detection** — query function to identify draft pool levels for the active league
2. **Draft pool query** — `get_draft_pool()` in `queries.py`: fetch top 800 amateur players by Pot, with ratings and tool data
3. **Draft FV calculation** — extend FV model for amateur levels, compute FV for pool players
4. **Draft tab on league page** — add Draft tab to league page tab bar, wire data into template
5. **Draft board template** — sortable table with position/type filters, prospect detail side panel on row click
6. **Draft board styling** — table styles, filter controls, side panel CSS

### Phase 2: Live Draft Tracking
7. **Draft API integration** — fetch picks from `/draftv2/`, match against pool players
8. **State detection** — determine page state (in-progress / complete / pre-draft / no data)
9. **Pick overlay** — mark drafted players in the table, show team/round/pick
10. **Update button** — manual refresh of draft picks with diff detection and highlight
11. **Best Available panel** — top undrafted prospects by FV, positional breakdown

### Phase 3: Analysis & Polish
12. **Sleeper/value flags** — identify high-upside and undervalued prospects
13. **Team needs integration** — cross-reference user's farm for positional gaps
14. **Post-draft grades** — team haul summaries after draft completion
15. **Draft history** — previous draft results if API supports historical data
