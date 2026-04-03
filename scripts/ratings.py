"""
ratings.py — Rating normalization utilities.

Provides norm() and norm_floor() for converting raw OOTP ratings to the
20-80 scouting scale. Imported by player_utils, fv_model, and any module
that needs rating normalization without pulling in the full player_utils.
"""

_ratings_scale = None  # set by init_ratings_scale() or auto-detected


def init_ratings_scale(scale="1-100"):
    """Set the module-level ratings scale. Called once at startup."""
    global _ratings_scale
    _ratings_scale = scale


def get_ratings_scale():
    """Return the current ratings scale ('1-100' or '20-80'). Public accessor."""
    global _ratings_scale
    if _ratings_scale is None:
        from league_config import config
        _ratings_scale = config.ratings_scale
    return _ratings_scale


# Keep private alias for internal use
_get_ratings_scale = get_ratings_scale


def norm(raw):
    """Normalize a tool rating to 20-80 scouting scale, rounded to nearest 5.
    Returns None for missing/zero/invalid input.
    On 1-100 leagues: converts via linear mapping.
    On 20-80 leagues: clamps and rounds (values are already on the scouting scale)."""
    if raw is None:
        return None
    try:
        raw = int(raw)
    except (ValueError, TypeError):
        return None
    if raw <= 0:
        return None
    if get_ratings_scale() == "20-80":
        return max(20, min(80, round(raw / 5) * 5))
    return round((20 + (min(raw, 100) / 100) * 60) / 5) * 5


def norm_floor(raw, floor=20):
    """norm() with a numeric fallback for call sites that require a number.
    Use when the result feeds a comparison or numeric operation, not just display."""
    return norm(raw) or floor
