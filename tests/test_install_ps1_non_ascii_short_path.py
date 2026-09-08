"""Regression: non-ASCII profile paths crash native build tools (0xC0000409).

Issue #bifrost-desktop-cyrillic: Windows users with a non-ASCII username
(e.g. ``Кузнецова Елизавета``) hit ``STATUS_STACK_BUFFER_OVERRUN``
(exit ``-1073740791`` / ``0xC0000409``) during ``npm run pack`` because
esbuild / electron-builder / rcedit are native executables that cannot
handle non-ASCII bytes in their cwd or ``%TEMP%``.

The fix mirrors the existing 8.3→long normalization block: when the build
cwd or ``%TEMP%`` contains non-ASCII, collapse it to the ASCII 8.3 short
alias via ``kernel32!GetShortPathNameW`` for the duration of the native
build, then restore in ``finally``.

install.ps1 only runs on Windows, so these tests lock the contract at the
source-text level (same style as test_install_ps1_resolver_strictmode.py).
"""

from __future__ import annotations

import re
from pathlib import Path

_INSTALL_PS1 = Path(__file__).resolve().parents[1] / "scripts" / "install.ps1"


def _ps1() -> str:
    return _INSTALL_PS1.read_text(encoding="utf-8")


def test_get_short_path_native_helper_exists():
    """Get-ShortPath must exist as the mirror of the long-path resolver."""
    source = _ps1()
    assert re.search(r"function Get-ShortPath\b", source), (
        "Get-ShortPath (GetShortPathNameW P/Invoke) must exist to collapse "
        "non-ASCII paths to ASCII 8.3 short form for native build tools"
    )
    assert "GetShortPathNameW" in source, (
        "Get-ShortPath must P/Invoke kernel32!GetShortPathNameW"
    )


def test_non_ascii_detection_helper_exists():
    source = _ps1()
    assert re.search(r"function Test-PathHasNonAscii\b", source), (
        "Test-PathHasNonAscii must exist to gate the short-path swap on "
        "paths that actually contain non-ASCII characters"
    )


def test_install_desktop_swaps_non_ascii_paths_before_pack():
    """The desktop build must collapse non-ASCII cwd/TEMP before npm run pack."""
    source = _ps1()
    pack = re.search(r"& \$npmExe run pack", source)
    assert pack, "npm run pack invocation not found"
    pack_pos = pack.start()

    # Look backwards from the pack invocation for the non-ASCII swap block.
    region = source[max(0, pack_pos - 3000) : pack_pos]
    assert "Test-PathHasNonAscii" in region, (
        "Install-Desktop must check for non-ASCII in cwd/TEMP before npm run pack"
    )
    assert "Get-ShortPath" in region, (
        "Install-Desktop must collapse non-ASCII paths to short form before npm run pack"
    )
    assert re.search(r"\$env:TEMP\s*=\s*\$shortTemp", region), (
        "Install-Desktop must set %TEMP% to the ASCII short form for native tools"
    )


def test_temp_tmp_restored_after_build():
    """TEMP/TMP must be restored in the finally block to avoid leaking."""
    source = _ps1()
    assert re.search(r"\$prevTemp\s*=\s*\$env:TEMP", source), (
        "Install-Desktop must snapshot $env:TEMP before the build"
    )
    assert re.search(r"\$prevTmp\s*=\s*\$env:TMP", source), (
        "Install-Desktop must snapshot $env:TMP before the build"
    )
    assert re.search(r"\$env:TEMP\s*=\s*\$prevTemp", source), (
        "Install-Desktop must restore $env:TEMP in finally"
    )
    assert re.search(r"\$env:TMP\s*=\s*\$prevTmp", source), (
        "Install-Desktop must restore $env:TMP in finally"
    )


def test_short_path_swap_does_not_touch_long_path_normalization():
    """The new short-path logic must not alter the existing long-path block.

    ConvertTo-LongPath and Set-LongProfileEnvVars fix PowerShell provider
    cmdlets by expanding 8.3→long. The new Get-ShortPath fixes native build
    tools by collapsing non-ASCII long→8.3. Both must coexist.
    """
    source = _ps1()
    assert re.search(r"function ConvertTo-LongPath\b", source), (
        "ConvertTo-LongPath (existing long-path normalizer) must be preserved"
    )
    assert re.search(r"function Set-LongProfileEnvVars\b", source), (
        "Set-LongProfileEnvVars (existing long-path normalizer) must be preserved"
    )
    assert re.search(r"GetLongPathNameW", source), (
        "GetLongPathNameW P/Invoke (existing) must be preserved"
    )
