#!/usr/bin/env python3
"""Keep the fork's ``pip-mirror`` GitHub release equal to the wheels uv.lock asks PyPI for.

``pm.wheel_mirror`` retries a failed ``uv sync`` against this release, so it must hold every wheel an
install of the default closure (all extras except the opt-in ones, Python 3.14) can download on a
supported platform. Assets keep the wheels' own file names (uv reads name, version and tags from
them); each is fetched through PM's verified downloader against the lock's sha256 before upload, so
the release only ever holds locked bytes. Wheels no longer in the lock are deleted: a release holds at
most 1000 assets.

    scripts/bifrost/mirror_wheels.py             # sync the release
    scripts/bifrost/mirror_wheels.py --dry-run   # list what would be uploaded / deleted

The release is a prerelease, never latest, for the reason mirror_pm_inputs.py gives.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import tomllib

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from pm.downloader import Download, Source
from pm.features import opt_in_extras
from pm.wheel_mirror import MIRROR_PREFIX, mirrored_wheel_names

TAG = MIRROR_PREFIX.rstrip("/").rsplit("/", 1)[-1]
REPOSITORY = MIRROR_PREFIX.split("github.com/", 1)[1].split("/releases/", 1)[0]
NOTES = ("Wheels from uv.lock, under their PyPI file names. Hermes PM retries a failed install from here. "
         "Not a Hermes release.")
PYTHON = "3.14"
_PLATFORMS = re.compile(r"^(any|win_amd64|win_arm64|macosx_.+|(many|musl)linux.*_(x86_64|aarch64)|linux_(x86_64|aarch64))$")


def wanted_wheel(filename: str) -> bool:
    """A wheel Python 3.14 installs on Windows x64/arm64, macOS or 64-bit Linux (glibc or musl)."""
    python, abi, platform = filename.removesuffix(".whl").rsplit("-", 3)[1:]
    if abi == "none":
        python_ok = "py3" in python.split(".")
    elif abi == "abi3":
        python_ok = python.startswith("cp3") and int(python[3:]) <= 14
    else:
        python_ok = python == abi == "cp314"
    return python_ok and any(_PLATFORMS.match(tag) for tag in platform.split("."))


def closure() -> set[tuple[str, str]]:
    """(name, version) of every package the default all-extras install can need."""
    command = ["uv", "export", "--frozen", "--all-packages", "--no-emit-project", "--no-hashes", "--no-annotate",
               "--no-header", "--format", "requirements-txt", "--python", PYTHON, "--all-extras",
               *(arg for extra in opt_in_extras(REPO_ROOT) for arg in ("--no-extra", extra))]
    out = subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout
    return {(m[1].lower().replace("_", "-"), m[2]) for line in out.splitlines() if (m := re.match(r"([\w.\-]+)==(\S+?)\s*(;|$)", line))}


def wanted_wheels() -> dict[str, tuple[str, str]]:
    """file name → (url, sha256) for every mirrored wheel of the closure."""
    text = (REPO_ROOT / "uv.lock").read_text(encoding="utf-8")
    servable = mirrored_wheel_names(text)
    needed = closure()
    wheels = {}
    for package in tomllib.loads(text)["package"]:
        if (package["name"].lower().replace("_", "-"), package.get("version")) not in needed:
            continue
        for wheel in package.get("wheels", []):
            name = wheel["url"].rsplit("/", 1)[-1]
            if name in servable and wanted_wheel(name):
                wheels[name] = (wheel["url"], wheel["hash"].removeprefix("sha256:"))
    return wheels


def _gh(*args: str, check: bool = True, timeout: float = 120) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args, "-R", REPOSITORY], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", check=check, timeout=timeout)


def mirrored_assets() -> set[str] | None:
    result = _gh("release", "view", TAG, "--json", "assets", check=False)
    if result.returncode != 0:
        if "not found" in result.stderr.lower():
            return None
        raise SystemExit(result.stderr.strip())
    return {asset["name"] for asset in json.loads(result.stdout)["assets"]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="list uploads and deletions without doing them")
    args = parser.parse_args(argv)

    wanted = wanted_wheels()
    have = mirrored_assets()
    missing = sorted(set(wanted) - (have or set()))
    stale = sorted((have or set()) - set(wanted))
    size = len(wanted)
    print(f"{size} wheels wanted, {size - len(missing)} already in {REPOSITORY}@{TAG}, {len(stale)} stale", flush=True)
    if args.dry_run:
        for name in missing:
            print(f"  missing {name}")
        for name in stale:
            print(f"  stale   {name}")
        return 0
    if have is None and missing:
        _gh("release", "create", TAG, "--prerelease", "--latest=false", "--title", "Wheel mirror", "--notes", NOTES)
    failed = []
    with tempfile.TemporaryDirectory(prefix="wheel-mirror-") as temporary:
        work = Path(temporary)
        for name in missing:
            url, digest = wanted[name]
            local = work / name
            try:
                Download([Source(url, local, digest)], partials_dir=work / "partials").run()
                uploaded = _gh("release", "upload", TAG, str(local), "--clobber", check=False, timeout=1800)
            except Exception as error:  # one wheel must not hold back the rest; a rerun retries it
                print(f"  NOT uploaded {name}: {error}", flush=True)
                failed.append(name)
                continue
            local.unlink(missing_ok=True)
            if uploaded.returncode:
                print(f"  NOT uploaded {name}: {uploaded.stderr.strip()}", flush=True)
                failed.append(name)
            else:
                print(f"  uploaded {name}", flush=True)
    for name in stale:
        _gh("release", "delete-asset", TAG, name, "--yes", check=False)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
