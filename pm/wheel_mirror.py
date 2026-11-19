"""Bifrost edition: the fork's GitHub-release copy of the locked wheels, used when PyPI's CDN fails.

``uv sync --frozen`` downloads every wheel from the URL recorded in ``uv.lock`` and ignores index and
``--find-links`` settings, so a mirror cannot be reached through uv's own knobs. Instead, after a sync
failed on the network, PM retries once against a copy of the lock whose PyPI wheel URLs point at the
``pip-mirror`` release (scripts/bifrost/mirror_wheels.py fills it). The ``hash`` of every entry stays,
so uv still verifies each wheel and a mirror that serves different bytes is rejected. Stdlib only.
"""
from __future__ import annotations

import re

MIRROR_PREFIX = "https://github.com/temga/hermes-agent/releases/download/pip-mirror/"

# A wheel's file name is part of its identity (uv parses name, version and tags from the URL's last
# segment), so the release keeps the original names. `+` (local versions) is not kept by GitHub's
# asset naming, so such wheels are never mirrored or rewritten.
_PYPI_WHEEL = re.compile(r'url = "https://files\.pythonhosted\.org/packages/[^"]+/([^"/+]+\.whl)"')

# uv's English diagnostics for a failed fetch. A resolver conflict or a build failure is not one.
_NETWORK_MARKERS = (
    "error sending request", "failed to download", "failed to fetch", "timed out",
    "dns error", "connection refused", "connection reset", "tcp connect error",
    "status code 429", "429 too many requests", "403 forbidden",
)


def is_network_failure(output: str) -> bool:
    lowered = output.lower()
    return any(marker in lowered for marker in _NETWORK_MARKERS)


def mirrored_lock(lock_text: str) -> str:
    """*lock_text* with every PyPI wheel URL moved to the pip-mirror release."""
    return _PYPI_WHEEL.sub(lambda match: f'url = "{MIRROR_PREFIX}{match.group(1)}"', lock_text)


def mirrored_wheel_names(lock_text: str) -> set[str]:
    """File names of the wheels a lock asks for from PyPI that the mirror serves."""
    return set(_PYPI_WHEEL.findall(lock_text))
