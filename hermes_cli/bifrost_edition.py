"""Bifrost edition: one-key service config, and cleanup of pre-bundle plugin copies.

The five Bifrost plugins ship in-tree (``plugins/<category>/bifrost/``) and update with the build.
This step points every service (LLM, image gen, web, STT, TTS) at Bifrost so one ``sk-bf-*`` key
powers everything. It runs once per home (stamp file) through the installation launcher —
``hermes --run-module hermes_cli.bifrost_edition`` — from ``scripts/install.sh`` /
``scripts/install.ps1`` (stage ``bifrost-plugins``) and the desktop's first launch; it never fails
the install. The config write goes through ``save_config``: one YAML-aware writer for all callers.

Earlier builds copied the plugins into ``$HERMES_HOME/plugins/``. Such a copy shadows the bundled one
(user > bundled) and pins the user to the version of their first install, so ``remove_legacy_copies``
deletes it — on every run of this step and after every ``hermes update``, for every profile.
The standalone pack (temga/hermes-plugin-bifrost-gateway, for stock Hermes) is exported from this
tree by ``scripts/bifrost/sync_plugin_pack.py``.
"""
from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

from hermes_constants import get_hermes_home

# Installs before the Bifrost build moved to the fork's main pinned this branch; it is kept as a
# mirror of main for them, but new configs follow main (the default) and drop the legacy pin.
LEGACY_BIFROST_BRANCH = "bifrost-edition"
# category/name under plugins/ — the same layout the standalone pack uses.
BIFROST_PLUGINS = (
    "model-providers/bifrost",
    "image_gen/bifrost",
    "web/bifrost",
    "transcription/bifrost",
    "tts/bifrost",
)
# Written once the services are configured; its presence makes the config step a no-op.
STAMP = Path("plugins") / ".bifrost-plugins-stamp"
# Desktops that configured the services themselves (before this step existed) left this one.
_LEGACY_DESKTOP_STAMP = Path(".bifrost-plugins-installed")
# The plugin pack clone the pre-bundle installer kept for its copies.
_LEGACY_CLONE_DIR = Path(".bifrost-cache")


def _log(message: str) -> None:
    print(f"-> {message}", flush=True)


def remove_legacy_copies(home: Path) -> list[str]:
    """Delete the pre-bundle plugin copies (and their source clone) under *home*; returns what was removed."""
    removed = []
    for plugin in BIFROST_PLUGINS:
        copy = home / "plugins" / plugin
        if copy.is_dir():
            shutil.rmtree(copy)
            removed.append(plugin)
    shutil.rmtree(home / _LEGACY_CLONE_DIR, ignore_errors=True)
    return removed


def remove_legacy_copies_all_profiles() -> list[str]:
    """``hermes update`` hook: clean every profile home; returns ``<profile>: <plugin>`` lines."""
    from hermes_cli.profiles import list_profiles

    return [f"{profile.name}: {plugin}" for profile in list_profiles()
            for plugin in remove_legacy_copies(profile.path)]


def configure(cfg: dict) -> dict:
    """Route every service through Bifrost (mutates and returns ``cfg``)."""
    # No `plugins.enabled` entries: bundled backends and model providers load without them.

    # base_url MUST be the Bifrost gateway: _keyresolver.py only resolves the key when the host is
    # router.rove-ai.ru, so the template's openrouter.ai URL 403s at runtime.
    model = cfg.get("model")
    if not isinstance(model, dict):  # the bare-string form (`model: name`) is replaced below anyway
        model = cfg["model"] = {}
    model.update(provider="bifrost", default="auto", base_url="https://router.rove-ai.ru/v1")
    cfg.setdefault("image_gen", {})["provider"] = "bifrost"
    cfg.setdefault("web", {}).update(search_backend="bifrost", extract_backend="bifrost")
    stt = cfg.setdefault("stt", {})
    stt["provider"] = "bifrost"
    # language: ru is critical — the global default is "en".
    stt.setdefault("bifrost", {}).update(model="neuraldeep/whisper-podlodka-turbo", language="ru")
    tts = cfg.setdefault("tts", {})
    tts["provider"] = "bifrost"
    tts.setdefault("bifrost", {})["model"] = "espeech-tts"
    # The default Skills Hub (hermes-agent.nousresearch.com) is 403-blocked by CDN geofencing in RF.
    cfg.setdefault("skills", {})["hub_url"] = "https://hub.rove-ai.ru"
    updates = cfg.get("updates")
    if isinstance(updates, dict) and updates.get("branch") == LEGACY_BIFROST_BRANCH:
        del updates["branch"]
    return cfg


def main() -> int:
    home = get_hermes_home()
    for plugin in remove_legacy_copies(home):
        _log(f"Removed pre-bundle plugin copy (the build ships it now): {plugin}")
    if any((home / done).is_file() for done in (STAMP, _LEGACY_DESKTOP_STAMP)):
        _log("Bifrost services already configured (stamp found), skipping")
        return 0
    from hermes_cli.config import load_config, save_config

    save_config(configure(load_config()), merge_existing=True)
    stamp = home / STAMP
    stamp.parent.mkdir(parents=True, exist_ok=True)
    stamp.write_text(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) + "\n", encoding="utf-8")
    _log("Configured all service providers -> bifrost; one BIFROST_API_KEY (sk-bf-*) powers LLM + image gen + web + STT + TTS")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # Bifrost setup is optional: never fail the install over it.
        print(f"[!] Bifrost setup failed: {exc}", file=sys.stderr)
        sys.exit(0)
