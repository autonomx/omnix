from app.image.consumer_adapters import build_chat_image_request, build_story_image_request


def test_build_chat_image_request_sets_source():
    payload = build_chat_image_request({"prompt": "draw a castle"})
    assert payload["source"] == "chat"
    assert payload["kind"] == "image"


def test_build_story_image_request_sets_story_defaults():
    payload = build_story_image_request({"prompt": "a forest", "kind": "scene"})
    assert payload["source"] == "story"
    assert payload["width"] == 1344
    assert payload["height"] == 768
