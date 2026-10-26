"""Single source of truth for the app version + semantic-version comparison.

The installed version comes from the package metadata (populated from
``pyproject.toml`` at install time), so there is no hand-maintained string to
forget to bump. A source-tree fallback reads ``pyproject.toml`` directly for the
rare case of running uninstalled.
"""

from __future__ import annotations

import re
from pathlib import Path


def _pyproject_version() -> str | None:
    """Read the version from the source-tree pyproject.toml, or None."""
    try:
        root = Path(__file__).resolve().parent.parent.parent
        pyproject = root / "pyproject.toml"
        if pyproject.exists():
            for line in pyproject.read_text().splitlines():
                m = re.match(r'\s*version\s*=\s*["\']([^"\']+)["\']', line)
                if m:
                    return m.group(1)
    except Exception:
        pass
    return None


def current_version() -> str:
    """Return the app version (e.g. ``"1.21.1"``).

    The source-tree ``pyproject.toml`` is authoritative when present — it
    describes the code actually running, and avoids a stale version from a
    long-lived editable install whose metadata lags the tree. Falls back to the
    installed package metadata (the normal case for a zip/launcher install where
    the source tree may not be laid out as expected), then to ``"0.0.0"``.
    """
    v = _pyproject_version()
    if v:
        return v
    try:
        from importlib.metadata import version as _meta_version
        return _meta_version("statsplusplus")
    except Exception:
        return "0.0.0"


def installed_version() -> str:
    """Return the version pip last registered for the installed package.

    This is ``importlib.metadata`` only — it can lag the source tree in a
    long-lived editable install (pip skips reinstalling when it thinks the
    package is already satisfied). The launchers compare this to the shipped
    ``pyproject`` version to decide whether a reinstall is needed and what to
    report to the user. Returns ``"0.0.0"`` if not installed.
    """
    try:
        from importlib.metadata import version as _meta_version
        return _meta_version("statsplusplus")
    except Exception:
        return "0.0.0"


def parse_version(v: str) -> tuple[int, ...]:
    """Parse a version string into a comparable tuple of ints.

    Tolerates a leading ``v`` and trailing pre-release/build suffixes
    (``1.2.3-rc1`` → ``(1, 2, 3)``). Non-numeric or empty input → ``(0,)``.
    """
    if not v:
        return (0,)
    v = v.strip().lstrip("vV")
    # Keep the leading numeric dotted core only.
    core = re.split(r"[-+]", v, maxsplit=1)[0]
    parts = []
    for p in core.split("."):
        m = re.match(r"\d+", p)
        if not m:
            break
        parts.append(int(m.group(0)))
    return tuple(parts) if parts else (0,)


def is_newer(candidate: str, baseline: str) -> bool:
    """True if ``candidate`` is a strictly newer version than ``baseline``."""
    return parse_version(candidate) > parse_version(baseline)
