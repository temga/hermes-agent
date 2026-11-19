#!/usr/bin/env bash
# Bifrost edition: copy the fork's GitHub refs to the GitVerse mirror from this machine.
#
# Same job as .github/workflows/bifrost-gitverse-mirror.yml, for when GitHub Actions is unavailable
# (billing lock, outage) or you want the mirror current before an installer release. Installers fall
# back to this copy when github.com does not answer (scripts/install.sh, scripts/install.ps1).
#
# Reads GitHub's state (origin), not the working tree, so unpushed local commits never reach the
# mirror. Never forces: a diverged mirror fails the push instead of being overwritten.
#
#   GITVERSE_TOKEN=... scripts/bifrost/mirror_gitverse.sh            # main, bifrost-edition, bifrost-next, v* tags
#   GITVERSE_TOKEN=... scripts/bifrost/mirror_gitverse.sh --dry-run
#
# The token is sent only as an HTTP header of the push; it is never written to git config or disk.
set -euo pipefail

GITVERSE_URL="${GITVERSE_URL:-https://gitverse.ru/temga1502/hermes-agent.git}"
GITVERSE_USER="${GITVERSE_USER:-temga1502}"
ORIGIN="${MIRROR_SOURCE_REMOTE:-origin}"

dry=()
case "${1:-}" in
  "") ;;
  --dry-run) dry=(--dry-run) ;;
  *) echo "usage: $0 [--dry-run]" >&2; exit 2 ;;
esac

if [ -z "${GITVERSE_TOKEN:-}" ]; then
  echo "GITVERSE_TOKEN is not set (a GitVerse access token with write access to the mirror repo)" >&2
  exit 1
fi

git fetch --quiet --tags "$ORIGIN" main bifrost-next

auth="$(printf '%s:%s' "$GITVERSE_USER" "$GITVERSE_TOKEN" | base64 | tr -d '\n')"
# Header via the environment, not `git -c`, so the credential never shows up in `ps` output.
push() {
  GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=http.extraheader GIT_CONFIG_VALUE_0="Authorization: Basic $auth" \
    git push ${dry[@]+"${dry[@]}"} "$GITVERSE_URL" "$@"
}

refspecs=(
  "refs/remotes/$ORIGIN/main:refs/heads/main"
  "refs/remotes/$ORIGIN/main:refs/heads/bifrost-edition"
  "refs/remotes/$ORIGIN/bifrost-next:refs/heads/bifrost-next"
)
# v* tags as GitHub has them (not local-only ones); a tag already on the mirror is rejected, never moved.
while IFS= read -r tag; do
  [ -n "$tag" ] && refspecs+=("refs/tags/$tag:refs/tags/$tag")
done < <(git ls-remote --tags --refs "$ORIGIN" 'v*' | sed 's|.*refs/tags/||')

push "${refspecs[@]}"
