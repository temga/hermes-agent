#!/usr/bin/env python3
"""Export the bundled Bifrost plugins into a checkout of the standalone pack repo.

The plugins live in this tree (``plugins/<category>/bifrost/``); temga/hermes-plugin-bifrost-gateway
is their copy for stock Hermes. That repo keeps one shared ``_keyresolver.py`` at its root (its
installer copies it into every plugin), so each plugin's own copy is exported there once instead.
Everything else in the repo (installers, docs, skills) is left alone.

    scripts/bifrost/sync_plugin_pack.py ~/src/hermes-plugin-bifrost-gateway
    git -C ~/src/hermes-plugin-bifrost-gateway diff
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from hermes_cli.bifrost_edition import BIFROST_PLUGINS  # noqa: E402

KEY_RESOLVER = "_keyresolver.py"


def export(pack: Path) -> None:
    resolvers = {(REPO_ROOT / "plugins" / plugin / KEY_RESOLVER).read_bytes() for plugin in BIFROST_PLUGINS}
    if len(resolvers) != 1:
        sys.exit(f"The bundled {KEY_RESOLVER} copies differ; make them identical before exporting.")
    for plugin in BIFROST_PLUGINS:
        dest = pack / plugin
        shutil.rmtree(dest, ignore_errors=True)
        shutil.copytree(REPO_ROOT / "plugins" / plugin, dest,
                        ignore=shutil.ignore_patterns(KEY_RESOLVER, "__pycache__", "*.pyc"))
        print(f"exported {plugin}")
    (pack / KEY_RESOLVER).write_bytes(resolvers.pop())
    print(f"exported {KEY_RESOLVER}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pack", type=Path, help="checkout of temga/hermes-plugin-bifrost-gateway")
    pack = parser.parse_args().pack
    if not (pack / "install.sh").is_file():
        sys.exit(f"{pack} does not look like the plugin pack checkout (no install.sh).")
    export(pack)


if __name__ == "__main__":
    main()
