"""Smoke tests for packaging interfaces.

These guard the class of bug that shipped silently after the package refactor:
entry points pointing at a non-existent ``main()``. Cheap to run, no I/O.

Reads the installed ``console_scripts`` entry points via
``importlib.metadata`` (stdlib on every supported Python) and asserts every
target resolves to a callable — nothing is mocked, the real modules are
imported. Reading the installed metadata (rather than parsing the source
pyproject) also verifies the package was installed with its scripts.
"""

from __future__ import annotations

import importlib
from importlib import metadata

import pytest


def _entry_points() -> dict[str, str]:
    eps = metadata.entry_points(group="console_scripts")
    return {ep.name: ep.value for ep in eps if ep.name.startswith("spp-")}


def test_entry_points_present():
    eps = _entry_points()
    assert eps, "no spp-* console_scripts entry points found (package not installed?)"


@pytest.mark.parametrize("name,target", sorted(_entry_points().items()))
def test_entry_point_resolves_to_callable(name: str, target: str):
    """Every `spp-*` entry point must resolve to a callable `main`."""
    module_path, _, attr = target.partition(":")
    assert attr, f"{name}: entry point '{target}' has no ':function' part"
    mod = importlib.import_module(module_path)
    fn = getattr(mod, attr, None)
    assert fn is not None, f"{name}: {module_path} has no attribute '{attr}'"
    assert callable(fn), f"{name}: {target} is not callable"
