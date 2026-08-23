"""Shared Bifrost key resolver.

All five Bifrost plugins (LLM, image_gen, web, transcription, TTS) need the
same virtual key (sk-bf-*).  Historically each plugin hard-coded
``os.environ.get("BIFROST_API_KEY")``.  But when the user added Bifrost as a
custom provider through the Desktop UI or ``hermes config set``, the key is
stored under a generated name like ``HERMES_CUSTOM_ROVE_API_KEY`` and
referenced from ``config.yaml`` via ``providers.<name>.key_env``.  The
plugins never saw it and the SETUP.md agent ended up writing a second copy
under ``BIFROST_API_KEY`` — two names, one value.

This module is the single source of truth.  Resolution order:

1.  ``BIFROST_API_KEY`` in the environment (explicit, still works).
2.  ``providers.<name>.key_env`` from ``config.yaml`` — scan every provider
    entry whose ``base_url`` points at the Bifrost gateway
    (``router.rove-ai.ru``) and read the env var named in ``key_env``.
3.  ``HERMES_CUSTOM_*_API_KEY`` env vars whose value starts with ``sk-bf-``
    (last-resort fallback so a key saved by the Desktop UI is found even
    without a matching ``providers`` section).

Usage::

    from _keyresolver import resolve_bifrost_key, resolve_bifrost_base_url

    key = resolve_bifrost_key()
    base = resolve_bifrost_base_url()
"""

from __future__ import annotations

import os
from typing import Optional

# Host fragment that identifies a Bifrost gateway endpoint in config.yaml.
# Checked as a substring (case-insensitive) of the base_url.
_BIFROST_HOST = "router.rove-ai.ru"

# The canonical env-var name.  Still the first thing we check so existing
# setups that write BIFROST_API_KEY keep working unchanged.
_CANONICAL_ENV = "BIFROST_API_KEY"

# Default gateway URL (with /v1 suffix for OpenAI-compatible endpoints).
_DEFAULT_BASE_URL_V1 = "https://router.rove-ai.ru/v1"


def _load_config() -> dict:
    """Load config.yaml without raising — plugins must never crash on config read."""
    try:
        from hermes_cli.config import load_config
        cfg = load_config()
        return cfg if isinstance(cfg, dict) else {}
    except Exception:
        return {}


def _is_bifrost_url(url: str) -> bool:
    """True if *url* looks like a Bifrost gateway endpoint."""
    if not url:
        return False
    return _BIFROST_HOST in url.lower()


def resolve_bifrost_key() -> str:
    """Return the Bifrost virtual key, or '' if not found.

    Resolution order:
    1. ``BIFROST_API_KEY`` env var (canonical).
    2. ``providers.*.key_env`` pointing at a Bifrost-URL entry.
    3. Any ``HERMES_CUSTOM_*_API_KEY`` env var whose value starts with ``sk-bf-``.
    """
    # 1 — canonical env var
    key = os.environ.get(_CANONICAL_ENV, "")
    if key:
        return key

    # 2 — scan providers section for a Bifrost entry with key_env
    cfg = _load_config()
    providers = cfg.get("providers")
    if isinstance(providers, dict):
        for _name, entry in providers.items():
            if not isinstance(entry, dict):
                continue
            base_url = (
                entry.get("base_url")
                or entry.get("api")
                or entry.get("url")
                or ""
            )
            if not _is_bifrost_url(str(base_url)):
                continue
            key_env = entry.get("key_env", "")
            if not key_env:
                continue
            val = os.environ.get(key_env, "")
            if val:
                return val

    # 3 — scan HERMES_CUSTOM_*_API_KEY env vars for an sk-bf-* value
    for env_name, env_val in os.environ.items():
        if not env_name.startswith("HERMES_CUSTOM_"):
            continue
        if not env_name.endswith("_API_KEY"):
            continue
        if env_val and env_val.startswith("sk-bf-"):
            return env_val

    return ""


def resolve_bifrost_base_url() -> str:
    """Return the Bifrost base URL (with ``/v1``), or the default.

    Resolution order:
    1. ``BIFROST_BASE_URL`` env var.
    2. ``providers.*.base_url`` for a Bifrost entry in config.yaml.
    3. Default ``https://router.rove-ai.ru/v1``.
    """
    # 1 — explicit env var
    env_url = os.environ.get("BIFROST_BASE_URL", "")
    if env_url:
        url = env_url.rstrip("/")
        if not url.endswith("/v1"):
            url += "/v1"
        return url

    # 2 — config providers section
    cfg = _load_config()
    providers = cfg.get("providers")
    if isinstance(providers, dict):
        for _name, entry in providers.items():
            if not isinstance(entry, dict):
                continue
            base_url = (
                entry.get("base_url")
                or entry.get("api")
                or entry.get("url")
                or ""
            )
            if _is_bifrost_url(str(base_url)):
                url = str(base_url).rstrip("/")
                if not url.endswith("/v1"):
                    url += "/v1"
                return url

    # 3 — default
    return _DEFAULT_BASE_URL_V1
