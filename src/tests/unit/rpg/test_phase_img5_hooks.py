from app.image.chat_hooks import maybe_enqueue_chat_image
from app.image.story_hooks import maybe_enqueue_story_scene_image


def test_maybe_enqueue_chat_image_disabled():
    result = maybe_enqueue_chat_image(
        session_id="chat1",
        user_text="hello",
        assistant_text="a dragon in the clouds",
        settings={"auto_generate_images": False},
    )
    assert result["ok"] is False
    assert result["reason"] == "disabled"


def test_maybe_enqueue_story_scene_image_disabled():
    result = maybe_enqueue_story_scene_image(
        session_id="story1",
        story_text="The hero entered the ruined city.",
        settings={"auto_generate_scene_images": False},
    )
    assert result["ok"] is False
    assert result["reason"] == "disabled"
