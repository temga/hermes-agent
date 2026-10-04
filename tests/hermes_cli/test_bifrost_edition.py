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


def test_install_from_local_pack_keeps_one_loadable_plugins_section(tmp_path, monkeypatch):
    """The desktop's first launch hands its bundled pack to this step (``--from``): the config keeps
    the user's existing ``plugins`` keys and stays loadable, and a second run is a no-op."""
    from hermes_cli import bifrost_edition
    from hermes_cli.config import load_config

    home = tmp_path / ".hermes"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    (home / "config.yaml").write_text("plugins:\n  # deadline\n  clone_timeout_seconds: 120\n", encoding="utf-8")
    pack = tmp_path / "pack"
    for plugin in BIFROST_PLUGINS:
        (pack / plugin).mkdir(parents=True)
        (pack / plugin / "plugin.yaml").write_text("name: bifrost\n", encoding="utf-8")
    (pack / "_keyresolver.py").write_text("", encoding="utf-8")

    assert bifrost_edition.main(["--from", str(pack)]) == 0
    first = (home / "config.yaml").read_text(encoding="utf-8")
    assert bifrost_edition.main(["--from", str(pack)]) == 0

    assert (home / "config.yaml").read_text(encoding="utf-8") == first
    plugins = load_config()["plugins"]
    assert plugins["clone_timeout_seconds"] == 120
    assert set(BIFROST_PLUGINS) <= set(plugins["enabled"])
    assert all((home / "plugins" / plugin / "_keyresolver.py").is_file() for plugin in BIFROST_PLUGINS)
