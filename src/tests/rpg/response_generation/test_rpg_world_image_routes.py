from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.gateway.rpg_world_image_routes import register_rpg_world_image_routes


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

    assert manifest.status_code == 200
    assert manifest.json()["targets"][0]["target_id"] == "world:cover"
    assert generated.status_code == 200
    assert reviewed.status_code == 200
    assert regenerated.status_code == 200
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
