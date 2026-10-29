"""A Bifrost edition install refuses ``--channel stable`` instead of landing on an upstream release.

The stable channel resolves NousResearch's releases and the fork mirrors those tags, so a fork
checkout on ``--channel stable`` would silently drop every Bifrost change.
"""
from pathlib import Path
import os
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.platforms("posix")


def test_fork_install_refuses_the_stable_channel_before_touching_disk(tmp_path):
    home = tmp_path / "home"
    install = home / ".hermes" / "hermes-agent"
    home.mkdir()
    env = {"PATH": os.environ["PATH"], "HOME": str(home), "NO_COLOR": "1", "GIT_CONFIG_NOSYSTEM": "1"}

    result = subprocess.run(
        ["bash", str(ROOT / "scripts" / "install.sh"), "--stage", "repository", "--dir", str(install),
         "--hermes-home", str(home / ".hermes"), "--non-interactive", "--channel", "stable"],
        check=False, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60, env=env,
    )

    assert result.returncode == 2, result.stdout + result.stderr
    assert "--channel main" in result.stderr
    assert not install.exists()
