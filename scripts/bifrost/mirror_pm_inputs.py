#!/usr/bin/env python3
"""Copy every pinned PM input into the fork's ``pm-mirror`` GitHub release.

PM tries these assets first (``pm.artifact_mirror.FORK_MIRROR_PREFIX``): installs on Russian
networks reach GitHub but not always the upstream hosts, and the Nous mirror's Cloudflare
answers them 403. Each asset is named by its sha256 and is downloaded through PM's own
verified downloader before upload, so the release only ever holds the pinned bytes. Assets
already in the release are skipped; run it again after every lockfile change.

    scripts/bifrost/mirror_pm_inputs.py               # every pinned input
    scripts/bifrost/mirror_pm_inputs.py --dry-run     # list what would be uploaded

The release is a prerelease that is never marked latest: the stable updater reads
``/releases/latest`` and the canary scan rejects a tag that is not a release version.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from pm.artifact_mirror import FORK_MIRROR_PREFIX, mirror_url
from pm.downloader import Download, Source
from scripts.ci.archive_inputs import pinned_inputs

TAG = FORK_MIRROR_PREFIX.rstrip("/").rsplit("/", 1)[-1]
REPOSITORY = FORK_MIRROR_PREFIX.split("github.com/", 1)[1].split("/releases/", 1)[0]
NOTES = ("Content-addressed copies of the binaries pinned in pm/lock.json, named by sha256. "
         "Hermes PM downloads them from here first. Not a Hermes release.")


def _gh(*args: str, check: bool = True, timeout: float = 120) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args, "-R", REPOSITORY], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", check=check, timeout=timeout)


def mirrored_assets() -> set[str] | None:
    """Asset names already in the release, or None when the release does not exist yet."""
    result = _gh("release", "view", TAG, "--json", "assets", check=False)
    if result.returncode != 0:
        if "not found" in result.stderr.lower():
            return None
        raise SystemExit(result.stderr.strip())
    return {asset["name"] for asset in json.loads(result.stdout)["assets"]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="list missing inputs without uploading")
    args = parser.parse_args(argv)

    pins = {}
    for pin in pinned_inputs(REPO_ROOT):
        pins.setdefault(pin.sha256, pin)
    have = mirrored_assets()
    missing = [pin for digest, pin in pins.items() if digest not in (have or set())]
    print(f"{len(pins)} pinned inputs, {len(pins) - len(missing)} already in {REPOSITORY}@{TAG}", flush=True)
    if args.dry_run:
        for pin in missing:
            print(f"  missing {pin.sha256}  {pin.name}  {pin.url}")
        return 0
    if have is None and missing:
        _gh("release", "create", TAG, "--prerelease", "--latest=false",
            "--title", "PM input mirror", "--notes", NOTES)
    with tempfile.TemporaryDirectory(prefix="pm-mirror-") as temporary:
        work = Path(temporary)
        for pin in missing:
            local = work / pin.sha256
            # The upstream host can be gone; the Nous mirror holds the same pinned bytes.
            fallbacks = () if pin.url == mirror_url(pin.sha256) else (mirror_url(pin.sha256),)
            Download([Source(pin.url, local, pin.sha256, fallbacks)], partials_dir=work / "partials").run()
            _gh("release", "upload", TAG, str(local), timeout=1800)
            local.unlink()
            print(f"  uploaded {pin.sha256}  {pin.name}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
