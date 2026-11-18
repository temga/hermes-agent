"""Bifrost AI Gateway — model-provider profile.

Routes all LLM requests through a single Bifrost gateway endpoint.
One virtual key (sk-bf-*) gives access to all upstream providers
(neuraldeep, tropass, turbocloud, routerai) with centralized rate
limits, budgets, and logging.

Environment variables:
    BIFROST_API_KEY   — virtual key (sk-bf-*), required
    BIFROST_BASE_URL  — gateway URL (default: https://router.rove-ai.ru/v1)

The Bifrost API is fully OpenAI Chat-Completions compatible, so a
basic ProviderProfile without hook overrides is sufficient.
"""

from __future__ import annotations

import os

from providers import register_provider
from providers.base import ProviderProfile

from ._keyresolver import _CANONICAL_ENV, _DEFAULT_BASE_URL_V1, _custom_key_names, _env


# Provider discovery imports this module and must read no config (upstream b4d8e4c332: a config
# backend that refuses reads raises SystemExit and would take the whole provider catalog down).
# So the import looks only at the environment and .env; the config.yaml ``providers:`` lookup in
# _keyresolver stays with the sibling Bifrost plugins, which run it at call time.
def _env_only_key() -> str:
    """BIFROST_API_KEY, else the first ``HERMES_CUSTOM_*_API_KEY`` holding an sk-bf-* key."""
    key = _env(_CANONICAL_ENV)
    if key:
        return key
    for name in sorted(_custom_key_names()):
        value = _env(name)
        if value.startswith("sk-bf-"):
            return value
    return ""


def _env_only_base_url() -> str:
    """BIFROST_BASE_URL (with /v1 appended when missing), else the default gateway."""
    url = _env("BIFROST_BASE_URL").rstrip("/")
    if not url:
        return _DEFAULT_BASE_URL_V1
    return url if url.endswith("/v1") else url + "/v1"


# Seed BIFROST_API_KEY so the core key resolver (which reads the profile's env_vars) finds a key
# the user saved under a custom-provider name (e.g. HERMES_CUSTOM_ROVE_API_KEY). Never while
# multiplexing: os.environ is shared by every served profile, and there is no profile scope to
# resolve against at import. The base URL is never seeded.
from agent.secret_scope import is_multiplex_active

if not is_multiplex_active() and not os.environ.get(_CANONICAL_ENV):
    _seeded = _env_only_key()
    if _seeded:
        os.environ[_CANONICAL_ENV] = _seeded

_DEFAULT_BASE_URL = _env_only_base_url()

# Curated model list, in preference order — the full catalog is dynamic (24+
# models across 4 upstream providers) and each sk-bf-* key reaches only part of
# it. The silent default (onboarding, /api/model/recommended-default) is the
# first entry the key's live /v1/models listing carries. "auto" leads: the
# gateway picks the upstream model itself. A key without it gets Qwen, not
# GLM: the gateway lists tropass/GLM-5.2 to keys it then answers 404 for, and
# the listing cannot tell. Users can set any model id in config.yaml and it
# will be passed through to the gateway.
_FALLBACK_MODELS = (
    "auto",
    "neuraldeep/qwen3.8-27b",
    "turbocloud/GLM-5.2",
    "tropass/GLM-5.2",
    # neuraldeep — reasoning + noreason variants
    "neuraldeep/gpt-oss-120b",
    "neuraldeep/qwen3.6-35b-a3b",
    "neuraldeep/qwen3.6-35b-a3b-noreason",
    "neuraldeep/qwen3.8-27b-noreason",
    "neuraldeep/kimi-k2.6",
    "neuraldeep/gemma-4-31b",
    "neuraldeep/gemma-4-31b-noreason",
    "neuraldeep/frida",
    # tropass
    "tropass/Qwen3.5-397B-A17B-FP8",
)

bifrost = ProviderProfile(
    name="bifrost",
    aliases=("bf", "gateway"),
    env_vars=("BIFROST_API_KEY",),
    display_name="Bifrost Gateway",
    description=(
        "Bifrost AI Gateway — единый шлюз: LLM, image gen, search. "
        "Один ключ sk-bf-* для всех провайдеров."
    ),
    signup_url="https://router.rove-ai.ru",
    # Resolved at import time; the profile dataclass stores a static string,
    # so a changed BIFROST_BASE_URL takes effect next session. A regional gateway
    # for this provider goes in BIFROST_BASE_URL or model.base_url.
    base_url=_DEFAULT_BASE_URL,
    fallback_models=_FALLBACK_MODELS,
    # Non-reasoning model for background/aux text tasks (compression, session
    # search, title generation, etc.). NOT used for vision — see below.
    default_aux_model="neuraldeep/qwen3.6-35b-a3b-noreason",
    supports_vision=True,
)


def _bifrost_default_vision_model() -> str | None:
    """Return a vision-capable model for the Bifrost gateway.

    The main chat model (e.g. turbocloud/GLM-5.2) is text-only —
    sending image input to it produces a cryptic upstream error. This
    override routes vision auto-detect to a known multimodal model so
    ``auxiliary.vision.provider: auto`` works out of the box.
    """
    return "neuraldeep/qwen3.8-27b"


# Patch the hook onto the profile instance. ProviderProfile.default_vision_model
# is an overridable method; we set it per-instance so the auto-detect chain in
# auxiliary_client._resolve_provider_vision_default() picks up our choice.
bifrost.default_vision_model = _bifrost_default_vision_model

register_provider(bifrost)
