"""Bifrost edition first-install step: Bifrost Gateway plugins + one-key service config.

Shared by ``scripts/install.sh`` and ``scripts/install.ps1`` (stage ``bifrost-plugins``), run through
the installation launcher: ``hermes --run-module hermes_cli.bifrost_edition``.

Clones temga/hermes-plugin-bifrost-gateway, copies its five plugins into ``$HERMES_HOME/plugins``,
enables them, and points every service (LLM, image gen, web, STT, TTS) at Bifrost so one
``sk-bf-*`` key powers everything. Idempotent via a stamp file; never fails the install.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

from hermes_constants import get_hermes_home

BIFROST_REPO_URL = "https://github.com/temga/hermes-plugin-bifrost-gateway.git"
# Installs before the Bifrost build moved to the fork's main pinned this branch; it is kept as a
# mirror of main for them, but new configs follow main (the default) and drop the legacy pin.
LEGACY_BIFROST_BRANCH = "bifrost-edition"
# category/name, mirroring install.sh in hermes-plugin-bifrost-gateway (single flat repo, no submodules).
BIFROST_PLUGINS = (
    "model-providers/bifrost",
    "image_gen/bifrost",
    "web/bifrost",
    "transcription/bifrost",
    "tts/bifrost",
)


def _log(message: str) -> None:
    print(f"-> {message}", flush=True)


def _sync_plugin_repo(clone_dir: Path) -> bool:
    """Clone (or fast-forward) the plugin pack; False when it is unavailable."""
    if (clone_dir / ".git").is_dir():
        _log("Updating Bifrost plugin cache...")
        subprocess.run(["git", "-C", str(clone_dir), "pull", "--ff-only"], capture_output=True, check=False)
        return True
    _log("Cloning Bifrost plugin pack...")
    shutil.rmtree(clone_dir, ignore_errors=True)
    result = subprocess.run(["git", "clone", "--depth", "1", BIFROST_REPO_URL, str(clone_dir)],
                            capture_output=True, text=True, check=False)
    if result.returncode != 0:
        _log(f"Failed to clone Bifrost plugins ({result.stderr.strip()}); install them later from {BIFROST_REPO_URL}")
        return False
    return True


def install_plugins(home: Path) -> int:
    """Copy the plugin directories into ``home/plugins``; returns how many were installed."""
    plugins_dir = home / "plugins"
    clone_dir = home / ".bifrost-cache"
    plugins_dir.mkdir(parents=True, exist_ok=True)
    if not _sync_plugin_repo(clone_dir):
        return 0
    key_resolver = clone_dir / "_keyresolver.py"
    copied = 0
    for plugin in BIFROST_PLUGINS:
        src, dest = clone_dir / plugin, plugins_dir / plugin
        if not (src / "plugin.yaml").is_file():
            _log(f"Source not found: {src / 'plugin.yaml'}")
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.rmtree(dest, ignore_errors=True)
        shutil.copytree(src, dest, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))
        # Every plugin carries the shared key resolver.
        if key_resolver.is_file():
            shutil.copy2(key_resolver, dest / "_keyresolver.py")
        copied += 1
        _log(f"Installed plugin: {plugin}")
    return copied


def configure(cfg: dict) -> dict:
    """Enable the plugins and route every service through Bifrost (mutates and returns ``cfg``)."""
    plugins = cfg.setdefault("plugins", {})
    enabled = plugins.get("enabled")
    enabled = [name for name in enabled if isinstance(name, str)] if isinstance(enabled, list) else []
    plugins["enabled"] = enabled + [name for name in BIFROST_PLUGINS if name not in enabled]

    # base_url MUST be the Bifrost gateway: _keyresolver.py only resolves the key when the host is
    # router.rove-ai.ru, so the template's openrouter.ai URL 403s at runtime.
    model = cfg.setdefault("model", {})
    model.update(provider="bifrost", default="turbocloud/GLM-5.2", base_url="https://router.rove-ai.ru/v1")
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
    stamp = home / "plugins" / ".bifrost-plugins-stamp"
    if stamp.is_file():
        _log("Bifrost plugins already installed (stamp found), skipping")
        return 0
    _log("Installing Bifrost Gateway plugins...")
    copied = install_plugins(home)
    if copied:
        from hermes_cli.config import load_config, save_config

        save_config(configure(load_config()), merge_existing=True)
        _log("Configured all service providers -> bifrost")
    stamp.parent.mkdir(parents=True, exist_ok=True)
    stamp.write_text(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) + "\n", encoding="utf-8")
    _log(f"Installed {copied} Bifrost plugins; one BIFROST_API_KEY (sk-bf-*) powers LLM + image gen + web + STT + TTS")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # The plugin pack is optional: never fail the install over it.
        print(f"[!] Bifrost plugin setup failed: {exc}", file=sys.stderr)
        sys.exit(0)
