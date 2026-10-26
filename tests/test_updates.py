"""Hermetic tests for the update-check + What's New logic (no network).

Covers version parsing/comparison, the cached update check (with the GitHub
fetch stubbed), and the "What's New" unseen-gating: first-run baseline, newer-
version surfacing, and dismiss.
"""

import json
import time

import pytest

from statsplusplus import updates, version


# ── version parsing / comparison ──


def test_parse_version_tolerates_prefix_and_suffix():
    assert version.parse_version("v1.21.1") == (1, 21, 1)
    assert version.parse_version("1.21.1") == (1, 21, 1)
    assert version.parse_version("1.22.0-rc1") == (1, 22, 0)
    assert version.parse_version("") == (0,)
    assert version.parse_version("garbage") == (0,)


def test_is_newer():
    assert version.is_newer("1.22.0", "1.21.1")
    assert version.is_newer("1.21.2", "1.21.1")
    assert version.is_newer("2.0.0", "1.99.99")
    assert not version.is_newer("1.21.1", "1.21.1")
    assert not version.is_newer("1.21.0", "1.21.1")


def test_current_version_is_a_dotted_string():
    v = version.current_version()
    assert version.parse_version(v) >= (1,)  # real version, not the 0.0.0 fallback


def test_installed_version_resolves_or_fallbacks():
    # Either a real installed version, or the 0.0.0 fallback — never raises.
    v = version.installed_version()
    assert isinstance(v, str) and v.count(".") >= 1


# ── fixtures: isolate app_config to a temp file, stub the network ──


@pytest.fixture
def tmp_config(tmp_path, monkeypatch):
    cfg_path = tmp_path / "app_config.json"
    monkeypatch.setattr(updates, "APP_CONFIG_PATH", cfg_path)
    return cfg_path


def _read(cfg_path):
    return json.loads(cfg_path.read_text()) if cfg_path.exists() else {}


# ── update check ──


def test_update_check_reports_available(tmp_config, monkeypatch):
    monkeypatch.setattr(updates, "current_version", lambda: "1.21.1")
    monkeypatch.setattr(updates, "_fetch_latest_tag", lambda: "v1.22.0")
    r = updates.check_for_update(force=True)
    assert r["current"] == "1.21.1"
    assert r["latest"] == "1.22.0"
    assert r["update_available"] is True
    # Result cached.
    assert _read(tmp_config)["updates"]["cache"]["latest"] == "1.22.0"


def test_update_check_no_update_when_current(tmp_config, monkeypatch):
    monkeypatch.setattr(updates, "current_version", lambda: "1.22.0")
    monkeypatch.setattr(updates, "_fetch_latest_tag", lambda: "v1.22.0")
    r = updates.check_for_update(force=True)
    assert r["update_available"] is False


def test_update_check_uses_cache_without_refetch(tmp_config, monkeypatch):
    monkeypatch.setattr(updates, "current_version", lambda: "1.21.1")
    calls = {"n": 0}

    def _fetch():
        calls["n"] += 1
        return "v1.22.0"

    monkeypatch.setattr(updates, "_fetch_latest_tag", _fetch)
    updates.check_for_update(force=True)   # fetch 1
    updates.check_for_update(force=False)  # fresh cache → no fetch
    assert calls["n"] == 1


def test_update_check_refetches_when_cache_stale(tmp_config, monkeypatch):
    monkeypatch.setattr(updates, "current_version", lambda: "1.21.1")
    calls = {"n": 0}
    monkeypatch.setattr(updates, "_fetch_latest_tag",
                        lambda: (calls.__setitem__("n", calls["n"] + 1), "v1.22.0")[1])
    updates.check_for_update(force=True)
    # Age the cache past the TTL.
    cfg = _read(tmp_config)
    cfg["updates"]["cache"]["checked_at"] = time.time() - (updates._CACHE_TTL + 10)
    tmp_config.write_text(json.dumps(cfg))
    updates.check_for_update(force=False)
    assert calls["n"] == 2


def test_update_check_failed_fetch_degrades_gracefully(tmp_config, monkeypatch):
    monkeypatch.setattr(updates, "current_version", lambda: "1.21.1")
    monkeypatch.setattr(updates, "_fetch_latest_tag", lambda: None)
    r = updates.check_for_update(force=True)
    assert r["latest"] is None
    assert r["update_available"] is False


# ── What's New gating ──


def test_whats_new_first_run_sets_baseline_shows_nothing(tmp_config, monkeypatch):
    monkeypatch.setattr(updates, "current_version", lambda: "1.21.1")
    r = updates.whats_new_unseen()
    assert r["show"] is False
    assert r["entries"] == []
    # Baseline recorded so a future genuine upgrade triggers the popup.
    assert _read(tmp_config)["updates"]["last_seen_version"] == "1.21.1"


def test_whats_new_shows_entries_after_upgrade(tmp_config, monkeypatch):
    # Seed last-seen older than current with curated entries in between.
    tmp_config.write_text(json.dumps({"updates": {"last_seen_version": "1.19.0"}}))
    monkeypatch.setattr(updates, "current_version", lambda: "1.21.1")
    monkeypatch.setattr(updates, "_load_whats_new", lambda: [
        {"version": "1.21.1", "highlights": ["a"]},
        {"version": "1.21.0", "highlights": ["b"]},
        {"version": "1.19.0", "highlights": ["seen already"]},
        {"version": "1.25.0", "highlights": ["future, not yet installed"]},
    ])
    r = updates.whats_new_unseen()
    assert r["show"] is True
    got = [e["version"] for e in r["entries"]]
    # Newer than last-seen AND not newer than current.
    assert got == ["1.21.1", "1.21.0"]


def test_whats_new_nothing_when_up_to_date(tmp_config, monkeypatch):
    tmp_config.write_text(json.dumps({"updates": {"last_seen_version": "1.21.1"}}))
    monkeypatch.setattr(updates, "current_version", lambda: "1.21.1")
    r = updates.whats_new_unseen()
    assert r["show"] is False


def test_mark_seen_records_current(tmp_config, monkeypatch):
    monkeypatch.setattr(updates, "current_version", lambda: "1.22.0")
    updates.mark_seen()
    assert _read(tmp_config)["updates"]["last_seen_version"] == "1.22.0"
