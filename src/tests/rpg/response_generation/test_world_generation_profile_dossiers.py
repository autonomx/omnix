from __future__ import annotations

import pytest

from app.rpg.worlds import generation_compilation
from app.rpg.worlds.generation_profile_dossiers import (
    ProfileDossierCompilationError,
    dossier_policy,
    profile_dossier_issues,
    profile_dossier_report,
)
from app.rpg.worlds.generation_publication import WorldGenerationPublication


class _Document:
    def __init__(self, kind: str) -> None:
        self.kind = kind

    def model_dump(self, *, mode: str) -> dict:
        assert mode == "json"
        return {"kind": self.kind}


class _Release(_Document):
    artifact_stage = "playtested"
    runtime_seed = {"seed": "runtime"}
    materialization = {"hub_location_id": "ent:place:001"}
    playtest_report = {"passed": True}


def _publication() -> WorldGenerationPublication:
    return WorldGenerationPublication(
        world_revision=_Document("revision"),  # type: ignore[arg-type]
        world_release=_Release("release"),  # type: ignore[arg-type]
        certification={"launch_ready": True, "missing_requirements": []},
    )


def _graph() -> dict:
    return {
        "metadata": {
            "resolved_profile": {
                "domains": [
                    {
                        "domain_id": "actors",
                        "entity_kind": "actor",
                        "semantic_roles": ["initial_actors"],
                    },
                    {"domain_id": "places", "entity_kind": "place"},
                    {"domain_id": "groups", "entity_kind": "group"},
                    {
                        "domain_id": "companions",
                        "entity_kind": "crew_member",
                        "generation_guidance": {"dossier_policy": "actor"},
                    },
                ]
            }
        }
    }


def _complete_actor(entity_id: str = "ent:actor:001") -> dict:
    return {
        "id": entity_id,
        "kind": "actor",
        "name": "Ari",
        "appearance": "A weathered courier with a silver eye and patched field coat.",
        "personality": "Careful, dryly funny, and protective of people who keep their word.",
        "backstory": "Ari survived the harbour collapse and now carries messages between isolated districts.",
        "speech_style": "Short practical sentences with understated humour.",
        "goals": ["Reconnect the districts"],
        "motives": ["Protect displaced families"],
        "faction_ids": [],
        "secrets": [],
        "known_facts": [],
        "dossier_status": "complete",
        "location_id": "ent:place:001",
    }


def _complete_place() -> dict:
    return {
        "id": "ent:place:001",
        "kind": "place",
        "name": "Harbour Nine",
        "region_id": "ent:region:001",
        "sensory_profile": "Salt mist, transformer hum, gull cries, and hot oil drifting between gantries.",
        "dossier_status": "complete",
    }


def _complete_group() -> dict:
    return {
        "id": "ent:group:001",
        "kind": "group",
        "name": "The Lantern Compact",
        "values": ["Mutual aid"],
        "goals": ["Keep the district routes open"],
    }


def _rows(actor: dict | None = None) -> list[dict]:
    return [
        {
            "topic_id": "actors",
            "candidate": {
                "topic_id": "actors",
                "entities": [actor or _complete_actor()],
            },
        },
        {
            "topic_id": "places",
            "candidate": {"topic_id": "places", "entities": [_complete_place()]},
        },
        {
            "topic_id": "groups",
            "candidate": {"topic_id": "groups", "entities": [_complete_group()]},
        },
    ]


def test_policy_resolution_uses_domain_role_kind_and_explicit_extension() -> None:
    domains = _graph()["metadata"]["resolved_profile"]["domains"]

    assert dossier_policy(domains[0]) == "actor"
    assert dossier_policy(domains[1]) == "place"
    assert dossier_policy(domains[2]) == "institution"
    assert dossier_policy(domains[3]) == "actor"


def test_profile_actor_place_and_group_dossiers_pass_when_complete() -> None:
    report = profile_dossier_report(_rows(), _graph())

    assert report["passed"] is True
    assert report["issues"] == []
    assert report["policies"] == {
        "actors": "actor",
        "places": "place",
        "groups": "institution",
        "companions": "actor",
    }


def test_actor_kind_cannot_bypass_legacy_npc_policy() -> None:
    actor = _complete_actor()
    actor.pop("speech_style")
    actor.pop("motives")

    issues = profile_dossier_issues(_rows(actor), _graph())

    assert len(issues) == 1
    issue = issues[0]
    assert issue.code == "incomplete_profile_actor_dossier"
    assert issue.domain_id == "actors"
    assert issue.entity_id == "ent:actor:001"
    assert issue.missing_fields == ("motives", "speech_style")


def test_explicit_extension_policy_applies_to_custom_entity_kind() -> None:
    rows = [
        {
            "topic_id": "companions",
            "candidate": {
                "topic_id": "companions",
                "entities": [{"id": "ent:companion:001", "kind": "crew_member"}],
            },
        }
    ]

    issues = profile_dossier_issues(rows, _graph())

    assert len(issues) == 1
    assert issues[0].policy == "actor"
    assert "appearance" in issues[0].missing_fields
    assert "location_id_or_mobility_status" in issues[0].missing_fields


def test_legacy_npc_kind_is_left_to_existing_quality_audit() -> None:
    actor = {"id": "ent:actor:legacy", "kind": "npc"}

    assert profile_dossier_issues(_rows(actor), _graph()) == ()


def test_certified_compilation_fails_before_legacy_compiler_on_profile_dossier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False
    incomplete = _complete_actor()
    incomplete.pop("backstory")

    def _compile(**_kwargs: object) -> WorldGenerationPublication:
        nonlocal called
        called = True
        return _publication()

    monkeypatch.setattr(
        generation_compilation,
        "compile_world_generation_publication",
        _compile,
    )

    with pytest.raises(ProfileDossierCompilationError) as exc_info:
        generation_compilation.compile_world_generation_certified_artifact(
            run={"run_id": "run:1", "graph": _graph()},
            world={"id": "world:1"},
            topic_rows=_rows(incomplete),
            revision=2,
        )

    assert called is False
    assert exc_info.value.as_dict()["issues"][0]["missing_fields"] == ["backstory"]


def test_diagnostic_draft_retains_profile_dossier_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    incomplete = _complete_actor()
    incomplete.pop("personality")
    monkeypatch.setattr(
        generation_compilation,
        "compile_world_generation_publication",
        lambda **_kwargs: _publication(),
    )

    artifact = generation_compilation.compile_world_generation_diagnostic_draft(
        run={"run_id": "run:1", "graph": _graph()},
        world={"id": "world:1"},
        topic_rows=_rows(incomplete),
        revision=2,
    )
    payload = artifact.as_dict()

    assert payload["certification"]["launch_ready"] is False
    assert payload["certification"]["profile_dossier_quality"]["passed"] is False
    assert payload["certification"]["manifest_reference_closure"]["passed"] is False
    assert payload["certification"]["missing_requirements"] == [
        "profile_dossier_quality",
        "manifest_reference_closure",
    ]
    assert "world_release" not in payload
