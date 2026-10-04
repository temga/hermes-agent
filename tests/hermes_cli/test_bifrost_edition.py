from pathlib import Path

from hermes_cli.bifrost_edition import BIFROST_PLUGINS, configure

_BUNDLED = Path(__file__).resolve().parents[2] / "plugins"


def test_configure_routes_services_through_bifrost():
    cfg = configure({"model": {"provider": "openrouter", "base_url": "https://openrouter.ai/api/v1"}})
    assert cfg["model"]["provider"] == "bifrost"
    assert cfg["model"]["base_url"] == "https://router.rove-ai.ru/v1"
    assert cfg["web"] == {"search_backend": "bifrost", "extract_backend": "bifrost"}
    assert cfg["stt"]["bifrost"]["language"] == "ru"
    assert cfg["skills"]["hub_url"] == "https://hub.rove-ai.ru"
    assert "branch" not in cfg.get("updates", {})


def test_configure_drops_legacy_branch_pin_only():
    assert "branch" not in configure({"updates": {"branch": "bifrost-edition"}})["updates"]
    assert configure({"updates": {"branch": "my-fork"}})["updates"]["branch"] == "my-fork"


def test_bundled_plugins_win_over_pre_bundle_copies_and_load_unlisted(tmp_path, monkeypatch):
    """A home that older builds filled with plugin copies ends up on the bundled plugins: the step drops
    the copies (they would shadow the bundled ones forever), keeps the user's config and stays a no-op
    afterwards, and the bundled backends load without any ``plugins.enabled`` entry."""
    from hermes_cli import bifrost_edition
    from hermes_cli.config import load_config
    from hermes_cli.plugins import discover_plugins, get_plugin_manager

    home = tmp_path / ".hermes"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    (home / "config.yaml").write_text("plugins:\n  # deadline\n  clone_timeout_seconds: 120\n", encoding="utf-8")
    for plugin in BIFROST_PLUGINS:
        (home / "plugins" / plugin).mkdir(parents=True)
        (home / "plugins" / plugin / "plugin.yaml").write_text("name: stale-copy\nkind: backend\n", encoding="utf-8")
    (home / ".bifrost-cache" / ".git").mkdir(parents=True)  # the pack clone the old installer copied from

    assert bifrost_edition.main() == 0
    first = (home / "config.yaml").read_text(encoding="utf-8")
    assert bifrost_edition.main() == 0

    assert (home / "config.yaml").read_text(encoding="utf-8") == first
    assert load_config()["plugins"]["clone_timeout_seconds"] == 120
    assert not any((home / "plugins" / plugin).exists() for plugin in BIFROST_PLUGINS)
    assert not (home / ".bifrost-cache").exists()

    discover_plugins(force=True)
    loaded = {p["key"]: p for p in get_plugin_manager().list_plugins()}
    backends = [plugin for plugin in BIFROST_PLUGINS if not plugin.startswith("model-providers/")]
    for key in backends:
        assert loaded[key]["source"] == "bundled", key
        assert loaded[key]["enabled"] and not loaded[key]["error"], (key, loaded[key])


def test_key_resolver_copies_match():
    """Each plugin imports its own ``_keyresolver.py`` (the standalone pack ships one shared copy), so the
    bundled copies must not drift apart."""
    copies = {plugin: (_BUNDLED / plugin / "_keyresolver.py").read_text(encoding="utf-8") for plugin in BIFROST_PLUGINS}
    assert len(set(copies.values())) == 1, sorted(copies)


def test_default_model_is_in_the_bifrost_catalog(monkeypatch):
    """A fresh install's default must be a model the bifrost provider offers on the shared gateway even
    though the gateway's /v1/models omits it (``auto`` is a routing rule there), while a self-hosted
    Bifrost's listing passes through untouched."""
    from providers import get_provider_profile
    from providers.base import ProviderProfile

    listing = ["neuraldeep/qwen3.8-27b", "neuraldeep/kimi-k2.6"]
    monkeypatch.setattr(ProviderProfile, "fetch_models", lambda self, **_kwargs: list(listing))
    profile = get_provider_profile("bifrost")
    model = configure({})["model"]

    assert model["default"] in profile.fetch_models(api_key="sk-bf-test", base_url=model["base_url"])
    assert profile.fetch_models(api_key="sk-bf-test", base_url="https://bifrost.example/v1") == listing
