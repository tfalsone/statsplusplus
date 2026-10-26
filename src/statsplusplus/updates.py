"""Update check + "What's New" highlights.

Stage 1 of the in-app update experience (the one-click installer is deferred —
see docs/task_list.md). This module:

  - checks the public GitHub Releases API for a newer release (cached),
  - tracks the last version the user has seen (for the "What's New" popup),
  - reads the curated per-version highlights from docs/whats_new.json.

All state is stored in ``data/app_config.json`` under an ``updates`` key.
Network and file errors degrade gracefully (the feature is a nicety, never a
blocker): a failed check reports "unknown", not an error.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from statsplusplus.config.league_context import APP_CONFIG_PATH
from statsplusplus.version import current_version, is_newer

_RELEASES_API = "https://api.github.com/repos/tfalsone/statsplusplus/releases/latest"
_CACHE_TTL = 6 * 3600  # 6 hours — don't hammer the API or block page loads
_FETCH_TIMEOUT = 8  # seconds — a slow check must never stall the nav
# Cloudflare fronts GitHub and 403s the bare python-urllib User-Agent (error 1010);
# always send a descriptive UA on outbound requests.
_USER_AGENT = "Stats++ (https://github.com/tfalsone/statsplusplus)"

_WHATS_NEW_PATH = Path(__file__).resolve().parent.parent.parent / "docs" / "whats_new.json"


# ── app_config.json access (full JSON, not the string-coerced league reader) ──


def _read_config() -> dict:
    if APP_CONFIG_PATH.exists():
        try:
            data = json.loads(APP_CONFIG_PATH.read_text())
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _write_config(cfg: dict) -> None:
    APP_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    APP_CONFIG_PATH.write_text(json.dumps(cfg, indent=2) + "\n")


# ── Update check ──


def _fetch_latest_tag() -> str | None:
    """Fetch the latest release tag from GitHub, or None on any failure."""
    req = urllib.request.Request(_RELEASES_API, headers={
        "User-Agent": _USER_AGENT,
        "Accept": "application/vnd.github+json",
    })
    try:
        with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        tag = data.get("tag_name") or ""
        return tag or None
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError):
        return None


def check_for_update(force: bool = False) -> dict:
    """Return the current update status.

    Uses a cached result (stored in app_config under ``updates.cache``) unless it
    is stale or ``force`` is set. The cache holds only the latest tag + when it
    was fetched; the comparison against the installed version is always fresh.

    Returns a dict:
        {
          "current": "1.21.1",
          "latest": "1.22.0" | null,     # null = check failed / unknown
          "update_available": bool,
          "checked_at": <epoch seconds> | null,
          "release_url": "https://github.com/tfalsone/statsplusplus/releases/latest"
        }
    """
    cfg = _read_config()
    updates = cfg.get("updates") if isinstance(cfg.get("updates"), dict) else {}
    cache = updates.get("cache") if isinstance(updates.get("cache"), dict) else {}

    now = time.time()
    latest = cache.get("latest")
    checked_at = cache.get("checked_at")
    fresh = (
        not force
        and isinstance(checked_at, (int, float))
        and (now - checked_at) < _CACHE_TTL
    )

    if not fresh:
        fetched = _fetch_latest_tag()
        if fetched is not None:
            latest = fetched.lstrip("vV")
            checked_at = now
            updates["cache"] = {"latest": latest, "checked_at": checked_at}
            cfg["updates"] = updates
            _write_config(cfg)
        # On a failed fetch, keep whatever (possibly stale) cache we had.

    cur = current_version()
    available = bool(latest) and is_newer(latest, cur)
    return {
        "current": cur,
        "latest": latest or None,
        "update_available": available,
        "checked_at": checked_at or None,
        "release_url": "https://github.com/tfalsone/statsplusplus/releases/latest",
    }


# ── "What's New" ──


def _load_whats_new() -> list[dict]:
    """Load the curated per-version highlights (newest first)."""
    if not _WHATS_NEW_PATH.exists():
        return []
    try:
        data = json.loads(_WHATS_NEW_PATH.read_text())
        versions = data.get("versions", [])
        return versions if isinstance(versions, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def all_highlights() -> list[dict]:
    """Every curated version-highlights entry (newest first). For the changelog page."""
    return _load_whats_new()


def _last_seen_version() -> str:
    cfg = _read_config()
    updates = cfg.get("updates") if isinstance(cfg.get("updates"), dict) else {}
    return str(updates.get("last_seen_version", "") or "")


def whats_new_unseen() -> dict:
    """Highlights for versions newer than the user's last-seen version.

    On a brand-new install (no last_seen_version recorded) we do NOT pop the
    modal for the whole history — we silently mark the current version seen and
    return nothing, so the popup only ever appears after a genuine upgrade.

    Returns:
        {"show": bool, "current": "1.22.0", "entries": [<version highlight dicts>]}
    """
    cur = current_version()
    last_seen = _last_seen_version()
    if not last_seen:
        # First run on this install — establish a baseline, show nothing.
        mark_seen(cur)
        return {"show": False, "current": cur, "entries": []}

    if not is_newer(cur, last_seen):
        return {"show": False, "current": cur, "entries": []}

    entries = [e for e in _load_whats_new()
               if is_newer(str(e.get("version", "")), last_seen)
               and not is_newer(str(e.get("version", "")), cur)]
    return {"show": bool(entries), "current": cur, "entries": entries}


def mark_seen(version: str | None = None) -> None:
    """Record that the user has seen the What's New for ``version`` (default: current)."""
    version = version or current_version()
    cfg = _read_config()
    updates = cfg.get("updates") if isinstance(cfg.get("updates"), dict) else {}
    updates["last_seen_version"] = version
    cfg["updates"] = updates
    _write_config(cfg)
