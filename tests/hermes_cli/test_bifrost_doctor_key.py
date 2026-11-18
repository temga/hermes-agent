"""Bifrost edition: a .env holding only the Bifrost key counts as a configured provider."""

from hermes_cli.doctor_config import _has_provider_env_config


def test_bifrost_key_alone_counts_as_provider_config():
    assert _has_provider_env_config("BIFROST_API_KEY=sk-bf-test\n")


def test_unrelated_env_is_not_provider_config():
    assert not _has_provider_env_config("TELEGRAM_BOT_TOKEN=123\n")
