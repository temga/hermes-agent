#!/usr/bin/env bash
# Run a Hermes Bifrost installer build in a sandbox that does not touch the
# main install (~/.hermes, ~/.local/bin, shell rc files, desktop userData).
#
#   scripts/dev/bifrost-sandbox.sh install [DMG]  # run the installer (default: release DMG in sandbox/dl)
#   scripts/dev/bifrost-sandbox.sh desktop        # open the sandboxed Hermes desktop
#   scripts/dev/bifrost-sandbox.sh shell          # shell with the sandbox env (hermes, logs)
#   scripts/dev/bifrost-sandbox.sh done           # end the test: clear the GUI env (before using the main Hermes.app)
#   scripts/dev/bifrost-sandbox.sh reset          # delete the sandbox install (keeps dl/)
#
# `install` also publishes HERMES_HOME / HERMES_DESKTOP_USER_DATA_DIR to the
# GUI session (launchctl setenv) so apps opened through LaunchServices -- the
# installer's "Launch Hermes" button, Finder, Dock -- land in the sandbox too.
# While that is set, the main Hermes.app would ALSO open the sandbox; quit it
# before testing and run `done` afterwards. The main gateway pins its own
# HERMES_HOME in its launchd plist and is unaffected.
set -euo pipefail

SB="${BIFROST_SANDBOX:-$HOME/hermes-sandbox}"

if [ "${1:-}" = done ]; then
    launchctl unsetenv HERMES_HOME
    launchctl unsetenv HERMES_DESKTOP_USER_DATA_DIR
    echo "GUI env cleared; the main Hermes.app uses ~/.hermes again"
    exit 0
fi

if [ "${1:-}" = reset ]; then
    rm -rf "$SB/home" "$SB/userdata" "$SB/app"
    echo "removed sandbox install under $SB"
    exit 0
fi

mkdir -p "$SB/home" "$SB/userdata" "$SB/app"

export HOME="$SB/home"
export HERMES_HOME="$SB/home/.hermes"
export HERMES_DESKTOP_USER_DATA_DIR="$SB/userdata"
# Drop the real ~/.local/bin so the main `hermes` launcher is never picked up.
export PATH="$SB/home/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export ZDOTDIR="$SB/home"
touch "$SB/home/.zshrc"

case "${1:-}" in
    install)
        dmg="${2:-$SB/dl/Hermes-Setup-Bifrost.dmg}"
        mnt="$(mktemp -d)"
        hdiutil attach -nobrowse -readonly -mountpoint "$mnt" "$dmg" >/dev/null
        rm -rf "$SB/app/Hermes Bifrost.app"
        ditto "$mnt/Hermes Bifrost.app" "$SB/app/Hermes Bifrost.app"
        hdiutil detach "$mnt" >/dev/null
        launchctl setenv HERMES_HOME "$HERMES_HOME"
        launchctl setenv HERMES_DESKTOP_USER_DATA_DIR "$HERMES_DESKTOP_USER_DATA_DIR"
        exec "$SB/app/Hermes Bifrost.app/Contents/MacOS/Hermes-Setup" </dev/null
        ;;
    desktop)
        exe="$(ls "$HERMES_HOME"/hermes-agent/apps/desktop/release/mac*/Hermes.app/Contents/MacOS/Hermes 2>/dev/null | head -1)"
        [ -n "$exe" ] || { echo "desktop app not installed in the sandbox yet" >&2; exit 1; }
        exec "$exe"
        ;;
    shell)
        echo "sandbox shell: HOME=$HOME HERMES_HOME=$HERMES_HOME (exit to leave)"
        exec /bin/zsh -i
        ;;
    *)
        sed -n '2,16p' "$0"
        exit 2
        ;;
esac
