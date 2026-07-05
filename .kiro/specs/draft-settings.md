# Draft Board Settings — Implementation Spec

## Overview

Configurable sliders that influence how the auto-draft list is built and ordered.
Accessible via a ⚙️ gear icon next to the "Generate Auto-Draft List" button.
Settings are per-league, per-round-group, and persistent across sessions.

---

## Scope (v1)

**In scope:**
- 4 core sliders with user-friendly labels and ⓘ tooltips
- User-defined round groups with explicit round ranges
- Per-league persistence (`data/<league>/config/draft_settings.json`)
- Settings gear icon (⚙️) next to Generate button opens modal
- Named presets as starting points
- "Copy from league" option
- Generate and Sim both respect saved settings
- 5 discrete slider positions (Very Low → Very High)

**Out of scope (future):**
- Live preview / feedback loop showing top-N changes as sliders move
- Sim UX integration (unified workflow)
- Advanced/granular settings (RP discount, arsenal penalty, personality weight, etc.)

---

## UI Design

### Entry Point

```
[🎲 Sim] [📋 Generate Auto-Draft List] [⚙️]
```

The ⚙️ opens a modal overlay. The "Generate" button always uses whatever settings
are currently saved (defaults if never configured).

### Settings Modal

```
┌─── Auto-Draft List Settings ─────────────────────────── [✕] ───┐
│                                                                  │
│  Preset: [● Balanced] [Upside] [Conservative] [Org Needs]       │
│                                                                  │
│  ┌─ Rounds 1 to 2 ─────────────────────────────── [✕ Remove] ─┐│
│  │                                                              ││
│  │  Upside vs Safety                    ⓘ                      ││
│  │  [Safe ● ─ ─ ─ ─ ─ ─ ─ ─ Upside]                           ││
│  │   ▲ Moderate                                                 ││
│  │                                                              ││
│  │  Risk Tolerance                      ⓘ                      ││
│  │  [Cautious ─ ─ ─ ● ─ ─ ─ Aggressive]                       ││
│  │   ▲ Moderate                                                 ││
│  │                                                              ││
│  │  Pitcher/Hitter Mix                  ⓘ                      ││
│  │  [More Bats ─ ─ ● ─ ─ ─ More Arms]                         ││
│  │   ▲ Balanced                                                 ││
│  │                                                              ││
│  │  Organizational Need                 ⓘ                      ││
│  │  [Best Available ─ ─ ● ─ Fill Gaps]                         ││
│  │   ▲ Low                                                      ││
│  │                                                              ││
│  └──────────────────────────────────────────────────────────────┘│
│                                                                  │
│  ┌─ Rounds 3 to 5 ─────────────────────────────── [✕ Remove] ─┐│
│  │  (same 4 sliders)                                            ││
│  └──────────────────────────────────────────────────────────────┘│
│                                                                  │
│  ┌─ Rounds 6+ ─────────────────────────────────── [✕ Remove] ─┐│
│  │  (same 4 sliders)                                            ││
│  └──────────────────────────────────────────────────────────────┘│
│                                                                  │
│  [+ Add Round Group]                                             │
│                                                                  │
│  ──────────────────────────────────────────────────────────────  │
│  League: EMLB │ [Copy settings from… ▾]                          │
│                                                                  │
│  [Reset to Defaults]                      [Save] [Save & Close]  │
└──────────────────────────────────────────────────────────────────┘
```

---

## Slider Design

### Discrete Positions

5 positions per slider, stored as normalized values:

| Position | Stored Value | Generic Label |
|----------|-------------|---------------|
| 1 | 0.0 | Very Low |
| 2 | 0.25 | Low |
| 3 | 0.5 | Moderate |
| 4 | 0.75 | High |
| 5 | 1.0 | Very High |

Each slider displays contextual labels (left/right endpoints + current position label).

### Core Sliders

| # | Label | Left endpoint | Right endpoint | Position labels |
|---|-------|---------------|----------------|-----------------|
| 1 | Upside vs Safety | Safe | Upside | Very Safe / Safe / Balanced / Upside / Max Upside |
| 2 | Risk Tolerance | Cautious | Aggressive | Very Cautious / Cautious / Moderate / Aggressive / Very Aggressive |
| 3 | Pitcher/Hitter Mix | More Bats | More Arms | Heavy Bats / More Bats / Balanced / More Arms / Heavy Arms |
| 4 | Organizational Need | Best Available | Fill Gaps | BPA Only / Slight / Moderate / Strong / Fill Gaps |

### Tooltip Content (ⓘ hover)

| Slider | Tooltip |
|--------|---------|
| Upside vs Safety | "Controls how much the board favors high-ceiling players over predictable outcomes. Higher = prefer players who could be stars but may not pan out. Lower = prefer players with a clearer path to the majors, even if their ceiling is lower." |
| Risk Tolerance | "Controls how much the board penalizes players with low scouting accuracy or high bust probability. Aggressive = treat uncertain players the same as known quantities. Cautious = significantly downgrade players we're less sure about." |
| Pitcher/Hitter Mix | "Sets the target ratio of pitchers to hitters in your draft class. The board will give a slight boost to the underrepresented group as picks are made to stay near your target. Center = roughly even split." |
| Organizational Need | "Controls whether the board factors in your team's positional depth when ranking players. Higher = boost players at positions where your organization is thin. Lower = ignore depth and rank purely on talent." |

---

## Round Group Configuration

### Rules

- At least one group must exist (cannot delete the last one)
- The final group always uses "N+" format (catch-all for remaining rounds)
- Ranges cannot overlap — UI auto-adjusts adjacent groups when boundaries change
- Round boundaries set via number inputs (start/end per group)
- Default: two groups — "Rounds 1-3" and "Rounds 4+"

### Adding a Group

[+ Add Round Group] splits the current catch-all group. If the catch-all is
"Rounds 4+", adding a group creates "Rounds 4-6" and "Rounds 7+". The user can
then adjust the boundaries.

### Removing a Group

[✕ Remove] merges that group's rounds into the adjacent group below it (or above
if it's the last group). The remaining group expands to cover the freed rounds.

---

## Presets

| Preset | Upside | Risk | Balance | Need |
|--------|--------|------|---------|------|
| **Balanced** | 0.5 (Balanced) | 0.5 (Moderate) | 0.5 (Balanced) | 0.25 (Slight) |
| **Upside** | 1.0 (Max Upside) | 0.75 (Aggressive) | 0.5 (Balanced) | 0.0 (BPA Only) |
| **Conservative** | 0.0 (Very Safe) | 0.25 (Cautious) | 0.5 (Balanced) | 0.25 (Slight) |
| **Org Needs** | 0.5 (Balanced) | 0.5 (Moderate) | 0.5 (Balanced) | 1.0 (Fill Gaps) |

Selecting a preset applies its values to ALL round groups uniformly. The user can
then customize individual groups. Once any slider moves from preset values,
`active_preset` becomes null and UI shows "Custom."

---

## Persistence

### File: `data/<league>/config/draft_settings.json`

```json
{
  "version": 1,
  "round_groups": [
    {
      "start": 1,
      "end": 2,
      "settings": { "upside": 0.5, "risk_tolerance": 0.5, "balance": 0.5, "need": 0.25 }
    },
    {
      "start": 3,
      "end": 5,
      "settings": { "upside": 0.5, "risk_tolerance": 0.5, "balance": 0.5, "need": 0.5 }
    },
    {
      "start": 6,
      "end": null,
      "settings": { "upside": 0.25, "risk_tolerance": 0.25, "balance": 0.5, "need": 0.75 }
    }
  ],
  "active_preset": null
}
```

- `end: null` = "this round and beyond" (catch-all)
- All slider values are one of: 0.0, 0.25, 0.5, 0.75, 1.0
- `active_preset`: string (preset name) or null (custom)

### Copy from League

Dropdown lists other leagues that have a `draft_settings.json`. Copies the file
content directly. User confirms before overwriting.

---

## Parameter Mapping

Normalized slider values (0.0–1.0) map to internal parameters:

| Slider | Parameter(s) | At 0.0 | At 0.5 (default) | At 1.0 |
|--------|-------------|--------|---------|--------|
| upside | `ceiling_weight` | 0.0 | 0.2 | 0.40 |
| risk_tolerance | `risk_scale` | 2.0 | 1.0 | 0.0 |
| risk_tolerance | `acc_scale` | 2.0 | 1.0 | 0.0 |
| balance | `balance_target` | 0.25 | 0.45 | 0.65 |
| need | `need_scale` | 0.0 | 1.5 | 3.0 |

Mapping via linear interpolation:
```python
def _lerp(val, low, high):
    return low + val * (high - low)
```

Note: `risk_scale` and `acc_scale` are inverted — slider right (1.0) = less
penalty = more aggressive. The lerp handles this naturally since high > low
for the parameter range (2.0 → 0.25).

---

## API

### New Endpoints

```
GET  /api/draft-settings
  → Returns current settings JSON for active league (or defaults if no file)

POST /api/draft-settings
  → Body: full settings JSON
  → Writes to data/<league>/config/draft_settings.json
  → Returns: {"ok": true}

POST /api/draft-settings/copy
  → Body: {"from_league": "emlb"}
  → Copies draft_settings.json from source league to active league
  → Returns: {"ok": true, "settings": <copied settings>}
```

### Modified Endpoints

`POST /api/draft-upload-list`:
- Reads saved settings automatically
- Optional `"settings"` key in body overrides saved file (for programmatic use)

`POST /api/draft-sim`:
- Same — reads saved settings automatically

---

## Backend Changes

### New: `scripts/draft_settings.py`

```python
"""Draft board settings — persistence and parameter mapping."""

DEFAULT_SETTINGS = { ... }
PRESETS = { ... }

def load_settings(league_dir: Path) -> dict:
    """Load settings from file or return defaults."""

def save_settings(league_dir: Path, settings: dict):
    """Validate and write settings."""

def resolve_for_round(settings: dict, round_num: int) -> dict:
    """Find which round group applies and return mapped parameters."""

def map_to_params(normalized: dict) -> dict:
    """Convert normalized slider values to internal parameter dict."""
```

### Modified: `scripts/draft_board.py`

`draft_value(r, needs=None, pick_round=None, params=None)`:
- New optional `params` dict argument
- When provided, uses `params["ceiling_weight"]`, `params["risk_scale"]`, etc.
- When None, uses current hardcoded values (backwards compatible)

`build_pick_list(rows, adp, needs, num_teams, limit, settings=None, ...)`:
- New optional `settings` argument (the full round-group structure)
- Per-pick: resolves current round → finds matching group → maps to params
- Passes params to `draft_value()` calls
- Reads `balance_target` from the current round's mapped params

### Modified: `web/app.py`

- `api_draft_upload_list()`: loads settings, passes to `build_pick_list()`
- `api_draft_sim()`: loads settings, passes to `simulate_draft()` (which calls `build_pick_list()`)
- New routes for settings CRUD and copy

---

## Frontend Implementation

### Technology

Vanilla JS, consistent with existing codebase. No framework.

### Modal Structure

- Rendered in `league.html` as a hidden `<div class="modal">` overlay
- Opened by ⚙️ button click
- Closed by ✕, Save & Close, or clicking outside

### Slider HTML

```html
<div class="draft-setting">
  <div class="draft-setting-header">
    <span class="draft-setting-label">Upside vs Safety</span>
    <span class="draft-setting-info" title="...tooltip...">ⓘ</span>
  </div>
  <div class="draft-slider-row">
    <span class="draft-slider-end">Safe</span>
    <input type="range" min="0" max="4" step="1" value="2" class="draft-slider"
           data-key="upside" data-group="0">
    <span class="draft-slider-end">Upside</span>
  </div>
  <span class="draft-slider-value">Balanced</span>
</div>
```

`min=0 max=4 step=1` gives 5 discrete positions. JS maps 0-4 → 0.0/0.25/0.5/0.75/1.0.

### Interactions

- Slider change → update displayed position label, clear active preset if values differ
- Preset click → set all sliders in all groups to preset values, set active_preset
- Add group → split last catch-all, render new group card
- Remove group → merge into adjacent, re-render
- Save → POST settings to API
- Save & Close → POST + close modal
- Reset → restore DEFAULT_SETTINGS, re-render all

---

## Implementation Order

1. `scripts/draft_settings.py` — model, load/save, mapping, validation
2. Refactor `draft_value()` to accept params dict
3. Refactor `build_pick_list()` to accept settings and resolve per-round
4. API endpoints: GET/POST settings, copy
5. Update `api_draft_upload_list` and `api_draft_sim` to load/use settings
6. Frontend: modal HTML structure + CSS
7. Frontend: slider interactions, round group CRUD, presets
8. Frontend: wire to API (load on open, save, generate respects settings)
9. End-to-end testing

---

## Testing Strategy

- Unit: `draft_settings.py` — mapping correctness, round resolution, validation
- Integration: generate list with different settings → verify ordering changes
- UI: manual — adjust sliders, add/remove groups, verify save/load cycle
- Backwards compat: generate list with no settings file → same output as before
