"""GET /api/config must omit display.language when the user never set it.

Regression for the Bifrost-edition onboarding language bug: ``load_config()``
deep-merges ``DEFAULT_CONFIG`` (``display.language = "en"``) into every config,
so ``/api/config`` always returned ``display.language = "en"`` even for a brand-
new user whose ``config.yaml`` has no ``display`` section at all. The desktop
``I18nProvider`` treats any non-undefined ``display.language`` as authoritative
and overrides the edition's ``initialLocale`` (e.g. "ru") — showing the first-
run onboarding in English instead of the edition default.

The endpoint now reads the raw config and strips ``display.language`` when it
isn't explicitly written, so ``getConfigDisplayLanguage()`` returns undefined
and the provider keeps its ``initialLocale`` (commit 53137a2c92's intent).
"""

import pytest


class TestGetConfigDisplayLanguage:
    @pytest.fixture(autouse=True)
    def _home(self, _isolate_hermes_home):
        pass

    def test_omits_display_language_for_fresh_user(self):
        """A new user with no display.language in config.yaml must NOT receive
        the DEFAULT_CONFIG-merged value — the frontend reads its absence as
        'use the edition initialLocale'."""
        try:
            from starlette.testclient import TestClient
        except ImportError:
            pytest.skip("fastapi/starlette not installed")
        from hermes_cli.web_server import app, _SESSION_HEADER_NAME, _SESSION_TOKEN

        client = TestClient(app)
        client.headers[_SESSION_HEADER_NAME] = _SESSION_TOKEN
        resp = client.get("/api/config")
        assert resp.status_code == 200
        body = resp.json()
        display = body.get("display", {})
        # The DEFAULT_CONFIG value ("en") must NOT leak for a user who never
        # chose a language — the desktop I18nProvider keeps its initialLocale.
        assert "language" not in display, (
            f"display.language leaked as {display.get('language')!r} from "
            "DEFAULT_CONFIG merge — I18nProvider will override initialLocale"
        )

    def test_preserves_explicit_display_language(self):
        """When the user explicitly set display.language in config.yaml, it
        must round-trip through /api/config so the provider honours the choice."""
        try:
            from starlette.testclient import TestClient
        except ImportError:
            pytest.skip("fastapi/starlette not installed")
        from hermes_cli.config import get_hermes_home
        from hermes_cli.web_server import app, _SESSION_HEADER_NAME, _SESSION_TOKEN
        from pathlib import Path

        home = Path(get_hermes_home())
        home.mkdir(parents=True, exist_ok=True)
        (home / "config.yaml").write_text("display:\n  language: ja\n", encoding="utf-8")

        client = TestClient(app)
        client.headers[_SESSION_HEADER_NAME] = _SESSION_TOKEN
        resp = client.get("/api/config")
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("display", {}).get("language") == "ja"
