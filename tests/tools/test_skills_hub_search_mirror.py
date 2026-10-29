"""``skills.hub_url`` names a mirror origin for the CLI skills index, the same value Desktop reads."""

import pytest

from hermes_cli.config import load_config, save_config
from tools.skills_hub_search import DEFAULT_HERMES_INDEX_URL, _hermes_index_url


def _write_hub_url(value: str) -> None:
    cfg = load_config()
    cfg.setdefault("skills", {})["hub_url"] = value
    save_config(cfg)


@pytest.mark.parametrize(
    ("hub_url", "expected"),
    [
        ("https://hub.example.test", "https://hub.example.test/docs/api/skills-index.json"),
        ("https://hub.example.test/", "https://hub.example.test/docs/api/skills-index.json"),
        ("https://cdn.example.test/skills-index.json", "https://cdn.example.test/skills-index.json"),
        ("", DEFAULT_HERMES_INDEX_URL),
    ],
)
def test_index_url_follows_the_configured_mirror(hub_url, expected):
    _write_hub_url(hub_url)

    assert _hermes_index_url() == expected
