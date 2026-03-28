"""
Tests for audiobook WebSocket improvements (Steps 1-8).

Tests do not require external services (LLM, TTS, STT).
Tests for server_fastapi functions use source file inspection since uvicorn
is not available in the sandboxed test environment (same as Flask).
"""

import json
import os
import re
import sys
import threading
import time

import numpy as np
import pytest

# Ensure src/ is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Repo root (parent of src/)
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_source(relative_path):
    """Read a source file from the repo root."""
    with open(os.path.join(REPO_ROOT, relative_path)) as f:
        return f.read()


# ---------------------------------------------------------------------------
# STEP 2: _generate_audiobook_tts_pcm yields raw PCM int16
# ---------------------------------------------------------------------------

class TestGenerateAudiobookTtsPcm:
    """Test that _generate_audiobook_tts_pcm in server_fastapi.py produces
    raw PCM int16 bytes — no base64, no WAV header."""

    def _get_source(self):
        return _read_source("server_fastapi.py")

    def test_function_defined(self):
        src = self._get_source()
        assert "def _generate_audiobook_tts_pcm" in src

    def test_yields_int16_tobytes(self):
        """Must convert float32 → int16 and call .tobytes()."""
        src = self._get_source()
        # Find the function body
        match = re.search(
            r'def _generate_audiobook_tts_pcm.*?(?=\ndef |\nclass |\n# ===)',
            src, re.DOTALL
        )
        assert match, "_generate_audiobook_tts_pcm must exist"
        body = match.group(0)
        assert "np.int16" in body, "Must convert to int16"
        assert ".tobytes()" in body, "Must call tobytes()"

    def test_no_base64_encoding(self):
        """Function must NOT base64-encode the output."""
        src = self._get_source()
        match = re.search(
            r'def _generate_audiobook_tts_pcm.*?(?=\ndef |\nclass |\n# ===)',
            src, re.DOTALL
        )
        assert match
        body = match.group(0)
        assert "base64.b64encode" not in body, "Must not use base64 encoding"
        assert "b64encode" not in body, "Must not use b64encode"

    def test_no_wav_header_creation(self):
        """Function must NOT build WAV/RIFF headers."""
        src = self._get_source()
        match = re.search(
            r'def _generate_audiobook_tts_pcm.*?(?=\ndef |\nclass |\n# ===)',
            src, re.DOTALL
        )
        assert match
        body = match.group(0)
        assert "RIFF" not in body, "Must not write RIFF header"
        assert "wave.open" not in body, "Must not create WAV file"

    def test_uses_semaphore(self):
        """Must use a semaphore for concurrency control."""
        src = self._get_source()
        match = re.search(
            r'def _generate_audiobook_tts_pcm.*?(?=\ndef |\nclass |\n# ===)',
            src, re.DOTALL
        )
        assert match
        body = match.group(0)
        assert "_audiobook_tts_semaphore" in body, "Must use semaphore"

    def test_frame_size_defined(self):
        """Must define AUDIOBOOK_FRAME_SIZE for consistent chunk sizes."""
        src = self._get_source()
        assert "AUDIOBOOK_FRAME_SIZE" in src
        # Should be 2400 (100ms at 24kHz)
        match = re.search(r'AUDIOBOOK_FRAME_SIZE\s*=\s*(\d+)', src)
        assert match
        assert int(match.group(1)) == 2400


# ---------------------------------------------------------------------------
# STEP 7: Semaphore replaces Lock in audio.py
# ---------------------------------------------------------------------------

class TestSemaphoreReplacement:
    """Verify that audio.py uses Semaphore(2) instead of Lock."""

    def test_semaphore_exists(self):
        content = _read_source("src/app/audio.py")

        assert "_generation_semaphore" in content, "Must define _generation_semaphore"
        assert "threading.Semaphore(2)" in content, "Must use Semaphore(2)"
        assert "_generation_lock = threading.Lock()" not in content, (
            "Old _generation_lock = threading.Lock() must be removed"
        )

    def test_semaphore_used_in_sse(self):
        """The SSE handler should acquire the semaphore, not a Lock."""
        content = _read_source("src/app/audio.py")
        assert "with _generation_semaphore:" in content


# ---------------------------------------------------------------------------
# STEP 8: _split_into_paragraphs / chunk_text
# ---------------------------------------------------------------------------

class TestSplitIntoParagraphs:
    """Test the text splitting logic used for long audiobook text.

    Since server_fastapi.py delegates to audiobook.segmentation.chunk_text,
    we test that module directly.
    """

    def test_short_text_single_chunk(self):
        from audiobook.segmentation.chunk_text import chunk_text
        result = chunk_text("Hello world.", max_chars=500)
        assert len(result) == 1
        assert result[0] == "Hello world."

    def test_splits_long_text(self):
        from audiobook.segmentation.chunk_text import chunk_text
        text = "This is a sentence. " * 50  # ~1000 chars
        result = chunk_text(text, max_chars=200)
        assert len(result) > 1

    def test_empty_text(self):
        from audiobook.segmentation.chunk_text import chunk_text
        result = chunk_text("")
        assert result == ['']

    def test_preserves_content(self):
        from audiobook.segmentation.chunk_text import chunk_text
        text = "First paragraph. Second paragraph."
        result = chunk_text(text, max_chars=500)
        combined = " ".join(result)
        assert "First" in combined
        assert "Second" in combined

    def test_split_into_paragraphs_defined(self):
        """server_fastapi.py must define _split_into_paragraphs."""
        src = _read_source("server_fastapi.py")
        assert "def _split_into_paragraphs" in src
        assert "chunk_text" in src

    def test_split_into_sentences_defined(self):
        """server_fastapi.py must define _split_into_sentences."""
        src = _read_source("server_fastapi.py")
        assert "def _split_into_sentences" in src
        assert "split_sentences" in src


class TestSentenceBasedSegments:
    """Test sentence-based segmentation for the audiobook WebSocket handler."""

    def test_split_into_sentences_basic(self):
        """_split_into_sentences splits text at sentence boundaries."""
        # Can't import server_fastapi directly, test via chunk_text module
        from audiobook.segmentation.chunk_text import split_sentences
        result = split_sentences("Hello world. How are you? I'm fine.")
        assert len(result) == 3
        assert result[0] == "Hello world."
        assert result[1] == "How are you?"
        assert result[2] == "I'm fine."

    def test_split_into_sentences_preserves_short(self):
        """Short text with one sentence stays as one segment."""
        from audiobook.segmentation.chunk_text import split_sentences
        result = split_sentences("Hello world.")
        assert len(result) == 1
        assert result[0] == "Hello world."

    def test_split_into_sentences_abbreviations(self):
        """Don't split on abbreviations like Mr. or Dr."""
        from audiobook.segmentation.chunk_text import split_sentences
        result = split_sentences("Mr. Smith went home. He was tired.")
        assert len(result) == 2
        assert "Mr. Smith" in result[0]

    def test_ws_handler_uses_sentence_segments(self):
        """WS handler must use _split_into_sentences for sentence-level
        segmentation."""
        src = _read_source("server_fastapi.py")
        match = re.search(
            r'async def websocket_audiobook.*?(?=\nasync def |\nclass |\n# ===|\Z)',
            src, re.DOTALL
        )
        assert match
        fn_body = match.group(0)
        assert "_split_into_sentences" in fn_body, (
            "WS handler must use _split_into_sentences for sentence-level segments"
        )

    def test_ws_handler_sends_total_segments(self):
        """WS handler must send total_segments in the start response."""
        src = _read_source("server_fastapi.py")
        match = re.search(
            r'async def websocket_audiobook.*?(?=\nasync def |\nclass |\n# ===|\Z)',
            src, re.DOTALL
        )
        assert match
        fn_body = match.group(0)
        assert "total_segments" in fn_body, (
            "WS handler must send total_segments in start response"
        )

    def test_client_reads_total_segments(self):
        """Client must read total_segments from server's start message."""
        src = _read_source("src/static/audiobook.js")
        match = re.search(
            r'function generateAudiobookWS.*?(?=\nfunction |\n// ===|\Z)',
            src, re.DOTALL
        )
        assert match
        body = match.group(0)
        assert "total_segments" in body, (
            "Client must read total_segments from server start message"
        )


# ---------------------------------------------------------------------------
# STEP 5: AudioOutput buffering (source code check)
# ---------------------------------------------------------------------------

class TestAudioOutputBuffering:
    """Verify AudioOutput.enqueue() has minimum buffer logic."""

    def test_min_buffer_in_source(self):
        content = _read_source("src/static/voice/audioOutput.js")

        assert "minBufferSize" in content, "Must define minBufferSize property"
        assert "flush" in content, "Must have flush method"
        assert "_flushing" in content, "Must have _flushing flag"

    def test_enqueue_has_buffer_check(self):
        content = _read_source("src/static/voice/audioOutput.js")

        assert "this.minBufferSize" in content
        assert "this.audioQueue.length < this.minBufferSize" in content
        assert "_shouldWaitForBuffer" in content, "Must have helper method"

    def test_flushing_reset_on_stop(self):
        content = _read_source("src/static/voice/audioOutput.js")

        # Both stop() and stopAll() should reset _flushing
        assert content.count("this._flushing = false") >= 2


# ---------------------------------------------------------------------------
# STEP 3: TTSClient.speakAudiobook (source code check)
# ---------------------------------------------------------------------------

class TestTTSClientAudiobookMode:
    """Verify TTSClient.js has speakAudiobook method."""

    def test_speak_audiobook_exists(self):
        content = _read_source("src/static/voice/ttsClient.js")

        assert "speakAudiobook" in content, "Must define speakAudiobook method"
        assert "type: 'start'" in content or 'type: "start"' in content

    def test_on_segment_callback(self):
        content = _read_source("src/static/voice/ttsClient.js")

        assert "onSegment" in content, "Must have onSegment callback"
        assert "'segment'" in content or '"segment"' in content

    def test_sends_segments_and_voice_mapping(self):
        content = _read_source("src/static/voice/ttsClient.js")

        assert "segments" in content
        assert "voice_mapping" in content
        assert "default_voices" in content


# ---------------------------------------------------------------------------
# STEP 1: WebSocket endpoint exists in server_fastapi.py
# ---------------------------------------------------------------------------

class TestWebSocketEndpointDefined:
    """Verify /ws/audiobook endpoint is defined."""

    def test_ws_audiobook_route(self):
        content = _read_source("server_fastapi.py")

        assert '/ws/audiobook' in content, "Must define /ws/audiobook endpoint"
        assert 'websocket_audiobook' in content, "Must define handler function"

    def test_no_base64_in_ws_handler(self):
        """The WS audiobook handler must not use base64 encoding."""
        content = _read_source("server_fastapi.py")

        match = re.search(
            r'async def websocket_audiobook.*?(?=\nasync def |\nclass |\n# ===|\Z)',
            content, re.DOTALL
        )
        assert match, "websocket_audiobook function must exist"
        fn_body = match.group(0)
        assert 'base64' not in fn_body, (
            "websocket_audiobook must not use base64 encoding"
        )

    def test_sends_segment_metadata(self):
        """WS handler should send segment index metadata."""
        content = _read_source("server_fastapi.py")

        match = re.search(
            r'async def websocket_audiobook.*?(?=\nasync def |\nclass |\n# ===|\Z)',
            content, re.DOTALL
        )
        assert match
        fn_body = match.group(0)
        assert '"segment"' in fn_body or "'segment'" in fn_body
        assert '"index"' in fn_body or "'index'" in fn_body


# ---------------------------------------------------------------------------
# STEP 6: Deprecation comments on old endpoints
# ---------------------------------------------------------------------------

class TestDeprecationComments:
    """Old streaming endpoints should have deprecation notices."""

    def test_tts_stream_deprecated(self):
        content = _read_source("src/app/audio.py")
        assert "deprecated" in content.lower(), "Must contain deprecation notice"

    def test_tts_stream_sse_deprecated(self):
        content = _read_source("src/app/audio.py")
        assert "Prefer the ``/ws/audiobook``" in content or "Prefer the `/ws/audiobook`" in content


# ---------------------------------------------------------------------------
# Audiobook.js WebSocket integration (source code check)
# ---------------------------------------------------------------------------

class TestAudiobookJSWebSocket:
    """Verify audiobook.js uses WebSocket with SSE fallback."""

    def test_ws_generation_function(self):
        content = _read_source("src/static/audiobook.js")

        assert "generateAudiobookWS" in content, "Must define WS generation function"
        assert "generateAudiobookSSE" in content, "Must define SSE fallback function"
        assert "/ws/audiobook" in content, "Must reference /ws/audiobook endpoint"

    def test_ws_fallback_to_sse(self):
        content = _read_source("src/static/audiobook.js")

        assert "generateAudiobookWS" in content
        assert "generateAudiobookSSE" in content
        assert "catch" in content

    def test_ws_uses_arraybuffer(self):
        content = _read_source("src/static/audiobook.js")

        assert "binaryType" in content
        assert "'arraybuffer'" in content or '"arraybuffer"' in content

    def test_stop_closes_websocket(self):
        content = _read_source("src/static/audiobook.js")

        assert "audiobookWs" in content
        assert "audiobookWs.close()" in content or "audiobookWs.close" in content

    def test_pcm_playback_without_base64(self):
        """The WS generation path should play PCM directly from ArrayBuffer."""
        content = _read_source("src/static/audiobook.js")

        # generateAudiobookWS should use Int16Array for PCM playback
        match = re.search(
            r'function generateAudiobookWS.*?(?=\nfunction |\n// ===|\Z)',
            content, re.DOTALL
        )
        assert match, "generateAudiobookWS must exist"
        fn_body = match.group(0)
        assert "Int16Array" in fn_body, "Must decode PCM as Int16Array"
        assert "ArrayBuffer" in fn_body, "Must handle ArrayBuffer data"


# ---------------------------------------------------------------------------
# Issue 1: Voice mapping normalisation
# ---------------------------------------------------------------------------

class TestVoiceMappingNormalisation:
    """Verify that voice mapping keys are normalised to lowercase in both the
    frontend (audiobook.js) and the backend (audiobook.py, server_fastapi.py).
    This prevents stale voice assignments when users change voices in the UI."""

    def test_normalize_key_function_exists(self):
        content = _read_source("src/static/audiobook.js")
        assert "_normalizeKey" in content, "audiobook.js must define _normalizeKey helper"

    def test_normalize_key_lowercases(self):
        content = _read_source("src/static/audiobook.js")
        # Find the _normalizeKey function using a robust terminator set
        match = re.search(
            r'function _normalizeKey\s*\(.*?\{.*?\}',
            content, re.DOTALL
        )
        assert match, "_normalizeKey function must be defined"
        body = match.group(0)
        assert "toLowerCase" in body, "_normalizeKey must call toLowerCase()"
        assert "trim" in body, "_normalizeKey must call trim()"

    def test_update_voice_mapping_uses_normalize(self):
        content = _read_source("src/static/audiobook.js")
        match = re.search(
            r'function updateVoiceMapping.*?(?=\n// |\nfunction )',
            content, re.DOTALL
        )
        assert match, "updateVoiceMapping must exist"
        body = match.group(0)
        assert "_normalizeKey" in body, "updateVoiceMapping must normalise the key"

    def test_display_speakers_uses_normalize(self):
        content = _read_source("src/static/audiobook.js")
        match = re.search(
            r'function displaySpeakers.*?(?=\n// |\nfunction )',
            content, re.DOTALL
        )
        assert match, "displaySpeakers must exist"
        body = match.group(0)
        assert "_normalizeKey" in body, "displaySpeakers must normalise voiceMapping keys"

    def test_backend_normalises_merged_map_keys(self):
        """audiobook.py must build merged_map with lower-cased keys."""
        content = _read_source("src/app/audiobook.py")
        # Should contain a dict comprehension that calls .lower() or .lower().strip()
        assert "lower().strip()" in content or ".lower().strip():" in content, (
            "audiobook.py generate() must normalise merged_map keys"
        )

    def test_fastapi_normalises_merged_map_keys(self):
        """server_fastapi.py WS handler must build merged_map with lower-cased keys."""
        content = _read_source("server_fastapi.py")
        match = re.search(
            r'async def websocket_audiobook.*?(?=\nasync def |\nclass |\n# ===|\Z)',
            content, re.DOTALL
        )
        assert match, "websocket_audiobook must exist"
        body = match.group(0)
        assert "lower().strip()" in body, (
            "websocket_audiobook must normalise merged_map keys"
        )


# ---------------------------------------------------------------------------
# Issue 2: PCM chunk validation
# ---------------------------------------------------------------------------

class TestPcmChunkValidation:
    """Verify that the WebSocket binary handler validates PCM chunk integrity
    before pushing to the AudioWorklet, to prevent noise from corrupted data."""

    def test_odd_byte_length_check(self):
        content = _read_source("src/static/audiobook.js")
        # Must check that byteLength is even before creating Int16Array
        assert re.search(r'byteLength\s*%\s*2', content), (
            "audiobook.js WS handler must reject odd-length PCM chunks"
        )

    def test_minimum_sample_count_check(self):
        content = _read_source("src/static/audiobook.js")
        # Must skip chunks that are too short
        assert re.search(r'pcm16\.length\s*<\s*100', content), (
            "audiobook.js WS handler must skip chunks with fewer than 100 samples"
        )

    def test_validation_before_schedule(self):
        """Validation must happen before pushAudioChunk is called in onmessage."""
        content = _read_source("src/static/audiobook.js")
        match = re.search(
            r'function generateAudiobookWS.*?(?=\nfunction |\n// ===|\Z)',
            content, re.DOTALL
        )
        assert match, "generateAudiobookWS must exist"
        body = match.group(0)
        # Find the onmessage handler section
        onmessage_match = re.search(r'ws\.onmessage\s*=', body, re.DOTALL)
        assert onmessage_match, "Must have onmessage handler"
        onmessage_body = body[onmessage_match.start():]
        odd_match = re.search(r'byteLength\s*%\s*2', onmessage_body)
        push_match = re.search(r'pushAudioChunk\s*\(', onmessage_body)
        assert odd_match, "onmessage handler must check odd byte length"
        assert push_match, "onmessage handler must call pushAudioChunk"
        assert odd_match.start() < push_match.start(), \
            "Validation must precede pushAudioChunk call"


# ---------------------------------------------------------------------------
# Issue 3: Download available after segmentation
# ---------------------------------------------------------------------------

class TestEarlyDownloadAvailability:
    """Verify that the download button is made available as soon as audio
    generation completes (WS: on 'done'; SSE: on 'job' event) rather than
    waiting for the full playback UI to render."""

    def test_show_early_download_button_defined(self):
        content = _read_source("src/static/audiobook.js")
        assert "_showEarlyDownloadButton" in content, (
            "audiobook.js must define _showEarlyDownloadButton"
        )

    def test_show_early_server_download_button_defined(self):
        content = _read_source("src/static/audiobook.js")
        assert "_showEarlyServerDownloadButton" in content, (
            "audiobook.js must define _showEarlyServerDownloadButton"
        )

    def test_ws_done_builds_blob_early(self):
        """On WS 'done', build WAV blob and show download button before audio drains."""
        content = _read_source("src/static/audiobook.js")
        match = re.search(
            r'function generateAudiobookWS.*?(?=\nfunction |\n// ===|\Z)',
            content, re.DOTALL
        )
        assert match, "generateAudiobookWS must exist"
        body = match.group(0)
        # The 'done' case must call _showEarlyDownloadButton
        assert "_showEarlyDownloadButton" in body, (
            "WS 'done' handler must call _showEarlyDownloadButton"
        )

    def test_sse_handler_handles_job_type(self):
        """SSE handler must handle the 'job' event type to show the download button."""
        content = _read_source("src/static/audiobook.js")
        match = re.search(
            r'function generateAudiobookSSE.*?(?=\nfunction |\n// ===|\Z)',
            content, re.DOTALL
        )
        assert match, "generateAudiobookSSE must exist"
        body = match.group(0)
        assert "data.type === 'job'" in body or 'data.type === "job"' in body, (
            "SSE handler must handle 'job' event type"
        )
        assert "_showEarlyServerDownloadButton" in body, (
            "SSE handler must call _showEarlyServerDownloadButton on 'job' event"
        )

    def test_backend_emits_job_event(self):
        """audiobook.py SSE generator must yield a 'job' event before TTS loop."""
        content = _read_source("src/app/audiobook.py")
        assert "'type': 'job'" in content or '"type": "job"' in content, (
            "audiobook.py generate() must yield a 'job' SSE event"
        )
        assert "download_url" in content, (
            "The 'job' event must include a download_url"
        )

    def test_backend_saves_wav_file(self):
        """audiobook.py SSE generator must write a WAV file for download."""
        content = _read_source("src/app/audiobook.py")
        # Must create the output path
        assert "output_path" in content, "Must define output_path for WAV file"
        # Must write RIFF/WAV header
        assert "RIFF" in content and "WAVE" in content, (
            "Must write valid WAV (RIFF/WAVE) header"
        )

    def test_buildAndShowFinalPlayer_skips_double_blob_build(self):
        """buildAndShowFinalPlayer must skip blob building if already done eagerly."""
        content = _read_source("src/static/audiobook.js")
        assert "!combinedAudioBlob" in content, (
            "buildAndShowFinalPlayer must check for pre-built blob to avoid duplication"
        )


# ---------------------------------------------------------------------------
# P1: updateVoicePanelEntry uses delete not undefined
# ---------------------------------------------------------------------------

class TestUpdateVoicePanelEntryDelete:
    """updateVoicePanelEntry must delete the key when voice is falsy, not store
    undefined, to prevent stale entries remaining in voiceMapping."""

    def test_uses_delete_for_falsy_voice(self):
        content = _read_source("src/static/audiobook.js")
        assert "function updateVoicePanelEntry" in content, (
            "updateVoicePanelEntry must be defined"
        )
        # The function must contain a 'delete' operation on voiceMapping
        assert "delete audiobookState.voiceMapping" in content, (
            "updateVoicePanelEntry must use 'delete' to remove falsy voice entries"
        )
        # Must NOT store undefined as a voiceMapping value
        assert "voiceMapping[key] = voice || undefined" not in content, (
            "Must NOT assign 'undefined' to voiceMapping; use delete instead"
        )

    def test_uses_normalize_key(self):
        content = _read_source("src/static/audiobook.js")
        match = re.search(
            r'function updateVoicePanelEntry\s*\(.*?\{.*?\}',
            content, re.DOTALL
        )
        assert match, "updateVoicePanelEntry must be defined"
        body = match.group(0)
        assert "_normalizeKey" in body, (
            "updateVoicePanelEntry must use _normalizeKey for the lookup key"
        )


# ---------------------------------------------------------------------------
# P2: Float32 sample validation (NaN / overflow protection)
# ---------------------------------------------------------------------------

class TestFloat32SampleValidation:
    """pushAudioChunk must validate float32 samples and hard-clamp to [-1, 1]
    to prevent squeaking noise from NaN values or overflow distortion."""

    def _get_push_chunk_body(self):
        content = _read_source("src/static/audiobook.js")
        match = re.search(
            r'function pushAudioChunk\s*\(.*?\{.*?(?=\n        \}\n\n        function )',
            content, re.DOTALL
        )
        assert match, "pushAudioChunk must be defined inside generateAudiobookWS"
        return match.group(0)

    def test_nan_check_present(self):
        body = self._get_push_chunk_body()
        assert re.search(r'Number\.isFinite\s*\(', body) or \
               re.search(r'isFinite\s*\(', body), (
            "pushAudioChunk must check Number.isFinite to skip corrupt samples"
        )
        assert re.search(
            r'if\s*\(\s*!Number\.isFinite\s*\(\s*sample\s*\)\s*\)\s*\{[^}]*return\s+false\s*;',
            body,
            re.DOTALL
        ), "Corrupt sample guard must return false so skipped chunk is not treated as pushed"

    def test_hard_clamp_present(self):
        body = self._get_push_chunk_body()
        # The clamp: sample > 1 → 1; sample < -1 → -1
        assert re.search(r'>\s*1(\s|;|\?|:)', body), (
            "pushAudioChunk must hard-clamp values above 1"
        )
        assert re.search(r'<\s*-1(\s|;|\?|:)', body), (
            "pushAudioChunk must hard-clamp values below -1"
        )

    def test_nan_check_before_postmessage(self):
        """The NaN/isFinite check must happen before postMessage to avoid
        sending corrupt data to the AudioWorklet ring buffer."""
        body = self._get_push_chunk_body()
        nan_match = re.search(r'isFinite\s*\(', body)
        post_match = re.search(r'\.postMessage\s*\(\s*\{[^}]*type\s*:\s*["\']push["\']', body)
        assert nan_match, "pushAudioChunk must call isFinite"
        assert post_match, "pushAudioChunk must postMessage with type 'push'"
        assert nan_match.start() < post_match.start(), \
            "isFinite check must precede postMessage"


# ---------------------------------------------------------------------------
# P3: AudioWorklet streaming for artifact-free continuous playback
# ---------------------------------------------------------------------------

class TestAudioWorkletStreaming:
    """generateAudiobookWS must use an AudioWorklet with a ring buffer for
    continuous streaming playback instead of per-chunk AudioBufferSourceNodes."""

    def _get_ws_body(self):
        content = _read_source("src/static/audiobook.js")
        match = re.search(
            r'function generateAudiobookWS.*?(?=\nfunction |\n// ===|\Z)',
            content, re.DOTALL
        )
        assert match, "generateAudiobookWS must exist"
        return match.group(0)

    def test_audioworklet_module_loaded(self):
        body = self._get_ws_body()
        assert re.search(r'audioWorklet\.addModule\s*\(', body), (
            "Must load AudioWorklet module via audioWorklet.addModule"
        )
        assert re.search(r'addModule\s*\(\s*["\'].*streamProcessor\.js["\']', body), (
            "Must load streamProcessor.js as the AudioWorklet module path"
        )

    def test_worklet_node_created(self):
        body = self._get_ws_body()
        assert re.search(r'new\s+AudioWorkletNode\s*\(', body), (
            "Must create an AudioWorkletNode for streaming playback"
        )
        assert re.search(r'["\']stream-processor["\']', body), (
            "Must use 'stream-processor' as the registered processor name"
        )

    def test_worklet_connected_to_destination(self):
        body = self._get_ws_body()
        assert re.search(r'workletNode\.connect\s*\(\s*audioCtx\.destination\s*\)', body), (
            "AudioWorkletNode must connect to audioCtx.destination"
        )

    def test_push_via_postmessage(self):
        body = self._get_ws_body()
        assert re.search(r'\.port\.postMessage\s*\(\s*\{[^}]*type\s*:\s*["\']push["\']', body), (
            "Must push audio data via workletNode.port.postMessage with type 'push'"
        )

    def test_backpressure_control(self):
        body = self._get_ws_body()
        assert re.search(r'MAX_BUFFER_SECONDS\s*=\s*\d+', body), (
            "Must define MAX_BUFFER_SECONDS for backpressure control"
        )
        assert "bufferedSeconds" in body, (
            "Must track bufferedSeconds for backpressure"
        )

    def test_no_scheduling_logic_present(self):
        """Continuous playback via AudioWorklet: no per-chunk
        AudioBufferSourceNode scheduling must remain."""
        body = self._get_ws_body()
        assert "createBufferSource" not in body, (
            "Must NOT use AudioBufferSourceNode — use AudioWorklet ring buffer instead"
        )
        assert not re.search(r'source\.start\s*\(', body), (
            "Must NOT use source.start() scheduling — use AudioWorklet instead"
        )

    def test_waveform_stitching_present(self):
        """pushAudioChunk must NOT apply per-chunk crossfade — the server sends
        continuous PCM frames within each sentence-level segment, and the
        AudioWorklet's underrun recovery handles any gaps."""
        body = self._get_ws_body()
        # The old FADE_SAMPLES crossfade has been intentionally removed to
        # eliminate crackling artifacts during streaming playback.
        assert "FADE_SAMPLES" not in body, (
            "FADE_SAMPLES crossfade must be removed — "
            "it caused crackling by blending already-continuous frames"
        )

    def test_backpressure_considers_audio_consumption(self):
        """Backpressure must be driven by real worklet progress reports —
        bufferedSeconds is updated from the worklet's availableSamples, not
        a setInterval timer.  The worklet sends postMessage progress reports
        and tracks buffer occupancy via availableSamples."""
        body = self._get_ws_body()
        assert re.search(r'port\.onmessage', body), (
            "Must receive worklet progress messages via port.onmessage"
        )
        assert re.search(r'postMessage', body), (
            "Backpressure must involve worklet communication via postMessage"
        )
        # The worklet itself must track buffer occupancy
        worklet_src = _read_source("src/static/voice/streamProcessor.js")
        assert re.search(r'availableSamples', worklet_src), (
            "Worklet must track availableSamples for buffer occupancy"
        )


# ---------------------------------------------------------------------------
# P4: Progressive WAV streaming in backend
# ---------------------------------------------------------------------------

class TestProgressiveWavStreaming:
    """audiobook.py must write a WAV header at the start and append PCM bytes
    incrementally, then finalize the header at the end — so the file is usable
    for download before generation is complete."""

    def test_wav_header_written_before_loop(self):
        """A WAV header must be written BEFORE the TTS generation loop."""
        content = _read_source("src/app/audiobook.py")
        # The header-write and the job-yield must come before the for-loop
        header_idx = content.find("b\"RIFF\"")
        loop_idx = content.find("for i, seg in enumerate(segments)")
        assert header_idx != -1, "Must write RIFF header before loop"
        assert loop_idx != -1, "Must have segment for-loop"
        assert header_idx < loop_idx, "WAV header must be written before the TTS loop"

    def test_pcm_appended_per_segment(self):
        """Each segment's PCM must be appended to the file as it is generated."""
        content = _read_source("src/app/audiobook.py")
        # Must open in append-binary mode inside the loop
        assert '"ab"' in content or "'ab'" in content, (
            "audiobook.py must open the WAV file in append mode ('ab') per segment"
        )

    def test_header_finalized_after_loop(self):
        """After the loop the RIFF/data sizes must be updated with real values."""
        content = _read_source("src/app/audiobook.py")
        # Must seek to offset 4 (RIFF size) and 40 (data size)
        assert "seek(4)" in content, "Must seek to byte 4 to update RIFF size"
        assert "seek(40)" in content, "Must seek to byte 40 to update data size"

    def test_total_pcm_bytes_tracked(self):
        """Must track total PCM bytes written to correctly finalize the header."""
        content = _read_source("src/app/audiobook.py")
        assert "total_pcm_bytes" in content, (
            "audiobook.py must track total_pcm_bytes for WAV header finalization"
        )

    def test_no_full_accumulation_in_memory(self):
        """Should NOT accumulate all PCM in memory (bytearray) before writing."""
        content = _read_source("src/app/audiobook.py")
        assert "accumulated_pcm" not in content, (
            "audiobook.py must NOT use an accumulated_pcm bytearray; "
            "append each segment directly to the file instead"
        )


# ---------------------------------------------------------------------------
# Safe PCM decoding — ttsClient.js pads odd-length buffers
# ---------------------------------------------------------------------------

class TestSafePcmDecoding:
    """Verify pcm16ToFloat32 in ttsClient.js pads odd-length buffers instead
    of dropping frames."""

    def test_pads_odd_length_buffers(self):
        content = _read_source("src/static/voice/ttsClient.js")
        assert "byteLength + 1" in content, (
            "pcm16ToFloat32 must pad odd-length buffers to even alignment"
        )

    def test_no_dropping_frames(self):
        content = _read_source("src/static/voice/ttsClient.js")
        assert "Dropping odd-length" not in content, (
            "pcm16ToFloat32 must NOT drop odd-length frames"
        )

    def test_always_returns_float32(self):
        """pcm16ToFloat32 must never return null — always returns Float32Array."""
        content = _read_source("src/static/voice/ttsClient.js")
        # Find only the pcm16ToFloat32 function body
        match = re.search(
            r'function pcm16ToFloat32\s*\(.*?\{.*?\n\}',
            content, re.DOTALL
        )
        assert match, "pcm16ToFloat32 must exist"
        body = match.group(0)
        assert "return null" not in body, (
            "pcm16ToFloat32 must never return null"
        )

    def test_normalizes_to_32768(self):
        content = _read_source("src/static/voice/ttsClient.js")
        assert "/ 32768" in content, (
            "pcm16ToFloat32 must normalize by dividing by 32768"
        )

    def test_clipping_detection(self):
        content = _read_source("src/static/voice/ttsClient.js")
        assert "Clipping detected" in content, (
            "ttsClient.js must log a warning when clipping is detected"
        )


# ---------------------------------------------------------------------------
# Safe PCM decoding — audiobook.js pads odd-length chunks
# ---------------------------------------------------------------------------

class TestAudiobookSafePcmDecoding:
    """Verify audiobook.js WS handler pads odd-length PCM chunks."""

    def test_pads_odd_length_chunks(self):
        content = _read_source("src/static/audiobook.js")
        match = re.search(
            r'function generateAudiobookWS.*?(?=\nfunction |\n// ===|\Z)',
            content, re.DOTALL
        )
        assert match, "generateAudiobookWS must exist"
        body = match.group(0)
        assert "byteLength + 1" in body, (
            "audiobook.js WS handler must pad odd-length chunks"
        )

    def test_no_skipping_odd_chunks(self):
        content = _read_source("src/static/audiobook.js")
        match = re.search(
            r'function generateAudiobookWS.*?(?=\nfunction |\n// ===|\Z)',
            content, re.DOTALL
        )
        assert match
        body = match.group(0)
        assert "Skipping odd-length chunk" not in body, (
            "audiobook.js WS handler must NOT skip odd-length chunks"
        )


# ---------------------------------------------------------------------------
# Safe PCM decoding — ws-client.js pads odd-length frames
# ---------------------------------------------------------------------------

class TestWsClientSafePcmDecoding:
    """Verify ws-client.js handleAudioData pads odd-length PCM frames."""

    def test_pads_odd_length_frames(self):
        content = _read_source("src/static/chat/ws-client.js")
        assert "byteLength + 1" in content, (
            "ws-client.js must pad odd-length PCM frames"
        )

    def test_no_dropping_frames(self):
        content = _read_source("src/static/chat/ws-client.js")
        assert "Dropping odd-length" not in content, (
            "ws-client.js must NOT drop odd-length frames"
        )


# ---------------------------------------------------------------------------
# AudioWorklet — audiobook stream processor (voice/streamProcessor.js)
# ---------------------------------------------------------------------------

class TestStreamProcessor:
    """Verify the audiobook streamProcessor.js AudioWorklet has a ring buffer,
    backpressure safety, and continuous playback output."""

    def _get_source(self):
        return _read_source("src/static/voice/streamProcessor.js")

    def test_file_exists(self):
        import os
        assert os.path.isfile("src/static/voice/streamProcessor.js"), (
            "streamProcessor.js must exist for AudioWorklet streaming"
        )

    def test_registers_processor(self):
        src = self._get_source()
        assert re.search(r'registerProcessor\s*\(\s*["\']stream-processor["\']', src), (
            "Processor must be registered with exact name 'stream-processor'"
        )

    def test_ring_buffer_structure(self):
        src = self._get_source()
        assert re.search(r'this\.writeIndex\s*=', src), "Must have writeIndex for ring buffer"
        assert re.search(r'this\.readIndex\s*=', src), "Must have readIndex for ring buffer"
        assert re.search(r'this\.availableSamples\s*=', src), "Must track availableSamples"

    def test_push_message_handler(self):
        src = self._get_source()
        assert re.search(r'["\']push["\']', src), \
            "Must handle 'push' messages from main thread"
        assert re.search(r'port\.onmessage\s*=', src), \
            "Must set up port.onmessage handler"

    def test_backpressure_overflow_safety(self):
        src = self._get_source()
        assert re.search(
            r'this\.availableSamples\s*>=\s*this\.buffer\.length',
            src
        ), "Must handle buffer overflow when availableSamples >= buffer.length"

    def test_ring_buffer_overflow_drops_oldest(self):
        """When the ring buffer is full, must advance readIndex to drop oldest."""
        src = self._get_source()
        assert re.search(
            r'this\.availableSamples\s*>=\s*this\.buffer\.length',
            src
        ), "Must detect buffer full condition"
        # Intent-based checks: readIndex is reassigned, incremented by 1, with modulo wrap
        assert re.search(r'this\.readIndex\s*=', src), \
            "Must reassign readIndex when buffer is full"
        assert re.search(r'readIndex.*\+\s*1', src), \
            "Must advance readIndex by 1 when dropping oldest sample"
        assert re.search(r'readIndex.*%', src), \
            "Must use modulo on readIndex for ring buffer wraparound"

    def test_worklet_outputs_smoothed_on_underrun(self):
        src = self._get_source()
        match = re.search(r'UNDERRUN_DECAY_FACTOR\s*=\s*([0-9.]+)', src)
        assert match, "Processor must define an explicit underrun decay factor constant"
        assert float(match.group(1)) >= 0.995, (
            "UNDERRUN_DECAY_FACTOR should be at least 0.995 for smoother underrun decay"
        )
        assert "this.underrunDecayFactor = StreamProcessor.UNDERRUN_DECAY_FACTOR" in src, (
            "Processor must initialize underrun decay factor from class-level constant"
        )
        assert "this.lastSample *= this.underrunDecayFactor" in src and "output[i] = this.lastSample" in src, (
            "Processor must smooth underrun output with decayed lastSample"
        )

    def test_process_returns_true(self):
        src = self._get_source()
        assert re.search(r'return\s+true', src), (
            "process() must return true to keep the processor alive"
        )

    def test_buffer_size_defined(self):
        src = self._get_source()
        assert re.search(r'Float32Array\s*\(\s*\w+\s*\*\s*\d+\s*\)', src), (
            "Buffer size must be explicitly defined (sampleRate * seconds)"
        )


# ---------------------------------------------------------------------------
# AudioWorklet — canonical worklet (js/audio/pcm-player-worklet.js)
# ---------------------------------------------------------------------------

class TestWorkletStreamingImprovements:
    """Verify the canonical pcm-player-worklet.js has streaming read model with
    crossfade, underrun smoothing, and sample-based overflow protection."""

    def _get_worklet_source(self):
        return _read_source("src/static/js/audio/pcm-player-worklet.js")

    def test_current_chunk_model(self):
        src = self._get_worklet_source()
        assert "this.currentChunk" in src, (
            "Worklet must use currentChunk/chunkOffset streaming model"
        )

    def test_previous_chunk_tracking(self):
        src = self._get_worklet_source()
        assert "this.previousChunk" in src, (
            "Worklet must track previousChunk for crossfade"
        )

    def test_last_sample_hold(self):
        src = self._get_worklet_source()
        assert "this.lastSample" in src, (
            "Worklet must track lastSample for underrun smoothing"
        )

    def test_underrun_smoothing(self):
        src = self._get_worklet_source()
        assert "lastSample *= 0.98" in src or "this.lastSample *= 0.98" in src, (
            "Worklet must use exponential decay (0.98) for underrun smoothing"
        )

    def test_underrun_updates_last_sample(self):
        """After writing a decayed sample, lastSample must be updated from the
        output so the next decay iteration stays consistent."""
        src = self._get_worklet_source()
        # The underrun path writes to output[outputIndex] then assigns lastSample
        # from that same index — without a truthy-guard that would suppress zero.
        assert "this.lastSample = output[outputIndex]" in src, (
            "Underrun path must update lastSample from the written output sample"
        )

    def test_crossfade_at_boundaries(self):
        src = self._get_worklet_source()
        assert "CROSSFADE_SAMPLES" in src, (
            "Worklet must define CROSSFADE_SAMPLES for cross-chunk smoothing"
        )

    def test_crossfade_32_samples(self):
        src = self._get_worklet_source()
        assert "CROSSFADE_SAMPLES = 32" in src, (
            "CROSSFADE_SAMPLES must be 32 for consistent smoothing"
        )

    def test_buffer_overflow_sample_based(self):
        src = self._get_worklet_source()
        assert "MAX_BUFFER_SAMPLES" in src, (
            "Worklet must use sample-based MAX_BUFFER_SAMPLES, not chunk-based"
        )

    def test_input_validation(self):
        src = self._get_worklet_source()
        assert "!(data instanceof Float32Array)" in src, (
            "Worklet must validate that input data is Float32Array"
        )

    def test_corruption_detection(self):
        src = self._get_worklet_source()
        assert "isFinite" in src, (
            "Worklet must check Number.isFinite to reject corrupt samples"
        )


# ---------------------------------------------------------------------------
# AudioWorklet (pcm-player-processor.js) — backwards-compat copy
# ---------------------------------------------------------------------------

class TestWorkletProcessorBackwardsCompat:
    """Verify pcm-player-processor.js is kept in sync with the canonical worklet
    and includes a deprecation notice pointing to the canonical source."""

    def _get_processor_source(self):
        return _read_source("src/static/pcm-player-processor.js")

    def test_deprecation_notice(self):
        src = self._get_processor_source()
        assert "pcm-player-worklet.js" in src, (
            "pcm-player-processor.js must reference the canonical worklet path"
        )

    def test_same_crossfade_value(self):
        src = self._get_processor_source()
        assert "CROSSFADE_SAMPLES = 32" in src, (
            "Processor must use same CROSSFADE_SAMPLES = 32 as canonical worklet"
        )

    def test_sample_based_buffer(self):
        src = self._get_processor_source()
        assert "MAX_BUFFER_SAMPLES" in src, (
            "Processor must use sample-based MAX_BUFFER_SAMPLES"
        )

    def test_corruption_detection(self):
        src = self._get_processor_source()
        assert "isFinite" in src

    def test_input_validation(self):
        src = self._get_processor_source()
        assert "!(data instanceof Float32Array)" in src


# ---------------------------------------------------------------------------
# Audiobook: micro-crossfade in pushAudioChunk (streamProcessor has no crossfade)
# ---------------------------------------------------------------------------

class TestAudiobookNoCrossfade:
    """Verify audiobook.js does NOT apply per-chunk micro-crossfade in
    pushAudioChunk — the per-chunk crossfade was removed because it modifies
    already-continuous server frames, causing crackling artifacts during
    streaming playback.  Sentence-level TTS on the server and the
    AudioWorklet's underrun recovery handle transitions smoothly."""

    def _get_push_chunk_body(self):
        content = _read_source("src/static/audiobook.js")
        match = re.search(
            r'function pushAudioChunk\s*\(.*?\{.*?(?=\n        \}\n\n)',
            content, re.DOTALL
        )
        assert match, "pushAudioChunk must be defined inside generateAudiobookWS"
        return match.group(0)

    def test_no_per_chunk_crossfade(self):
        """pushAudioChunk must NOT apply per-chunk crossfade — server frames
        are continuous within a sentence segment."""
        body = self._get_push_chunk_body()
        assert "FADE_SAMPLES" not in body, (
            "pushAudioChunk must NOT define FADE_SAMPLES — "
            "per-chunk crossfade was removed to fix crackling"
        )
        assert "previousTail" not in body, (
            "pushAudioChunk must NOT use previousTail — "
            "per-chunk crossfade was removed"
        )

    def test_no_legacy_crossfade(self):
        body = self._get_push_chunk_body()
        assert "lastScheduledFloat32" not in body, (
            "pushAudioChunk must NOT use legacy lastScheduledFloat32 variable"
        )
        assert "CROSSFADE_LEN" not in body, (
            "pushAudioChunk must NOT define legacy CROSSFADE_LEN"
        )

    def test_no_last_scheduled_variable(self):
        content = _read_source("src/static/audiobook.js")
        match = re.search(
            r'function generateAudiobookWS.*?(?=\nfunction |\n// ===|\Z)',
            content, re.DOTALL
        )
        assert match
        body = match.group(0)
        assert "lastScheduledFloat32" not in body, (
            "generateAudiobookWS must NOT declare lastScheduledFloat32 variable"
        )


# ---------------------------------------------------------------------------
# Playback-driven audio pipeline
# ---------------------------------------------------------------------------

class TestPlaybackDrivenPipeline:
    """Verify the audiobook pipeline is playback-driven: subtitle sync follows
    actual audio playback position reported by the worklet, not generation rate.
    Buffer tracking uses real worklet data, not a setInterval timer."""

    def _get_ws_body(self):
        content = _read_source("src/static/audiobook.js")
        match = re.search(
            r'function generateAudiobookWS.*?(?=\nfunction |\n// ===|\Z)',
            content, re.DOTALL
        )
        assert match
        return match.group(0)

    def test_no_setinterval_drain_timer(self):
        """bufferedSeconds must NOT use a setInterval drain timer — it must
        be updated from the worklet's reported availableSamples."""
        body = self._get_ws_body()
        assert "setInterval" not in body, (
            "Must NOT use setInterval for buffer drain — use worklet progress reports"
        )

    def test_samples_played_by_worklet_tracked(self):
        """Main thread must track samplesPlayedByWorklet from worklet messages."""
        body = self._get_ws_body()
        assert "samplesPlayedByWorklet" in body, (
            "Must track samplesPlayedByWorklet for playback-driven sync"
        )

    def test_subtitle_uses_playback_time(self):
        """Subtitle loop must use samplesPlayedByWorklet-based playbackTime for
        segment matching.  audioCtx.currentTime may be used for interpolation
        but must NOT be used directly in segment comparisons."""
        body = self._get_ws_body()
        # Find the updateSubtitlesLoop function (match up to the next function def)
        match = re.search(
            r'function updateSubtitlesLoop\b.*?(?=\n\s+function |\Z)',
            body, re.DOTALL
        )
        assert match, "updateSubtitlesLoop must exist"
        loop_body = match.group(0)
        assert "samplesPlayedByWorklet" in loop_body, (
            "Subtitle loop must use samplesPlayedByWorklet for playback-driven sync"
        )
        # Segment comparison must use playbackTime, not raw audioCtx.currentTime
        assert re.search(r'playbackTime\s*>=\s*seg\.startTime', loop_body), (
            "Segment comparison must use playbackTime (derived from worklet), not audioCtx.currentTime"
        )
        # audioCtx.currentTime must NOT be used directly in segment condition
        assert not re.search(r'audioCtx\.currentTime\s*>=\s*seg', loop_body), (
            "Segment comparison must NOT use audioCtx.currentTime directly"
        )

    def test_overflow_queue_present(self):
        """Backpressure must queue chunks instead of dropping them."""
        body = self._get_ws_body()
        assert "overflowQueue" in body, (
            "Must have an overflow queue for backpressure (no dropping)"
        )

    def test_overflow_queue_bounded(self):
        """Overflow queue must be bounded by MAX_QUEUE_SECONDS to prevent
        unbounded memory growth.  Must use incremental sample tracking."""
        body = self._get_ws_body()
        assert "MAX_QUEUE_SECONDS" in body, (
            "Must define MAX_QUEUE_SECONDS to bound overflow queue"
        )
        assert "trimOverflowQueue" in body, (
            "Must have trimOverflowQueue function to enforce the limit"
        )
        assert "overflowQueueSamples" in body, (
            "Must track overflowQueueSamples incrementally for O(1) duration checks"
        )
        assert re.search(r'>\s*MAX_QUEUE_SECONDS', body), (
            "trimOverflowQueue must compare against MAX_QUEUE_SECONDS"
        )
        assert "preserving queued audio to avoid word skips" in body, (
            "When queue exceeds limit, code must preserve queued audio to avoid dropping words"
        )

    def test_drain_overflow_queue_exists(self):
        """Must have a drainOverflowQueue function to push queued chunks."""
        body = self._get_ws_body()
        assert "drainOverflowQueue" in body, (
            "Must have drainOverflowQueue function for backpressure release"
        )

    def test_drain_checks_chunk_size(self):
        """drainOverflowQueue must check the next chunk's size before pushing
        to avoid overshooting the buffer limit."""
        body = self._get_ws_body()
        match = re.search(
            r'function drainOverflowQueue\b.*?(?=\n        function |\Z)',
            body, re.DOTALL
        )
        assert match, "drainOverflowQueue must exist"
        drain_body = match.group(0)
        assert re.search(r'overflowQueue\[0\]\.length', drain_body), (
            "drainOverflowQueue must check overflowQueue[0].length before pushing"
        )

    def test_no_chunk_dropping(self):
        """pushAudioChunk must NOT drop chunks — overflow queue instead."""
        body = self._get_ws_body()
        assert "dropping audio chunk" not in body, (
            "Must NOT drop audio chunks — use overflow queue instead"
        )

    def test_push_returns_false_when_no_context(self):
        """pushAudioChunk must return false when audioCtx or workletNode is null."""
        body = self._get_ws_body()
        match = re.search(
            r'function pushAudioChunk\s*\(.*?\{.*?(?=\n        \}\n\n)',
            body, re.DOTALL
        )
        assert match, "pushAudioChunk must exist"
        push_body = match.group(0)
        assert re.search(r'return false', push_body), (
            "pushAudioChunk must return false when audioCtx/workletNode is unavailable"
        )

    def test_worklet_reports_progress(self):
        """The AudioWorklet must send progress messages with samplesPlayed."""
        worklet_src = _read_source("src/static/voice/streamProcessor.js")
        assert "totalSamplesPlayed" in worklet_src, (
            "Worklet must track totalSamplesPlayed for progress reporting"
        )
        assert re.search(r'samplesPlayed', worklet_src), (
            "Worklet must send samplesPlayed in progress messages"
        )
        assert re.search(r'if\s*\(\s*this\.frameCount\s*>=\s*\d+', worklet_src), (
            "Worklet should gate progress reporting on a frame-count threshold"
        )
        threshold_match = re.search(r'if\s*\(\s*this\.frameCount\s*>=\s*(\d+)', worklet_src)
        assert threshold_match, "Worklet progress threshold must be parseable"
        assert int(threshold_match.group(1)) <= 6, (
            "Worklet progress cadence should be tight (<=6 frames) to reduce subtitle drift"
        )

    def test_worklet_reports_available_samples(self):
        """The AudioWorklet must send availableSamples in progress messages."""
        worklet_src = _read_source("src/static/voice/streamProcessor.js")
        assert re.search(
            r'postMessage\s*\(\s*\{[^}]*availableSamples',
            worklet_src
        ), "Worklet must include availableSamples in progress messages"

    def test_worklet_accepts_sample_rate(self):
        """The StreamProcessor must accept sampleRate from processorOptions."""
        worklet_src = _read_source("src/static/voice/streamProcessor.js")
        assert "processorOptions" in worklet_src, (
            "Worklet must accept processorOptions for sample rate configuration"
        )

    def test_worklet_node_passes_sample_rate(self):
        """AudioWorkletNode must pass sampleRate via processorOptions."""
        body = self._get_ws_body()
        assert re.search(r'processorOptions\s*:', body), (
            "Must pass processorOptions when creating AudioWorkletNode"
        )
        assert re.search(r'sampleRate\s*:', body), (
            "processorOptions must include sampleRate"
        )

    def test_segment_timing_relative(self):
        """Segment timing must be relative to 0 (cumulative samples pushed),
        not offset by playbackOrigin."""
        body = self._get_ws_body()
        assert "playbackOrigin" not in body, (
            "Segment timing must NOT use playbackOrigin — use relative timing from 0"
        )

    def test_samples_played_guarded(self):
        """samplesPlayedByWorklet must be guarded against undefined with || 0."""
        body = self._get_ws_body()
        assert re.search(r'\(samplesPlayedByWorklet\s*\|\|\s*0\)', body), (
            "Must guard samplesPlayedByWorklet with || 0 for safety"
        )

    def test_no_dropped_chunks(self):
        """Audio must NEVER be silently dropped — pushAudioChunk must push to
        overflowQueue on backpressure and return false for caller to detect."""
        body = self._get_ws_body()
        match = re.search(
            r'function pushAudioChunk\s*\(.*?\{.*?(?=\n        \}\n\n)',
            body, re.DOTALL
        )
        assert match, "pushAudioChunk must exist"
        push_body = match.group(0)
        assert "overflowQueue.push" in push_body, (
            "pushAudioChunk must push to overflowQueue on backpressure"
        )
        assert "return false" in push_body, (
            "pushAudioChunk must return false when chunk is queued or not accepted"
        )

    def test_no_previous_tail_state(self):
        """previousTail must NOT be present — per-chunk crossfade was removed
        to fix crackling artifacts during streaming playback."""
        body = self._get_ws_body()
        assert "previousTail" not in body, (
            "previousTail must not exist — per-chunk crossfade removed"
        )

    def test_drain_allowance(self):
        """drainOverflowQueue must allow slight overshoot to prevent queue
        starvation when chunks are large."""
        body = self._get_ws_body()
        assert "DRAIN_ALLOWANCE" in body, (
            "Must define DRAIN_ALLOWANCE for drain overshoot tolerance"
        )

    def test_playback_time_interpolation(self):
        """Subtitle loop must interpolate playback time between worklet
        progress reports for smooth 60fps subtitle movement."""
        body = self._get_ws_body()
        assert "lastProgressTimestamp" in body, (
            "Must track lastProgressTimestamp for playback time interpolation"
        )
        match = re.search(
            r'function updateSubtitlesLoop\b.*?(?=\n\s+function |\Z)',
            body, re.DOTALL
        )
        assert match, "updateSubtitlesLoop must exist"
        loop_body = match.group(0)
        assert "lastProgressTimestamp" in loop_body, (
            "Subtitle loop must use lastProgressTimestamp for interpolation"
        )
        assert "Math.min" in loop_body and "bufferedSeconds" in loop_body, (
            "Interpolation must be clamped by bufferedSeconds to avoid transcript getting ahead"
        )

    def test_caller_handles_push_return(self):
        """The caller of pushAudioChunk must check its return value."""
        body = self._get_ws_body()
        assert re.search(r'if\s*\(\s*!pushAudioChunk', body), (
            "Caller must check pushAudioChunk return value with if (!pushAudioChunk(...))"
        )


# ---------------------------------------------------------------------------
# Clipping detection is throttled
# ---------------------------------------------------------------------------

class TestClippingDetectionThrottled:
    """Verify that clipping detection in ttsClient.js is throttled to avoid
    main-thread slowdown from scanning every sample of every chunk."""

    def test_throttled_with_random(self):
        content = _read_source("src/static/voice/ttsClient.js")
        assert "Math.random()" in content, (
            "ttsClient.js clipping detection must be throttled with Math.random()"
        )


# ---------------------------------------------------------------------------
# Sample rate consistency
# ---------------------------------------------------------------------------

class TestSampleRateConsistency:
    """Verify sample rate is defined as a single source of truth."""

    def test_audiobook_sample_rate_constant(self):
        content = _read_source("src/static/audiobook.js")
        match = re.search(
            r'function generateAudiobookWS.*?(?=\nfunction |\n// ===|\Z)',
            content, re.DOTALL
        )
        assert match
        body = match.group(0)
        assert "SAMPLE_RATE = 24000" in body, (
            "audiobook.js must define SAMPLE_RATE constant"
        )

    def test_audio_output_uses_24k(self):
        content = _read_source("src/static/voice/audioOutput.js")
        assert "sampleRate: 24000" in content, (
            "audioOutput.js must use 24000 Hz sample rate"
        )


# ---------------------------------------------------------------------------
# PDF upload must populate textarea so AI Structure / Analyze can read it
# ---------------------------------------------------------------------------

class TestPdfUploadPopulatesTextarea:
    """After a successful PDF upload the textarea (audiobookText.value) must be
    populated with the extracted text.  Otherwise AI Structure / Analyze will
    see an empty textarea and show 'Please enter or upload some text first'."""

    def _get_upload_handler(self):
        content = _read_source("src/static/audiobook.js")
        m = re.search(
            r'(async\s+function\s+handleAudiobookFileUpload\b.*?)(?=\nasync\s+function\s|\nfunction\s|\n//\s*[-=]{3,})',
            content,
            re.DOTALL,
        )
        assert m, "handleAudiobookFileUpload must exist in audiobook.js"
        return m.group(1)

    def test_textarea_set_after_pdf_upload(self):
        """The PDF branch must assign audiobookText.value with the extracted text."""
        body = self._get_upload_handler()
        # Look for textarea assignment in the PDF branch (after the .pdf check)
        pdf_branch = body.split(".endsWith('.pdf')")[1] if ".endsWith('.pdf')" in body else body
        assert "audiobookText.value" in pdf_branch, (
            "handleAudiobookFileUpload must set audiobookText.value in the PDF branch "
            "so that AI Structure / Analyze can read the uploaded text"
        )

    def test_fallback_chain_uses_best_source(self):
        """The PDF handler must use a fallback chain: full_text > initial_text > segments."""
        body = self._get_upload_handler()
        assert "full_text" in body, (
            "handleAudiobookFileUpload must check data.full_text as the best text source"
        )
        assert "initial_text" in body, (
            "handleAudiobookFileUpload must fall back to data.initial_text"
        )
        assert "segments" in body and ".map" in body, (
            "handleAudiobookFileUpload must reconstruct text from segments as a final fallback"
        )


# ---------------------------------------------------------------------------
# getAudiobookText helper – single source of truth for text retrieval
# ---------------------------------------------------------------------------

class TestGetAudiobookTextHelper:
    """audiobook.js must define a getAudiobookText() helper and use it in
    analyzeAudiobookText and aiStructureAudiobookText instead of reading
    audiobookText.value directly."""

    def _get_content(self):
        return _read_source("src/static/audiobook.js")

    def test_helper_defined(self):
        content = self._get_content()
        assert "function getAudiobookText()" in content, (
            "audiobook.js must define a getAudiobookText() helper function"
        )

    def test_helper_checks_textarea(self):
        content = self._get_content()
        m = re.search(
            r'function getAudiobookText\(\).*?\}',
            content,
            re.DOTALL,
        )
        assert m, "getAudiobookText must exist"
        body = m.group(0)
        assert "audiobookText" in body, (
            "getAudiobookText must read from the textarea element"
        )

    def test_helper_falls_back_to_state(self):
        content = self._get_content()
        m = re.search(
            r'function getAudiobookText\(\).*?\}',
            content,
            re.DOTALL,
        )
        assert m, "getAudiobookText must exist"
        body = m.group(0)
        assert "audiobookState.text" in body, (
            "getAudiobookText must fall back to audiobookState.text"
        )

    def test_analyze_uses_helper(self):
        content = self._get_content()
        m = re.search(
            r'(async\s+function\s+analyzeAudiobookText\b.*?)(?=\n(?:async\s+)?function\s|\n//\s*[-=]{3,})',
            content,
            re.DOTALL,
        )
        assert m, "analyzeAudiobookText must exist"
        body = m.group(1)
        assert "getAudiobookText()" in body, (
            "analyzeAudiobookText must use getAudiobookText() helper"
        )

    def test_ai_structure_uses_helper(self):
        content = self._get_content()
        m = re.search(
            r'(async\s+function\s+aiStructureAudiobookText\b.*?)(?=\n(?:async\s+)?function\s|\n//\s*[-=]{3,})',
            content,
            re.DOTALL,
        )
        assert m, "aiStructureAudiobookText must exist"
        body = m.group(1)
        assert "getAudiobookText()" in body, (
            "aiStructureAudiobookText must use getAudiobookText() helper"
        )
