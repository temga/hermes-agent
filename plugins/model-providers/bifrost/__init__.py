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

from ._keyresolver import _is_bifrost_url, resolve_bifrost_key, resolve_bifrost_base_url

# Seed BIFROST_API_KEY / BIFROST_BASE_URL from config.yaml providers section
# so the core key resolver (which reads env_vars from the profile) finds the
# key even when the user added Bifrost as a custom provider with a different
# env-var name (e.g. HERMES_CUSTOM_ROVE_API_KEY).  This runs at import time,
# before the agent init reads the profile's env_vars.
if not os.environ.get("BIFROST_API_KEY"):
    _seeded = resolve_bifrost_key()
    if _seeded:
        os.environ["BIFROST_API_KEY"] = _seeded
if not os.environ.get("BIFROST_BASE_URL"):
    _seeded_url = resolve_bifrost_base_url()
    if _seeded_url:
        os.environ["BIFROST_BASE_URL"] = _seeded_url

# Default gateway URL (local Bifrost instance)
_DEFAULT_BASE_URL = os.environ.get("BIFROST_BASE_URL", "https://router.rove-ai.ru/v1")

# ``auto`` is not an upstream model: a routing rule on router.rove-ai.ru (``model == "auto"``)
# sends it down a fallback chain (qwen3.8-27b -> kimi-k2.6 -> gpt-oss-120b), so the gateway picks
# a model that is up right now. The gateway's /v1/models never lists it, hence fetch_models adds it.
AUTO_MODEL = "auto"
# The smallest window in the auto chain (qwen3.8-27b / gpt-oss-120b: 128K), so a conversation
# still fits after the gateway falls back to another model.
_AUTO_CONTEXT_LENGTH = 131_072

# Curated model list, in preference order — the full catalog is dynamic (24+
# models across 4 upstream providers) and each sk-bf-* key reaches only part of
# it. The silent default (onboarding, /api/model/recommended-default) is the
# first entry the key's catalog (fetch_models) carries: ``auto`` on the shared
# gateway, else the first listed model. Users can set any model id in
# config.yaml and it will be passed through to the gateway.
_FALLBACK_MODELS = (
    AUTO_MODEL,
    "neuraldeep/qwen3.8-27b",
    "neuraldeep/kimi-k2.6",
    "neuraldeep/gpt-oss-120b",
    "turbocloud/GLM-5.2",
    "tropass/GLM-5.2",
    # neuraldeep — reasoning + noreason variants
    "neuraldeep/qwen3.6-35b-a3b",
    "neuraldeep/qwen3.6-35b-a3b-noreason",
    "neuraldeep/qwen3.8-27b-noreason",
    "neuraldeep/gemma-4-31b",
    "neuraldeep/gemma-4-31b-noreason",
    "neuraldeep/frida",
    # tropass
    "tropass/Qwen3.5-397B-A17B-FP8",
)


class BifrostProfile(ProviderProfile):
    """Bifrost gateway: OpenAI-compatible, plus the gateway-routed ``auto`` model."""

    def fetch_models(
        self, *, api_key: str | None = None, base_url: str | None = None, timeout: float = 8.0
    ) -> list[str] | None:
        models = super().fetch_models(api_key=api_key, base_url=base_url, timeout=timeout)
        # Only the shared gateway carries the auto routing rule; a self-hosted Bifrost would reject it.
        if models is None or AUTO_MODEL in models or not _is_bifrost_url(base_url or self.base_url or ""):
            return models
        return [AUTO_MODEL, *models]

    def get_model_context_length(self, model: str) -> int | None:
        return _AUTO_CONTEXT_LENGTH if model == AUTO_MODEL else None

    def default_vision_model(self) -> str | None:
        """turbocloud/GLM-5.2 is text-only and the auto chain may land on a model that is too, so
        vision auto-detect (``auxiliary.vision.provider: auto``) goes to a known multimodal model
        instead of a cryptic upstream error."""
        return "neuraldeep/qwen3.8-27b"


bifrost = BifrostProfile(
    name="bifrost",
    aliases=("bf", "gateway"),
    env_vars=("BIFROST_API_KEY",),
    display_name="Bifrost Gateway",
    description=(
        "Bifrost AI Gateway — единый шлюз: LLM, image gen, search. "
        "Один ключ sk-bf-* для всех провайдеров."
    ),
    signup_url="https://router.rove-ai.ru",
    # Resolve base URL at import time from env (or fall back to default).
    # The profile dataclass stores a static string; if the user sets
    # BIFROST_BASE_URL in .env, it takes effect on next session start.
    base_url=os.environ.get("BIFROST_BASE_URL", _DEFAULT_BASE_URL),
    fallback_models=_FALLBACK_MODELS,
    # Non-reasoning model for background/aux text tasks (compression, session
    # search, title generation, etc.). NOT used for vision — see default_vision_model.
    default_aux_model="neuraldeep/qwen3.6-35b-a3b-noreason",
    supports_vision=True,
)

register_provider(bifrost)
