import pathlib


def test_rpg_js_renders_world_advance_recap_sections():
    root = pathlib.Path(__file__).resolve().parents[2]
    js_path = root / "static" / "rpg" / "rpg.js"
    text = js_path.read_text(encoding="utf-8")

    assert "buildWorldAdvanceRecapMarkdown" in text
    assert "Director Activity" in text
    assert "World Events" in text
    assert "Active Threads" in text
    assert "Notable Changes" in text


def test_rpg_js_detects_world_advance_recap_payload_shapes():
    root = pathlib.Path(__file__).resolve().parents[2]
    js_path = root / "static" / "rpg" / "rpg.js"
    text = js_path.read_text(encoding="utf-8")

    assert "isWorldAdvanceRecapPayload" in text
    assert "world_advance_recap" in text
    assert "resume_recap" in text
    assert "resume_summary" in text
    assert "director_activity" in text
    assert "recent_world_events" in text


def test_rpg_js_handles_resume_and_stream_recaps():
    root = pathlib.Path(__file__).resolve().parents[2]
    js_path = root / "static" / "rpg" / "rpg.js"
    text = js_path.read_text(encoding="utf-8")

    assert "handleResumePayload" in text
    assert "handleStreamEventPayload" in text
    assert "es.addEventListener('resume_recap'" in text
    assert "es.addEventListener('world_advance_recap'" in text