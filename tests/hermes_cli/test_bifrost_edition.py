from hermes_cli.bifrost_edition import BIFROST_PLUGINS, configure


def test_configure_enables_plugins_without_duplicates():
    cfg = configure({"plugins": {"enabled": ["other", "web/bifrost"]}})
    enabled = cfg["plugins"]["enabled"]
    assert enabled[0] == "other"
    assert sorted(set(enabled)) == sorted(enabled)
    assert set(BIFROST_PLUGINS) <= set(enabled)


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
