"""
Source-level tests for Story Teller websocket audio streaming.

These tests do not require a running FastAPI server or TTS provider. They make
sure the Story Teller frontend uses the existing binary websocket audio path
while keeping the legacy SSE path as a fallback.
"""

import os
import re

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def _read_source(relative_path):
    with open(os.path.join(REPO_ROOT, relative_path), encoding="utf-8") as f:
        return f.read()


def _story_source():
    return _read_source("src/static/story.js")


def _function_body(name):
    src = _story_source()
    match = re.search(
        rf"(?:async\s+)?function {re.escape(name)}\s*\([^)]*\)\s*\{{.*?(?=\n    function |\n    async function |\n    // -{{5,}}|\n    if \(document|\n\}}\)\(\);|\Z)",
        src,
        re.DOTALL,
    )
    assert match, f"{name} must be defined"
    return match.group(0)


def test_story_teller_uses_audiobook_websocket_endpoint():
    src = _story_source()

    assert "_generateStoryAudiobookWS" in src
    assert "_generateStoryAudiobookSSE" in src
    assert "/ws/audiobook" in src


def test_story_teller_websocket_uses_binary_pcm():
    body = _function_body("_generateStoryAudiobookWS")

    assert "binaryType" in body
    assert "'arraybuffer'" in body or '"arraybuffer"' in body
    assert "ArrayBuffer" in body
    assert "_playPcmChunkImmediately" in body


def test_story_teller_websocket_sends_voice_mapping_and_defaults():
    body = _function_body("_generateStoryAudiobookWS")

    assert "segments" in body
    assert "voice_mapping" in body
    assert "_normaliseVoiceMap(storyState.voiceMapping)" in body
    assert "default_voices" in body


def test_story_teller_falls_back_to_sse_without_losing_playback():
    body = _function_body("generateStoryAudiobook")

    assert "_generateStoryAudiobookWS(segments)" in body
    assert "_generateStoryAudiobookSSE(segments)" in body
    assert "falling back to SSE" in body


def test_story_teller_websocket_path_does_not_decode_base64():
    body = _function_body("_generateStoryAudiobookWS")

    assert "atob(" not in body
    assert "base64" not in body.lower()
