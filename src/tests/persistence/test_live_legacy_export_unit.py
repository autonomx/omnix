from __future__ import annotations

import json
from argparse import Namespace

from app.persistence.cutover import preflight_bundle
from app.persistence.legacy_export import build_bundle


def _arguments(tmp_path, **overrides):
    values = {
        "source_id": "local-installation:test",
        "asset_manifest": None,
        "character_db": None,
        "memory_db": None,
        "chat_db": None,
        "jobs_db": None,
        "rpg_sessions_dir": None,
        "settings_json": None,
        "secret_references_json": None,
        "providers_json": None,
        "prompts_json": None,
        "research_json": None,
        "reports_json": None,
        "module_records_json": None,
        "module_document": None,
        "module_jsonl": None,
    }
    values.update(overrides)
    return Namespace(**values)


def test_live_documents_are_normalized_without_secret_values(tmp_path) -> None:
    first_asset = tmp_path / "first.png"
    second_asset = tmp_path / "second.wav"
    first_asset.write_bytes(b"image")
    second_asset.write_bytes(b"audio")
    first_manifest = tmp_path / "assets.json"
    first_manifest.write_text(
        json.dumps(
            {
                "assets": {
                    "asset:image": {
                        "module": "image-generation",
                        "type": "image",
                        "path": str(first_asset),
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    second_manifest = tmp_path / "voice-assets.json"
    second_manifest.write_text(
        json.dumps(
            {
                "assets": {
                    "asset:voice": {
                        "module": "voice",
                        "type": "audio",
                        "storage_path": str(second_asset),
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "provider": "openrouter",
                "audio_provider_tts": "local-tts",
                "openrouter": {
                    "model": "provider/model",
                    "api_key": "must-not-migrate",
                },
                "local-tts": {"base_url": "http://127.0.0.1:9000"},
            }
        ),
        encoding="utf-8",
    )
    secrets_path = tmp_path / "secrets.json"
    secrets_path.write_text(
        json.dumps({"api_keys": {"openrouter": "must-not-migrate"}}),
        encoding="utf-8",
    )
    profiles_path = tmp_path / "profiles.json"
    profiles_path.write_text(
        json.dumps({"defaults": {"presence_preset": "natural"}, "token": "drop"}),
        encoding="utf-8",
    )
    ledger_path = tmp_path / "ledger.jsonl"
    ledger_path.write_text(
        json.dumps({"execution_id": "execution:1", "tool_id": "tool:1"}) + "\n",
        encoding="utf-8",
    )

    bundle = build_bundle(
        _arguments(
            tmp_path,
            asset_manifest=[first_manifest, second_manifest],
            settings_json=settings_path,
            secret_references_json=secrets_path,
            module_document=[("live-chat", "conversation-profiles", str(profiles_path))],
            module_jsonl=[
                ("assistant-tools", "execution-ledger", "execution_id", str(ledger_path))
            ],
        )
    )

    assert len(bundle["entities"]["assets"]) == 2
    assert bundle["entities"]["settings"][0]["key"] == "application.settings"
    assert "api_key" not in bundle["entities"]["settings"][0]["value"]["openrouter"]
    provider = next(
        item for item in bundle["entities"]["providers"] if item["id"] == "openrouter"
    )
    assert provider["secret_reference"] == "legacy-secret:openrouter"
    assert "api_key" not in provider["config"]
    assert bundle["entities"]["module_records"][0]["payload"] == {
        "defaults": {"presence_preset": "natural"}
    }
    assert bundle["entities"]["module_records"][1]["record_id"] == "execution:1"
    assert preflight_bundle(bundle)["ok"] is True
    assert "must-not-migrate" not in json.dumps(bundle)


def test_missing_manifested_asset_fails_preflight(tmp_path) -> None:
    manifest = tmp_path / "assets.json"
    manifest.write_text(
        json.dumps(
            {
                "assets": {
                    "asset:missing": {
                        "path": str(tmp_path / "missing.png"),
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    bundle = build_bundle(_arguments(tmp_path, asset_manifest=[manifest]))
    report = preflight_bundle(bundle)
    assert report["ok"] is False
    assert any("asset:missing source file is missing" in error for error in report["errors"])


def test_module_record_identity_includes_document_coordinates(tmp_path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first.write_text("{}", encoding="utf-8")
    second.write_text("{}", encoding="utf-8")
    bundle = build_bundle(
        _arguments(
            tmp_path,
            module_document=[
                ("platform", "application-settings", str(first)),
                ("live-chat", "conversation-profiles", str(second)),
            ],
        )
    )
    assert preflight_bundle(bundle)["ok"] is True
