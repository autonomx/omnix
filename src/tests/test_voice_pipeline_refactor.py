"""
Tests for the voice pipeline refactor: timeline-scheduled AudioOutput,
streaming text buffer in VoiceEngine, partial-STT early LLM, immediate TTS.

Uses source-code inspection (regex) since no JS test framework exists.
"""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _read_source(relative_path):
    with open(os.path.join(REPO_ROOT, relative_path)) as f:
        return f.read()


# ---------------------------------------------------------------------------
# audioOutput.js – timeline-scheduled playback (AudioScheduler)
# ---------------------------------------------------------------------------

class TestAudioOutputScheduler:
    """audioOutput.js must use timeline-scheduled playback, not sequential queue."""

    def _get_source(self):
        return _read_source("src/static/voice/audioOutput.js")

    # -- removed queue-based members --

    def test_no_audioQueue_array(self):
        """Must NOT have this.audioQueue = []."""
        src = self._get_source()
        assert "this.audioQueue" not in src, \
            "audioQueue array should be removed in favour of timeline scheduling"

    def test_no_playing_flag(self):
        """Must NOT have a this.playing boolean flag."""
        src = self._get_source()
        assert "this.playing" not in src, \
            "this.playing sequential flag should be removed"

    def test_no_playNext_method(self):
        """playNext() should not exist."""
        src = self._get_source()
        assert "playNext()" not in src and "playNext (" not in src, \
            "playNext should be removed – scheduling replaces sequential play"

    def test_no_playAudioChunk_method(self):
        """playAudioChunk() should not exist (internal detail removed)."""
        src = self._get_source()
        assert "playAudioChunk(" not in src, \
            "playAudioChunk should be removed in favour of _scheduleBuffer"

    def test_no_minBufferSize_count(self):
        """Chunk-count-based minBufferSize should be replaced by time-based minBufferSec."""
        src = self._get_source()
        assert "this.minBufferSize" not in src, \
            "minBufferSize (chunk count) should be replaced by minBufferSec (time)"

    # -- new scheduler members --

    def test_has_ctx(self):
        src = self._get_source()
        assert "this.ctx" in src

    def test_has_nextTime(self):
        src = self._get_source()
        assert "this.nextTime" in src

    def test_has_started(self):
        src = self._get_source()
        assert "this.started" in src

    def test_has_bufferedTime(self):
        src = self._get_source()
        assert "this.bufferedTime" in src

    def test_has_minBufferSec(self):
        src = self._get_source()
        assert "this.minBufferSec" in src

    def test_ensureContext_method(self):
        src = self._get_source()
        assert "_ensureContext()" in src or "_ensureContext ()" in src

    def test_scheduleBuffer_method(self):
        src = self._get_source()
        assert "_scheduleBuffer(" in src

    def test_reset_method(self):
        src = self._get_source()
        assert "reset()" in src

    # -- scheduling behaviour --

    def test_enqueue_calls_scheduleBuffer(self):
        """enqueue must call _scheduleBuffer, not playNext."""
        src = self._get_source()
        # Class methods are at 2-space indent; use \n  \} to find their closing brace
        m = re.search(r'enqueue\s*\(.*?\)\s*\{.*?\n  \}', src, re.DOTALL)
        assert m, "enqueue method not found"
        body = m.group(0)
        assert "_scheduleBuffer" in body, \
            "enqueue must delegate to _scheduleBuffer for timeline scheduling"

    def test_scheduleBuffer_uses_start_t(self):
        """_scheduleBuffer must call source.start(t), not source.start()."""
        src = self._get_source()
        m = re.search(r'_scheduleBuffer\s*\(.*?\)\s*\{.*?\n  \}', src, re.DOTALL)
        assert m, "_scheduleBuffer method not found"
        body = m.group(0)
        assert "source.start(t)" in body, \
            "_scheduleBuffer must schedule on timeline with source.start(t)"

    def test_scheduleBuffer_advances_nextTime(self):
        """_scheduleBuffer must advance this.nextTime."""
        src = self._get_source()
        m = re.search(r'_scheduleBuffer\s*\(.*?\)\s*\{.*?\n  \}', src, re.DOTALL)
        assert m
        body = m.group(0)
        assert "this.nextTime +=" in body, \
            "_scheduleBuffer must advance the timeline"

    def test_scheduleBuffer_micro_fade(self):
        """_scheduleBuffer must apply micro fade to prevent clicks."""
        src = self._get_source()
        m = re.search(r'_scheduleBuffer\s*\(.*?\)\s*\{.*?\n  \}', src, re.DOTALL)
        assert m
        body = m.group(0)
        assert "linearRampToValueAtTime" in body, \
            "_scheduleBuffer must apply micro fade"

    def test_scheduleBuffer_creates_gain_node(self):
        """_scheduleBuffer must use a GainNode for fading."""
        src = self._get_source()
        m = re.search(r'_scheduleBuffer\s*\(.*?\)\s*\{.*?\n  \}', src, re.DOTALL)
        assert m
        body = m.group(0)
        assert "createGain()" in body

    def test_scheduleBuffer_underrun_protection(self):
        """_scheduleBuffer must have underrun protection."""
        src = self._get_source()
        m = re.search(r'_scheduleBuffer\s*\(.*?\)\s*\{.*?\n  \}', src, re.DOTALL)
        assert m
        body = m.group(0)
        assert "this.nextTime < now" in body, \
            "_scheduleBuffer must detect underrun and reset timeline"

    def test_scheduleBuffer_fire_and_forget(self):
        """_scheduleBuffer must not return a Promise."""
        src = self._get_source()
        m = re.search(r'_scheduleBuffer\s*\(.*?\)\s*\{.*?\n  \}', src, re.DOTALL)
        assert m
        body = m.group(0)
        assert "return new Promise" not in body, \
            "_scheduleBuffer must be fire-and-forget (no Promise)"

    def test_enqueue_no_await(self):
        """enqueue must not use await – fire-and-forget scheduling."""
        src = self._get_source()
        m = re.search(r'enqueue\s*\(.*?\)\s*\{.*?\n  \}', src, re.DOTALL)
        assert m
        body = m.group(0)
        assert "await " not in body, \
            "enqueue must not await anything"

    def test_reset_closes_context(self):
        """reset() must close the AudioContext."""
        src = self._get_source()
        m = re.search(r'reset\s*\(\s*\)\s*\{.*?\n  \}', src, re.DOTALL)
        assert m, "reset method not found"
        body = m.group(0)
        assert ".close()" in body, \
            "reset must close the AudioContext"

    def test_reset_clears_nextTime(self):
        """reset() must set nextTime to 0."""
        src = self._get_source()
        m = re.search(r'reset\s*\(\s*\)\s*\{.*?\n  \}', src, re.DOTALL)
        assert m
        body = m.group(0)
        assert "this.nextTime = 0" in body

    def test_reset_clears_started(self):
        """reset() must set started to false."""
        src = self._get_source()
        m = re.search(r'reset\s*\(\s*\)\s*\{.*?\n  \}', src, re.DOTALL)
        assert m
        body = m.group(0)
        assert "this.started = false" in body

    def test_stop_calls_reset(self):
        """stop() must delegate to reset()."""
        src = self._get_source()
        m = re.search(r'stop\s*\(\s*\)\s*\{.*?\n  \}', src, re.DOTALL)
        assert m
        body = m.group(0)
        assert "this.reset()" in body

    def test_no_currentAudio_singleton(self):
        """Must not track a singleton currentAudio source."""
        src = self._get_source()
        assert "this.currentAudio" not in src, \
            "currentAudio singleton tracking should be removed"

    def test_flush_schedules_pending(self):
        """flush() must schedule pending buffers that were below minBufferSec."""
        src = self._get_source()
        m = re.search(r'flush\s*\(\s*\)\s*\{.*?\n  \}', src, re.DOTALL)
        assert m, "flush method not found"
        body = m.group(0)
        assert "_scheduleBuffer" in body, \
            "flush must schedule pending buffers"

    def test_isPlaying_checks_sources(self):
        """isPlaying must check active source count, not a boolean flag."""
        src = self._get_source()
        m = re.search(r'isPlaying\s*\(\s*\)\s*\{.*?\n  \}', src, re.DOTALL)
        assert m
        body = m.group(0)
        assert "_activeSourceCount" in body


# ---------------------------------------------------------------------------
# voiceEngine.js – streaming pipeline
# ---------------------------------------------------------------------------

class TestVoiceEngineStreamingPipeline:
    """voiceEngine.js must use streaming text buffer and immediate TTS."""

    def _get_source(self):
        return _read_source("src/static/voice/voiceEngine.js")

    # -- removed queue system --

    def test_no_ttsQueue_array(self):
        """ttsQueue array must be removed."""
        src = self._get_source()
        assert "this.ttsQueue" not in src

    def test_no_ttsProcessing_flag(self):
        """ttsProcessing flag must be removed."""
        src = self._get_source()
        assert "this.ttsProcessing" not in src

    def test_no_addToTTSQueue_method(self):
        """addToTTSQueue method must be removed."""
        src = self._get_source()
        assert "addToTTSQueue" not in src

    def test_no_processTTSQueue_method(self):
        """processTTSQueue method must be removed."""
        src = self._get_source()
        assert "processTTSQueue" not in src

    # -- new streaming members --

    def test_has_textBuffer(self):
        src = self._get_source()
        assert "this.textBuffer" in src

    def test_has_llmStarted(self):
        src = self._get_source()
        assert "this.llmStarted" in src

    def test_has_ttsInFlight(self):
        src = self._get_source()
        assert "this._ttsInFlight" in src

    def test_has_shouldFlush(self):
        src = self._get_source()
        assert "shouldFlush(" in src

    def test_has_sendTTS(self):
        src = self._get_source()
        assert "_sendTTS(" in src

    # -- partial STT → early LLM --

    def test_onTranscript_starts_llm_early(self):
        """onTranscript must start LLM early when partial text is long enough."""
        src = self._get_source()
        m = re.search(r'  onTranscript\s*\(.*?\)\s*\{.*?\n  \}', src, re.DOTALL)
        assert m, "onTranscript method not found"
        body = m.group(0)
        assert "this.llmStarted" in body, \
            "onTranscript must check/set llmStarted"
        assert "sendMessage" in body or "startStreaming" in body, \
            "onTranscript must start the LLM on partial text"

    def test_onSTTFinal_skips_if_llm_started(self):
        """onSTTFinal must skip LLM re-send if already started on partial."""
        src = self._get_source()
        m = re.search(r'onSTTFinal\s*\(.*?\)\s*\{.*?\n  \}', src, re.DOTALL)
        assert m, "onSTTFinal method not found"
        body = m.group(0)
        assert "this.llmStarted" in body

    # -- immediate TTS (no queue) --

    def test_onLLMToken_sends_tts_directly(self):
        """onLLMToken must send text to TTS via _sendTTS, not addToTTSQueue."""
        src = self._get_source()
        m = re.search(r'onLLMToken\s*\(.*?\)\s*\{.*?\n  \}', src, re.DOTALL)
        assert m, "onLLMToken method not found"
        body = m.group(0)
        assert "_sendTTS" in body, \
            "onLLMToken must call _sendTTS for immediate TTS"
        assert "addToTTSQueue" not in body, \
            "onLLMToken must not use the removed addToTTSQueue"

    def test_sendTTS_no_await(self):
        """_sendTTS must be fire-and-forget (no await in audio path)."""
        src = self._get_source()
        m = re.search(r'_sendTTS\s*\(.*?\)\s*\{.*?\n  \}', src, re.DOTALL)
        assert m, "_sendTTS method not found"
        body = m.group(0)
        assert "await " not in body, \
            "_sendTTS must not use await"

    def test_sendTTSHTTP_no_await_fetch(self):
        """_sendTTSHTTP must use .then() chain, not await."""
        src = self._get_source()
        m = re.search(r'  _sendTTSHTTP\s*\(text,', src)
        assert m, "_sendTTSHTTP method not found"
        start = m.start()
        body = src[start:start + 1200]
        assert "await fetch" not in body, \
            "_sendTTSHTTP must not use await fetch"
        assert ".then(" in body, \
            "_sendTTSHTTP must use .then() chain"

    # -- interrupt / reset --

    def test_interrupt_resets_audio(self):
        """interrupt() must call audioOutput.reset() or audioOutput.softReset()."""
        src = self._get_source()
        m = re.search(r'  interrupt\s*\(\s*\)\s*\{.*?\n  \}', src, re.DOTALL)
        assert m, "interrupt method not found"
        body = m.group(0)
        assert "audioOutput.reset()" in body or "audioOutput.softReset()" in body or "_cancelOngoingResponse" in body

    def test_interrupt_clears_textBuffer(self):
        """interrupt() must clear textBuffer."""
        src = self._get_source()
        m = re.search(r'  interrupt\s*\(\s*\)\s*\{.*?\n  \}', src, re.DOTALL)
        assert m
        body = m.group(0)
        assert "textBuffer" in body

    def test_interrupt_resets_llmStarted(self):
        """interrupt() must reset llmStarted."""
        src = self._get_source()
        m = re.search(r'  interrupt\s*\(\s*\)\s*\{.*?\n  \}', src, re.DOTALL)
        assert m
        body = m.group(0)
        assert "llmStarted" in body

    def test_cancelOngoingResponse_resets_audio(self):
        """_cancelOngoingResponse must call audioOutput.reset() or audioOutput.softReset()."""
        src = self._get_source()
        m = re.search(r'_cancelOngoingResponse\s*\(\s*\)\s*\{.*?\n  \}', src, re.DOTALL)
        assert m
        body = m.group(0)
        assert "audioOutput.reset()" in body or "audioOutput.softReset()" in body

    # -- startConversation --

    def test_startConversation_exists(self):
        """startConversation() method must exist."""
        src = self._get_source()
        assert "startConversation()" in src or "startConversation ()" in src

    def test_startConversation_resets_audio(self):
        """startConversation must call audioOutput.reset()."""
        src = self._get_source()
        m = re.search(r'startConversation\s*\(\s*\)\s*\{.*?\n  \}', src, re.DOTALL)
        assert m, "startConversation method not found"
        body = m.group(0)
        assert "audioOutput.reset()" in body

    def test_startConversation_clears_textBuffer(self):
        src = self._get_source()
        m = re.search(r'startConversation\s*\(\s*\)\s*\{.*?\n  \}', src, re.DOTALL)
        assert m
        body = m.group(0)
        assert "textBuffer" in body

    def test_startConversation_resets_llmStarted(self):
        src = self._get_source()
        m = re.search(r'startConversation\s*\(\s*\)\s*\{.*?\n  \}', src, re.DOTALL)
        assert m
        body = m.group(0)
        assert "llmStarted" in body

    # -- _tryCompleteResponse uses new API --

    def test_tryComplete_checks_ttsInFlight(self):
        """_tryCompleteResponse must check _ttsInFlight, not ttsQueue/ttsProcessing."""
        src = self._get_source()
        m = re.search(r'_tryCompleteResponse\s*\(\s*\)\s*\{.*?\n  \}', src, re.DOTALL)
        assert m
        body = m.group(0)
        assert "_ttsInFlight" in body
        assert "ttsQueue" not in body
        assert "ttsProcessing" not in body

    def test_tryComplete_flushes_audio(self):
        """_tryCompleteResponse must flush audio output before checking isPlaying."""
        src = self._get_source()
        m = re.search(r'_tryCompleteResponse\s*\(\s*\)\s*\{.*?\n  \}', src, re.DOTALL)
        assert m
        body = m.group(0)
        assert "audioOutput.flush()" in body

    # -- no await in audio path --

    def test_no_await_playAudioChunk(self):
        """No file in voice/ should await playAudioChunk."""
        for fname in ['voiceEngine.js', 'audioOutput.js', 'ttsClient.js']:
            src = _read_source(f"src/static/voice/{fname}")
            assert "await" not in src or "await this.playAudioChunk" not in src, \
                f"{fname} must not await playAudioChunk"

    def test_no_await_audioOutput_in_engine(self):
        """voiceEngine.js must not await audioOutput methods in the audio path."""
        src = self._get_source()
        assert "await this.audioOutput" not in src


# ---------------------------------------------------------------------------
# llmClient.js – abort alias
# ---------------------------------------------------------------------------

class TestLLMClientAbort:
    """llmClient.js must expose abort() as alias for cancel()."""

    def _get_source(self):
        return _read_source("src/static/voice/llmClient.js")

    def test_abort_method_exists(self):
        src = self._get_source()
        assert "abort()" in src or "abort ()" in src

    def test_abort_calls_cancel(self):
        src = self._get_source()
        m = re.search(r'abort\s*\(\s*\)\s*\{.*?\n\s*\}', src, re.DOTALL)
        assert m, "abort method not found"
        body = m.group(0)
        assert "this.cancel()" in body


# ---------------------------------------------------------------------------
# Follow-up fixes: shouldFlush, TTS sequencing, audio starvation,
# fast-path, backpressure, interrupt safety
# ---------------------------------------------------------------------------

class TestShouldFlushEndOfString:
    """shouldFlush must only match punctuation at end of string."""

    def _get_source(self):
        return _read_source("src/static/voice/voiceEngine.js")

    def test_shouldFlush_uses_end_anchor(self):
        """Regex must use $ anchor so punctuation mid-string doesn't trigger flush."""
        src = self._get_source()
        # Find the shouldFlush method definition (with argument)
        m = re.search(r'shouldFlush\s*\(text\)', src)
        assert m, "shouldFlush(text) method not found"
        start = m.start()
        body = src[start:start + 300]
        # Must use $ anchor in the regex: /[.!?,;:]$/
        assert "$/.test" in body or "$/." in body, \
            "shouldFlush regex must use $ anchor for end-of-string matching"

    def test_shouldFlush_includes_colon(self):
        """shouldFlush regex must include semantic boundary triggers."""
        src = self._get_source()
        m = re.search(r'shouldFlush\s*\(text\)', src)
        assert m
        start = m.start()
        body = src[start:start + 400]
        # Must include comma-space and/or conjunction-based flush triggers
        assert ",\\s" in body or "and" in body, \
            "shouldFlush must include semantic boundary triggers (comma-space, conjunctions)"


class TestTTSSequencing:
    """TTS must use sequence numbers for ordered playback."""

    def _get_source(self):
        return _read_source("src/static/voice/voiceEngine.js")

    def test_ttsSeq_field(self):
        src = self._get_source()
        assert "this.ttsSeq" in src

    def test_expectedSeq_field(self):
        src = self._get_source()
        assert "this.expectedSeq" in src

    def test_pendingAudio_field(self):
        src = self._get_source()
        assert "this.pendingAudio" in src

    def test_pendingAudio_is_map(self):
        src = self._get_source()
        assert "new Map()" in src

    def test_handleTTSAudio_method(self):
        src = self._get_source()
        assert "_handleTTSAudio(" in src

    def test_handleTTSAudio_orders_by_seq(self):
        """_handleTTSAudio must buffer and play in expectedSeq order."""
        src = self._get_source()
        # Match the method definition (with 2-space indent), not call sites
        m = re.search(r'  _handleTTSAudio\s*\(buffer,\s*seq', src)
        assert m, "_handleTTSAudio method definition not found"
        start = m.start()
        body = src[start:start + 500]
        assert "this.pendingAudio.set(" in body
        assert "this.expectedSeq" in body
        assert "this.audioOutput.enqueue" in body

    def test_sendTTS_uses_seq(self):
        """_sendTTS must assign a sequence number."""
        src = self._get_source()
        # Find _sendTTS method definition (not calls to it)
        m = re.search(r'  _sendTTS\s*\(text\)', src)
        assert m, "_sendTTS method not found"
        start = m.start()
        body = src[start:start + 800]
        assert "this.ttsSeq++" in body

    def test_sendTTSHTTP_uses_handleTTSAudio(self):
        """_sendTTSHTTP must route audio through _handleTTSAudio, not direct enqueue."""
        src = self._get_source()
        m = re.search(r'  _sendTTSHTTP\s*\(text,', src)
        assert m, "_sendTTSHTTP method not found"
        start = m.start()
        body = src[start:start + 1200]
        assert "_handleTTSAudio" in body, \
            "_sendTTSHTTP must use _handleTTSAudio for ordered playback"

    def test_cancel_resets_sequencing(self):
        """_cancelOngoingResponse must reset sequencing state."""
        src = self._get_source()
        m = re.search(r'_cancelOngoingResponse\s*\(\s*\)\s*\{.*?\n  \}', src, re.DOTALL)
        assert m
        body = m.group(0)
        assert "this.ttsSeq = 0" in body
        assert "this.expectedSeq = 0" in body
        assert "pendingAudio.clear()" in body

    def test_interrupt_resets_sequencing(self):
        """interrupt() must reset sequencing state."""
        src = self._get_source()
        m = re.search(r'  interrupt\s*\(\s*\)\s*\{.*?\n  \}', src, re.DOTALL)
        assert m
        body = m.group(0)
        assert "this.ttsSeq = 0" in body
        assert "this.expectedSeq = 0" in body
        assert "pendingAudio.clear()" in body

    def test_startConversation_resets_sequencing(self):
        """startConversation must reset sequencing state."""
        src = self._get_source()
        m = re.search(r'startConversation\s*\(\s*\)\s*\{.*?\n  \}', src, re.DOTALL)
        assert m
        body = m.group(0)
        assert "this.ttsSeq = 0" in body
        assert "this.expectedSeq = 0" in body
        assert "pendingAudio.clear()" in body


class TestAudioStarvationProtection:
    """audioOutput.js must protect against timeline gaps."""

    def _get_source(self):
        return _read_source("src/static/voice/audioOutput.js")

    def test_enqueue_gap_protection(self):
        """enqueue must push nextTime forward if it's fallen behind."""
        src = self._get_source()
        m = re.search(r'enqueue\s*\(.*?\)\s*\{.*?\n  \}', src, re.DOTALL)
        assert m, "enqueue method not found"
        body = m.group(0)
        assert "this.nextTime < this.ctx.currentTime" in body, \
            "enqueue must detect when timeline has fallen behind"
        assert "TIMELINE_GAP_OFFSET" in body, \
            "enqueue must use TIMELINE_GAP_OFFSET constant for gap protection"


class TestReducedBufferLatency:
    """audioOutput.js must use reduced buffer for lower latency."""

    def _get_source(self):
        return _read_source("src/static/voice/audioOutput.js")

    def test_minBufferSec_reduced(self):
        """minBufferSec must be 0.15 (not 0.3) for lower latency."""
        src = self._get_source()
        m = re.search(r'this\.minBufferSec\s*=\s*([\d.]+)', src)
        assert m, "minBufferSec assignment not found"
        val = float(m.group(1))
        assert val <= 0.15, \
            f"minBufferSec should be <= 0.15 for low latency, got {val}"


class TestFirstAudioFastPath:
    """audioOutput.js must start playing immediately on first audio."""

    def _get_source(self):
        return _read_source("src/static/voice/audioOutput.js")

    def test_no_buffering_wait(self):
        """enqueue must not wait for minBufferSec before starting playback."""
        src = self._get_source()
        m = re.search(r'enqueue\s*\(.*?\)\s*\{.*?\n  \}', src, re.DOTALL)
        assert m
        body = m.group(0)
        assert "this.bufferedTime < this.minBufferSec" not in body, \
            "enqueue must not delay start by waiting for minBufferSec threshold"

    def test_fast_start_offset(self):
        """First audio must set nextTime to currentTime + TIMELINE_GAP_OFFSET."""
        src = self._get_source()
        m = re.search(r'enqueue\s*\(.*?\)\s*\{.*?\n  \}', src, re.DOTALL)
        assert m
        body = m.group(0)
        assert "this.ctx.currentTime + TIMELINE_GAP_OFFSET" in body, \
            "First audio fast-path must use TIMELINE_GAP_OFFSET"


class TestTTSBackpressure:
    """_sendTTS must apply backpressure to prevent TTS flooding."""

    def _get_source(self):
        return _read_source("src/static/voice/voiceEngine.js")

    def test_tts_inflight_limit(self):
        """_sendTTS must skip if too many TTS requests are in-flight."""
        src = self._get_source()
        m = re.search(r'  _sendTTS\s*\(text\)', src)
        assert m, "_sendTTS method not found"
        start = m.start()
        body = src[start:start + 800]
        assert "this._ttsInFlight > 6" in body, \
            "_sendTTS must check _ttsInFlight > 6 for backpressure (increased concurrency)"

    def test_audio_buffer_limit(self):
        """_sendTTS must skip if too much audio is buffered."""
        src = self._get_source()
        m = re.search(r'  _sendTTS\s*\(text\)', src)
        assert m
        start = m.start()
        body = src[start:start + 800]
        assert "this.audioOutput.bufferedTime > 0.8" in body, \
            "_sendTTS must check audioOutput.bufferedTime > 0.8 for reduced audio backpressure"


class TestInterruptSafety:
    """TTS HTTP path must drop stale audio after interrupt."""

    def _get_source(self):
        return _read_source("src/static/voice/voiceEngine.js")

    def test_sendTTSHTTP_checks_requestId(self):
        """_sendTTSHTTP must check requestId against _ttsRequestId before enqueuing."""
        src = self._get_source()
        m = re.search(r'  _sendTTSHTTP\s*\(text,', src)
        assert m, "_sendTTSHTTP method not found"
        start = m.start()
        body = src[start:start + 1200]
        assert "requestId !== this._ttsRequestId" in body, \
            "_sendTTSHTTP must check requestId freshness"

    def test_sendTTS_captures_requestId(self):
        """_sendTTS must capture requestId before making TTS call."""
        src = self._get_source()
        m = re.search(r'  _sendTTS\s*\(text\)', src)
        assert m
        start = m.start()
        body = src[start:start + 800]
        assert "this._ttsRequestId" in body, \
            "_sendTTS must reference _ttsRequestId"


# ---------------------------------------------------------------------------
# Follow-up fixes (round 2): deferred TTS, safe decrement, pending timeout,
# semantic flush, prosody, early first chunk, word-count LLM, softReset
# ---------------------------------------------------------------------------

class TestDeferredTTSQueue:
    """ISSUE 1: TTS chunks must be deferred, not dropped, under backpressure."""

    def _get_source(self):
        return _read_source("src/static/voice/voiceEngine.js")

    def test_deferredTTSQueue_field(self):
        src = self._get_source()
        assert "this.deferredTTSQueue" in src

    def test_sendTTS_defers_instead_of_dropping(self):
        """_sendTTS must push to deferredTTSQueue instead of returning silently."""
        src = self._get_source()
        m = re.search(r'  _sendTTS\s*\(text\)', src)
        assert m
        start = m.start()
        body = src[start:start + 800]
        assert "deferredTTSQueue.push(" in body, \
            "_sendTTS must push deferred items instead of dropping"

    def test_drainDeferredTTS_method(self):
        """_drainDeferredTTS must exist and process deferred items."""
        src = self._get_source()
        m = re.search(r'_drainDeferredTTS\s*\(\)', src)
        assert m, "_drainDeferredTTS method must exist"
        start = m.start()
        body = src[start:start + 400]
        assert "deferredTTSQueue" in body
        assert "shift()" in body

    def test_dispatchTTS_method(self):
        """_dispatchTTS must exist as internal dispatch helper."""
        src = self._get_source()
        assert "_dispatchTTS(" in src

    def test_drain_called_after_completion(self):
        """_drainDeferredTTS must be called after TTS completion."""
        src = self._get_source()
        m = re.search(r'  _sendTTSHTTP\s*\(text,', src)
        assert m
        start = m.start()
        body = src[start:start + 1500]
        assert "_drainDeferredTTS()" in body

    def test_tryComplete_checks_deferred_queue(self):
        """_tryCompleteResponse must check deferredTTSQueue is empty."""
        src = self._get_source()
        m = re.search(r'_tryCompleteResponse\s*\(\s*\)\s*\{', src)
        assert m
        start = m.start()
        body = src[start:start + 600]
        assert "deferredTTSQueue" in body

    def test_cancel_clears_deferred_queue(self):
        """_cancelOngoingResponse must clear deferredTTSQueue."""
        src = self._get_source()
        m = re.search(r'_cancelOngoingResponse\s*\(\s*\)\s*\{', src)
        assert m
        start = m.start()
        body = src[start:start + 800]
        assert "deferredTTSQueue" in body

    def test_interrupt_clears_deferred_queue(self):
        """interrupt() must clear deferredTTSQueue."""
        src = self._get_source()
        m = re.search(r'  interrupt\s*\(\s*\)\s*\{', src)
        assert m
        start = m.start()
        body = src[start:start + 1000]
        assert "deferredTTSQueue" in body


class TestSafeTTSInFlightDecrement:
    """ISSUE 2: _ttsInFlight must use Math.max(0, ...) to prevent negative values."""

    def _get_source(self):
        return _read_source("src/static/voice/voiceEngine.js")

    def test_sendTTSHTTP_safe_decrement(self):
        src = self._get_source()
        m = re.search(r'  _sendTTSHTTP\s*\(text,', src)
        assert m
        start = m.start()
        body = src[start:start + 1500]
        assert "Math.max(0" in body, \
            "_sendTTSHTTP .finally must use Math.max(0, ...) for safe decrement"

    def test_onTTSDone_safe_decrement(self):
        src = self._get_source()
        m = re.search(r'  onTTSDone\s*\(\s*\)\s*\{', src)
        assert m
        start = m.start()
        body = src[start:start + 200]
        assert "Math.max(0" in body, \
            "onTTSDone must use Math.max(0, ...) for safe decrement"


class TestPendingAudioTimeout:
    """ISSUE 3: pendingAudio must have timeout fallback for lost seqs."""

    def _get_source(self):
        return _read_source("src/static/voice/voiceEngine.js")

    def test_handleTTSAudio_has_timeout(self):
        """_handleTTSAudio must set a timeout to skip stalled seqs."""
        src = self._get_source()
        m = re.search(r'  _handleTTSAudio\s*\(buffer,\s*seq', src)
        assert m
        start = m.start()
        body = src[start:start + 800]
        assert "setTimeout" in body, \
            "_handleTTSAudio must have a timeout fallback"

    def test_timeout_skips_ahead(self):
        """The timeout must advance expectedSeq to avoid memory leak."""
        src = self._get_source()
        m = re.search(r'  _handleTTSAudio\s*\(buffer,\s*seq', src)
        assert m
        start = m.start()
        body = src[start:start + 800]
        assert "this.expectedSeq = seq" in body


class TestSemanticFlush:
    """ISSUE 4: shouldFlush must detect semantic boundaries."""

    def _get_source(self):
        return _read_source("src/static/voice/voiceEngine.js")

    def test_shouldFlush_detects_comma(self):
        """shouldFlush must flush on comma-space pattern."""
        src = self._get_source()
        m = re.search(r'shouldFlush\s*\(text\)', src)
        assert m
        start = m.start()
        body = src[start:start + 400]
        assert r",\s" in body, \
            "shouldFlush must detect comma-space for natural pausing"

    def test_shouldFlush_detects_conjunction_and(self):
        src = self._get_source()
        m = re.search(r'shouldFlush\s*\(text\)', src)
        assert m
        start = m.start()
        body = src[start:start + 400]
        assert "and" in body

    def test_shouldFlush_detects_conjunction_but(self):
        src = self._get_source()
        m = re.search(r'shouldFlush\s*\(text\)', src)
        assert m
        start = m.start()
        body = src[start:start + 400]
        assert "but" in body


class TestProsodyGaps:
    """ISSUE 5: _scheduleBuffer must add inter-chunk gaps for natural prosody."""

    def _get_source(self):
        return _read_source("src/static/voice/audioOutput.js")

    def test_inter_chunk_gap(self):
        """_scheduleBuffer must add a small gap between chunks."""
        src = self._get_source()
        # Match the method definition (2-space indent), not call sites
        m = re.search(r'  _scheduleBuffer\s*\(audioBuffer\)', src)
        assert m, "_scheduleBuffer definition not found"
        start = m.start()
        body = src[start:start + 1800]
        assert "+ 0.03" in body, \
            "_scheduleBuffer must add 30ms inter-chunk gap"

    def test_sentence_end_pause(self):
        """_scheduleBuffer must add extra pause after sentence-ending punctuation."""
        src = self._get_source()
        m = re.search(r'  _scheduleBuffer\s*\(audioBuffer\)', src)
        assert m
        start = m.start()
        body = src[start:start + 1800]
        assert "+= 0.08" in body or "+ 0.08" in body, \
            "_scheduleBuffer must add 80ms pause after sentence end"

    def test_lastChunkText_tracked(self):
        """AudioOutput must track _lastChunkText for prosody decisions."""
        src = self._get_source()
        assert "this._lastChunkText" in src


class TestEarlyFirstChunk:
    """ISSUE 6: onLLMToken must send first TTS chunk earlier."""

    def _get_source(self):
        return _read_source("src/static/voice/voiceEngine.js")

    def test_hasSentFirstChunk_field(self):
        src = self._get_source()
        assert "this.hasSentFirstChunk" in src

    def test_early_first_chunk_in_onLLMToken(self):
        """onLLMToken must send TTS earlier for the first chunk."""
        src = self._get_source()
        m = re.search(r'onLLMToken\s*\(', src)
        assert m
        start = m.start()
        body = src[start:start + 1000]
        assert "hasSentFirstChunk" in body
        assert "_sendTTS" in body

    def test_hasSentFirstChunk_reset_on_complete(self):
        """hasSentFirstChunk must be reset when response completes."""
        src = self._get_source()
        m = re.search(r'_tryCompleteResponse\s*\(\s*\)\s*\{', src)
        assert m
        start = m.start()
        body = src[start:start + 800]
        assert "hasSentFirstChunk" in body


class TestWordCountLLMTrigger:
    """ISSUE 7: LLM early start must use word count, not char length."""

    def _get_source(self):
        return _read_source("src/static/voice/voiceEngine.js")

    def test_onTranscript_uses_word_count(self):
        """onTranscript must use word count (split) for early LLM trigger."""
        src = self._get_source()
        m = re.search(r'  onTranscript\s*\(.*?\)\s*\{', src)
        assert m
        start = m.start()
        body = src[start:start + 500]
        assert "split(" in body, \
            "onTranscript must use split for word count"
        assert "MIN_PARTIAL_WORD_COUNT" in body, \
            "onTranscript must use MIN_PARTIAL_WORD_COUNT constant"


class TestAudioContextReuse:
    """ISSUE 8: AudioOutput must support softReset to reuse AudioContext."""

    def _get_source(self):
        return _read_source("src/static/voice/audioOutput.js")

    def test_softReset_method_exists(self):
        src = self._get_source()
        assert "softReset()" in src or "softReset ()" in src

    def test_softReset_resets_timeline(self):
        """softReset must reset nextTime without closing context."""
        src = self._get_source()
        m = re.search(r'softReset\s*\(\s*\)\s*\{', src)
        assert m
        start = m.start()
        body = src[start:start + 400]
        assert "this.nextTime" in body
        assert "this.started = false" in body
        assert "this.bufferedTime = 0" in body

    def test_softReset_keeps_context(self):
        """softReset must not close the AudioContext."""
        src = self._get_source()
        m = re.search(r'softReset\s*\(\s*\)\s*\{', src)
        assert m
        start = m.start()
        body = src[start:start + 400]
        assert ".close()" not in body, \
            "softReset must not close the AudioContext"

    def test_voiceEngine_uses_softReset_for_interrupts(self):
        """VoiceEngine interrupt paths must use softReset, not reset."""
        src = _read_source("src/static/voice/voiceEngine.js")
        m = re.search(r'_cancelOngoingResponse\s*\(\s*\)\s*\{', src)
        assert m
        start = m.start()
        body = src[start:start + 200]
        assert "softReset()" in body


# ---------------------------------------------------------------------------
# Latency Upgrades
# ---------------------------------------------------------------------------

class TestIncreasedTTSConcurrency:
    """TTS concurrency limit must be raised to 6 for parallel TTS prefetch."""

    def _get_source(self):
        return _read_source("src/static/voice/voiceEngine.js")

    def test_inflight_limit_is_6(self):
        """_sendTTS backpressure must use _ttsInFlight > 6."""
        src = self._get_source()
        m = re.search(r'  _sendTTS\s*\(text\)', src)
        assert m
        start = m.start()
        body = src[start:start + 800]
        assert "this._ttsInFlight > 6" in body, \
            "TTS concurrency limit must be 6 for parallel prefetch"

    def test_buffered_time_limit_reduced(self):
        """_sendTTS must use bufferedTime > 0.8 (reduced from 2.0)."""
        src = self._get_source()
        m = re.search(r'  _sendTTS\s*\(text\)', src)
        assert m
        start = m.start()
        body = src[start:start + 800]
        assert "this.audioOutput.bufferedTime > 0.8" in body, \
            "Buffered time backpressure must be 0.8 for reduced lag"


class TestEarlierFirstChunkTrigger:
    """First TTS chunk trigger must fire at 5 chars (reduced from 10)."""

    def _get_source(self):
        return _read_source("src/static/voice/voiceEngine.js")

    def test_first_chunk_threshold_is_5(self):
        """onLLMToken must trigger first chunk at > 5 chars."""
        src = self._get_source()
        m = re.search(r'onLLMToken\s*\(', src)
        assert m
        start = m.start()
        body = src[start:start + 1000]
        assert "this.textBuffer.length > 5" in body, \
            "First chunk threshold must be 5 chars for predictive start"


class TestPhraseLevelFlush:
    """onLLMToken must flush on word boundary for speech-rhythm chunking."""

    def _get_source(self):
        return _read_source("src/static/voice/voiceEngine.js")

    def test_phrase_flush_on_word_boundary(self):
        """onLLMToken must check token.endsWith(' ') for phrase-level flush."""
        src = self._get_source()
        m = re.search(r'onLLMToken\s*\(', src)
        assert m
        start = m.start()
        body = src[start:start + 1200]
        assert "token.endsWith(' ')" in body, \
            "Must flush on word boundary (token ending with space)"

    def test_phrase_flush_min_length(self):
        """Phrase-level flush requires textBuffer.length > 8."""
        src = self._get_source()
        m = re.search(r'onLLMToken\s*\(', src)
        assert m
        start = m.start()
        body = src[start:start + 1200]
        assert "this.textBuffer.length > 8" in body, \
            "Phrase flush must require at least 8 chars"

    def test_phrase_flush_sends_tts(self):
        """Phrase-level flush must call _sendTTS with flushText."""
        src = self._get_source()
        m = re.search(r'onLLMToken\s*\(', src)
        assert m
        start = m.start()
        body = src[start:start + 1400]
        # After phrase-level flush check, buffer is flushed via _sendTTS
        assert "token.endsWith(' ')" in body
        assert "_sendTTS(flushText)" in body


class TestPendingAudioDestructuring:
    """_handleTTSAudio must store and destructure { buffer, text } properly."""

    def _get_source(self):
        return _read_source("src/static/voice/voiceEngine.js")

    def test_stores_object_with_buffer_and_text(self):
        """pendingAudio.set must store { buffer, text } object."""
        src = self._get_source()
        m = re.search(r'  _handleTTSAudio\s*\(buffer', src)
        assert m, "_handleTTSAudio method definition not found"
        start = m.start()
        body = src[start:start + 600]
        assert "pendingAudio.set(seq, { buffer, text })" in body or \
               "pendingAudio.set(seq, {buffer, text})" in body, \
            "_handleTTSAudio must store { buffer, text } in pendingAudio"

    def test_enqueue_uses_entry_buffer(self):
        """audioOutput.enqueue must receive entry.buffer, not raw entry."""
        src = self._get_source()
        m = re.search(r'  _handleTTSAudio\s*\(buffer', src)
        assert m, "_handleTTSAudio method definition not found"
        start = m.start()
        body = src[start:start + 600]
        assert "this.audioOutput.enqueue(entry.buffer" in body, \
            "Must destructure entry.buffer for enqueue, not pass raw entry"
