// Canonical `https://github.com/<owner>/<repo>` URL for a git remote (SSH or
// HTTPS). Null for non-GitHub remotes so callers fall back to the upstream URL
// instead of rendering a broken link. The About panel uses it to point
// release-notes links at the fork the user actually tracks.
export function repoOriginUrl(originUrl: string | null | undefined): string | null {
  const value = String(originUrl || '').trim()

  const match =
    /^git@github\.com:([^/]+\/[^/]+?)(?:\.git)?\/?$/i.exec(value) ||
    /^(?:ssh:\/\/git@|https:\/\/|http:\/\/)github\.com\/([^/]+\/[^/]+?)(?:\.git)?\/?$/i.exec(value)

  return match ? `https://github.com/${match[1]}` : null
}
