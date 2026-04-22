def test_story_generate_calls_story_image_hook(client, monkeypatch):
    import run_app as ra

    captured = {}

    monkeypatch.setattr(
        ra,
        "_llm_generate_audiobook",
        lambda prompt: "Narrator: The hero entered the ruined city."
    )
    monkeypatch.setattr(
        ra,
        "_parse_story_format",
        lambda text: [{"speaker": "Narrator", "text": "The hero entered the ruined city."}]
    )

    def _fake_story_hook(*, session_id, story_text, settings=None):
        captured["session_id"] = session_id
        captured["story_text"] = story_text
        captured["settings"] = dict(settings or {})
        return {"ok": True}

    monkeypatch.setattr(ra, "maybe_enqueue_story_scene_image", _fake_story_hook)
    monkeypatch.setattr(
        ra.shared,
        "load_settings",
        lambda: {
            "image": {
                "story": {
                    "auto_generate_scene_images": True,
                    "style": "story",
                }
            }
        },
    )

    res = client.post("/api/story/generate", json={
        "session_id": "story_test_1",
        "genre": "fantasy",
        "tone": "epic",
        "length": "short",
        "custom_prompt": "",
        "characters": [],
    })

    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert captured["session_id"] == "story_test_1"
    assert "ruined city" in captured["story_text"]


def test_chat_stream_calls_chat_image_hook(client, monkeypatch):
    import run_app as ra

    class _Chunk:
        def __init__(self, content="", thinking=""):
            self.content = content
            self.thinking = thinking
            self.reasoning = ""

    class _Provider:
        class _Config:
            model = "test-model"
        config = _Config()

        def supports_streaming(self):
            return True

        def chat_completion(self, messages, model=None, stream=False):
            return [
                _Chunk(content="A moonlit tower rises above the forest."),
            ]

    captured = {}

    def _fake_chat_hook(*, session_id, user_text, assistant_text, settings=None):
        captured["session_id"] = session_id
        captured["user_text"] = user_text
        captured["assistant_text"] = assistant_text
        captured["settings"] = dict(settings or {})
        return {"ok": True}

    monkeypatch.setattr(ra.shared, "get_provider", lambda: _Provider())
    monkeypatch.setattr(ra, "maybe_enqueue_chat_image", _fake_chat_hook)
    monkeypatch.setattr(
        ra.shared,
        "load_settings",
        lambda: {
            "image": {
                "chat": {
                    "auto_generate_images": True,
                    "style": "cinematic",
                }
            }
        },
    )
    monkeypatch.setattr(ra.shared, "sessions_data", {"chat_test_1": {"messages": []}})
    monkeypatch.setattr(ra.shared, "save_sessions", lambda data: None)

    res = client.post("/api/chat/stream", json={
        "session_id": "chat_test_1",
        "message": "Describe a magical tower.",
        "model": "test-model",
        "system_prompt": "",
        "speaker": "default",
    })

    assert res.status_code == 200
    assert captured["session_id"] == "chat_test_1"
    assert captured["user_text"] == "Describe a magical tower."
    assert "moonlit tower" in captured["assistant_text"]
