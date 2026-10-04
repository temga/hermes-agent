"""``GET /api/model/recommended-default`` recommends only models the credential's listing carries.

A Bifrost key reaches part of the gateway's catalog; the curated list led with a model the key could
not use, ``/api/model/set`` rejected it against the live listing, and desktop onboarding stalled.
"""

from types import SimpleNamespace

import pytest

CURATED = ["vendor/unreachable", "vendor/second", "vendor/third"]


@pytest.fixture()
def recommend(monkeypatch):
    import hermes_cli.inventory as inventory
    import hermes_cli.models as models_mod
    import hermes_cli.runtime_provider as runtime_provider
    from hermes_cli.web_routers.models import get_recommended_default_model

    def call(*, listed, current_model="", current_provider="gw"):
        context = SimpleNamespace(current_model=current_model, current_provider=current_provider)
        monkeypatch.setattr(inventory, "load_picker_context", lambda: context)
        monkeypatch.setattr(inventory, "build_models_payload",
                            lambda _ctx: {"providers": [{"slug": "gw", "models": list(CURATED)}]})
        monkeypatch.setattr(runtime_provider, "resolve_runtime_provider",
                            lambda **_k: {"api_key": "k", "base_url": "https://gw.example/v1"})
        monkeypatch.setattr(models_mod, "fetch_api_models", lambda *_a, **_k: listed)
        return get_recommended_default_model(provider="gw")["model"]

    return call


def test_recommendation_is_the_first_curated_model_the_listing_carries(recommend):
    listed = ["vendor/third", "vendor/second", "vendor/embeddings"]
    assert recommend(listed=listed) == "vendor/second"
    # Without a listing there is nothing to narrow by: the curated order stands.
    assert recommend(listed=None) == "vendor/unreachable"


def test_configured_model_is_kept_only_while_the_listing_carries_it(recommend):
    assert recommend(listed=CURATED, current_model="vendor/third") == "vendor/third"
    assert recommend(listed=["vendor/second"], current_model="vendor/unreachable") == "vendor/second"
    assert recommend(listed=CURATED, current_model="vendor/third", current_provider="other") == "vendor/unreachable"
