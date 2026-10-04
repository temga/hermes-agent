"""Bifrost image generation backend.

Routes image generation through the Bifrost gateway's OpenAI-compatible
``POST /v1/images/generations`` endpoint. Uses the same ``BIFROST_API_KEY``
(sk-bf-*) as the LLM provider — no separate credentials needed.

Configuration (config.yaml)::

    image_gen:
      provider: bifrost
      model: openai/gpt-image-2          # default model
      bifrost:
        base_url: https://router.rove-ai.ru  # optional override (without /v1)

Environment variables::

    BIFROST_API_KEY=sk-bf-...            # required
    BIFROST_BASE_URL=https://router.rove-ai.ru/v1  # optional, for non-default gateway

Output: base64-encoded images saved to ``$HERMES_HOME/cache/images/``.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import requests

from agent.image_gen_provider import (
    DEFAULT_ASPECT_RATIO,
    ImageGenProvider,
    error_response,
    normalize_reference_images,
    resolve_aspect_ratio,
    save_b64_image,
    save_url_image,
    success_response,
)

from ._keyresolver import resolve_bifrost_key

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_MODEL = "routerai/openai/gpt-image-2"

_DEFAULT_BASE_URL = "https://router.rove-ai.ru"

# Aspect ratio → OpenAI image API size mapping.
# Bifrost passes these through to the upstream provider (routerai).
_ASPECT_TO_SIZE = {
    "landscape": "1536x1024",
    "square": "1024x1024",
    "portrait": "1024x1536",
}

# Curated model catalog — Bifrost requires provider prefix (routerai/)
# for image models. The gateway proxies to routerai which offers 38+ models.
# Users can set any model id in config.yaml as long as it has the routerai/ prefix.
_MODELS: Dict[str, Dict[str, Any]] = {
    "routerai/openai/gpt-image-2": {
        "display": "GPT Image 2",
        "speed": "~15s",
        "strengths": "High quality, strong prompt adherence, text-in-image",
        "price": "~1 ₽/img",
    },
    "routerai/openai/gpt-image-1": {
        "display": "GPT Image 1 (legacy)",
        "speed": "~15s",
        "strengths": "Previous generation, may be deprecated",
        "price": "~1 ₽/img",
    },
    "routerai/black-forest-labs/flux.2-klein": {
        "display": "Flux 2 Klein",
        "speed": "~5s",
        "strengths": "Fast, photorealistic, good for landscapes",
        "price": "~0.5 ₽/img",
    },
    "routerai/black-forest-labs/flux.2-pro": {
        "display": "Flux 2 Pro",
        "speed": "~10s",
        "strengths": "Top quality, best prompt adherence",
        "price": "~2 ₽/img",
    },
    "routerai/bytedance/seedream-4.0": {
        "display": "Seedream 4.0",
        "speed": "~8s",
        "strengths": "Strong aesthetic quality, good for art",
        "price": "~0.8 ₽/img",
    },
}


class BifrostImageGenProvider(ImageGenProvider):
    """Image generation through Bifrost gateway."""

    @property
    def name(self) -> str:
        return "bifrost"

    @property
    def display_name(self) -> str:
        return "Bifrost Gateway"

    def is_available(self) -> bool:
        return bool(resolve_bifrost_key())

    def list_models(self) -> list[dict]:
        return [
            {"id": mid, "display": m["display"], "speed": m["speed"],
             "strengths": m["strengths"], "price": m["price"]}
            for mid, m in _MODELS.items()
        ]

    def default_model(self) -> str | None:
        return DEFAULT_MODEL

    def get_setup_schema(self) -> dict:
        return {
            "name": "Bifrost Gateway",
            "badge": "free",
            "env_vars": [
                {"key": "BIFROST_API_KEY", "prompt": "Bifrost virtual key (sk-bf-*)",
                 "url": "https://router.rove-ai.ru", "secret": True},
            ],
        }

    def capabilities(self) -> dict:
        return {"modalities": ["text", "image"], "max_reference_images": 4}

    def _resolve_base_url(self) -> str:
        """Resolve gateway base URL from env or config."""
        # BIFROST_BASE_URL may include /v1 or not — strip it for image endpoint
        url = os.environ.get("BIFROST_BASE_URL", "")
        if not url:
            url = _DEFAULT_BASE_URL
        # Strip trailing /v1 if present (we add it in the request path)
        if url.endswith("/v1"):
            url = url[:-3]
        return url.rstrip("/")

    def _resolve_model(self, model: str | None) -> str:
        if model:
            return model
        # Check provider-specific config: image_gen.bifrost.model
        cfg_model = os.environ.get("BIFROST_IMAGE_MODEL", "")
        if cfg_model:
            return cfg_model
        return DEFAULT_MODEL

    def generate(
        self,
        prompt: str,
        aspect_ratio: str = DEFAULT_ASPECT_RATIO,
        *,
        image_url: str | None = None,
        reference_image_urls: list[str] | None = None,
        model: str | None = None,
        **kwargs,
    ) -> dict:
        """Generate an image via Bifrost gateway."""
        api_key = resolve_bifrost_key()
        if not api_key:
            return error_response(
                error="Bifrost key not found (set BIFROST_API_KEY or add a Bifrost custom provider)",
                error_type="auth_required",
                provider=self.name,
                model=model or DEFAULT_MODEL,
                prompt=prompt,
                aspect_ratio=aspect_ratio,
            )

        base_url = self._resolve_base_url()
        resolved_model = self._resolve_model(model)
        # resolve_aspect_ratio clamps to valid set; then map to pixel size
        ar = resolve_aspect_ratio(aspect_ratio)
        size = _ASPECT_TO_SIZE.get(ar, _ASPECT_TO_SIZE["square"])

        # Build request body — OpenAI-compatible
        body: Dict[str, Any] = {
            "model": resolved_model,
            "prompt": prompt,
            "n": 1,
            "size": size,
            "response_format": "b64_json",
        }

        # Image-to-image: if reference images provided
        # normalize_reference_images accepts a single value (string or list)
        refs_source = image_url if image_url else reference_image_urls
        refs = normalize_reference_images(refs_source)
        if refs:
            # OpenAI gpt-image-1 edit format — Bifrost proxies to routerai
            body["input_references"] = refs
            modality = "image"
        else:
            modality = "text"

        url = f"{base_url}/v1/images/generations"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        try:
            resp = requests.post(url, json=body, headers=headers, timeout=120)
            if resp.status_code != 200:
                error_msg = resp.text[:500]
                logger.error("Bifrost image gen failed: %s %s", resp.status_code, error_msg)
                return error_response(
                    error=f"Gateway error {resp.status_code}: {error_msg}",
                    error_type="api_error",
                    provider=self.name,
                    model=resolved_model,
                    prompt=prompt,
                    aspect_ratio=aspect_ratio,
                )

            data = resp.json()
            images = data.get("data", [])
            if not images:
                return error_response(
                    error="Empty response from gateway",
                    error_type="empty_response",
                    provider=self.name,
                    model=resolved_model,
                    prompt=prompt,
                    aspect_ratio=aspect_ratio,
                )

            # Process first image
            img_data = images[0]
            b64 = img_data.get("b64_json")
            img_url = img_data.get("url")

            if b64:
                saved = save_b64_image(b64, prefix="bifrost")
            elif img_url:
                saved = save_url_image(img_url, prefix="bifrost")
            else:
                return error_response(
                    error="No image data in response",
                    error_type="empty_response",
                    provider=self.name,
                    model=resolved_model,
                    prompt=prompt,
                    aspect_ratio=aspect_ratio,
                )

            return success_response(
                image=str(saved),
                model=resolved_model,
                prompt=prompt,
                aspect_ratio=aspect_ratio,
                provider=self.name,
                modality=modality,
            )

        except requests.Timeout:
            return error_response(
                error="Request timed out (120s)",
                error_type="io_error",
                provider=self.name,
                model=resolved_model,
                prompt=prompt,
                aspect_ratio=aspect_ratio,
            )
        except requests.ConnectionError as e:
            return error_response(
                error=f"Connection error: {e}",
                error_type="io_error",
                provider=self.name,
                model=resolved_model,
                prompt=prompt,
                aspect_ratio=aspect_ratio,
            )
        except Exception as e:
            logger.exception("Unexpected error in Bifrost image gen")
            return error_response(
                error=f"Unexpected error: {e}",
                error_type="api_error",
                provider=self.name,
                model=resolved_model,
                prompt=prompt,
                aspect_ratio=aspect_ratio,
            )


def register(ctx) -> None:
    """Register the Bifrost image gen provider with the plugin context."""
    ctx.register_image_gen_provider(BifrostImageGenProvider())
