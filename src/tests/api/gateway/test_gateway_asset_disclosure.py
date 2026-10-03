"""Asset APIs name assets by id and URL, never by where they are stored (WP-4.10)."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.assets import (
    AssetListResponse,
    AssetMigrationPreview,
    AssetRecord,
    AssetType,
    PublicAssetRecord,
)
from app.providers.tts_service import voice_stem

OPENAPI = Path(__file__).resolve().parents[3] / "apps" / "web" / "src" / "api" / "generated" / "openapi.json"


def _record(path: Path, **changes) -> AssetRecord:
    values = {
        "id": "voice-cloning:jinx",
        "module": "voice-cloning",
        "type": AssetType.VOICE_PROFILE,
        "mime_type": "audio/wav",
        "storage_path": str(path),
        "created_at": "2026-10-03T00:00:00+00:00",
        "metadata": {
            "profile_name": "Jinx",
            "source_path": str(path),
            "segments": [{"voice_id": "C:\\Users\\owner\\voices\\jinx.wav"}, {"voice_id": "\\\\nas\\voices\\vi.wav"}],
            "preview_url": "/api/assets/voice-cloning%3Ajinx/audio",
            "relative": "voice_clones/jinx.wav",
        },
        "compat": {"legacy_manifest": "/srv/omnix/resources/voice_clones/voice_clones.json"},
    }
    return AssetRecord(**{**values, **changes})


def test_the_public_record_leaves_out_storage_and_reduces_paths_to_file_names(tmp_path: Path) -> None:
    public = PublicAssetRecord.model_validate(_record(tmp_path / "voices" / "jinx.wav")).model_dump(mode="json")

    assert {"storage_path", "storage_key", "compat"}.isdisjoint(public)
    assert public["file_name"] == "jinx.wav"
    assert public["download_url"] == "/api/assets/voice-cloning%3Ajinx/download"
    assert public["metadata"]["source_path"] == "jinx.wav"
    assert [item["voice_id"] for item in public["metadata"]["segments"]] == ["jinx.wav", "vi.wav"]
    # API URLs and relative names are not filesystem locations and stay.
    assert public["metadata"]["preview_url"] == "/api/assets/voice-cloning%3Ajinx/audio"
    assert public["metadata"]["relative"] == "voice_clones/jinx.wav"
    assert str(tmp_path) not in json.dumps(public)


def test_a_blob_backed_asset_is_named_by_its_key() -> None:
    public = PublicAssetRecord.model_validate(_record(Path(), storage_path="", storage_key="assets/ab/cover.png"))
    assert public.file_name == "cover.png"


class _Store:
    def __init__(self, record: AssetRecord) -> None:
        self.record = record

    def get_asset(self, asset_id: str) -> AssetRecord | None:
        return self.record if asset_id == self.record.id else None

    def list_assets(self, **_page) -> AssetListResponse:
        return AssetListResponse(assets=[self.record])

    def import_image_manifest_dry_run(self) -> AssetMigrationPreview:
        return AssetMigrationPreview(source="fake", would_import=1, assets=[self.record])


def _client(store: _Store) -> TestClient:
    from app.gateway.main import create_gateway_app

    return TestClient(
        create_gateway_app(asset_store_factory=lambda: store),
        base_url="http://127.0.0.1",
        raise_server_exceptions=False,
        headers={"X-Omnix-Client": "test"},
    )


def test_asset_lists_and_migration_previews_leave_out_the_storage_path(tmp_path: Path) -> None:
    clip = tmp_path / "private" / "jinx.wav"
    client = _client(_Store(_record(clip)))

    for response in (client.get("/api/assets"), client.post("/api/assets/migrations/image/dry-run")):
        assert response.status_code == 200
        asset = response.json()["assets"][0]
        assert "storage_path" not in asset and "compat" not in asset
        assert asset["file_name"] == "jinx.wav"
        assert str(tmp_path) not in response.text
        assert json.dumps(str(tmp_path))[1:-1] not in response.text


def test_an_asset_downloads_by_id(tmp_path: Path) -> None:
    clip = tmp_path / "private" / "jinx.wav"
    clip.parent.mkdir()
    clip.write_bytes(b"RIFF-voice")
    client = _client(_Store(_record(clip)))

    response = client.get("/api/assets/voice-cloning%3Ajinx/download")
    assert response.status_code == 200
    assert response.content == b"RIFF-voice"
    assert response.headers["content-disposition"].startswith("attachment;")
    assert 'filename="jinx.wav"' in response.headers["content-disposition"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert client.get("/api/assets/voice-cloning%3Aunknown/download").status_code == 404


def test_no_api_response_schema_carries_a_storage_location() -> None:
    contract = json.loads(OPENAPI.read_text(encoding="utf-8"))
    schemas = contract["components"]["schemas"]

    def refs(node):
        if isinstance(node, dict):
            if "$ref" in node:
                yield node["$ref"].rsplit("/", 1)[-1]
            for value in node.values():
                yield from refs(value)
        elif isinstance(node, list):
            for value in node:
                yield from refs(value)

    reachable: set[str] = set()
    pending = [name for operations in contract["paths"].values() for operation in operations.values()
               for name in refs(operation.get("responses", {}))]
    while pending:
        name = pending.pop()
        if name not in reachable:
            reachable.add(name)
            pending.extend(refs(schemas.get(name, {})))
    # A filesystem location; blob keys (backtest artifacts) name no host path.
    exposed = sorted(name for name in reachable if "storage_path" in schemas.get(name, {}).get("properties", {}))
    assert exposed == []


def test_voice_asset_ids_reach_the_tts_provider_unchanged() -> None:
    assert voice_stem("voice-cloning:dr.who") == "voice-cloning:dr.who"
    # A path saved by an older client still names its file.
    assert voice_stem("C:\\voices\\jinx.wav") == "jinx"
    assert voice_stem("") == ""
