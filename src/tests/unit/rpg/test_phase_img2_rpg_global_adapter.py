from app.rpg.visual.global_image_adapter import (
    generate_rpg_portrait_image,
    generate_rpg_scene_image,
)


class _FakeResponse:
    def __init__(self):
        self.ok = True
        self.provider = "flux_klein"
        self.status = "completed"
        self.error = ""
        self.asset_url = "/assets/fake.png"
        self.local_path = "F:/fake.png"
        self.seed = 123
        self.width = 1
        self.height = 1
        self.metadata = {}


def test_generate_rpg_scene_image_adapts_payload(monkeypatch):
    captured = {}

    def _fake_generate_image(payload):
        captured.update(payload)
        return _FakeResponse()

    monkeypatch.setattr("app.rpg.visual.global_image_adapter.generate_image", _fake_generate_image)
    generate_rpg_scene_image({"prompt": "scene prompt"})
    assert captured["kind"] == "scene"
    assert captured["source"] == "rpg"
    assert captured["width"] == 1344
    assert captured["height"] == 768


def test_generate_rpg_portrait_image_adapts_payload(monkeypatch):
    captured = {}

    def _fake_generate_image(payload):
        captured.update(payload)
        return _FakeResponse()

    monkeypatch.setattr("app.rpg.visual.global_image_adapter.generate_image", _fake_generate_image)
    generate_rpg_portrait_image({"prompt": "portrait prompt"})
    assert captured["kind"] == "portrait"
    assert captured["source"] == "rpg"
    assert captured["width"] == 768
    assert captured["height"] == 1024
