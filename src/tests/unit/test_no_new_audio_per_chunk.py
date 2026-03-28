"""
Tests that streaming audio playback does NOT create a new Audio() element
per chunk.  Instead, all chunk-level playback should use the Web Audio API
(AudioContext + createBufferSource) to reuse a single context.

Tests use source-code inspection (regex) since no JS test framework exists.
"""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def _read_source(relative_path):
    with open(os.path.join(REPO_ROOT, relative_path)) as f:
        return f.read()


# ---------------------------------------------------------------------------
# audiobook.js  –  playAudioSegment must NOT use new Audio()
# ---------------------------------------------------------------------------

class TestAudiobookNoNewAudio:
    """playAudioSegment in audiobook.js must use Web Audio API."""

    def _get_source(self):
        return _read_source("src/static/audiobook.js")

    def test_play_audio_segment_defined(self):
        src = self._get_source()
        assert "function playAudioSegment" in src

    def test_play_audio_segment_no_new_audio(self):
        """playAudioSegment must not contain 'new Audio('."""
        src = self._get_source()
        # Extract the playAudioSegment function body
        m = re.search(r'function playAudioSegment\b.*?\n\}', src, re.DOTALL)
        assert m, "playAudioSegment function not found"
        body = m.group(0)
        assert "new Audio(" not in body, \
            "playAudioSegment still creates a new Audio element per chunk"

    def test_play_audio_segment_uses_audio_context(self):
        """playAudioSegment should use AudioContext."""
        src = self._get_source()
        m = re.search(r'function playAudioSegment\b.*?\n\}', src, re.DOTALL)
        assert m
        body = m.group(0)
        assert "AudioContext" in body or "_sseAudioCtx" in body, \
            "playAudioSegment should use Web Audio API AudioContext"

    def test_play_audio_segment_uses_buffer_source(self):
        """playAudioSegment should use createBufferSource."""
        src = self._get_source()
        m = re.search(r'function playAudioSegment\b.*?\n\}', src, re.DOTALL)
        assert m
        body = m.group(0)
        assert "createBufferSource" in body, \
            "playAudioSegment should use createBufferSource for playback"

    def test_sse_audio_ctx_declared(self):
        """A reusable _sseAudioCtx variable should exist."""
        src = self._get_source()
        assert "_sseAudioCtx" in src

    def test_stop_cleans_up_sse_ctx(self):
        """stopStreamingAudio should clean up _sseAudioCtx."""
        src = self._get_source()
        m = re.search(r'function stopStreamingAudio\b.*?\n\}', src, re.DOTALL)
        assert m
        body = m.group(0)
        assert "_sseAudioCtx" in body, \
            "stopStreamingAudio must clean up _sseAudioCtx"

    def test_pause_suspends_sse_ctx(self):
        """pauseStreamingAudio should suspend _sseAudioCtx."""
        src = self._get_source()
        m = re.search(r'function pauseStreamingAudio\b.*?\n\}', src, re.DOTALL)
        assert m
        body = m.group(0)
        assert "_sseAudioCtx" in body, \
            "pauseStreamingAudio must suspend _sseAudioCtx"

    def test_resume_resumes_sse_ctx(self):
        """resumeStreamingAudio should resume _sseAudioCtx."""
        src = self._get_source()
        m = re.search(r'function resumeStreamingAudio\b.*?\n\}', src, re.DOTALL)
        assert m
        body = m.group(0)
        assert "_sseAudioCtx" in body, \
            "resumeStreamingAudio must resume _sseAudioCtx"


# ---------------------------------------------------------------------------
# podcast.js  –  playPodcastChunk must NOT use new Audio()
# ---------------------------------------------------------------------------

class TestPodcastNoNewAudio:
    """playPodcastChunk in podcast.js must use Web Audio API."""

    def _get_source(self):
        return _read_source("src/static/podcast.js")

    def test_play_podcast_chunk_defined(self):
        src = self._get_source()
        assert "function playPodcastChunk" in src

    def test_play_podcast_chunk_no_new_audio(self):
        src = self._get_source()
        m = re.search(r'function playPodcastChunk\b.*?\n\}', src, re.DOTALL)
        assert m, "playPodcastChunk function not found"
        body = m.group(0)
        assert "new Audio(" not in body, \
            "playPodcastChunk still creates a new Audio element per chunk"

    def test_play_podcast_chunk_uses_buffer_source(self):
        src = self._get_source()
        m = re.search(r'function playPodcastChunk\b.*?\n\}', src, re.DOTALL)
        assert m
        body = m.group(0)
        assert "createBufferSource" in body

    def test_podcast_audio_ctx_declared(self):
        src = self._get_source()
        assert "_podcastAudioCtx" in src

    def test_stop_cleans_up_podcast_ctx(self):
        src = self._get_source()
        m = re.search(r'function stopPodcastStreaming\b.*?\n\}', src, re.DOTALL)
        assert m
        body = m.group(0)
        assert "_podcastAudioCtx" in body

    def test_pause_suspends_podcast_ctx(self):
        src = self._get_source()
        m = re.search(r'function pausePodcastStreaming\b.*?\n\}', src, re.DOTALL)
        assert m
        body = m.group(0)
        assert "_podcastAudioCtx" in body

    def test_resume_resumes_podcast_ctx(self):
        src = self._get_source()
        m = re.search(r'function resumePodcastStreaming\b.*?\n\}', src, re.DOTALL)
        assert m
        body = m.group(0)
        assert "_podcastAudioCtx" in body


# ---------------------------------------------------------------------------
# chat/audio-player.js  –  playTTSQueue and playTTS must NOT use new Audio()
# ---------------------------------------------------------------------------

class TestChatAudioPlayerNoNewAudio:
    """TTS playback in chat/audio-player.js must not create Audio elements."""

    def _get_source(self):
        return _read_source("src/static/chat/audio-player.js")

    def test_play_tts_queue_no_new_audio(self):
        src = self._get_source()
        m = re.search(r'(?:async )?function playTTSQueue\b.*?\n\}', src, re.DOTALL)
        assert m, "playTTSQueue function not found"
        body = m.group(0)
        assert "new Audio(" not in body, \
            "playTTSQueue still creates a new Audio element per queue item"

    def test_play_tts_queue_uses_web_audio(self):
        src = self._get_source()
        m = re.search(r'(?:async )?function playTTSQueue\b.*?\n\}', src, re.DOTALL)
        assert m
        body = m.group(0)
        assert "getWebAudioContext" in body or "decodeAudioData" in body, \
            "playTTSQueue should use Web Audio API"

    def test_play_tts_no_new_audio(self):
        src = self._get_source()
        m = re.search(r'function playTTS\b.*?\n\}', src, re.DOTALL)
        assert m, "playTTS function not found"
        body = m.group(0)
        assert "new Audio(" not in body, \
            "playTTS still creates a new Audio element"

    def test_play_tts_uses_web_audio(self):
        src = self._get_source()
        m = re.search(r'function playTTS\b.*?\n\}', src, re.DOTALL)
        assert m
        body = m.group(0)
        assert "getWebAudioContext" in body or "decodeAudioData" in body, \
            "playTTS should use Web Audio API"

    def test_clear_tts_queue_stops_source(self):
        src = self._get_source()
        m = re.search(r'function clearTTSQueue\b.*?\n\}', src, re.DOTALL)
        assert m
        body = m.group(0)
        # Should close the AudioContext (kills all scheduled audio), not just stop a single source
        assert ".close()" in body, \
            "clearTTSQueue should close AudioContext to stop all scheduled audio"


# ---------------------------------------------------------------------------
# features.js  –  playAudiobookFromLibrary must NOT use new Audio()
# ---------------------------------------------------------------------------

class TestFeaturesNoNewAudio:
    """playAudiobookFromLibrary in features.js must not create Audio element."""

    def _get_source(self):
        return _read_source("src/static/features.js")

    def test_no_new_audio(self):
        src = self._get_source()
        m = re.search(r'function playAudiobookFromLibrary\b.*?\n\}', src, re.DOTALL)
        assert m, "playAudiobookFromLibrary function not found"
        body = m.group(0)
        assert "new Audio(" not in body, \
            "playAudiobookFromLibrary still creates a new Audio element"

    def test_uses_web_audio(self):
        src = self._get_source()
        m = re.search(r'function playAudiobookFromLibrary\b.*?\n\}', src, re.DOTALL)
        assert m
        body = m.group(0)
        assert "AudioContext" in body or "createBufferSource" in body, \
            "playAudiobookFromLibrary should use Web Audio API"


# ---------------------------------------------------------------------------
# Timeline-scheduled playback tests
# ---------------------------------------------------------------------------

class TestAudiobookTimelineScheduling:
    """audiobook.js must use time-scheduled playback, not immediate source.start()."""

    def _get_source(self):
        return _read_source("src/static/audiobook.js")

    def test_next_playback_time_declared(self):
        """_sseNextPlaybackTime timeline variable must exist."""
        src = self._get_source()
        assert "_sseNextPlaybackTime" in src

    def test_initial_buffer_sec(self):
        """SSE_INITIAL_BUFFER_SEC constant must exist."""
        src = self._get_source()
        assert "SSE_INITIAL_BUFFER_SEC" in src

    def test_target_sample_rate(self):
        """SSE_TARGET_SAMPLE_RATE constant must exist."""
        src = self._get_source()
        assert "SSE_TARGET_SAMPLE_RATE" in src

    def test_play_audio_segment_uses_scheduled_start(self):
        """playAudioSegment must call source.start(_sseNextPlaybackTime), not source.start()."""
        src = self._get_source()
        m = re.search(r'function playAudioSegment\b.*?\n\}', src, re.DOTALL)
        assert m, "playAudioSegment function not found"
        body = m.group(0)
        assert "source.start(_sseNextPlaybackTime)" in body, \
            "playAudioSegment must schedule on timeline, not play immediately"

    def test_play_audio_segment_advances_timeline(self):
        """playAudioSegment must advance _sseNextPlaybackTime after scheduling."""
        src = self._get_source()
        m = re.search(r'function playAudioSegment\b.*?\n\}', src, re.DOTALL)
        assert m
        body = m.group(0)
        assert "_sseNextPlaybackTime +=" in body, \
            "playAudioSegment must advance the timeline"

    def test_play_audio_segment_underrun_protection(self):
        """playAudioSegment must have underrun protection for timeline."""
        src = self._get_source()
        m = re.search(r'function playAudioSegment\b.*?\n\}', src, re.DOTALL)
        assert m
        body = m.group(0)
        assert "_sseNextPlaybackTime < now" in body, \
            "playAudioSegment must detect underrun"

    def test_play_audio_segment_no_singleton_source(self):
        """playAudioSegment must NOT assign _sseAudioSource (no singleton tracking)."""
        src = self._get_source()
        m = re.search(r'function playAudioSegment\b.*?\n\}', src, re.DOTALL)
        assert m
        body = m.group(0)
        assert "_sseAudioSource" not in body, \
            "playAudioSegment must not track a singleton source"

    def test_play_audio_segment_not_promise(self):
        """playAudioSegment must not return a Promise (fire-and-forget scheduling)."""
        src = self._get_source()
        m = re.search(r'function playAudioSegment\b.*?\n\}', src, re.DOTALL)
        assert m
        body = m.group(0)
        assert "return new Promise" not in body, \
            "playAudioSegment must not return a Promise"

    def test_play_audio_segment_no_context_recreation(self):
        """playAudioSegment must NOT recreate AudioContext on sample rate mismatch."""
        src = self._get_source()
        m = re.search(r'function playAudioSegment\b.*?\n\}', src, re.DOTALL)
        assert m
        body = m.group(0)
        # Should only warn on mismatch, not recreate the context
        assert "_sseAudioCtx.sampleRate !== " not in body, \
            "Must not recreate AudioContext based on sample rate comparison"
        # The function should use the fixed target sample rate
        assert "SSE_TARGET_SAMPLE_RATE" in body, \
            "Must use fixed SSE_TARGET_SAMPLE_RATE, not dynamic sample rate"

    def test_play_audio_segment_crossfade(self):
        """playAudioSegment must apply equal-power crossfade with overlap trimming."""
        src = self._get_source()
        m = re.search(r'function playAudioSegment\b.*?\n\}', src, re.DOTALL)
        assert m
        body = m.group(0)
        assert "_ssePrevTail" in body, \
            "playAudioSegment must use _ssePrevTail for crossfade continuity"
        assert "Math.cos" in body and "Math.sin" in body, \
            "playAudioSegment must use equal-power (cos/sin) crossfade"
        assert "float32.slice(overlap)" in body or ".slice(overlap)" in body, \
            "playAudioSegment must trim overlapped region after crossfade"
        assert "Math.min(" in body, \
            "playAudioSegment must use Math.min for robust overlap calculation"

    def test_play_audio_segment_let_float32(self):
        """float32 must be declared with let (not const) to allow slice reassignment."""
        src = self._get_source()
        m = re.search(r'function playAudioSegment\b.*?\n\}', src, re.DOTALL)
        assert m
        body = m.group(0)
        assert "let float32" in body, \
            "float32 must be let (not const) for slice reassignment after crossfade"

    def test_play_audio_segment_tiny_chunk_guard(self):
        """playAudioSegment must guard against very small chunks."""
        src = self._get_source()
        m = re.search(r'function playAudioSegment\b.*?\n\}', src, re.DOTALL)
        assert m
        body = m.group(0)
        assert "float32.length < 128" in body or "float32.length<128" in body, \
            "playAudioSegment must skip crossfade for tiny chunks (< 128 samples)"

    def test_play_streaming_audio_no_await_segment(self):
        """playStreamingAudio must NOT await playAudioSegment (fire-and-forget)."""
        src = self._get_source()
        m = re.search(r'(?:async )?function playStreamingAudio\b.*?\n\}', src, re.DOTALL)
        assert m, "playStreamingAudio function not found"
        body = m.group(0)
        assert "await playAudioSegment" not in body, \
            "playStreamingAudio must not await playAudioSegment"

    def test_stop_resets_timeline(self):
        """stopStreamingAudio must reset _sseNextPlaybackTime."""
        src = self._get_source()
        m = re.search(r'function stopStreamingAudio\b.*?\n\}', src, re.DOTALL)
        assert m
        body = m.group(0)
        assert "_sseNextPlaybackTime = 0" in body, \
            "stopStreamingAudio must reset the timeline"

    def test_stop_resets_prev_tail(self):
        """stopStreamingAudio must reset _ssePrevTail for crossfade."""
        src = self._get_source()
        m = re.search(r'function stopStreamingAudio\b.*?\n\}', src, re.DOTALL)
        assert m
        body = m.group(0)
        assert "_ssePrevTail = null" in body, \
            "stopStreamingAudio must reset _ssePrevTail"

    def test_reset_state_clears_prev_tail(self):
        """resetAudiobookState must reset _ssePrevTail."""
        src = self._get_source()
        m = re.search(r'function resetAudiobookState\b.*?\n\}', src, re.DOTALL)
        assert m
        body = m.group(0)
        assert "_ssePrevTail = null" in body, \
            "resetAudiobookState must reset _ssePrevTail"

    def test_crossfade_samples_constant(self):
        """SSE_CROSSFADE_SAMPLES constant must exist (>=256)."""
        src = self._get_source()
        assert "SSE_CROSSFADE_SAMPLES" in src
        m = re.search(r'SSE_CROSSFADE_SAMPLES\s*=\s*(\d+)', src)
        assert m
        assert int(m.group(1)) >= 256, \
            "SSE_CROSSFADE_SAMPLES must be >= 256 for adequate crossfade"


class TestPodcastTimelineScheduling:
    """podcast.js must use time-scheduled playback."""

    def _get_source(self):
        return _read_source("src/static/podcast.js")

    def test_next_playback_time_declared(self):
        src = self._get_source()
        assert "_podcastNextPlaybackTime" in src

    def test_play_podcast_chunk_uses_scheduled_start(self):
        src = self._get_source()
        m = re.search(r'function playPodcastChunk\b.*?\n\}', src, re.DOTALL)
        assert m
        body = m.group(0)
        assert "source.start(_podcastNextPlaybackTime)" in body

    def test_play_podcast_chunk_advances_timeline(self):
        src = self._get_source()
        m = re.search(r'function playPodcastChunk\b.*?\n\}', src, re.DOTALL)
        assert m
        body = m.group(0)
        assert "_podcastNextPlaybackTime +=" in body

    def test_play_podcast_chunk_not_promise(self):
        src = self._get_source()
        m = re.search(r'function playPodcastChunk\b.*?\n\}', src, re.DOTALL)
        assert m
        body = m.group(0)
        assert "return new Promise" not in body

    def test_play_podcast_chunk_no_singleton_source(self):
        src = self._get_source()
        m = re.search(r'function playPodcastChunk\b.*?\n\}', src, re.DOTALL)
        assert m
        body = m.group(0)
        assert "_podcastAudioSource" not in body

    def test_play_next_no_await_chunk(self):
        src = self._get_source()
        m = re.search(r'(?:async )?function playNextPodcastChunk\b.*?\n\}', src, re.DOTALL)
        assert m
        body = m.group(0)
        assert "await playPodcastChunk" not in body

    def test_stop_resets_timeline(self):
        src = self._get_source()
        m = re.search(r'function stopPodcastStreaming\b.*?\n\}', src, re.DOTALL)
        assert m
        body = m.group(0)
        assert "_podcastNextPlaybackTime = 0" in body

    def test_play_podcast_chunk_crossfade(self):
        """playPodcastChunk must apply equal-power crossfade with overlap trimming."""
        src = self._get_source()
        m = re.search(r'function playPodcastChunk\b.*?\n\}', src, re.DOTALL)
        assert m
        body = m.group(0)
        assert "_podcastPrevTail" in body, \
            "playPodcastChunk must use _podcastPrevTail for crossfade"
        assert "Math.cos" in body and "Math.sin" in body, \
            "playPodcastChunk must use equal-power (cos/sin) crossfade"
        assert "float32.slice(overlap)" in body or ".slice(overlap)" in body, \
            "playPodcastChunk must trim overlapped region after crossfade"

    def test_play_podcast_chunk_let_float32(self):
        """float32 must be declared with let in playPodcastChunk."""
        src = self._get_source()
        m = re.search(r'function playPodcastChunk\b.*?\n\}', src, re.DOTALL)
        assert m
        body = m.group(0)
        assert "let float32" in body, \
            "float32 must be let (not const) for slice reassignment after crossfade"

    def test_stop_resets_prev_tail(self):
        """stopPodcastStreaming must reset _podcastPrevTail."""
        src = self._get_source()
        m = re.search(r'function stopPodcastStreaming\b.*?\n\}', src, re.DOTALL)
        assert m
        body = m.group(0)
        assert "_podcastPrevTail = null" in body

    def test_crossfade_samples_constant(self):
        """PODCAST_CROSSFADE_SAMPLES must exist (>=256)."""
        src = self._get_source()
        assert "PODCAST_CROSSFADE_SAMPLES" in src
        m = re.search(r'PODCAST_CROSSFADE_SAMPLES\s*=\s*(\d+)', src)
        assert m
        assert int(m.group(1)) >= 256


class TestChatAudioScheduling:
    """chat/audio-player.js TTS queue must use timeline scheduling."""

    def _get_source(self):
        return _read_source("src/static/chat/audio-player.js")

    def test_tts_queue_uses_scheduled_start(self):
        src = self._get_source()
        m = re.search(r'(?:async )?function playTTSQueue\b.*?\n\}', src, re.DOTALL)
        assert m
        body = m.group(0)
        assert "source.start(startTime)" in body or "source.start(webAudioNextStartTime)" in body, \
            "playTTSQueue must use scheduled start, not immediate"

    def test_tts_queue_advances_timeline(self):
        src = self._get_source()
        m = re.search(r'(?:async )?function playTTSQueue\b.*?\n\}', src, re.DOTALL)
        assert m
        body = m.group(0)
        assert "webAudioNextStartTime" in body, \
            "playTTSQueue must advance webAudioNextStartTime"

    def test_clear_tts_queue_resets_timeline(self):
        src = self._get_source()
        m = re.search(r'function clearTTSQueue\b.*?\n\}', src, re.DOTALL)
        assert m
        body = m.group(0)
        assert "webAudioNextStartTime = 0" in body, \
            "clearTTSQueue must reset the timeline"
