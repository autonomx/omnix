"""The community world catalog and sharing by pull request, with GitHub and the database faked."""
from __future__ import annotations

import base64
import hashlib
import json
from types import SimpleNamespace

import pytest

from app.apps.rpg.genesis.worlds import world_catalog, world_sharing
from app.apps.rpg.genesis.worlds.world_sharing import GitHubResponse

REPO = "autonomx/omnix-worlds"
BUNDLE = b"PK\x03\x04 a world bundle"


def _index(**bundle_overrides) -> dict:
    bundle = {
        "url": f"https://github.com/{REPO}/releases/download/world-aurelia-v1/aurelia.omnix-world.zip",
        "sha256": hashlib.sha256(BUNDLE).hexdigest(),
        "bytes": len(BUNDLE),
        **bundle_overrides,
    }
    return {
        "schema_version": "omnix-world-catalog-v1",
        "updated_at": "2026-10-23T00:00:00Z",
        "worlds": [
            {"id": "aurelia", "version": 1, "title": "Aurelia", "summary": "A gate opens.", "genre": "fantasy",
             "tone": "heroic", "author": "someone", "published_at": "2026-10-23", "bundle": bundle}
        ],
    }


def _downloads(index: dict, files: dict[str, bytes] | None = None):
    seen: list[str] = []

    def download(url: str, limit: int) -> bytes:
        seen.append(url)
        if url.endswith("/main/index.json"):
            return json.dumps(index).encode()
        content = (files or {})[url]
        assert len(content) <= limit
        return content

    download.seen = seen  # type: ignore[attr-defined]
    return download


@pytest.fixture(autouse=True)
def _catalog_repo(monkeypatch):
    monkeypatch.setenv("OMNIX_RPG_WORLD_CATALOG_REPO", REPO)


def test_install_checks_the_bundle_against_the_index_and_records_the_catalog_entry(monkeypatch) -> None:
    index = _index()
    url = index["worlds"][0]["bundle"]["url"]
    imported: list[dict] = []
    monkeypatch.setattr(world_catalog, "_installed", lambda _database: {})

    def fake_import(content, *, target_world_id, catalog, database):
        imported.append({"content": content, "target": target_world_id, "catalog": catalog})
        return {"world_id": target_world_id, "bundle_sha256": hashlib.sha256(content).hexdigest()}

    monkeypatch.setattr(world_catalog, "import_world_bundle", fake_import)
    result = world_catalog.import_catalog_world("aurelia", download=_downloads(index, {url: BUNDLE}))

    assert result["world_id"] == "world:aurelia" and result["adopted"] is False
    assert imported[0]["content"] == BUNDLE
    assert imported[0]["catalog"] == {"repo": REPO, "id": "aurelia", "version": 1, "author": "someone", "title": "Aurelia"}


def test_install_refuses_a_file_that_does_not_match_the_index(monkeypatch) -> None:
    index = _index()
    url = index["worlds"][0]["bundle"]["url"]
    monkeypatch.setattr(world_catalog, "_installed", lambda _database: {})
    monkeypatch.setattr(world_catalog, "import_world_bundle", lambda *a, **k: pytest.fail("imported a bad file"))
    tampered = BUNDLE[:-1] + b"!"
    with pytest.raises(ValueError, match="world_catalog_file_digest_mismatch"):
        world_catalog.import_catalog_world("aurelia", download=_downloads(index, {url: tampered}))


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/aurelia.zip",
        "https://github.com/someone-else/omnix-worlds/releases/download/x/aurelia.zip",
        f"https://github.com/{REPO}/releases/download/../../evil/aurelia.zip",
    ],
)
def test_install_downloads_only_from_the_catalog_releases(monkeypatch, url) -> None:
    monkeypatch.setattr(world_catalog, "_installed", lambda _database: {})
    download = _downloads(_index(url=url))
    with pytest.raises(ValueError, match="world_catalog_file_url_untrusted"):
        world_catalog.import_catalog_world("aurelia", download=download)
    assert all(seen.endswith("/main/index.json") for seen in download.seen)


def test_install_reuses_a_world_already_downloaded(monkeypatch) -> None:
    index = _index()
    installed = {"world_id": "world:aurelia", "version": 1, "bundle_sha256": index["worlds"][0]["bundle"]["sha256"], "adopted": True}
    monkeypatch.setattr(world_catalog, "_installed", lambda _database: {"aurelia": installed})
    result = world_catalog.import_catalog_world("aurelia", download=_downloads(index))
    assert result["reused"] is True and result["world_id"] == "world:aurelia"


def test_catalog_lists_nothing_before_the_index_exists(monkeypatch) -> None:
    import urllib.error

    def missing(url, limit):
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    monkeypatch.setattr(world_catalog, "_installed", lambda _database: {})
    assert world_catalog.list_catalog(download=missing)["worlds"] == []


class _Secrets:
    writable = True
    name = "memory"

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get(self, name):
        return self.values.get(name)

    def set(self, name, value):
        self.values[name] = value

    def delete(self, name):
        self.values.pop(name, None)


class _GitHub:
    """Answers the calls a share makes, and remembers them."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict | bytes | None]] = []

    def __call__(self, method, url, headers, body):
        payload = body if url.startswith("https://uploads.") else (json.loads(body) if body else None)
        self.calls.append((method, url, payload))
        if url.endswith("/user"):
            return GitHubResponse(200, {"login": "author1"})
        if url.endswith("/forks"):
            return GitHubResponse(202, {"full_name": "author1/omnix-worlds"})
        if url.endswith("/repos/author1/omnix-worlds"):
            return GitHubResponse(200, {"full_name": "author1/omnix-worlds"})
        if url.endswith("/releases"):
            return GitHubResponse(201, {"id": 77})
        if url.startswith("https://uploads.github.com/"):
            return GitHubResponse(201, {"browser_download_url": "https://github.com/author1/omnix-worlds/releases/download/t/f.zip"})
        if url.endswith("/git/ref/heads/main"):
            return GitHubResponse(200, {"object": {"sha": "abc123"}})
        if url.endswith("/git/refs"):
            return GitHubResponse(201, {})
        if "/contents/submissions/" in url:
            return GitHubResponse(201, {})
        if url.endswith("/pulls"):
            return GitHubResponse(201, {"html_url": f"https://github.com/{REPO}/pull/5"})
        return GitHubResponse(404, {"message": "Not Found"})


class _Work:
    def __init__(self, world, playable):
        self.world_scenarios = SimpleNamespace(get_world=lambda _context, _world_id: world)
        row = (1,) if playable else None
        self.connection = SimpleNamespace(execute=lambda _sql, _params: SimpleNamespace(fetchone=lambda: row))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def rollback(self):
        return None


def _share_setup(monkeypatch, world, *, playable=True):
    secrets = _Secrets()
    monkeypatch.setattr(world_sharing, "secret_store", lambda: secrets)
    monkeypatch.setattr(world_sharing, "current_tenant", lambda: SimpleNamespace(workspace_id="ws1"))
    monkeypatch.setattr(world_sharing, "unit_of_work", lambda database=None: _Work(world, playable))
    monkeypatch.setattr(world_sharing, "export_world_bundle", lambda world_id, database=None: SimpleNamespace(content=BUNDLE))
    return secrets


def test_share_opens_a_pull_request_naming_the_uploaded_bundle(monkeypatch) -> None:
    world = {"id": "world:glass", "title": "The Glass Coast", "description": "Tides of glass.", "genre": "fantasy",
             "tone": "eerie", "metadata": {}}
    secrets = _share_setup(monkeypatch, world)
    github = _GitHub()
    status = world_sharing.connect_with_token("ghp_test", transport=github)
    assert status["connected"] is True and status["login"] == "author1"
    assert "ghp_test" in secrets.values["rpg-world-sharing/ws1/github"]

    result = world_sharing.share_world("world:glass", summary="A coast of glass.", transport=github)

    assert result["pull_request_url"] == f"https://github.com/{REPO}/pull/5"
    upload = next(body for method, url, body in github.calls if url.startswith("https://uploads.github.com/"))
    assert upload == BUNDLE
    submission_put = next(body for method, url, body in github.calls if "/contents/submissions/the-glass-coast.json" in url)
    submission = json.loads(base64.b64decode(submission_put["content"]))
    assert submission["bundle"] == {
        "url": "https://github.com/author1/omnix-worlds/releases/download/t/f.zip",
        "sha256": hashlib.sha256(BUNDLE).hexdigest(),
        "bytes": len(BUNDLE),
    }
    assert submission["author"] == "author1" and submission["summary"] == "A coast of glass."
    pull = next(body for method, url, body in github.calls if url.endswith(f"/repos/{REPO}/pulls"))
    assert pull["head"].startswith("author1:share/the-glass-coast-") and pull["base"] == "main"


def test_share_refuses_a_world_someone_else_shared(monkeypatch) -> None:
    world = {"id": "world:aurelia", "title": "Aurelia", "metadata": {"world_bundle_import": {"bundle_sha256": "a" * 64}}}
    _share_setup(monkeypatch, world)
    github = _GitHub()
    world_sharing.connect_with_token("ghp_test", transport=github)
    with pytest.raises(ValueError, match="world_sharing_imported_world"):
        world_sharing.share_world("world:aurelia", summary="", transport=github)


def test_share_needs_a_github_sign_in(monkeypatch) -> None:
    _share_setup(monkeypatch, {"id": "world:x", "title": "X", "metadata": {}})
    with pytest.raises(ValueError, match="github_not_connected"):
        world_sharing.share_world("world:x", summary="")


def test_share_needs_a_finished_world(monkeypatch) -> None:
    _share_setup(monkeypatch, {"id": "world:draft", "title": "Draft", "metadata": {}}, playable=False)
    github = _GitHub()
    world_sharing.connect_with_token("ghp_test", transport=github)
    with pytest.raises(ValueError, match="world_sharing_not_published"):
        world_sharing.share_world("world:draft", summary="", transport=github)
    assert not any(url.endswith("/forks") for _method, url, _body in github.calls)
