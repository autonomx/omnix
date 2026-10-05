from __future__ import annotations

from app.apps.rpg.worlds import profile_aware_world_images as profile_images
from app.apps.rpg.worlds import world_images


def test_profile_aware_import_does_not_replace_world_image_owner(monkeypatch):
    original_reader = world_images.read_world_image_targets
    captured = {}

    def generate(_world_id, **kwargs):
        captured.update(kwargs)
        return {"ok": True}

    monkeypatch.setattr(world_images, "generate_world_images", generate)

    assert world_images.read_world_image_targets is original_reader
    assert profile_images.generate_world_images("world-1", target_ids=["world:cover"]) == {
        "ok": True
    }
    assert captured["target_reader"] is profile_images.read_world_image_targets


def test_profile_aware_updates_return_profile_materialized_targets(monkeypatch):
    captured = {}

    def update(_world_id, _target_id, **kwargs):
        captured.update(kwargs)
        return {"ok": True}

    monkeypatch.setattr(world_images, "update_world_image_target", update)

    assert profile_images.update_world_image_target("world-1", "world:cover") == {
        "ok": True
    }
    assert captured["target_reader"] is profile_images.read_world_image_targets
