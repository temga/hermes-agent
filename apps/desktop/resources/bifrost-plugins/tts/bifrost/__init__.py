"""Bifrost TTS — text-to-speech через Bifrost → tts-proxy → NeuralDeep API.

Маршрут: Hermes → Bifrost (https://router.rove-ai.ru, auth/логи/метрики)
  → tts-proxy (8090, FastAPI, реинжектит language)
  → NeuralDeep API

Bifrost парсит /v1/audio/speech по OpenAI-схеме и дропает кастомное поле
``language``, которое требует NeuralDeep. Локальный прокси (tts-proxy.service)
реинжектит его: espeech-tts → Russian, qwen3-tts → автоопределение по тексту.
Заголовок ``x-tts-language`` переопределяет автоопределение.

Ключ: ``BIFROST_API_KEY`` (единый ключ на все сервисы через Bifrost).

Config (config.yaml)::

    tts:
      provider: bifrost
      bifrost:
        model: espeech-tts
        voice: alloy
        language: Russian
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from agent.tts_provider import TTSProvider, DEFAULT_OUTPUT_FORMAT

from ._keyresolver import resolve_bifrost_key

logger = logging.getLogger(__name__)

_API_BASE = os.environ.get("BIFROST_BASE_URL", "https://router.rove-ai.ru").rstrip("/").removesuffix("/v1") + "/v1"
_DEFAULT_MODEL = "espeech-tts"
_DEFAULT_VOICE = "alloy"
_DEFAULT_LANGUAGE = "Russian"

# NeuralDeep: 8 голосов (qwen3-tts — мультиязык, 10 языков).
_VOICES: List[Dict[str, Any]] = [
    {"id": "alloy",   "display": "Alloy — нейтральный",     "language": "multi"},
    {"id": "echo",    "display": "Echo — мужской",          "language": "multi"},
    {"id": "fable",   "display": "Fable — рассказчик",      "language": "multi"},
    {"id": "onyx",    "display": "Onyx — глубокий мужской", "language": "multi"},
    {"id": "nova",    "display": "Nova — женский",          "language": "multi"},
    {"id": "shimmer", "display": "Shimmer — мягкий женский","language": "multi"},
    {"id": "coral",   "display": "Coral — тёплый",          "language": "multi"},
    {"id": "sage",    "display": "Sage — спокойный",        "language": "multi"},
]

_MODELS: List[Dict[str, Any]] = [
    {
        "id": "espeech-tts",
        "display": "ESpeech TTS — русский с ударениями (F5 + RUAccent)",
        "languages": ["ru"],
        "max_text_length": 5000,
    },
    {
        "id": "qwen3-tts",
        "display": "Qwen3-TTS — мультиязык, 8 голосов, эмоции (vLLM-Omni)",
        "languages": ["ru", "en", "ja", "de", "fr", "es", "ko", "it", "pt", "ar"],
        "max_text_length": 5000,
    },
]


class BifrostTTSProvider(TTSProvider):
    """TTS provider routed through Bifrost → tts-proxy → NeuralDeep API."""

    @property
    def name(self) -> str:
        return "bifrost"

    @property
    def display_name(self) -> str:
        return "Bifrost TTS (ESpeech / Qwen3) via Bifrost gateway"

    def is_available(self) -> bool:
        return bool(resolve_bifrost_key())

    def list_models(self) -> List[Dict[str, Any]]:
        return list(_MODELS)

    def default_model(self) -> Optional[str]:
        return _DEFAULT_MODEL

    def list_voices(self) -> List[Dict[str, Any]]:
        return list(_VOICES)

    def default_voice(self) -> Optional[str]:
        return _DEFAULT_VOICE

    def get_setup_schema(self) -> Dict[str, Any]:
        return {
            "name": "Bifrost TTS",
            "badge": "paid",
            "tag": "espeech-tts (RU+ударения), qwen3-tts (8 голосов) — через Bifrost gateway",
            "env_vars": [
                {
                    "key": "BIFROST_API_KEY",
                    "prompt": "Bifrost API key (sk-bf-...)",
                    "url": "https://router.rove-ai.ru",
                },
            ],
        }

    @property
    def voice_compatible(self) -> bool:
        return True

    def synthesize(
        self,
        text: str,
        output_path: str,
        *,
        voice: Optional[str] = None,
        model: Optional[str] = None,
        speed: Optional[float] = None,
        format: str = DEFAULT_OUTPUT_FORMAT,
        **extra: Any,
    ) -> str:
        """Synthesize via Bifrost → tts-proxy → NeuralDeep API."""
        api_key = resolve_bifrost_key()
        if not api_key:
            raise RuntimeError("Bifrost key not set")

        model_name = model or _DEFAULT_MODEL
        voice_name = voice or _DEFAULT_VOICE
        language = extra.get("language") or _DEFAULT_LANGUAGE

        # Bifrost требует provider/model формат
        bifrost_model = f"neuraldeep/{model_name}" if "/" not in model_name else model_name

        # Формируем request body (OpenAI-схема + language для прокси)
        body: Dict[str, Any] = {
            "model": bifrost_model,
            "input": text,
            "voice": voice_name,
            "language": language,
            "response_format": format if format in ("mp3", "wav", "ogg", "flac") else "mp3",
        }
        if speed is not None:
            body["speed"] = speed

        import urllib.request
        import urllib.error
        import json as _json

        url = f"{_API_BASE}/audio/speech"
        req = urllib.request.Request(
            url,
            data=_json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                audio_bytes = resp.read()
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")[:500]
            logger.error("Bifrost TTS HTTP %s: %s", exc.code, err_body)
            raise RuntimeError(f"Bifrost TTS error {exc.code}: {err_body}") from exc
        except Exception as exc:
            logger.error("Bifrost TTS failed: %s", exc, exc_info=True)
            raise RuntimeError(f"Bifrost TTS error: {exc}") from exc

        if not audio_bytes:
            raise RuntimeError("Bifrost TTS returned empty audio")

        # Убеждаемся что extension правильный
        ext = ".mp3"
        if format == "wav":
            ext = ".wav"
        elif format == "ogg":
            ext = ".ogg"
        elif format == "flac":
            ext = ".flac"
        elif format == "opus":
            ext = ".opus"

        if not output_path.endswith(ext):
            base = os.path.splitext(output_path)[0]
            output_path = base + ext

        with open(output_path, "wb") as f:
            f.write(audio_bytes)

        logger.info(
            "Bifrost TTS: model=%s voice=%s lang=%s → %d bytes → %s",
            model_name, voice_name, language, len(audio_bytes), output_path,
        )
        return output_path


# --- Plugin registration hook ---
def register(ctx):
    """Register the Bifrost TTS provider with Hermes.

    Called by the plugin loader — it looks for a top-level ``register(ctx)``
    function in the plugin's ``__init__.py``.
    """
    try:
        ctx.register_tts_provider(BifrostTTSProvider())
        logger.info("Bifrost TTS provider registered")
    except Exception as exc:
        logger.warning("Failed to register Bifrost TTS provider: %s", exc)
