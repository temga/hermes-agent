"""Bifrost edition: pinned PM inputs come from the fork's GitHub mirror before upstream hosts."""
import hashlib

from pm import artifact_mirror, paths
from pm.store import Store
from tests.pm._range_server import RangeHandler, dl_server as dl_server, url  # noqa: PLC0414 -- pytest fixture re-export


def _serve(server, monkeypatch, tmp_path, *, fork_has_bytes: bool, lock_has_bytes: bool):
    body = b"ffmpeg pinned for darwin-x64" * 1000
    digest = hashlib.sha256(body).hexdigest()
    monkeypatch.setattr(artifact_mirror, "FORK_MIRROR_PREFIX", url(server, "/fork/"))
    monkeypatch.setattr(artifact_mirror, "PUBLIC_PREFIX", url(server, "/nous/"))
    monkeypatch.setattr(paths, "partials_root", lambda: tmp_path / "partials")
    if fork_has_bytes:
        RangeHandler.payloads["/fork/" + digest] = body
    if lock_has_bytes:
        RangeHandler.payloads["/upstream/ffmpeg.zip"] = body
    return body, digest


def _fetch(server, tmp_path, digest):
    store = Store(tmp_path / "store")
    with store.scratch() as scratch:
        return store.fetch(url(server, "/upstream/ffmpeg.zip"), digest, scratch).read_bytes()


def test_fork_mirror_serves_before_the_upstream_host(dl_server, tmp_path, monkeypatch):
    body, digest = _serve(dl_server, monkeypatch, tmp_path, fork_has_bytes=True, lock_has_bytes=True)
    assert _fetch(dl_server, tmp_path, digest) == body
    served = {path for path, *_ in RangeHandler.ranges_seen}
    assert served == {"/fork/" + digest}


def test_a_digest_missing_from_the_fork_mirror_falls_back_to_the_lock_url(dl_server, tmp_path, monkeypatch):
    body, digest = _serve(dl_server, monkeypatch, tmp_path, fork_has_bytes=False, lock_has_bytes=True)
    assert _fetch(dl_server, tmp_path, digest) == body
    assert {path for path, *_ in RangeHandler.ranges_seen} == {"/upstream/ffmpeg.zip"}


def test_users_npm_registry_still_goes_first(tmp_path, monkeypatch):
    digest = "b" * 64
    monkeypatch.setenv("NPM_CONFIG_REGISTRY", "https://npm.corp.example")
    source = artifact_mirror.pinned_source("https://registry.npmjs.org/npm/-/npm-10.9.2.tgz", tmp_path / "npm.tgz", digest)
    assert source.url == "https://npm.corp.example/npm/-/npm-10.9.2.tgz"
    assert source.fallbacks == (artifact_mirror.fork_mirror_url(digest), artifact_mirror.mirror_url(digest))
