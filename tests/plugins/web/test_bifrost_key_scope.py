"""The Bifrost key resolver reads the SERVED profile's key, like the core key resolver.

A served profile's ``.env`` lives in its secret scope, not in ``os.environ``. The resolver used to read
``os.environ`` only, so Bifrost web search reported "key not set" for a profile that had a key (and
fell back to the keyless tier), and a profile without one borrowed the launch profile's key.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from agent.secret_scope import build_profile_secret_scope, reset_secret_scope, set_secret_scope
from plugins.web.bifrost.provider import BifrostWebSearchProvider


@pytest.fixture
def two_homes(tmp_path, monkeypatch):
    launch, served = tmp_path / "launch", tmp_path / "served"
    for home in (launch, served):
        home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(launch))
    monkeypatch.delenv("BIFROST_API_KEY", raising=False)
    return launch, served


def _in_scope(home: Path):
    return set_secret_scope(build_profile_secret_scope(home), profile_home=str(home))


def test_served_profile_key_found_outside_os_environ(two_homes):
    _, served = two_homes
    (served / ".env").write_text("BIFROST_API_KEY=sk-bf-served\n", encoding="utf-8")
    token = _in_scope(served)
    try:
        assert BifrostWebSearchProvider().is_available()
    finally:
        reset_secret_scope(token)


def test_custom_key_never_borrowed_from_launch_env(two_homes, monkeypatch):
    _, served = two_homes
    monkeypatch.setenv("HERMES_CUSTOM_ROVE_API_KEY", "sk-bf-launch")
    (served / ".env").write_text("OTHER=1\n", encoding="utf-8")
    token = _in_scope(served)
    try:
        assert not BifrostWebSearchProvider().is_available()
    finally:
        reset_secret_scope(token)
