"""Bifrost edition: shared metrics stay off even for a profile that opted in before the kill switch.

Reads go through the real config.yaml of the hermetic HERMES_HOME, the way every gate reads it.
"""

from __future__ import annotations

import pytest

from hermes_cli.observability import relay_shared_metrics, shared_metrics_consent, shared_metrics_send_config
from hermes_constants import get_hermes_home


@pytest.fixture
def opted_in_profile(monkeypatch):
    monkeypatch.setattr(shared_metrics_send_config, "SHARED_METRICS_DISABLED", True)
    (get_hermes_home() / "config.yaml").write_text(
        "telemetry:\n  shared_metrics:\n    enabled: true\n    send: true\n", encoding="utf-8"
    )


@pytest.mark.usefixtures("opted_in_profile")
def test_an_opted_in_profile_neither_collects_nor_sends():
    assert relay_shared_metrics.enabled() is False
    resolved = relay_shared_metrics._resolved_send_config()
    assert (resolved.enabled, resolved.send) == (False, False)


def test_no_surface_offers_consent(monkeypatch):
    monkeypatch.setattr(shared_metrics_send_config, "SHARED_METRICS_DISABLED", True)
    # A fresh profile never answered: upstream would offer it on every surface.
    assert shared_metrics_consent._current_state() == {
        "enabled": False, "send": False, "decided": True, "reask": False,
    }
