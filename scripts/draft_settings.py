"""Draft board settings — persistence, validation, and parameter mapping.

Provides configurable sliders that influence how the auto-draft list is built.
Settings are per-league and per-round-group, stored in:
    data/<league>/config/draft_settings.json

Slider values are discrete (0.0, 0.25, 0.5, 0.75, 1.0) and map to internal
parameters via linear interpolation.
"""

import json
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════════

VALID_SLIDER_VALUES = (0.0, 0.25, 0.5, 0.75, 1.0)
SETTING_KEYS = ("upside", "risk_tolerance", "balance", "need",
                "rp_discount", "acc_penalty", "survival",
                "personality", "arsenal", "contact_floor", "balance_strength")

DEFAULT_SETTINGS = {
    "version": 1,
    "round_groups": [
        {
            "start": 1,
            "end": 3,
            "settings": {"upside": 0.5, "risk_tolerance": 0.5, "balance": 0.5, "need": 0.25,
                         "rp_discount": 0.5, "acc_penalty": 0.5, "survival": 0.5,
                         "personality": 0.5, "arsenal": 0.5, "contact_floor": 0.5, "balance_strength": 0.5},
        },
        {
            "start": 4,
            "end": None,
            "settings": {"upside": 0.5, "risk_tolerance": 0.5, "balance": 0.5, "need": 0.5,
                         "rp_discount": 0.5, "acc_penalty": 0.5, "survival": 0.5,
                         "personality": 0.5, "arsenal": 0.5, "contact_floor": 0.5, "balance_strength": 0.5},
        },
    ],
    "active_preset": "balanced",
}

PRESETS = {
    "balanced": {"upside": 0.5, "risk_tolerance": 0.5, "balance": 0.5, "need": 0.25,
                 "rp_discount": 0.5, "acc_penalty": 0.5, "survival": 0.5,
                 "personality": 0.5, "arsenal": 0.5, "contact_floor": 0.5, "balance_strength": 0.5},
    "upside": {"upside": 1.0, "risk_tolerance": 0.75, "balance": 0.5, "need": 0.0,
               "rp_discount": 0.5, "acc_penalty": 0.25, "survival": 0.5,
               "personality": 0.5, "arsenal": 0.5, "contact_floor": 0.25, "balance_strength": 0.5},
    "conservative": {"upside": 0.0, "risk_tolerance": 0.25, "balance": 0.5, "need": 0.25,
                     "rp_discount": 0.5, "acc_penalty": 0.75, "survival": 0.25,
                     "personality": 0.75, "arsenal": 0.75, "contact_floor": 0.75, "balance_strength": 0.5},
    "org_needs": {"upside": 0.5, "risk_tolerance": 0.5, "balance": 0.5, "need": 1.0,
                  "rp_discount": 0.5, "acc_penalty": 0.5, "survival": 0.5,
                  "personality": 0.5, "arsenal": 0.5, "contact_floor": 0.5, "balance_strength": 0.5},
}

# Internal parameter ranges: (slider_0.0_value, slider_1.0_value)
# Ranges are calibrated so that slider midpoint (0.5) produces the original
# hardcoded defaults — ensuring backwards compatibility when settings are untouched.
_PARAM_RANGES = {
    "ceiling_weight": (0.0, 0.40),       # upside slider: 0.5 → 0.2 (original)
    "risk_scale": (2.0, 0.0),            # risk_tolerance slider: 0.5 → 1.0 (original)
    "balance_target": (0.25, 0.65),      # balance slider: 0.5 → 0.45 (original)
    "need_scale": (0.0, 3.0),            # need slider: 0.5 → 1.5
    "rp_discount_scale": (2.0, 0.0),     # rp_discount slider: 0.5 → 1.0 (original)
    "acc_scale": (2.0, 0.0),             # acc_penalty slider: 0.5 → 1.0 (original)
    "survival_base": (15, 45),           # survival slider: 0.5 → 30 (original)
    "survival_scale": (3, 9),            # survival slider: 0.5 → 6 (original)
    "personality_scale": (0.0, 2.0),     # personality slider: 0.5 → 1.0 (original)
    "arsenal_scale": (0.0, 2.0),         # arsenal slider: 0.5 → 1.0 (original)
    "contact_floor_scale": (0.0, 2.0),   # contact_floor slider: 0.5 → 1.0 (original)
    "balance_bonus": (0.0, 4.0),         # balance_strength slider: 0.5 → 2.0 (original)
}

# Default internal parameters (equivalent to all sliders at 0.5)
DEFAULT_PARAMS = {
    "ceiling_weight": 0.2,
    "risk_scale": 1.0,
    "acc_scale": 1.0,
    "balance_target": 0.45,
    "need_scale": 1.5,
    "rp_discount_scale": 1.0,
    "survival_base": 30,
    "survival_scale": 6,
    "personality_scale": 1.0,
    "arsenal_scale": 1.0,
    "contact_floor_scale": 1.0,
    "balance_bonus": 2.0,
}


# ═══════════════════════════════════════════════════════════════════════════
# Persistence
# ═══════════════════════════════════════════════════════════════════════════

def _settings_path(league_dir: Path) -> Path:
    return league_dir / "config" / "draft_settings.json"


def load_settings(league_dir: Path) -> dict:
    """Load settings from file or return defaults.

    Args:
        league_dir: Path to the league data directory (e.g., data/emlb/).

    Returns:
        Settings dict with version, round_groups, and active_preset.
    """
    path = _settings_path(league_dir)
    if not path.exists():
        return _deep_copy(DEFAULT_SETTINGS)
    try:
        data = json.loads(path.read_text())
        return _validate_and_normalize(data)
    except (json.JSONDecodeError, ValueError):
        return _deep_copy(DEFAULT_SETTINGS)


def save_settings(league_dir: Path, settings: dict):
    """Validate and write settings to disk.

    Args:
        league_dir: Path to the league data directory.
        settings: Settings dict to save.

    Raises:
        ValueError: If settings fail validation.
    """
    validated = _validate_and_normalize(settings)
    path = _settings_path(league_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(validated, indent=2) + "\n")


def copy_settings(from_league_dir: Path, to_league_dir: Path) -> dict:
    """Copy settings from one league to another.

    Args:
        from_league_dir: Source league directory.
        to_league_dir: Destination league directory.

    Returns:
        The copied settings dict.

    Raises:
        FileNotFoundError: If source has no settings file.
    """
    source = _settings_path(from_league_dir)
    if not source.exists():
        raise FileNotFoundError(f"No draft settings in {from_league_dir.name}")
    settings = load_settings(from_league_dir)
    save_settings(to_league_dir, settings)
    return settings


# ═══════════════════════════════════════════════════════════════════════════
# Mapping — slider values to internal parameters
# ═══════════════════════════════════════════════════════════════════════════

def _lerp(val: float, low: float, high: float) -> float:
    """Linear interpolation from normalized 0-1 to parameter range."""
    return low + val * (high - low)


def map_to_params(normalized: dict) -> dict:
    """Convert normalized slider values to internal parameter dict.

    Args:
        normalized: Dict with keys from SETTING_KEYS, values in 0.0-1.0.

    Returns:
        Dict with internal parameter names and computed values.
    """
    upside = normalized.get("upside", 0.5)
    risk = normalized.get("risk_tolerance", 0.5)
    balance = normalized.get("balance", 0.5)
    need = normalized.get("need", 0.5)
    rp_discount = normalized.get("rp_discount", 0.5)
    acc_penalty = normalized.get("acc_penalty", 0.5)
    survival = normalized.get("survival", 0.5)
    personality = normalized.get("personality", 0.5)
    arsenal = normalized.get("arsenal", 0.5)
    contact_floor = normalized.get("contact_floor", 0.5)
    balance_strength = normalized.get("balance_strength", 0.5)

    return {
        "ceiling_weight": _lerp(upside, *_PARAM_RANGES["ceiling_weight"]),
        "risk_scale": _lerp(risk, *_PARAM_RANGES["risk_scale"]),
        "acc_scale": _lerp(acc_penalty, *_PARAM_RANGES["acc_scale"]),
        "balance_target": _lerp(balance, *_PARAM_RANGES["balance_target"]),
        "need_scale": _lerp(need, *_PARAM_RANGES["need_scale"]),
        "rp_discount_scale": _lerp(rp_discount, *_PARAM_RANGES["rp_discount_scale"]),
        "survival_base": _lerp(survival, *_PARAM_RANGES["survival_base"]),
        "survival_scale": _lerp(survival, *_PARAM_RANGES["survival_scale"]),
        "personality_scale": _lerp(personality, *_PARAM_RANGES["personality_scale"]),
        "arsenal_scale": _lerp(arsenal, *_PARAM_RANGES["arsenal_scale"]),
        "contact_floor_scale": _lerp(contact_floor, *_PARAM_RANGES["contact_floor_scale"]),
        "balance_bonus": _lerp(balance_strength, *_PARAM_RANGES["balance_bonus"]),
    }


def resolve_for_round(settings: dict, round_num: int) -> dict:
    """Find which round group applies and return mapped internal parameters.

    Args:
        settings: Full settings dict with round_groups.
        round_num: The current draft round (1-indexed).

    Returns:
        Mapped internal parameter dict for that round.
    """
    groups = settings.get("round_groups", DEFAULT_SETTINGS["round_groups"])

    for group in groups:
        start = group["start"]
        end = group["end"]
        if end is None:
            # Catch-all group: matches anything >= start
            if round_num >= start:
                return map_to_params(group["settings"])
        elif start <= round_num <= end:
            return map_to_params(group["settings"])

    # Fallback: should not happen with valid settings, but be safe
    return _deep_copy(DEFAULT_PARAMS)


# ═══════════════════════════════════════════════════════════════════════════
# Validation
# ═══════════════════════════════════════════════════════════════════════════

def _deep_copy(d: dict) -> dict:
    """Simple deep copy for JSON-serializable dicts."""
    return json.loads(json.dumps(d))


def _snap_to_discrete(val) -> float:
    """Snap a value to the nearest valid discrete position."""
    try:
        v = float(val)
    except (TypeError, ValueError):
        return 0.5
    # Find closest valid value
    return min(VALID_SLIDER_VALUES, key=lambda x: abs(x - v))


def _validate_and_normalize(data: dict) -> dict:
    """Validate settings structure and snap values to discrete positions.

    Raises ValueError for structural issues. Silently fixes slider values
    by snapping to nearest valid position.
    """
    if not isinstance(data, dict):
        raise ValueError("Settings must be a dict")

    groups = data.get("round_groups")
    if not groups or not isinstance(groups, list):
        raise ValueError("round_groups must be a non-empty list")

    validated_groups = []
    for i, group in enumerate(groups):
        if not isinstance(group, dict):
            raise ValueError(f"Round group {i} must be a dict")

        start = group.get("start")
        end = group.get("end")

        if not isinstance(start, int) or start < 1:
            raise ValueError(f"Round group {i}: start must be a positive integer")
        if end is not None and (not isinstance(end, int) or end < start):
            raise ValueError(f"Round group {i}: end must be >= start or null")

        settings = group.get("settings")
        if not isinstance(settings, dict):
            raise ValueError(f"Round group {i}: settings must be a dict")

        # Snap all slider values to valid discrete positions
        normalized_settings = {}
        for key in SETTING_KEYS:
            normalized_settings[key] = _snap_to_discrete(settings.get(key, 0.5))

        validated_groups.append({
            "start": start,
            "end": end,
            "settings": normalized_settings,
        })

    # Verify no overlaps and proper ordering
    validated_groups.sort(key=lambda g: g["start"])
    for i in range(len(validated_groups) - 1):
        current_end = validated_groups[i]["end"]
        next_start = validated_groups[i + 1]["start"]
        if current_end is None:
            raise ValueError("Only the last round group can have end=null")
        if next_start <= current_end:
            raise ValueError(f"Round groups overlap: group ending at {current_end} "
                             f"conflicts with group starting at {next_start}")

    # Last group should be catch-all (end=None) — enforce this
    if validated_groups[-1]["end"] is not None:
        validated_groups[-1]["end"] = None

    preset = data.get("active_preset")
    if preset is not None and preset not in PRESETS:
        preset = None

    return {
        "version": 1,
        "round_groups": validated_groups,
        "active_preset": preset,
    }
