from app.image.service import _normalize_request


def test_normalize_request_uses_defaults():
    req = _normalize_request({})
    assert req.provider == "flux_klein"
    assert req.width == 1024
    assert req.height == 1024
    assert req.kind == "image"
    assert req.source == "app"


def test_normalize_request_preserves_payload_values():
    req = _normalize_request({
        "provider": "flux_klein",
        "prompt": "castle on a cliff",
        "width": 1344,
        "height": 768,
        "kind": "scene",
        "source": "story",
        "style": "fantasy",
    })
    assert req.prompt == "castle on a cliff"
    assert req.width == 1344
    assert req.height == 768
    assert req.kind == "scene"
    assert req.source == "story"
    assert req.style == "fantasy"
