"""League configuration and context resolution.

Provides:
    - LeagueConfig: typed accessor for all league-specific settings
    - get_league_dir(): resolve the active league's data directory
    - ratings: pure normalization functions (no global state)
"""

from statsplusplus.config.league_context import (
    get_active_league_slug,
    get_league_dir,
    get_statsplus_token,
    set_statsplus_token,
    APP_CONFIG_PATH,
)
from statsplusplus.config.ratings import norm, norm_continuous, norm_floor

__all__ = [
    "get_active_league_slug",
    "get_league_dir",
    "get_statsplus_token",
    "set_statsplus_token",
    "APP_CONFIG_PATH",
    "norm",
    "norm_continuous",
    "norm_floor",
]
