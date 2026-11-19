#!/usr/bin/env bash
# Bifrost edition: copy the fork's GitHub refs to the GitVerse mirror from this machine.
#
# Same job as .github/workflows/bifrost-gitverse-mirror.yml, for when GitHub Actions is unavailable
# (billing lock, outage). Installers fall back to the GitVerse copy when github.com does not answer
# (scripts/install.sh, scripts/install.ps1).
#
# It works from its own bare clone of GitHub (never from your working checkout), so unpushed local
# commits never reach the mirror and your branches are not touched. Never forces: a diverged mirror
# fails the push instead of being overwritten.
#
#   scripts/bifrost/mirror_gitverse.sh            # main, bifrost-edition, bifrost-next, v* tags
#   scripts/bifrost/mirror_gitverse.sh --dry-run
#   scripts/bifrost/install_gitverse_mirror_agent.sh   # run it every 15 minutes (macOS launchd)
#
# Token: $GITVERSE_TOKEN, else the macOS Keychain item "bifrost-gitverse-mirror" (see the installer).
# It is sent only as an HTTP header of the push, never written to git config or disk.
set -euo pipefail

SOURCE_URL="${MIRROR_SOURCE_URL:-https://github.com/temga/hermes-agent.git}"
GITVERSE_URL="${GITVERSE_URL:-https://gitverse.ru/temga1502/hermes-agent.git}"
GITVERSE_USER="${GITVERSE_USER:-temga1502}"
CACHE="${MIRROR_CACHE:-$HOME/.cache/bifrost-gitverse-mirror.git}"

dry=()
case "${1:-}" in
  "") ;;
  --dry-run) dry=(--dry-run) ;;
  *) echo "usage: $0 [--dry-run]" >&2; exit 2 ;;
esac

token="${GITVERSE_TOKEN:-}"
if [ -z "$token" ] && command -v security >/dev/null 2>&1; then
  token="$(security find-generic-password -s bifrost-gitverse-mirror -w 2>/dev/null || true)"
fi
if [ -z "$token" ]; then
  echo "no GitVerse token: set GITVERSE_TOKEN or store it in the Keychain (scripts/bifrost/install_gitverse_mirror_agent.sh)" >&2
  exit 1
fi

[ -d "$CACHE" ] || git init --quiet --bare "$CACHE"
git="git --git-dir=$CACHE"
$git fetch --quiet --force "$SOURCE_URL" \
  '+refs/heads/main:refs/heads/main' \
  '+refs/heads/bifrost-next:refs/heads/bifrost-next' \
  '+refs/tags/v*:refs/tags/v*'

auth="$(printf '%s:%s' "$GITVERSE_USER" "$token" | base64 | tr -d '\n')"
# Header via the environment, not `git -c`, so the credential never shows up in `ps` output.
GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=http.extraheader GIT_CONFIG_VALUE_0="Authorization: Basic $auth" \
  $git push ${dry[@]+"${dry[@]}"} "$GITVERSE_URL" \
  refs/heads/main:refs/heads/main \
  refs/heads/main:refs/heads/bifrost-edition \
  refs/heads/bifrost-next:refs/heads/bifrost-next \
  'refs/tags/v*:refs/tags/v*'
