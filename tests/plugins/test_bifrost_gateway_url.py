"""A Bifrost gateway set only in config.yaml reaches every Bifrost plugin without touching os.environ.

The LLM provider used to seed ``BIFROST_BASE_URL`` into the process environment at import time, and
the sibling plugins (image gen, web, TTS, STT) read only that variable. The seed broke the import
side-effect invariants (it fired even with no Bifrost configured); each plugin now resolves the URL
itself through its ``_keyresolver``.
"""

from __future__ import annotations

import os

_GATEWAY = "https://eu.router.rove-ai.ru"


def test_config_gateway_reaches_plugins_without_seeding_env(monkeypatch):
    monkeypatch.delenv("BIFROST_BASE_URL", raising=False)
    monkeypatch.delenv("BIFROST_API_KEY", raising=False)
    monkeypatch.setenv("HERMES_CUSTOM_EUGW_API_KEY", "sk-bf-fixture")
    home = os.environ["HERMES_HOME"]
    with open(os.path.join(home, "config.yaml"), "w", encoding="utf-8") as fh:
        fh.write(f"providers:\n  eugw:\n    base_url: {_GATEWAY}/v1\n"
                 "    key_env: HERMES_CUSTOM_EUGW_API_KEY\n")

    from plugins.image_gen.bifrost import BifrostImageGenProvider
    from plugins.web.bifrost.provider import BifrostWebSearchProvider

    assert BifrostImageGenProvider()._resolve_base_url() == _GATEWAY
    assert BifrostWebSearchProvider()._get_client()._base == _GATEWAY
    assert "BIFROST_BASE_URL" not in os.environ
