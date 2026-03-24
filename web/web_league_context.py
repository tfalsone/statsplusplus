"""
web/league_context.py — request-scoped league context accessors.

In Flask request context, reads from `g`. Outside Flask (scripts), falls back
to the default league resolution.

Usage in query modules:
    from web_league_context import get_db, get_cfg, get_team_abbr_map, ...
"""

from flask import g, has_request_context


def get_db():
    """Get a new DB connection for the current league."""
    import db as _db
    if has_request_context() and hasattr(g, "league_dir"):
        return _db.get_conn(g.league_dir)
    return _db.get_conn()


def get_cfg():
    """Get the LeagueConfig for the current league."""
    if has_request_context() and hasattr(g, "league_config"):
        return g.league_config
    from league_config import config
    return config


# Convenience accessors — avoid repeated get_cfg() calls in hot paths
def team_abbr_map():
    return get_cfg().team_abbr_map

def team_names_map():
    return get_cfg().team_names_map

def team_div_map():
    return get_cfg().team_div_map

def mlb_team_ids():
    return get_cfg().mlb_team_ids

def level_map():
    return get_cfg().level_map

def pos_map():
    return get_cfg().pos_map

def pos_order():
    return get_cfg().pos_order

def pyth_exp():
    return get_cfg().pyth_exp

def year():
    return get_cfg().year

def my_team_id():
    return get_cfg().my_team_id


def has_extended_ratings():
    """Check if the ratings table has extended columns (babip, hra, pbabip, prone)."""
    if has_request_context() and hasattr(g, "_has_ext_ratings"):
        return g._has_ext_ratings
    conn = get_db()
    cols = {row[1] for row in conn.execute("PRAGMA table_info(ratings)").fetchall()}
    conn.close()
    result = "babip" in cols
    if has_request_context():
        g._has_ext_ratings = result
    return result


def league_averages():
    """Load league_averages.json for the current league, or return zeros."""
    import json
    cfg = get_cfg()
    path = cfg.league_dir / "config" / "league_averages.json"
    if path.exists():
        return json.loads(path.read_text())
    return {
        "year": cfg.year, "teams_in_sample": 0,
        "batting": {"avg": 0, "obp": 0, "slg": 0, "ops": 0, "woba": 0,
                     "babip": 0, "iso": 0, "k_pct": 0, "bb_pct": 0},
        "pitching": {"era": 0, "fip": 0, "x_fip": 0, "k_pct": 0, "bb_pct": 0,
                      "k_bb_pct": 0, "babip": 0, "avg": 0, "obp": 0},
        "dollar_per_war": 0,
    }
