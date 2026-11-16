//! Resolves and downloads `scripts/install.ps1` (and `install.sh`).
//!
//! Resolution order:
//!   1. Dev shortcut: a sibling repo checkout via $HERMES_SETUP_DEV_REPO_ROOT
//!      env var. Lets devs iterate without re-publishing the script.
//!   2. Bundled fallback: if the installer was bundled with a script (e.g.
//!      tauri's `resource` mechanism), serve from there. Not used today.
//!   3. Network: download from GitHub raw at a pinned commit or branch.
//!      Commit pins are immutable; branch pins are HEAD-tracking.
//!
//! Mirrors `apps/desktop/electron/bootstrap-runner.ts`'s `resolveInstallScript`,
//! but the dev-checkout resolution is driven by an env var rather than the
//! Electron app's APP_ROOT/../.. trick, because Hermes-Setup.exe is meant
//! to live OUTSIDE any repo checkout.

use anyhow::{anyhow, Context, Result};
use std::path::{Path, PathBuf};
use tokio::io::AsyncWriteExt;

use crate::paths;

/// Identity of the install.ps1 we'll execute. Used by both the manifest
/// fetch and the per-stage runs.
#[derive(Debug, Clone)]
pub struct ResolvedScript {
    pub path: PathBuf,
    pub source: ScriptSource,
    /// Commit pin (40-char SHA) if known. install.ps1's `-Commit` arg is
    /// what makes the repo stage clone the exact tested SHA.
    pub commit: Option<String>,
    pub branch: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ScriptSource {
    DevCheckout,
    Bundled,
    Downloaded,
}

/// What flavor of script (Windows .ps1 vs Unix .sh).
#[derive(Debug, Clone, Copy)]
pub enum ScriptKind {
    Ps1,
    Sh,
}

impl ScriptKind {
    pub fn for_current_os() -> Self {
        if cfg!(target_os = "windows") {
            Self::Ps1
        } else {
            Self::Sh
        }
    }

    fn filename(&self) -> &'static str {
        match self {
            Self::Ps1 => "install.ps1",
            Self::Sh => "install.sh",
        }
    }
}

/// Validates a string looks like a git SHA (7+ hex chars). Mirrors
/// `STAMP_COMMIT_RE` from bootstrap-runner.ts.
fn is_valid_commit(s: &str) -> bool {
    let len = s.len();
    (7..=40).contains(&len) && s.chars().all(|c| c.is_ascii_hexdigit())
}

/// Resolves the install script to use for this run.
///
/// `pin` is the commit-or-branch from either Hermes-Setup's build-time
/// constant (compiled into the installer) or a runtime override.
pub async fn resolve(
    kind: ScriptKind,
    pin: &Pin,
    emit_log: &impl Fn(&str),
) -> Result<ResolvedScript> {
    // 1. Dev shortcut.
    if let Ok(repo_root) = std::env::var("HERMES_SETUP_DEV_REPO_ROOT") {
        let candidate = PathBuf::from(repo_root).join("scripts").join(kind.filename());
        if candidate.exists() {
            emit_log(&format!(
                "[bootstrap] dev mode — using local {} at {}",
                kind.filename(),
                candidate.display()
            ));
            return Ok(ResolvedScript {
                path: candidate,
                source: ScriptSource::DevCheckout,
                commit: pin.commit.clone(),
                branch: pin.branch.clone(),
            });
        }
    }

    // 2. Bundled copy: a commit-pinned build embeds that commit's scripts, so
    //    the common install never touches raw.githubusercontent.com (anonymous
    //    429s behind shared NATs). Skipped when the pin was overridden.
    if let (Some(commit), Some(bytes)) = (&pin.commit, bundled_bytes(kind, pin.commit.as_deref())) {
        let dest = download_path(kind, commit);
        write_cached_script(kind, bytes, &dest).await?;
        emit_log(&format!(
            "[bootstrap] using {} bundled with the installer ({})",
            kind.filename(),
            truncate_ref(commit)
        ));
        return Ok(ResolvedScript {
            path: dest,
            source: ScriptSource::Bundled,
            commit: pin.commit.clone(),
            branch: pin.branch.clone(),
        });
    }

    // 3. Network. Pin must be a real commit or a branch ref.
    //
    // Always download; a previously downloaded script is never reused. A
    // stale script drives a tree it predates (the repository stage follows
    // the live branch), and a failed download is fatal so Retry refetches.
    let commit_or_ref = match (&pin.commit, &pin.branch) {
        (Some(c), _) if is_valid_commit(c) => c.clone(),
        (_, Some(b)) if !b.trim().is_empty() => b.clone(),
        (Some(other), _) => {
            return Err(anyhow!(
                "install script pin commit `{other}` is not a valid git SHA"
            ));
        }
        _ => {
            return Err(anyhow!(
                "no install-script pin supplied — installer cannot resolve a script source"
            ));
        }
    };

    let dest = download_path(kind, &commit_or_ref);
    emit_log(&format!(
        "[bootstrap] downloading {} for {} from GitHub",
        kind.filename(),
        truncate_ref(&commit_or_ref)
    ));
    download(kind, &commit_or_ref, &dest, emit_log).await?;
    emit_log(&format!("[bootstrap] downloaded to {}", dest.display()));
    Ok(ResolvedScript {
        path: dest,
        source: ScriptSource::Downloaded,
        commit: pin.commit.clone(),
        branch: pin.branch.clone(),
    })
}

#[derive(Debug, Clone, Default)]
pub struct Pin {
    pub commit: Option<String>,
    pub branch: Option<String>,
}

fn download_path(kind: ScriptKind, commit_or_ref: &str) -> PathBuf {
    let safe = sanitize_ref(commit_or_ref);
    let filename = match kind {
        ScriptKind::Ps1 => format!("install-{safe}.ps1"),
        ScriptKind::Sh => format!("install-{safe}.sh"),
    };
    paths::bootstrap_cache_dir().join(filename)
}

/// Replace anything that's not [A-Za-z0-9._-] with `_`. Branch refs can
/// contain `/`, dots, etc.; we want a flat filename.
fn sanitize_ref(s: &str) -> String {
    s.chars()
        .map(|c| {
            if c.is_ascii_alphanumeric() || c == '.' || c == '-' || c == '_' {
                c
            } else {
                '_'
            }
        })
        .collect()
}

fn truncate_ref(s: &str) -> &str {
    if is_valid_commit(s) && s.len() >= 12 {
        &s[..12]
    } else {
        s
    }
}

/// UTF-8 BOM. Windows PowerShell 5.1 reads a BOM-less `.ps1` using the system
/// ANSI code page; a leading BOM is what tells it the file is UTF-8. The
/// `irm | iex` / `[scriptblock]::Create` path strips BOMs on purpose, but the
/// GUI bootstrap runs the *cached file* via `-File`, so we write the opposite
/// (#67193).
const UTF8_BOM: &[u8] = &[0xEF, 0xBB, 0xBF];

/// Prepare bytes for the on-disk bootstrap cache.
///
/// `.ps1` files get a UTF-8 BOM (unless one is already present). `.sh` files
/// are left unchanged — a BOM would break `#!/usr/bin/env bash`.
pub(crate) fn prepare_cached_script_bytes(kind: ScriptKind, bytes: &[u8]) -> Vec<u8> {
    match kind {
        ScriptKind::Ps1 => {
            if bytes.starts_with(UTF8_BOM) {
                bytes.to_vec()
            } else {
                let mut out = Vec::with_capacity(UTF8_BOM.len() + bytes.len());
                out.extend_from_slice(UTF8_BOM);
                out.extend_from_slice(bytes);
                out
            }
        }
        ScriptKind::Sh => bytes.to_vec(),
    }
}

const BUNDLED_PS1: &[u8] = include_bytes!(concat!(env!("OUT_DIR"), "/bundled-install.ps1"));
const BUNDLED_SH: &[u8] = include_bytes!(concat!(env!("OUT_DIR"), "/bundled-install.sh"));

/// The script embedded at build time, if `commit` is exactly the commit it was
/// taken from.
fn bundled_bytes(kind: ScriptKind, commit: Option<&str>) -> Option<&'static [u8]> {
    let baked = option_env!("BUNDLED_SCRIPT_COMMIT")?;
    if !commit?.eq_ignore_ascii_case(baked) {
        return None;
    }
    let bytes = match kind {
        ScriptKind::Ps1 => BUNDLED_PS1,
        ScriptKind::Sh => BUNDLED_SH,
    };
    (!bytes.is_empty()).then_some(bytes)
}

/// Mirrors that serve the same bytes for a commit. raw.githubusercontent.com
/// rate-limits anonymous clients per IP (HTTP 429), and one shared NAT or VPN
/// exit is enough to exhaust it, so a second CDN answers when it does. jsDelivr
/// is only useful for an immutable commit; a branch would be served stale.
fn script_urls(kind: ScriptKind, commit_or_ref: &str) -> Vec<String> {
    let name = kind.filename();
    let mut urls = vec![format!(
        "https://raw.githubusercontent.com/temga/hermes-agent/{commit_or_ref}/scripts/{name}"
    )];
    if is_valid_commit(commit_or_ref) {
        urls.push(format!(
            "https://cdn.jsdelivr.net/gh/temga/hermes-agent@{commit_or_ref}/scripts/{name}"
        ));
    }
    urls
}

const ATTEMPTS_PER_URL: u32 = 3;
const MAX_RETRY_AFTER_SECS: u64 = 15;

/// Seconds to wait before attempt `attempt` (1-based) is retried: the server's
/// `Retry-After` when it sent one, else 1s, 2s, ...; capped so a hostile or
/// hour-long value never freezes the installer.
fn backoff_secs(retry_after: Option<&str>, attempt: u32) -> u64 {
    retry_after
        .and_then(|v| v.trim().parse::<u64>().ok())
        .unwrap_or(1u64 << (attempt - 1).min(4))
        .min(MAX_RETRY_AFTER_SECS)
}

fn is_retryable(status: reqwest::StatusCode) -> bool {
    status == reqwest::StatusCode::TOO_MANY_REQUESTS || status.is_server_error()
}

fn friendly_failure(kind: ScriptKind, errors: &[String]) -> anyhow::Error {
    let rate_limited = errors.iter().any(|e| e.contains("429"));
    let hint = if rate_limited {
        "GitHub temporarily limits requests from this network address. \
         Wait a minute and press Retry, or switch network / VPN."
    } else {
        "Check the internet connection (GitHub must be reachable) and press Retry."
    };
    anyhow!(
        "Failed to download {}. {hint}\n{}",
        kind.filename(),
        errors.join("\n")
    )
}

/// Downloads to `dest_path` via reqwest with rustls, trying each mirror in
/// turn and retrying 429/5xx/network errors with backoff.
///
/// Explicit timeouts: this runs on every bootstrap, and a black-holed
/// connection (captive portal, hung proxy) would otherwise hang forever
/// instead of failing so the user can Retry.
async fn download(
    kind: ScriptKind,
    commit_or_ref: &str,
    dest_path: &Path,
    emit_log: &impl Fn(&str),
) -> Result<()> {
    let client = reqwest::Client::builder()
        .connect_timeout(std::time::Duration::from_secs(10))
        .timeout(std::time::Duration::from_secs(60))
        .build()
        .context("building download client")?;

    let mut errors = Vec::new();
    for url in script_urls(kind, commit_or_ref) {
        for attempt in 1..=ATTEMPTS_PER_URL {
            let mut retry_after = None;
            let failure = match client
                .get(&url)
                .header("User-Agent", "hermes-setup/0.0.1")
                .send()
                .await
            {
                Ok(resp) if resp.status().is_success() => match resp.bytes().await {
                    Ok(bytes) => {
                        return write_cached_script(kind, &bytes, dest_path).await;
                    }
                    Err(e) => format!("reading body of {url}: {e}"),
                },
                Ok(resp) => {
                    let status = resp.status();
                    retry_after = resp
                        .headers()
                        .get(reqwest::header::RETRY_AFTER)
                        .and_then(|v| v.to_str().ok())
                        .map(str::to_owned);
                    let msg = format!("HTTP {status} from {url}");
                    if !is_retryable(status) {
                        errors.push(msg);
                        break;
                    }
                    msg
                }
                Err(e) => format!("GET {url}: {e}"),
            };
            emit_log(&format!("[bootstrap] {failure} (attempt {attempt}/{ATTEMPTS_PER_URL})"));
            if attempt == ATTEMPTS_PER_URL {
                errors.push(failure);
            } else {
                tokio::time::sleep(std::time::Duration::from_secs(backoff_secs(
                    retry_after.as_deref(),
                    attempt,
                )))
                .await;
            }
        }
    }
    Err(friendly_failure(kind, &errors))
}

/// Writes the script to `dest_path` via `dest_path.tmp` + rename so a partial
/// write is never executed.
async fn write_cached_script(kind: ScriptKind, bytes: &[u8], dest_path: &Path) -> Result<()> {
    if let Some(parent) = dest_path.parent() {
        std::fs::create_dir_all(parent).with_context(|| {
            format!("creating bootstrap-cache parent dir {}", parent.display())
        })?;
    }
    let tmp_path = dest_path.with_extension({
        let ext = dest_path
            .extension()
            .and_then(|s| s.to_str())
            .unwrap_or("tmp");
        format!("{ext}.tmp")
    });
    let bytes = prepare_cached_script_bytes(kind, bytes);

    let mut file = tokio::fs::File::create(&tmp_path)
        .await
        .with_context(|| format!("creating temp file {}", tmp_path.display()))?;
    file.write_all(&bytes)
        .await
        .with_context(|| format!("writing temp file {}", tmp_path.display()))?;
    file.flush().await.context("flushing temp file")?;
    drop(file);

    tokio::fs::rename(&tmp_path, dest_path)
        .await
        .with_context(|| {
            format!("renaming {} → {}", tmp_path.display(), dest_path.display())
        })?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn is_valid_commit_accepts_short_and_full_shas() {
        assert!(is_valid_commit("02d26981d3d4ad50e142399b8476f59ad5953ff0"));
        assert!(is_valid_commit("02d2698"));
        assert!(!is_valid_commit("02d269"));
        assert!(!is_valid_commit("not-a-sha"));
        assert!(!is_valid_commit(""));
    }

    #[test]
    fn sanitize_ref_replaces_slashes() {
        assert_eq!(sanitize_ref("bb/gui"), "bb_gui");
        assert_eq!(sanitize_ref("main"), "main");
        assert_eq!(sanitize_ref("release/1.2.3"), "release_1.2.3");
    }

    #[test]
    fn prepare_cached_ps1_prefixes_utf8_bom() {
        let out = prepare_cached_script_bytes(ScriptKind::Ps1, b"Write-Host hi\n");
        assert!(out.starts_with(UTF8_BOM), "cached .ps1 must start with UTF-8 BOM");
        assert_eq!(&out[UTF8_BOM.len()..], b"Write-Host hi\n");
    }

    #[test]
    fn prepare_cached_ps1_does_not_double_bom() {
        let mut already = UTF8_BOM.to_vec();
        already.extend_from_slice(b"x");
        let out = prepare_cached_script_bytes(ScriptKind::Ps1, &already);
        assert_eq!(out, already);
        assert_eq!(out.windows(3).filter(|w| *w == UTF8_BOM).count(), 1);
    }

    #[test]
    fn prepare_cached_sh_stays_bomless() {
        let out = prepare_cached_script_bytes(ScriptKind::Sh, b"#!/usr/bin/env bash\n");
        assert!(!out.starts_with(UTF8_BOM));
        assert_eq!(out, b"#!/usr/bin/env bash\n");
    }

    #[test]
    fn jsdelivr_mirror_only_for_immutable_commits() {
        let sha = "d13a83e42d43b8de14b7c73a5dadae8dd8d2c738";
        let urls = script_urls(ScriptKind::Ps1, sha);
        assert_eq!(urls.len(), 2);
        assert!(urls[0].starts_with("https://raw.githubusercontent.com/temga/"));
        assert!(urls[1].contains(&format!("hermes-agent@{sha}/scripts/install.ps1")));
        assert_eq!(script_urls(ScriptKind::Sh, "main").len(), 1);
    }

    #[test]
    fn backoff_honours_retry_after_but_is_capped() {
        assert_eq!(backoff_secs(Some("5"), 1), 5);
        assert_eq!(backoff_secs(Some("3600"), 1), MAX_RETRY_AFTER_SECS);
        assert_eq!(backoff_secs(None, 1), 1);
        assert_eq!(backoff_secs(None, 2), 2);
        assert_eq!(backoff_secs(Some("Wed, 21 Oct 2026 07:28:00 GMT"), 3), 4);
    }

    #[test]
    fn rate_limit_failure_tells_the_user_what_to_do() {
        let e = friendly_failure(ScriptKind::Ps1, &["HTTP 429 Too Many Requests from x".into()]);
        assert!(e.to_string().contains("Wait a minute"));
    }

    #[test]
    fn commit_pins_are_distinguished_from_branch_pins() {
        assert!(is_valid_commit("02d26981d3d4ad50e142399b8476f59ad5953ff0"));
        assert!(!is_valid_commit("main"));
        assert!(!is_valid_commit("release/1.2.3"));
    }
}
