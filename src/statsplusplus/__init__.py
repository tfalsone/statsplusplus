"""Stats++ — Assistant GM dashboard for OOTP Baseball / StatsPlus leagues."""

from statsplusplus.version import current_version

# Single source of truth: the installed package metadata (from pyproject.toml).
# Do not hand-maintain this string — it will drift from the real release version.
__version__ = current_version()
