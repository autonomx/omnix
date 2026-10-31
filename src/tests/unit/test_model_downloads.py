"""Pinned, checksum-verified model downloads for the model service images (WP-11.1)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.models.__main__ import main
from app.models.downloads import ModelDownloadError, download, load_catalog, select, verify

REVISION = "0123456789abcdef0123456789abcdef01234567"
WEIGHTS = b"pinned weights"
CONFIG = b'{"model": "test"}'


def _catalog(path: Path, *, weights: bytes = WEIGHTS, revision: str = REVISION) -> Path:
    path.write_text(json.dumps({"models": {"test-model": {
        "repo": "org/test-model", "revision": revision, "service": "tts",
        "files": {
            "config.json": {"sha256": hashlib.sha256(CONFIG).hexdigest(), "size": len(CONFIG)},
            "weights/model.safetensors": {"sha256": hashlib.sha256(weights).hexdigest(), "size": len(weights)},
        },
    }}}), encoding="utf-8")
    return path


class _FakeHub:
    """Writes files where hf_hub_download would: a blob plus the snapshot path."""

    def __init__(self, contents: dict[str, bytes]) -> None:
        self.contents = contents
        self.calls: list[str] = []

    def __call__(self, *, repo_id: str, filename: str, revision: str, cache_dir: str) -> str:
        self.calls.append(filename)
        repo = Path(cache_dir) / ("models--" + repo_id.replace("/", "--"))
        target = repo / "snapshots" / revision / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(self.contents[filename])
        return str(target)


def test_download_verifies_every_file_and_pins_the_main_ref(tmp_path):
    entry = load_catalog(_catalog(tmp_path / "catalog.json"))["test-model"]
    hub = _FakeHub({"config.json": CONFIG, "weights/model.safetensors": WEIGHTS})
    cache = tmp_path / "hub"

    snapshot = download(entry, cache_dir=cache, fetch=hub)

    assert snapshot == cache / "models--org--test-model" / "snapshots" / REVISION
    assert (cache / "models--org--test-model" / "refs" / "main").read_text() == REVISION
    assert verify(entry, cache_dir=cache) == []
    # A second run downloads nothing: the cached files already match.
    download(entry, cache_dir=cache, fetch=hub)
    assert hub.calls == ["config.json", "weights/model.safetensors"]


def test_a_file_with_the_wrong_digest_is_refused_and_removed(tmp_path):
    entry = load_catalog(_catalog(tmp_path / "catalog.json"))["test-model"]
    hub = _FakeHub({"config.json": CONFIG, "weights/model.safetensors": b"tampered weights"})
    cache = tmp_path / "hub"

    with pytest.raises(ModelDownloadError, match="weights/model.safetensors has SHA-256"):
        download(entry, cache_dir=cache, fetch=hub)

    assert not (cache / "models--org--test-model" / "snapshots" / REVISION / "weights/model.safetensors").exists()
    assert not (cache / "models--org--test-model" / "refs" / "main").exists()
    assert "weights/model.safetensors: missing" in verify(entry, cache_dir=cache)


def _direct_catalog(path: Path, *, weights: bytes = WEIGHTS) -> Path:
    path.write_text(json.dumps({"models": {"direct-model": {
        "repo": "org/direct-model", "revision": "v1", "service": "portrait", "source": "direct",
        "files": {"weights.pth": {"sha256": hashlib.sha256(weights).hexdigest(), "size": len(weights),
                                  "url": "https://example.org/weights.pth"}},
    }}}), encoding="utf-8")
    return path


class _FakeUrls:
    """Stands in for the direct fetcher: writes the URL's bytes to the target."""

    def __init__(self, contents: dict[str, bytes]) -> None:
        self.contents = contents
        self.calls: list[str] = []

    def __call__(self, item, target: Path) -> Path:
        self.calls.append(item.url)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(self.contents[item.url])
        return target


def test_a_direct_model_downloads_from_its_urls_into_the_snapshot_layout(tmp_path):
    entry = load_catalog(_direct_catalog(tmp_path / "catalog.json"))["direct-model"]
    urls = _FakeUrls({"https://example.org/weights.pth": WEIGHTS})
    cache = tmp_path / "hub"

    snapshot = download(entry, cache_dir=cache, fetch_url=urls)

    assert snapshot == cache / "models--org--direct-model" / "snapshots" / "v1"
    assert (snapshot / "weights.pth").read_bytes() == WEIGHTS
    assert verify(entry, cache_dir=cache) == []
    download(entry, cache_dir=cache, fetch_url=urls)
    assert urls.calls == ["https://example.org/weights.pth"]


def test_a_direct_file_with_the_wrong_digest_is_refused_and_removed(tmp_path):
    entry = load_catalog(_direct_catalog(tmp_path / "catalog.json"))["direct-model"]
    cache = tmp_path / "hub"

    with pytest.raises(ModelDownloadError, match="weights.pth has SHA-256"):
        download(entry, cache_dir=cache, fetch_url=_FakeUrls({"https://example.org/weights.pth": b"tampered"}))

    assert not (cache / "models--org--direct-model" / "snapshots" / "v1" / "weights.pth").exists()


def test_a_refused_direct_download_says_where_to_save_the_file_by_hand(tmp_path, monkeypatch):
    from app.models import packs
    from app.models.downloads import fetch_direct_file

    def refuse(url, target, **_kwargs):
        raise packs.PackError(f"download failed (403): {url}")

    monkeypatch.setattr(packs, "download_file", refuse)
    entry = load_catalog(_direct_catalog(tmp_path / "catalog.json"))["direct-model"]
    target = tmp_path / "snapshot" / "weights.pth"
    with pytest.raises(ModelDownloadError) as raised:
        fetch_direct_file(entry.files[0], target)
    message = str(raised.value)
    assert "403" in message and "https://example.org/weights.pth" in message and str(target) in message


def test_verify_reports_a_changed_file(tmp_path):
    entry = load_catalog(_catalog(tmp_path / "catalog.json"))["test-model"]
    cache = tmp_path / "hub"
    download(entry, cache_dir=cache, fetch=_FakeHub({"config.json": CONFIG, "weights/model.safetensors": WEIGHTS}))
    (cache / "models--org--test-model" / "snapshots" / REVISION / "config.json").write_bytes(b"{}")
    assert verify(entry, cache_dir=cache) == ["config.json: checksum mismatch"]


def test_the_catalog_requires_full_commit_revisions(tmp_path):
    with pytest.raises(ModelDownloadError, match="full commit hash"):
        load_catalog(_catalog(tmp_path / "catalog.json", revision="main"))


def test_selection_by_service_and_unknown_ids(tmp_path):
    catalog = load_catalog(_catalog(tmp_path / "catalog.json"))
    assert [entry.id for entry in select(catalog, [], "tts")] == ["test-model"]
    with pytest.raises(ModelDownloadError, match="unknown model"):
        select(catalog, ["missing"], None)
    with pytest.raises(ModelDownloadError, match="name a model"):
        select(catalog, [], None)


def test_the_shipped_catalog_covers_each_model_service():
    catalog = load_catalog()
    assert {"tts", "stt", "image"} <= {entry.service for entry in catalog.values()}
    for entry in catalog.values():
        assert all(len(item.sha256) == 64 and item.size > 0 for item in entry.files)


def test_verify_command_fails_when_models_are_missing(tmp_path, capsys):
    assert main(["verify", "--service", "tts", "--cache-dir", str(tmp_path)]) == 1
    assert "missing" in capsys.readouterr().out
