from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.gateway.image_workspace_routes as image_workspace_routes
from app.gateway.rpg_world_image_routes import register_rpg_world_image_routes
from app.jobs.image_contracts import ImageGenerateInput
from app.jobs.image_inline import _store_image_asset
from app.rpg.worlds import world_images


def test_world_image_routes_support_manifest_generation_and_review(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []

    monkeypatch.setattr(
        "app.gateway.rpg_world_image_routes.read_world_image_targets",
        lambda world_id: {
            "ok": True,
            "world": {"id": world_id, "title": "Aurelia"},
            "targets": [
                {
                    "target_id": "world:cover",
                    "target_type": "world",
                    "role": "cover",
                    "status": "missing",
                    "active_asset_id": None,
                    "suggested_prompt": "Aurelia cover",
                    "attempts": [],
                }
            ],
        },
    )

    def fake_generate(world_id: str, **kwargs):
        calls.append(("generate", {"world_id": world_id, **kwargs}))
        return {
            "ok": True,
            "world_id": world_id,
            "jobs": [{"job_id": "job:image", "target_id": kwargs["target_ids"][0]}],
        }

    def fake_update(world_id: str, target_id: str, **kwargs):
        calls.append(
            (
                "update",
                {"world_id": world_id, "target_id": target_id, **kwargs},
            )
        )
        return {"ok": True, "world": {"id": world_id}, "targets": []}

    monkeypatch.setattr(
        "app.gateway.rpg_world_image_routes.generate_world_images",
        fake_generate,
    )
    monkeypatch.setattr(
        "app.gateway.rpg_world_image_routes.update_world_image_target",
        fake_update,
    )
    monkeypatch.setattr(
        "app.gateway.rpg_world_image_routes.regenerate_world_image_prompts",
        lambda world_id, **kwargs: {"ok": True, "world_id": world_id, "targets": kwargs["target_ids"]},
    )

    app = FastAPI()
    register_rpg_world_image_routes(app)
    client = TestClient(app)

    manifest = client.get("/api/rpg/worlds/world:aurelia/image-targets")
    generated = client.post(
        "/api/rpg/worlds/world:aurelia/image-generation",
        json={
            "target_ids": ["world:cover"],
            "prompts": {"world:cover": "Revised cover"},
            "provider_id": "image:flux-klein",
            "width": 768,
            "height": 1024,
            "style": "cinematic",
        },
    )
    reviewed = client.patch(
        "/api/rpg/worlds/world:aurelia/image-targets/world%3Acover",
        json={
            "review_state": "approved",
            "active_asset_id": "image:asset-1",
            "suggested_prompt": "Approved prompt",
        },
    )
    regenerated = client.post(
        "/api/rpg/worlds/world:aurelia/image-targets/world%3Acover/regenerate",
        json={"prompt": "Try again", "provider_id": "image:flux-klein"},
    )
    prompts_regenerated = client.post(
        "/api/rpg/worlds/world:aurelia/image-prompts/regenerate",
        json={"target_ids": ["world:cover"]},
    )

    assert manifest.status_code == 200
    assert manifest.json()["targets"][0]["target_id"] == "world:cover"
    assert generated.status_code == 200
    assert reviewed.status_code == 200
    assert regenerated.status_code == 200
    assert prompts_regenerated.status_code == 200
    assert prompts_regenerated.json()["targets"] == ["world:cover"]
    assert calls[0] == (
        "generate",
        {
            "world_id": "world:aurelia",
            "target_ids": ["world:cover"],
            "prompts": {"world:cover": "Revised cover"},
            "provider_id": "image:flux-klein",
            "width": 768,
            "height": 1024,
            "style": "cinematic",
            "no_cache": False,
        },
    )
    assert calls[1] == (
        "update",
        {
            "world_id": "world:aurelia",
            "target_id": "world:cover",
            "review_state": "approved",
            "active_asset_id": "image:asset-1",
            "suggested_prompt": "Approved prompt",
        },
    )
    assert calls[2][0] == "generate"
    assert calls[2][1]["target_ids"] == ["world:cover"]
    assert calls[2][1]["no_cache"] is True
    assert "/api/rpg/worlds/{world_id}/image-targets" not in app.openapi()["paths"]


def test_world_image_generation_requires_at_least_one_target(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.gateway.rpg_world_image_routes.generate_world_images",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            ValueError("world_image_generation_targets_required")
        ),
    )
    app = FastAPI()
    register_rpg_world_image_routes(app)
    response = TestClient(app).post(
        "/api/rpg/worlds/world:aurelia/image-generation",
        json={"target_ids": []},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "world_image_generation_targets_required"


def test_world_image_generation_enqueues_for_the_active_user(monkeypatch) -> None:
    enqueued: dict[str, object] = {}

    monkeypatch.setattr(
        world_images,
        "read_world_image_targets",
        lambda _world_id, database=None: {
            "targets": [
                {
                    "target_id": "world:cover",
                    "target_type": "world",
                    "entity_id": "world:aurelia",
                    "role": "cover",
                    "source_content_hash": "sha256:cover",
                    "suggested_prompt": "Aurelia cover",
                }
            ]
        },
    )
    monkeypatch.setattr(
        world_images,
        "bootstrap_local_tenant",
        lambda database=None: SimpleNamespace(
            workspace_id="workspace:local", user_id="user:local"
        ),
    )
    monkeypatch.setattr(world_images, "require_world_writable", lambda *args: None)
    monkeypatch.setattr(world_images, "default_job_store", lambda: object())

    @contextmanager
    def fake_unit_of_work(database=None):
        del database
        yield SimpleNamespace(connection=SimpleNamespace(execute=lambda *args: None), commit=lambda: None)

    def fake_enqueue(store, **kwargs):
        enqueued["store"] = store
        enqueued.update(kwargs)
        return SimpleNamespace(id="job:image", status="queued")

    monkeypatch.setattr(world_images, "unit_of_work", fake_unit_of_work)
    monkeypatch.setattr(world_images, "enqueue_image_job", fake_enqueue)

    result = world_images.generate_world_images(
        "world:aurelia", target_ids=["world:cover"]
    )

    assert result["jobs"] == [
        {"job_id": "job:image", "target_id": "world:cover", "status": "queued"}
    ]
    assert enqueued["owner_id"] == "user:local"
    assert "module" not in enqueued


def test_sync_world_image_jobs_types_missing_asset_id_for_postgres(monkeypatch) -> None:
    class Connection:
        def __init__(self) -> None:
            self.calls: list[tuple[str, object]] = []

        def execute(self, sql, params):
            self.calls.append((sql, params))
            if sql.startswith("SELECT target_id"):
                return SimpleNamespace(
                    fetchall=lambda: [("world:cover", "sha256:cover", "job:image", None)]
                )
            return None

    connection = Connection()
    work = SimpleNamespace(connection=connection)
    context = SimpleNamespace(workspace_id="workspace:local")
    job = SimpleNamespace(status="completed", output_refs=[], error={})
    monkeypatch.setattr(
        world_images,
        "default_job_store",
        lambda: SimpleNamespace(get_job=lambda _job_id: job),
    )

    world_images._sync_jobs(work, context, "world:aurelia")

    target_update = connection.calls[-1][0]
    assert "%s::text IS NOT NULL" in target_update
    assert "review_state = CASE" in target_update


def test_desired_targets_include_realm_entities_for_document_card_art() -> None:
    targets = world_images._desired_targets(
        {
            "world": {"id": "world:aurelia", "title": "Aurelia"},
            "topics": [
                {
                    "topic_id": "realm",
                    "content": {
                        "entities": [
                            {"entity_id": "ent:realm:001", "dossier": {"subtitle": "The Shattered Realm"}},
                        ],
                    },
                },
            ],
        }
    )

    realm_target = next(target for target in targets if target["entity_id"] == "ent:realm:001")
    assert realm_target["role"] == "landscape"
    assert realm_target["target_id"] == "entity:ent:realm:001:landscape"
    assert "poster-quality illustration" in realm_target["suggested_prompt"]
    assert "theatrical lighting" in realm_target["suggested_prompt"]


def test_atmospheric_filtration_system_prompt_is_expanded_into_a_visible_scene() -> None:
    prompt = world_images._prompt(
        world={"title": "Neon Wastes", "genre": "cyberpunk", "tone": "rebellious"},
        target_type="illustration",
        role="illustration",
        entity={"name": "Atmospheric Filtration System (AFS)"},
    )

    assert "colossal life-support machine" in prompt
    assert "towering purification stacks" in prompt
    assert "toxic orange smog" in prompt
    assert "small augmented rebels" in prompt


def test_character_portrait_prompt_uses_stable_identity_and_tight_framing() -> None:
    prompt = world_images._prompt(
        world={"title": "Neon Wastes", "genre": "cyberpunk", "tone": "rebellious"},
        target_type="actor",
        role="portrait",
        entity={
            "name": "Kaelen 'Ghost' Voss",
            "dossier": {
                "sections": [
                    {
                        "id": "appearance",
                        "paragraphs": ["Subtle neural interfaces sit beneath his skin."],
                    }
                ]
            },
        },
    )

    assert "tight chest-up portrait" in prompt
    assert "face occupying roughly one-third" in prompt
    assert "matte-titanium augmentation" in prompt
    assert "compact optical-camouflage emitter" in prompt
    assert "Keep background figures minimal" in prompt
    assert "No text, logos, watermarks" in prompt
    assert "Show its scale, materials, construction" not in prompt


def test_non_character_prompts_use_role_specific_canon_and_composition() -> None:
    world = {"title": "Neon Wastes", "genre": "cyberpunk", "tone": "rebellious"}
    threat = world_images._prompt(
        world=world,
        target_type="cyberpunk_threat",
        role="portrait",
        entity={
            "name": "Praetorian Enforcer",
            "kind": "cyberpunk_threat",
            "behaviour": "Advances behind a ballistic shield.",
            "weaknesses": ["Exposed coolant spine"],
            "capabilities": ["Suppressive fire"],
        },
    )
    item = world_images._prompt(
        world=world,
        target_type="equipment",
        role="icon",
        entity={
            "name": "Signal Scrambler",
            "function": "Disrupts corporate tracking signals.",
            "limitations": "Overheats after one minute.",
        },
    )
    encounter = world_images._prompt(
        world=world,
        target_type="encounter_seed",
        role="scene",
        entity={
            "name": "Catwalk Ambush",
            "setup": "Rebels cross a rain-soaked filtration catwalk.",
            "complications": ["A corporate searchlight finds them"],
            "outcomes": ["The catwalk collapses"],
        },
    )

    assert "threat key art" in threat
    assert "Exposed coolant spine" in threat
    assert "tight chest-up portrait" not in threat
    assert "three-quarter product view" in item
    assert "Overheats after one minute" in item
    assert "Stage one decisive action" in encounter
    assert "corporate searchlight" in encounter


def test_desired_targets_include_a_regenerable_world_map() -> None:
    targets = world_images._desired_targets(
        {
            "world": {"id": "world:aurelia", "title": "Aurelia", "genre": "fantasy"},
            "topics": [
                {
                    "topic_id": "locations",
                    "content": {
                        "entities": [
                            {
                                "id": "location:moon_market",
                                "name": "Moon Market",
                                "location_type": "town",
                                "description": "A walled market town on the old trade road.",
                            },
                        ],
                    },
                },
            ],
            "map_blueprints": [
                {
                    "map_id": "map:moon_market",
                    "blueprint_revision": 1,
                    "document": {"location_id": "location:moon_market"},
                },
            ],
        }
    )

    map_target = next(target for target in targets if target["target_id"] == "world:map")
    assert map_target["role"] == "map"
    assert map_target["metadata"]["topic_id"] == "map"
    assert "Moon Market" in map_target["suggested_prompt"]
    assert "compact settlement with streets, roofs, and a clear civic centre" in map_target["suggested_prompt"]
    assert "walled market town on the old trade road" in map_target["suggested_prompt"]
    assert "cinematic colour grading" in map_target["suggested_prompt"]
    assert "Absolutely no typography or written marks" in map_target["suggested_prompt"]
    assert "names are supplied only by application overlay markers" in map_target["suggested_prompt"]
    local_map_target = next(target for target in targets if target["target_id"] == "entity:location:moon_market:map")
    assert local_map_target["metadata"]["map_level"] == "location"
    assert "detailed, navigable local RPG map" in local_map_target["suggested_prompt"]
    assert "Absolutely no typography or written marks" in local_map_target["suggested_prompt"]


def test_map_prompt_uses_places_as_canonical_landmarks() -> None:
    targets = world_images._desired_targets(
        {
            "world": {"id": "world:neon", "title": "Neon Wastes", "genre": "cyberpunk"},
            "topics": [
                {
                    "topic_id": "places",
                    "content": {
                        "entities": [
                            {
                                "id": "ent:places:spire",
                                "name": "OmniCorp Spire",
                                "kind": "place",
                                "description": "A corporate tower over a polluted city.",
                            }
                        ]
                    },
                }
            ],
        }
    )

    map_target = next(target for target in targets if target["target_id"] == "world:map")
    assert "OmniCorp Spire" in map_target["suggested_prompt"]
    assert "Absolutely no typography or written marks" in map_target["suggested_prompt"]


def test_rpg_world_images_are_marked_for_the_rpg_asset_boundary(tmp_path) -> None:
    class AssetStore:
        def upsert_asset(self, asset):
            return asset

    image_file = tmp_path / "aurelia.png"
    image_file.write_bytes(b"png")
    job = SimpleNamespace(id="job:image", module="image-generation")
    request = ImageGenerateInput(
        prompt="Aurelia cover",
        metadata={"world_id": "world:aurelia", "target_id": "world:cover"},
    )
    result = SimpleNamespace(
        local_path=str(image_file),
        provider="mock",
        width=768,
        height=768,
        mime_type="image/png",
        seed=None,
        metadata={},
    )

    asset, _ = _store_image_asset(job, request, result, AssetStore())

    assert asset.module == "rpg-world-authoring"
    assert asset.metadata["rpg_world_image"] is True
    assert asset.metadata["rpg_world_id"] == "world:aurelia"
    legacy_asset = SimpleNamespace(metadata={}, source_job_id="job:image")
    source_job = SimpleNamespace(
        input_payload=request.model_dump(),
        output_refs=[{"type": "image", "asset_id": "image:rpg-world"}],
    )
    job_store = SimpleNamespace(
        get_job=lambda _job_id: source_job,
        list_jobs=lambda: [source_job],
    )
    assert image_workspace_routes._is_rpg_world_image_asset(legacy_asset, job_store)
    assert image_workspace_routes._rpg_world_image_asset_ids(job_store) == {"image:rpg-world"}
