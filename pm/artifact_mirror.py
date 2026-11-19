"""Public, content-addressed copies of reviewed binary inputs."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re

from pm.downloader import Source
from pm.index_config import npm_registry, npm_registry_url

_LAYOUT = json.loads(Path(__file__).with_name("artifact-mirror.json").read_text(encoding="utf-8-sig"))
KEY_PREFIX = _LAYOUT["prefix"]
PUBLIC_PREFIX = _LAYOUT["origin"] + "/" + KEY_PREFIX
# Bifrost edition: the fork's own copies, GitHub release assets named by sha256
# (scripts/bifrost/mirror_pm_inputs.py). Installs from Russian networks reach GitHub (the
# installer clones from it) but often not martin-riedl.de, and Cloudflare answers 403 for
# hermes-assets.nousresearch.com, so a required tool like ffmpeg failed the whole install.
FORK_MIRROR_PREFIX = "https://github.com/temga/hermes-agent/releases/download/pm-mirror/"


def object_key(sha256: str) -> str:
    if not isinstance(sha256, str) or not re.fullmatch(r"[a-f0-9]{64}", sha256):
        raise ValueError("A pinned input requires a full lowercase SHA256")
    return KEY_PREFIX + sha256


def mirror_url(sha256: str) -> str:
    object_key(sha256)
    return PUBLIC_PREFIX + sha256


def fork_mirror_url(sha256: str) -> str:
    object_key(sha256)
    return FORK_MIRROR_PREFIX + sha256


def pinned_source(url: str, dest: Path, sha256: str) -> Source:
    archive = mirror_url(sha256)
    # The lock records registry.npmjs.org; a user's npm mirror serves the same pinned bytes (#123132).
    configured = npm_registry_url(url, os.environ)
    # Bifrost edition: the fork mirror goes first, ahead of an upstream host that can stall a
    # blocked network for minutes before the fallback runs; a digest it lacks is a quick 404.
    # A registry the user configured still wins, and the hash guards every host.
    if configured != url:
        urls = (configured, fork_mirror_url(sha256), archive)
    else:
        urls = (fork_mirror_url(sha256), url, archive)
    first, *rest = dict.fromkeys(urls)
    # A LAN registry is often plain http (#150032). Only its rewritten URL may use it.
    registry = npm_registry(os.environ) if configured != url else ""
    return Source(first, dest, sha256, fallbacks=tuple(rest),
                  http_mirror=registry if registry.startswith("http://") else "")
