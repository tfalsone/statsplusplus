"""
league_config.py — single source of truth for all league-specific settings.

Loads from <league_dir>/config/league_settings.json. All scripts and web code
import from here instead of hardcoding team IDs, divisions, mappings, etc.

Usage:
    from league_config import config
    config.my_team_id      # 44
    config.year            # 2033
    config.team_name(44)   # "Anaheim Angels"
    config.team_abbr(44)   # "ANA"
    config.division(44)    # "AL West"
    config.mlb_team_ids    # {31, 32, ...}
    config.pos_map         # {1: "P", 2: "C", ...}
"""

import json
from pathlib import Path

from league_context import get_league_dir
from constants import DEFAULT_MINIMUM_SALARY


class LeagueConfig:
    def __init__(self, base_dir: Path | None = None):
        self._base_dir = base_dir
        self._settings = None
        self._state = None
        self._mlb_tids = None

    def _resolve_paths(self):
        d = self._base_dir or get_league_dir()
        return d / "config" / "league_settings.json", d / "config" / "state.json"

    def _load(self):
        if self._settings is None:
            settings_path, state_path = self._resolve_paths()
            if settings_path.exists():
                self._settings = json.loads(settings_path.read_text())
            else:
                self._settings = {}
            if state_path.exists():
                self._state = json.loads(state_path.read_text())
            else:
                self._state = {}

    def reload(self):
        """Force reload from disk (e.g. after refresh updates state)."""
        self._settings = None
        self._state = None
        self._mlb_tids = None
        self._load()

    # --- State ---

    @property
    def my_team_id(self):
        self._load()
        return self._state.get("my_team_id", self._settings.get("default_team_id"))

    @property
    def year(self):
        self._load()
        return self._state.get("year", self._settings.get("year", 2033))

    @property
    def game_date(self):
        self._load()
        return self._state.get("game_date")

    # --- Mappings (int keys for pos/role, string keys for level) ---

    @property
    def pos_map(self):
        self._load()
        return {int(k): v for k, v in self._settings.get("pos_map", {}).items()}

    @property
    def role_map(self):
        self._load()
        return {int(k): v for k, v in self._settings.get("role_map", {}).items()}

    @property
    def level_map(self):
        self._load()
        return {k: v for k, v in self._settings.get("level_map", {}).items()}

    @property
    def pos_order(self):
        self._load()
        return self._settings.get("pos_order", {
            "SP": 1, "RP": 2, "CL": 3, "P": 1,
            "C": 4, "1B": 5, "2B": 6, "3B": 7, "SS": 8,
            "LF": 9, "CF": 10, "RF": 11, "OF": 10, "DH": 12,
        })

    @property
    def pyth_exp(self):
        self._load()
        return self._settings.get("pyth_exp", 1.83)

    @property
    def minimum_salary(self):
        self._load()
        return self._settings.get("minimum_salary", DEFAULT_MINIMUM_SALARY)

    @property
    def ratings_scale(self):
        """Rating scale for tool grades: '20-80' or '1-100'. Default '1-100'."""
        self._load()
        return self._settings.get("ratings_scale", "1-100")

    # --- Teams ---

    @property
    def divisions(self):
        self._load()
        return self._settings.get("divisions", {})

    @property
    def leagues(self):
        """Return the leagues array. Synthesize from old divisions format if missing."""
        self._load()
        if "leagues" in self._settings:
            return self._settings["leagues"]
        # Backward compat: parse "AL East" → league "AL", division "East"
        divs = self._settings.get("divisions", {})
        by_league = {}
        for full_name, tids in divs.items():
            parts = full_name.split(" ", 1)
            if len(parts) == 2:
                lg_short, div_name = parts
            else:
                lg_short, div_name = "League", full_name
            if lg_short not in by_league:
                by_league[lg_short] = {"name": lg_short, "short": lg_short,
                                        "color": "#508cff", "divisions": {}}
            by_league[lg_short]["divisions"][div_name] = tids
        return list(by_league.values())

    def league_for_team(self, tid):
        """Return the league dict for a given team ID, or None."""
        for lg in self.leagues:
            for tids in lg["divisions"].values():
                if tid in tids:
                    return lg
        return None

    @property
    def team_abbr_map(self):
        self._load()
        abbr = {int(k): v for k, v in self._settings.get("team_abbr", {}).items()}
        if not abbr:
            # Fall back to DB teams table (use name as abbr placeholder)
            import db as _db
            conn = _db.get_conn(self._base_dir)
            rows = conn.execute("SELECT team_id, name FROM teams").fetchall()
            abbr = {r[0]: r[1][:3].upper() for r in rows}
        return abbr

    @property
    def team_names_map(self):
        self._load()
        names = {int(k): v for k, v in self._settings.get("team_names", {}).items()}
        if not names:
            # Fall back to DB teams table when league_settings hasn't been populated
            import db as _db
            conn = _db.get_conn(self._base_dir)
            rows = conn.execute("SELECT team_id, name FROM teams").fetchall()
            names = {r[0]: r[1] for r in rows}
        return names

    @property
    def team_div_map(self):
        return {tid: div for div, tids in self.divisions.items() for tid in tids}

    @property
    def mlb_team_ids(self):
        """MLB team IDs: teams that have at least one level=1 player in the DB."""
        if not hasattr(self, "_mlb_tids") or self._mlb_tids is None:
            import db as _db
            conn = _db.get_conn(self._base_dir)
            rows = conn.execute(
                "SELECT DISTINCT team_id FROM players WHERE level='1'"
            ).fetchall()
            self._mlb_tids = {r[0] for r in rows}
        return self._mlb_tids

    def team_name(self, tid):
        return self.team_names_map.get(tid, "?")

    def team_abbr(self, tid):
        return self.team_abbr_map.get(tid, "?")

    def division(self, tid):
        return self.team_div_map.get(tid, "")

    # --- Raw access ---

    @property
    def settings(self):
        self._load()
        return self._settings

    @property
    def perpetual_arb(self):
        """True if the league has no free agency (perpetual arbitration)."""
        self._load()
        return self._settings.get("perpetual_arb", False)

    @property
    def state_path(self):
        _, sp = self._resolve_paths()
        return sp

    @property
    def league_dir(self):
        return self._base_dir or get_league_dir()


    @property
    def has_extended_ratings(self):
        """True if this league's ratings include BABIP, HRA, PBABIP, Prone columns."""
        if not hasattr(self, "_has_extended"):
            import db
            conn = db.get_conn(self.league_dir)
            cols = {row[1] for row in conn.execute("PRAGMA table_info(ratings)").fetchall()}
            self._has_extended = "babip" in cols and conn.execute(
                "SELECT 1 FROM ratings WHERE babip IS NOT NULL LIMIT 1").fetchone() is not None
            conn.close()
        return self._has_extended

config = LeagueConfig()
