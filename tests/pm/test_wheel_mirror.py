"""Bifrost edition: a sync that failed on PyPI is retried from the fork's pip-mirror release."""
import importlib.util
from pathlib import Path
import subprocess

import pytest

from pm import wheel_mirror
from pm.environment import PythonEnvironment

PYPI = "https://files.pythonhosted.org/packages/76/c6/c88e/"
LOCK = f"""\
[[package]]
name = "idna"
version = "3.10"
sdist = {{ url = "{PYPI}idna-3.10.tar.gz", hash = "sha256:aa", size = 1 }}
wheels = [
    {{ url = "{PYPI}idna-3.10-py3-none-any.whl", hash = "sha256:bb", size = 2 }},
    {{ url = "{PYPI}torch-2.1.0+cu121-cp314-linux_x86_64.whl", hash = "sha256:cc", size = 3 }},
]
[[package]]
name = "demo"
version = "1"
source = {{ url = "https://example.org/demo-1-py3-none-any.whl" }}
"""


def test_only_pypi_wheels_move_and_hashes_stay():
    out = wheel_mirror.mirrored_lock(LOCK)
    assert f'url = "{wheel_mirror.MIRROR_PREFIX}idna-3.10-py3-none-any.whl", hash = "sha256:bb"' in out
    assert f"{PYPI}idna-3.10.tar.gz" in out  # an sdist is not mirrored
    assert f"{PYPI}torch-2.1.0+cu121-cp314-linux_x86_64.whl" in out  # `+` is not a legal asset name
    assert "https://example.org/demo-1-py3-none-any.whl" in out
    assert wheel_mirror.mirrored_wheel_names(LOCK) == {"idna-3.10-py3-none-any.whl"}


def _environment(tmp_path):
    return PythonEnvironment(uv=Path("uv"), python=Path("python"), destination=tmp_path / "venv",
                             cache=tmp_path / "cache", env={})


def _fake_uv(monkeypatch, failure: str, seen: list):
    def run(self, args, *, cwd, timeout):
        seen.append((cwd / "uv.lock").read_text(encoding="utf-8"))
        # The first sync (and only the first) hits the unreachable CDN.
        code = 2 if len(seen) == 1 or wheel_mirror.MIRROR_PREFIX not in seen[-1] else 0
        return subprocess.CompletedProcess(args, code, "", failure if code else "")
    monkeypatch.setattr(PythonEnvironment, "_run", run)


def test_network_failure_retries_against_the_mirror_and_restores_the_lock(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")
    (tmp_path / "uv.lock").write_text(LOCK, encoding="utf-8")
    seen: list = []
    _fake_uv(monkeypatch, "error sending request for url (https://files.pythonhosted.org/...)", seen)
    _environment(tmp_path).sync(tmp_path)
    assert len(seen) == 2 and seen[0] == LOCK and wheel_mirror.MIRROR_PREFIX in seen[1]
    assert (tmp_path / "uv.lock").read_text(encoding="utf-8") == LOCK


def test_a_resolver_failure_is_not_retried(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")
    (tmp_path / "uv.lock").write_text(LOCK, encoding="utf-8")
    seen: list = []
    _fake_uv(monkeypatch, "No solution found when resolving dependencies", seen)
    with pytest.raises(Exception, match="No solution"):
        _environment(tmp_path).sync(tmp_path)
    assert len(seen) == 1


def test_the_mirror_script_wants_python_314_wheels_for_supported_platforms():
    spec = importlib.util.spec_from_file_location("mirror_wheels", Path(__file__).parents[2] / "scripts/bifrost/mirror_wheels.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    wanted = module.wanted_wheel
    assert wanted("a-1-py3-none-any.whl") and wanted("a-1-cp311-abi3-macosx_11_0_arm64.whl")
    assert wanted("a-1-cp314-cp314-win_amd64.whl") and wanted("a-1-cp314-cp314-musllinux_1_2_aarch64.whl")
    assert wanted("a-1-cp314-cp314-manylinux_2_28_x86_64.manylinux2014_x86_64.whl")
    assert not wanted("a-1-cp314-cp314t-manylinux_2_28_x86_64.whl")
    assert not wanted("a-1-cp313-cp313-win_amd64.whl") and not wanted("a-1-cp314-cp314-win32.whl")
    assert not wanted("a-1-cp314-cp314-manylinux2014_i686.whl")
