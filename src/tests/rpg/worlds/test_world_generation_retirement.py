from __future__ import annotations

import hashlib

from app.rpg.api.rpg_adventure_routes import rpg_adventure_bp
from app.rpg.worlds.generation_recovery_evidence import _DiagnosticsWithRawEvidence


_RETIRED_PATHS = {
    "/api/rpg/adventure/generate_world",
    "/api/rpg/adventure/generate-world",
    "/api/rpg/adventure/regenerate_section",
    "/api/rpg/adventure/regenerate_entity",
    "/api/rpg/adventure/apply_generated_package",
    "/api/rpg/adventure/fill_npc",
}


class _Diagnostics:
    def as_dict(self) -> dict:
        return {
            "provider_calls": 1,
            "selected_mode": "json_schema",
        }


def test_retired_legacy_generation_routes_are_not_registered() -> None:
    paths = {
        str(route.path)
        for route in rpg_adventure_bp.routes
    }

    assert not paths.intersection(_RETIRED_PATHS)
    assert {
        "/api/rpg/adventure/templates",
        "/api/rpg/adventure/validate",
        "/api/rpg/adventure/preview",
        "/api/rpg/adventure/start",
        "/api/rpg/adventure/inspect-world",
        "/api/rpg/adventure/simulate-step",
    }.issubset(paths)


def test_successful_provider_diagnostics_include_raw_response_evidence() -> None:
    raw = '{"topic_id":"places","entities":[]}'
    diagnostics = _DiagnosticsWithRawEvidence(_Diagnostics(), raw).as_dict()

    assert diagnostics["raw_response_hash"] == hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()
    assert diagnostics["raw_response_length"] == len(raw)
    assert diagnostics["raw_response_hash_kind"] == "provider_response"


def test_empty_provider_response_does_not_forge_raw_evidence() -> None:
    diagnostics = _DiagnosticsWithRawEvidence(_Diagnostics(), "").as_dict()

    assert "raw_response_hash" not in diagnostics
    assert "raw_response_hash_kind" not in diagnostics
