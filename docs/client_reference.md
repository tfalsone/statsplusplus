# StatsPlus Client Reference

Python API client at `statsplus/client.py`. Reads credentials from `statsplus/.env`.
All methods return parsed data (list of dicts, or dict) and raise on error.

Import: `from statsplus import client`

---

## Roster & Teams

### `get_players() -> list[dict]`
All players across all orgs and levels.

Key fields: `ID`, `First Name`, `Last Name`, `Team ID`, `Parent Team ID`, `Level`, `Pos`, `Role`, `Age`, `Retired`

Level values: 1=ML, 2=AAA, 3=AA, 4=A, 5=Short-A, 6=Rookie, 7=Indy, 8=International

```python
roster = client.get_players()
angels_ml = [p for p in roster if p["Parent Team ID"] == 44 and p["Level"] == 1]
```

### `get_teams() -> list[dict]`
Team ID ↔ name mapping for all teams.

Key fields: `ID`, `Name`, `Nickname`, `Parent Team ID`

Angels MLB team ID = **44**.

---

## Game Info

### `get_date() -> str`
Current game date as a string, e.g. `"2033-04-22"`. Use this to check if local data is stale before analysis.

### `get_exports() -> dict`
Export status for the last 10 game dates. Returns a dict with `current_date` and one key per game date mapping to a list of team IDs with valid exports.

```python
exports = client.get_exports()
print(exports["current_date"])   # "2033-04-22"
print(exports["2033-04-22"])     # [44, 12, 7, ...]
```

### `get_game_history() -> list[dict]`
All major league games since the league started. Includes score, starters, W/L/S pitchers, date, game type.

Key fields: `game_id`, `home_team`, `away_team`, `runs0`, `runs1`, `winning_pitcher`, `losing_pitcher`, `starter0`, `starter1`, `date`

---

## Player Stats

All three stat methods share the same optional parameters:

| Param | Type | Description |
|---|---|---|
| `year` | int | Season year. Defaults to current year (all years if `pid` also set) |
| `pid` | int | Single player ID. Omit for all players |
| `split` | int | 1=Overall, 2=vsL, 3=vsR, 21=Playoffs. Omit for all splits |
| `lid` | int | League ID filter. Omit for all top-level leagues |

### `get_player_batting_stats(...) -> list[dict]`
Player batting stat lines. Each row is one player+year+split combination.

Key fields: `player_id`, `year`, `split_id`, `ab`, `h`, `2b`, `3b`, `hr`, `rbi`, `bb`, `k`, `avg`, `obp`, `slg`, `ops`

```python
stats = client.get_player_batting_stats(year=2033, split=1)
```

### `get_player_pitching_stats(...) -> list[dict]`
Player pitching stat lines.

Key fields: `player_id`, `year`, `split_id`, `gs`, `g`, `ip`, `er`, `h`, `bb`, `k`, `era`, `whip`, `w`, `l`, `sv`

### `get_player_fielding_stats(...) -> list[dict]`
Player fielding stats by position. No splits — `split` param is ignored.

Key fields: `player_id`, `year`, `pos`, `g`, `gs`, `tc`, `e`, `fpct`, `rf`

---

## Team Stats

### `get_team_batting_stats(year: int = None, split: int = None) -> list[dict]`
Team batting stats for major league teams. Split values same as player stats (1/2/3).

### `get_team_pitching_stats(year: int = None, split: int = None) -> list[dict]`
Team pitching stats for major league teams.

```python
team_bat = client.get_team_batting_stats(year=2033, split=1)
angels_bat = next(r for r in team_bat if r.get("team_id") == 44)
```

---

## Contracts

### `get_contracts() -> list[dict]`
All current active contracts across the league, including farm players.

Key fields: `player_id`, `team_id`, `contract_team_id`, `is_major`, `season_year`, `salary0`–`salary14`, `years`, `current_year`, `no_trade`, `last_year_team_option`, `last_year_player_option`

Filter to Angels contracts: `contract_team_id == 44`

```python
contracts = client.get_contracts()
angels = [c for c in contracts if c["contract_team_id"] == 44]
```

### `get_contract_extensions() -> list[dict]`
Signed extensions that take effect in future seasons. Same schema as contracts. May be empty.

---

## Ratings

### `get_ratings(player_ids: list[int] = None, poll_url: str = None) -> list[dict]`
Ratings for all active players (scouted if league uses scouts, otherwise OSA). This endpoint enforces a ~4 min rate limit between requests — the client handles this automatically by sleeping.

- `player_ids` — optional filter to specific player IDs (full job still runs, results are filtered)
- `poll_url` — pass a previously returned poll URL to skip job startup and the initial delay

The endpoint is async: the initial request returns a poll URL; the client polls that URL until the CSV is ready. Export takes at least 30 seconds; the client waits 30s before the first poll, then retries at 15s intervals (up to ~5 minutes before timeout).

**International complex players** have a negative `League` field in the ratings response (e.g. `-150` instead of `150`). The client does **not** filter these out — they are legitimate org prospects and should be included in farm analysis. The `League` field can be used downstream to identify them if needed.

Key fields: `ID`, `Name`, `Team`, `Pos`, `Ovr`, `Pot`, plus per-attribute ratings (113 or 126 columns depending on OOTP version). The API sends a duplicate `Ctrl_L` column — the client renames the second occurrence to `Ctrl` (overall control). A header validation warning is printed if the API changes its column set.

Overall/Potential are stored as `(stars × 2)`, e.g. 3.5 stars = `7`.

```python
# Filter to Angels org only
players = client.get_players()
angel_ids = [p["ID"] for p in players if p["Parent Team ID"] == 44]
ratings = client.get_ratings(player_ids=angel_ids)
```

---

## Draft

### `get_draft(lid: int = None) -> list[dict]`
Current draft status — players picked so far. May be empty outside of draft periods. Pass `lid` for multi-league associations.

---

## Notes

- Farm player stats (`playerbatstatsv2` etc.) return empty for minor league player IDs — farm analysis is limited to roster + ratings.
- Angels MLB team ID = **44**, Angels org `Parent Team ID` = **44**.
- Credentials are read from `statsplus/.env` — requires `STATSPLUS_LEAGUE_URL` and `STATSPLUS_COOKIE`.
