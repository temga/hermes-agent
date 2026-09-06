"""Bifrost STT — speech-to-text through the Bifrost gateway.

Routes audio transcription through the gateway's OpenAI-compatible
``POST /v1/audio/transcriptions`` endpoint. Uses the same
``BIFROST_API_KEY`` (sk-bf-*) as the LLM provider.

Available models (via NeuralDeep upstream):
  - ``neuraldeep/whisper-1``              — standard OpenAI Whisper
  - ``neuraldeep/whisper-podlodka-turbo`` — Whisper fork tuned for Russian
  - ``neuraldeep/gigaam-v3``              — Sber GigaAM, Russian-specialised

Config (config.yaml)::

    stt:
      provider: bifrost
      bifrost:
        model: neuraldeep/whisper-podlodka-turbo
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from agent.transcription_provider import TranscriptionProvider

from ._keyresolver import resolve_bifrost_key

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://router.rove-ai.ru/v1"
_DEFAULT_MODEL = "neuraldeep/whisper-podlodka-turbo"

# Models exposed by Bifrost's NeuralDeep upstream.
_MODELS: List[Dict[str, Any]] = [
    {
        "id": "neuraldeep/whisper-podlodka-turbo",
        "display": "Whisper Podlodka Turbo (Russian-tuned)",
        "languages": ["ru", "en"],
    },
    {
        "id": "neuraldeep/whisper-1",
        "display": "Whisper-1 (OpenAI standard)",
        "languages": ["en", "ru", "ja", "de", "fr", "es"],
    },
    {
        "id": "neuraldeep/gigaam-v3",
        "display": "GigaAM v3 (Sber, Russian)",
        "languages": ["ru"],
    },
]


class BifrostSTTProvider(TranscriptionProvider):
    """Transcription provider backed by the Bifrost gateway."""

    @property
    def name(self) -> str:
        return "bifrost"

    @property
    def display_name(self) -> str:
        return "Bifrost Gateway (Whisper/GigaAM)"

    def is_available(self) -> bool:
        return bool(resolve_bifrost_key())

    def list_models(self) -> List[Dict[str, Any]]:
        return list(_MODELS)

    def default_model(self) -> Optional[str]:
        return _DEFAULT_MODEL

    def get_setup_schema(self) -> Dict[str, Any]:
        return {
            "name": "Bifrost STT",
            "badge": "paid",
            "tag": "whisper-1, whisper-podlodka-turbo, gigaam-v3 via Bifrost gateway",
            "env_vars": [
                {
                    "key": "BIFROST_API_KEY",
                    "prompt": "Bifrost API key (sk-bf-*)",
                    "url": "https://router.rove-ai.ru",
                },
            ],
        }

    def transcribe(
        self,
        file_path: str,
        *,
        model: Optional[str] = None,
        language: Optional[str] = None,
        **extra: Any,
    ) -> Dict[str, Any]:
        """Transcribe via ``POST /v1/audio/transcriptions`` on Bifrost."""
        api_key = resolve_bifrost_key()
        if not api_key:
            return {
                "success": False,
                "transcript": "",
                "error": "Bifrost key not set",
                "provider": self.name,
            }

        base_url = (
            os.environ.get("BIFROST_BASE_URL", "").rstrip("/")
            or _DEFAULT_BASE_URL
        )
        model_name = model or _DEFAULT_MODEL

        try:
            import urllib.request
            import urllib.error
            import json as _json
            import mimetypes

            # Build multipart/form-data
            boundary = "----bifrost-stt-boundary"
            filename = os.path.basename(file_path)
            mime = mimetypes.guess_type(file_path)[0] or "audio/wav"

            with open(file_path, "rb") as f:
                audio_bytes = f.read()

            body_parts = []
            # model field
            body_parts.append(
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="model"\r\n\r\n'
                f"{model_name}\r\n"
            )
            # language field (optional)
            if language:
                body_parts.append(
                    f"--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="language"\r\n\r\n'
                    f"{language}\r\n"
                )
            # response_format
            body_parts.append(
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="response_format"\r\n\r\n'
                f"json\r\n"
            )
            # file field
            body_parts.append(
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="file"; '
                f'filename="{filename}"\r\n'
                f"Content-Type: {mime}\r\n\r\n"
            )
            body = "".join(body_parts).encode("utf-8") + audio_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

            url = f"{base_url}/audio/transcriptions"
            req = urllib.request.Request(
                url,
                data=body,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                },
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=120) as resp:
                result = _json.loads(resp.read().decode("utf-8"))

            transcript = result.get("text", "").strip()
            logger.info(
                "Bifrost STT: model=%s lang=%s → %d chars",
                model_name, language or "auto", len(transcript),
            )
            return {
                "success": True,
                "transcript": transcript,
                "provider": self.name,
            }

        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")[:500]
            logger.error("Bifrost STT HTTP %s: %s", exc.code, err_body)
            return {
                "success": False,
                "transcript": "",
                "error": f"Bifrost STT error {exc.code}: {err_body}",
                "provider": self.name,
            }
        except Exception as exc:
            logger.error("Bifrost STT failed: %s", exc, exc_info=True)
            return {
                "success": False,
                "transcript": "",
                "error": f"Bifrost STT error: {exc}",
                "provider": self.name,
            }


# --- Plugin registration hook ---
def register(ctx):
    """Register the Bifrost STT provider with Hermes.

    Called by the plugin loader — it looks for a top-level ``register(ctx)``
    function in the plugin's ``__init__.py``.
    """
    try:
        ctx.register_transcription_provider(BifrostSTTProvider())
        logger.info("Bifrost STT provider registered")
    except Exception as exc:
        logger.warning("Failed to register Bifrost STT provider: %s", exc)
