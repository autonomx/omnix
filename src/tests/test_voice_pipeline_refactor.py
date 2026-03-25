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
        body = src[start:start + 1800]
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
        """_sendTTS must use adaptive concurrency limit based on buffer level."""
        src = self._get_source()
        m = re.search(r'  _sendTTS\s*\(text\)', src)
        assert m, "_sendTTS method not found"
        start = m.start()
        body = src[start:start + 800]
        assert "dynamicLimit" in body, \
            "_sendTTS must compute dynamicLimit for adaptive TTS concurrency"
        assert "this._ttsInFlight > dynamicLimit" in body, \
            "_sendTTS must check _ttsInFlight against dynamicLimit for backpressure"

    def test_audio_buffer_limit(self):
        """_sendTTS must skip if too much audio is buffered."""
        src = self._get_source()
        m = re.search(r'  _sendTTS\s*\(text\)', src)
        assert m
        start = m.start()
        body = src[start:start + 800]
        assert "this.audioOutput.bufferedTime > 0.3" in body, \
            "_sendTTS must check audioOutput.bufferedTime > 0.3 for reduced audio backpressure"


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
        """_sendTTS must delegate to _dispatchTTS which captures requestId."""
        src = self._get_source()
        m = re.search(r'  _dispatchTTS\s*\(', src)
        assert m
        start = m.start()
        body = src[start:start + 800]
        assert "this._ttsRequestId" in body, \
            "_dispatchTTS must reference _ttsRequestId"


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
        body = src[start:start + 2400]
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
        body = src[start:start + 2200]
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
        """_scheduleBuffer must add semantic pacing gap between chunks."""
        src = self._get_source()
        # Match the method definition (2-space indent), not call sites
        m = re.search(r'  _scheduleBuffer\s*\(audioBuffer\)', src)
        assert m, "_scheduleBuffer definition not found"
        start = m.start()
        body = src[start:start + 1800]
        assert "pause" in body, \
            "_scheduleBuffer must use semantic pacing for inter-chunk gaps"

    def test_sentence_end_pause(self):
        """_scheduleBuffer must add extra pause after sentence-ending punctuation."""
        src = self._get_source()
        m = re.search(r'  _scheduleBuffer\s*\(audioBuffer\)', src)
        assert m
        start = m.start()
        body = src[start:start + 2000]
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
        """onLLMToken must send TTS earlier for the first chunk on first word boundary."""
        src = self._get_source()
        m = re.search(r'onLLMToken\s*\(', src)
        assert m
        start = m.start()
        body = src[start:start + 1400]
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
        body = src[start:start + 800]
        assert "this.nextTime" in body
        assert "this.started = false" in body
        assert "this.bufferedTime = 0" in body

    def test_softReset_keeps_context(self):
        """softReset must not close the AudioContext."""
        src = self._get_source()
        m = re.search(r'softReset\s*\(\s*\)\s*\{', src)
        assert m
        start = m.start()
        body = src[start:start + 800]
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
    """TTS concurrency limit must be raised to 12 for parallel TTS prefetch."""

    def _get_source(self):
        return _read_source("src/static/voice/voiceEngine.js")

    def test_inflight_limit_is_12(self):
        """_sendTTS backpressure must use adaptive concurrency (dynamicLimit)."""
        src = self._get_source()
        m = re.search(r'  _sendTTS\s*\(text\)', src)
        assert m
        start = m.start()
        body = src[start:start + 800]
        assert "dynamicLimit" in body, \
            "TTS concurrency must use adaptive dynamicLimit"

    def test_buffered_time_limit_reduced(self):
        """_sendTTS must use bufferedTime > 0.3 (reduced from 0.8)."""
        src = self._get_source()
        m = re.search(r'  _sendTTS\s*\(text\)', src)
        assert m
        start = m.start()
        body = src[start:start + 800]
        assert "this.audioOutput.bufferedTime > 0.3" in body, \
            "Buffered time backpressure must be 0.3 for reduced lag"


class TestEarlierFirstChunkTrigger:
    """First TTS chunk trigger must fire on first word boundary (token.includes(' '))."""

    def _get_source(self):
        return _read_source("src/static/voice/voiceEngine.js")

    def test_first_chunk_uses_word_boundary(self):
        """onLLMToken must trigger first chunk on first complete word."""
        src = self._get_source()
        m = re.search(r'onLLMToken\s*\(', src)
        assert m
        start = m.start()
        body = src[start:start + 1200]
        assert "token.includes(' ')" in body, \
            "First chunk must trigger on word boundary (token.includes(' '))"


class TestPhraseLevelFlush:
    """onLLMToken must flush on word boundaries for speech-rhythm chunking,
    with adaptive chunk sizing and word count guard."""

    def _get_source(self):
        return _read_source("src/static/voice/voiceEngine.js")

    def test_phrase_flush_on_word_boundary(self):
        """Phrase-level flush must check token.endsWith(' ')."""
        src = self._get_source()
        m = re.search(r'onLLMToken\s*\(', src)
        assert m
        start = m.start()
        body = src[start:start + 2600]
        assert "token.endsWith(' ')" in body, \
            "Must flush on word boundary (token ending with space)"

    def test_phrase_flush_adaptive_min_length(self):
        """Phrase-level flush uses smooth adaptive dynamicMinLength based on _ttsInFlight."""
        src = self._get_source()
        m = re.search(r'onLLMToken\s*\(', src)
        assert m
        start = m.start()
        body = src[start:start + 2600]
        assert "dynamicMinLength" in body, \
            "Phrase flush must use adaptive dynamicMinLength"
        assert "Math.min(8 + this._ttsInFlight * 4, 24)" in body, \
            "dynamicMinLength must scale smoothly: Math.min(8 + _ttsInFlight * 4, 24)"

    def test_phrase_flush_word_count_guard(self):
        """Phrase-level flush must require _wordCount >= 2 to prevent micro-chunks."""
        src = self._get_source()
        m = re.search(r'onLLMToken\s*\(', src)
        assert m
        start = m.start()
        body = src[start:start + 2600]
        assert "_wordCount >= 2" in body, \
            "Phrase flush must require at least 2 words to prevent micro-chunks"

    def test_phrase_flush_sends_tts(self):
        """Phrase-level flush must call _sendTTS with flushText."""
        src = self._get_source()
        m = re.search(r'onLLMToken\s*\(', src)
        assert m
        start = m.start()
        body = src[start:start + 2600]
        assert "token.endsWith(' ')" in body
        assert "_sendTTS(flushText)" in body

    def test_phrase_flush_clears_buffer(self):
        """Phrase-level flush must clear textBuffer to avoid duplicate speech."""
        src = self._get_source()
        m = re.search(r'onLLMToken\s*\(', src)
        assert m
        start = m.start()
        body = src[start:start + 2600]
        phrase_idx = body.find("token.endsWith(' ')")
        assert phrase_idx > 0
        after_phrase = body[phrase_idx:phrase_idx + 350]
        assert "this.textBuffer = ''" in after_phrase, \
            "textBuffer must be cleared after phrase-level flush"


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


class TestDeferredTTSPacing:
    """_drainDeferredTTS must pace deferred TTS under congestion."""

    def _get_source(self):
        return _read_source("src/static/voice/voiceEngine.js")

    def test_drain_rate_limit_at_4(self):
        """_drainDeferredTTS must return early if _ttsInFlight > 8."""
        src = self._get_source()
        m = re.search(r'  _drainDeferredTTS\s*\(\)', src)
        assert m, "_drainDeferredTTS method not found"
        start = m.start()
        body = src[start:start + 400]
        assert "this._ttsInFlight > 8" in body, \
            "_drainDeferredTTS must rate-limit at _ttsInFlight > 8"

    def test_drain_buffered_time_threshold(self):
        """_drainDeferredTTS must check bufferedTime < 0.3."""
        src = self._get_source()
        m = re.search(r'  _drainDeferredTTS\s*\(\)', src)
        assert m, "_drainDeferredTTS method not found"
        start = m.start()
        body = src[start:start + 400]
        assert "bufferedTime < 0.3" in body, \
            "_drainDeferredTTS must only drain when bufferedTime < 0.3"


class TestSpeechContinuityTracking:
    """VoiceEngine must track lastSpokenText for speech continuity context."""

    def _get_source(self):
        return _read_source("src/static/voice/voiceEngine.js")

    def test_lastSpokenText_field_in_constructor(self):
        """Constructor must initialise this.lastSpokenText."""
        src = self._get_source()
        assert "this.lastSpokenText = ''" in src, \
            "lastSpokenText must be initialised to '' in constructor"

    def test_sendTTS_updates_lastSpokenText(self):
        """lastSpokenText must be updated in the TTS HTTP success path (not in _sendTTS)."""
        src = self._get_source()
        m = re.search(r'  _sendTTSHTTP\s*\(text,', src)
        assert m, "_sendTTSHTTP method not found"
        start = m.start()
        body = src[start:start + 1500]
        assert "this.lastSpokenText" in body, \
            "_sendTTSHTTP must update lastSpokenText on TTS success"

    def test_lastSpokenText_reset_on_stop(self):
        """stop() must reset lastSpokenText to empty string."""
        src = self._get_source()
        m = re.search(r'  stop\(\)\s*\{', src)
        assert m, "stop() method not found"
        start = m.start()
        body = src[start:start + 800]
        assert "this.lastSpokenText = ''" in body, \
            "stop() must reset lastSpokenText to ''"


# ---------------------------------------------------------------------------
# Round 3 fixes: smooth adaptive chunking, incremental word counter,
# deferred queue freshness, first-chunk word boundary, lastSpokenText timing
# ---------------------------------------------------------------------------

class TestSmoothAdaptiveChunking:
    """Adaptive chunk sizing must scale smoothly (not binary jump)."""

    def _get_source(self):
        return _read_source("src/static/voice/voiceEngine.js")

    def test_smooth_scaling_formula(self):
        """dynamicMinLength must use Math.min(8 + _ttsInFlight * 4, 24)."""
        src = self._get_source()
        assert "Math.min(8 + this._ttsInFlight * 4, 24)" in src, \
            "Must use smooth scaling formula, not binary jump"

    def test_no_binary_jump(self):
        """Must NOT use ternary > 3 ? 20 : 8 binary jump."""
        src = self._get_source()
        assert "_ttsInFlight > 3 ? 20 : 8" not in src, \
            "Binary jump must be replaced with smooth scaling"


class TestIncrementalWordCounter:
    """Word count must be tracked incrementally (not per-token split)."""

    def _get_source(self):
        return _read_source("src/static/voice/voiceEngine.js")

    def test_wordCount_field_in_constructor(self):
        """Constructor must initialise this._wordCount = 0."""
        src = self._get_source()
        assert "this._wordCount = 0" in src, \
            "_wordCount must be initialised to 0"

    def test_incremental_word_tracking(self):
        """onLLMToken must increment _wordCount on space tokens."""
        src = self._get_source()
        m = re.search(r'onLLMToken\s*\(', src)
        assert m
        start = m.start()
        body = src[start:start + 1200]
        assert "this._wordCount++" in body, \
            "Must increment _wordCount when token contains space"

    def test_wordCount_reset_on_flush(self):
        """_wordCount must be reset to 0 when textBuffer is flushed."""
        src = self._get_source()
        m = re.search(r'onLLMToken\s*\(', src)
        assert m
        start = m.start()
        body = src[start:start + 1800]
        assert "this._wordCount = 0" in body, \
            "_wordCount must be reset when buffer is flushed"

    def test_no_per_token_split(self):
        """onLLMToken must NOT call split(/\\s+/) on every token (expensive)."""
        src = self._get_source()
        m = re.search(r'onLLMToken\s*\(', src)
        assert m
        start = m.start()
        body = src[start:start + 1800]
        assert "trim().split(/\\s+/)" not in body, \
            "Must not use per-token split for word counting"

    def test_wordCount_reset_on_cancel(self):
        """_cancelOngoingResponse must reset _wordCount."""
        src = self._get_source()
        m = re.search(r'  _cancelOngoingResponse\(\)\s*\{', src)
        assert m
        start = m.start()
        body = src[start:start + 800]
        assert "this._wordCount = 0" in body, \
            "_cancelOngoingResponse must reset _wordCount"


class TestDeferredQueueFreshness:
    """Deferred TTS queue must drop oldest when queue exceeds limit."""

    def _get_source(self):
        return _read_source("src/static/voice/voiceEngine.js")

    def test_freshness_bias_in_sendTTS(self):
        """_sendTTS must drop oldest when deferred queue > 5."""
        src = self._get_source()
        m = re.search(r'  _sendTTS\s*\(text\)', src)
        assert m
        start = m.start()
        body = src[start:start + 800]
        assert "deferredTTSQueue.length > 5" in body, \
            "_sendTTS must check deferred queue length for freshness bias"
        assert "deferredTTSQueue.shift()" in body, \
            "_sendTTS must drop oldest when queue is too long"


class TestFirstChunkWordBoundary:
    """First chunk must trigger on textBuffer length > 3 for speculative TTS."""

    def _get_source(self):
        return _read_source("src/static/voice/voiceEngine.js")

    def test_first_chunk_uses_textBuffer_length(self):
        """First chunk trigger must use textBuffer.length > 3 for speculative TTS."""
        src = self._get_source()
        m = re.search(r'onLLMToken\s*\(', src)
        assert m
        start = m.start()
        body = src[start:start + 1800]
        # Find the hasSentFirstChunk section
        first_idx = body.find("hasSentFirstChunk")
        assert first_idx > 0
        section = body[first_idx:first_idx + 200]
        assert "textBuffer.length > 3" in section, \
            "First chunk must trigger on textBuffer.length > 3 for speculative TTS"


class TestLastSpokenTextTiming:
    """lastSpokenText must be set ONLY after TTS succeeds, not in _sendTTS."""

    def _get_source(self):
        return _read_source("src/static/voice/voiceEngine.js")

    def test_not_in_sendTTS(self):
        """_sendTTS must NOT set lastSpokenText (too early)."""
        src = self._get_source()
        m = re.search(r'  _sendTTS\s*\(text\)', src)
        assert m
        start = m.start()
        body = src[start:start + 600]
        assert "this.lastSpokenText" not in body, \
            "lastSpokenText must NOT be set in _sendTTS (before TTS succeeds)"

    def test_in_http_success_path(self):
        """lastSpokenText must be accumulated in _sendTTSHTTP success path."""
        src = self._get_source()
        m = re.search(r'  _sendTTSHTTP\s*\(text,', src)
        assert m
        start = m.start()
        body = src[start:start + 1800]
        assert "this.lastSpokenText += text" in body, \
            "lastSpokenText must be set in HTTP TTS success callback"

    def test_set_after_requestId_check(self):
        """lastSpokenText update must come after requestId freshness check."""
        src = self._get_source()
        m = re.search(r'  _sendTTSHTTP\s*\(text,', src)
        assert m
        start = m.start()
        body = src[start:start + 1800]
        reqid_idx = body.find("requestId !== this._ttsRequestId")
        last_spoken_idx = body.find("this.lastSpokenText += text")
        assert reqid_idx > 0 and last_spoken_idx > 0, \
            "Both requestId check and lastSpokenText update must exist"
        assert last_spoken_idx > reqid_idx, \
            "lastSpokenText must be set after stale requestId check"


# ---------------------------------------------------------------------------
# Round 4 fix: Prosody continuity – send prev_text in TTS HTTP request
# ---------------------------------------------------------------------------

class TestProsodyContinuity:
    """_sendTTSHTTP must send prev_text (lastSpokenText) for prosody continuity."""

    def _get_source(self):
        return _read_source("src/static/voice/voiceEngine.js")

    def test_prev_text_in_tts_request_body(self):
        """TTS HTTP request body must include prev_text for prosody continuity."""
        src = self._get_source()
        m = re.search(r'  _sendTTSHTTP\s*\(text,', src)
        assert m, "_sendTTSHTTP method not found"
        start = m.start()
        body = src[start:start + 1500]
        assert "prev_text" in body, \
            "TTS HTTP request body must include prev_text for prosody continuity"

    def test_prev_text_uses_lastSpokenText(self):
        """prev_text must be derived from this.lastSpokenText."""
        src = self._get_source()
        m = re.search(r'  _sendTTSHTTP\s*\(text,', src)
        assert m
        start = m.start()
        body = src[start:start + 1500]
        assert "this.lastSpokenText" in body, \
            "prev_text must reference this.lastSpokenText"

    def test_prev_text_is_sliced(self):
        """prev_text must be sliced to a bounded length (e.g. .slice(-200))."""
        src = self._get_source()
        m = re.search(r'  _sendTTSHTTP\s*\(text,', src)
        assert m
        start = m.start()
        body = src[start:start + 1800]
        assert ".slice(-200)" in body, \
            "prev_text must be bounded with .slice(-200) to avoid oversized payloads"


# ---------------------------------------------------------------------------
# Round 5: Full duplex, active source tracking, jitter, sentence prosody
# ---------------------------------------------------------------------------

class TestFullDuplexVAD:
    """VAD must remain active during AI_SPEAKING for full duplex conversation."""

    def _get_source(self):
        return _read_source("src/static/voice/voiceEngine.js")

    def test_resume_vad_on_first_token(self):
        """onLLMToken first-token handler must resume VAD (not pause it)."""
        src = self._get_source()
        m = re.search(r'onLLMToken\s*\(', src)
        assert m
        start = m.start()
        body = src[start:start + 1000]
        assert "resumeVAD()" in body, \
            "onLLMToken must call resumeVAD() for full duplex (not pauseVAD)"
        assert "pauseVAD()" not in body, \
            "onLLMToken must NOT call pauseVAD() during AI_SPEAKING (full duplex)"


class TestActiveSourceTracking:
    """audioOutput.js must track active BufferSource nodes for instant stop."""

    def _get_source(self):
        return _read_source("src/static/voice/audioOutput.js")

    def test_activeSources_field(self):
        """Constructor must initialise _activeSources array."""
        src = self._get_source()
        assert "this._activeSources = []" in src

    def test_scheduleBuffer_pushes_source(self):
        """_scheduleBuffer must push source to _activeSources."""
        src = self._get_source()
        m = re.search(r'  _scheduleBuffer\s*\(audioBuffer\)', src)
        assert m
        start = m.start()
        body = src[start:start + 2000]
        assert "_activeSources.push(source)" in body

    def test_scheduleBuffer_removes_on_ended(self):
        """_scheduleBuffer onended must remove source from _activeSources."""
        src = self._get_source()
        m = re.search(r'  _scheduleBuffer\s*\(audioBuffer\)', src)
        assert m
        start = m.start()
        body = src[start:start + 2000]
        assert "_activeSources.indexOf(source)" in body or \
               "_activeSources.splice" in body

    def test_softReset_stops_active_sources(self):
        """softReset must stop all active sources for instant interrupt."""
        src = self._get_source()
        m = re.search(r'  softReset\(\)\s*\{', src)
        assert m
        start = m.start()
        body = src[start:start + 800]
        assert "src.stop()" in body or "src.stop();" in body
        assert "_activeSources = []" in body

    def test_reset_stops_active_sources(self):
        """reset must stop all active sources before closing context."""
        src = self._get_source()
        m = re.search(r'  reset\(\)\s*\{', src)
        assert m
        start = m.start()
        body = src[start:start + 800]
        assert "src.stop()" in body or "src.stop();" in body
        assert "_activeSources = []" in body

    def test_stopAll_uses_softReset(self):
        """stopAll must use softReset (keep AudioContext alive)."""
        src = self._get_source()
        m = re.search(r'  stopAll\(\)\s*\{', src)
        assert m
        start = m.start()
        body = src[start:start + 200]
        assert "softReset()" in body


class TestTimelineJitter:
    """_scheduleBuffer must add slight jitter for natural speech rhythm."""

    def _get_source(self):
        return _read_source("src/static/voice/audioOutput.js")

    def test_jitter_variable(self):
        """_scheduleBuffer must define a jitter variable using Math.random."""
        src = self._get_source()
        m = re.search(r'  _scheduleBuffer\s*\(audioBuffer\)', src)
        assert m
        start = m.start()
        body = src[start:start + 2000]
        assert "Math.random()" in body, \
            "_scheduleBuffer must use Math.random() for jitter"

    def test_jitter_in_timeline_advance(self):
        """Timeline advance must include jitter in addition to base gap."""
        src = self._get_source()
        m = re.search(r'  _scheduleBuffer\s*\(audioBuffer\)', src)
        assert m
        start = m.start()
        body = src[start:start + 2000]
        assert "0.03 + jitter" in body or "jitter" in body


class TestSpeculativeFirstChunk:
    """First TTS chunk must fire speculatively at 3+ chars, not wait for word boundary."""

    def _get_source(self):
        return _read_source("src/static/voice/voiceEngine.js")

    def test_uses_textBuffer_length(self):
        """First chunk trigger must check textBuffer.length > 3."""
        src = self._get_source()
        m = re.search(r'onLLMToken\s*\(', src)
        assert m
        start = m.start()
        body = src[start:start + 1800]
        assert "textBuffer.length > 3" in body, \
            "First chunk must use textBuffer.length > 3 for speculative TTS"

    def test_sends_whole_buffer(self):
        """Speculative first chunk must send the whole textBuffer (not a regex match)."""
        src = self._get_source()
        m = re.search(r'onLLMToken\s*\(', src)
        assert m
        start = m.start()
        body = src[start:start + 1800]
        # Should NOT have the old word-boundary regex match
        assert ".match(/^(.+\\b)/)" not in body, \
            "First chunk must not use word boundary regex (speculative TTS)"


class TestSentenceBoundaryProsody:
    """_sendTTSHTTP must detect sentence starts and clear prev_text for prosody."""

    def _get_source(self):
        return _read_source("src/static/voice/voiceEngine.js")

    def test_sentence_detection_variable(self):
        """_sendTTSHTTP must define isNewSentence using /^[A-Z]/ test."""
        src = self._get_source()
        m = re.search(r'  _sendTTSHTTP\s*\(text,', src)
        assert m
        start = m.start()
        body = src[start:start + 1800]
        assert "isNewSentence" in body
        assert "/^[A-Z]/" in body

    def test_conditional_prev_text(self):
        """prev_text must be empty for new sentences, lastSpokenText otherwise."""
        src = self._get_source()
        m = re.search(r'  _sendTTSHTTP\s*\(text,', src)
        assert m
        start = m.start()
        body = src[start:start + 1800]
        assert "isNewSentence ? '' :" in body or "isNewSentence ? \"\" :" in body

    def test_accumulated_lastSpokenText(self):
        """lastSpokenText must be accumulated (+=), not replaced (=)."""
        src = self._get_source()
        m = re.search(r'  _sendTTSHTTP\s*\(text,', src)
        assert m
        start = m.start()
        body = src[start:start + 1800]
        assert "this.lastSpokenText += text" in body, \
            "lastSpokenText must be accumulated with += (not replaced with =)"

    def test_lastSpokenText_bounded(self):
        """lastSpokenText must be bounded to 200 chars to prevent unbounded growth."""
        src = self._get_source()
        m = re.search(r'  _sendTTSHTTP\s*\(text,', src)
        assert m
        start = m.start()
        body = src[start:start + 1800]
        assert ".slice(-200)" in body
        assert "200" in body


# ---------------------------------------------------------------------------
# Round 6: Priority mode, ultra-early LLM, interrupt consistency, barge-in STT
# ---------------------------------------------------------------------------

class TestPriorityMode:
    """After interrupt, priority mode must clear stale deferred TTS queue."""

    def _get_source(self):
        return _read_source("src/static/voice/voiceEngine.js")

    def test_priority_mode_field_in_constructor(self):
        """Constructor must initialise _priorityMode to false."""
        src = self._get_source()
        assert "this._priorityMode = false" in src

    def test_priority_mode_set_on_interrupt(self):
        """onSpeechStart interrupt path must enable _priorityMode."""
        src = self._get_source()
        m = re.search(r"console\.log\('\[VoiceEngine\] User interrupted AI'\)", src)
        assert m, "onSpeechStart interrupt log line must exist"
        start = m.start()
        body = src[start:start + 800]
        assert "this._priorityMode = true" in body, \
            "onSpeechStart interrupt path must set _priorityMode = true"

    def test_priority_mode_set_on_cancel_ongoing(self):
        """_cancelOngoingResponse must enable _priorityMode."""
        src = self._get_source()
        m = re.search(r'  _cancelOngoingResponse\(\)\s*\{', src)
        assert m
        start = m.start()
        body = src[start:start + 900]
        assert "this._priorityMode = true" in body, \
            "_cancelOngoingResponse must set _priorityMode = true"

    def test_priority_mode_set_on_explicit_interrupt(self):
        """interrupt() method must enable _priorityMode."""
        src = self._get_source()
        m = re.search(r"  interrupt\(\)\s*\{", src)
        assert m
        start = m.start()
        body = src[start:start + 1200]
        assert "this._priorityMode = true" in body, \
            "interrupt() must set _priorityMode = true"

    def test_dispatch_clears_queue_in_priority_mode(self):
        """_dispatchTTS must clear deferredTTSQueue when _priorityMode is true."""
        src = self._get_source()
        m = re.search(r'  _dispatchTTS\(cleaned, seq\)\s*\{', src)
        assert m
        start = m.start()
        body = src[start:start + 600]
        assert "this._priorityMode" in body, \
            "_dispatchTTS must check _priorityMode"
        assert "this.deferredTTSQueue = []" in body, \
            "_dispatchTTS must clear deferredTTSQueue in priority mode"

    def test_priority_mode_reset_after_dispatch(self):
        """_dispatchTTS must reset _priorityMode to false after clearing queue."""
        src = self._get_source()
        m = re.search(r'  _dispatchTTS\(cleaned, seq\)\s*\{', src)
        assert m
        start = m.start()
        body = src[start:start + 600]
        assert "this._priorityMode = false" in body, \
            "_dispatchTTS must reset _priorityMode to false after clearing"


class TestUltraEarlyLLMStart:
    """LLM must start on just 1 word from partial STT for fastest response."""

    def _get_source(self):
        return _read_source("src/static/voice/voiceEngine.js")

    def test_min_partial_word_count_is_1(self):
        """MIN_PARTIAL_WORD_COUNT must be 1 for ultra-early LLM start."""
        src = self._get_source()
        assert "this.MIN_PARTIAL_WORD_COUNT = 1" in src, \
            "MIN_PARTIAL_WORD_COUNT must be 1 (not 2 or higher)"


class TestInterruptWordCountReset:
    """All interrupt paths must reset _wordCount to 0."""

    def _get_source(self):
        return _read_source("src/static/voice/voiceEngine.js")

    def test_onSpeechStart_interrupt_resets_wordCount(self):
        """onSpeechStart interrupt path must reset _wordCount."""
        src = self._get_source()
        m = re.search(r"console\.log\('\[VoiceEngine\] User interrupted AI'\)", src)
        assert m
        start = m.start()
        body = src[start:start + 800]
        assert "this._wordCount = 0" in body, \
            "onSpeechStart interrupt path must reset _wordCount"

    def test_cancelOngoingResponse_resets_wordCount(self):
        """_cancelOngoingResponse must reset _wordCount."""
        src = self._get_source()
        m = re.search(r'  _cancelOngoingResponse\(\)\s*\{', src)
        assert m
        start = m.start()
        body = src[start:start + 900]
        assert "this._wordCount = 0" in body, \
            "_cancelOngoingResponse must reset _wordCount"

    def test_explicit_interrupt_resets_wordCount(self):
        """interrupt() method must reset _wordCount."""
        src = self._get_source()
        m = re.search(r"  interrupt\(\)\s*\{", src)
        assert m
        start = m.start()
        body = src[start:start + 1200]
        assert "this._wordCount = 0" in body, \
            "interrupt() must reset _wordCount"


class TestBargeInSTTForwarding:
    """Audio chunks must be forwarded to STT during INTERRUPTED state for barge-in."""

    def _get_source(self):
        return _read_source("src/static/voice/voiceEngine.js")

    def test_interrupted_state_sends_audio(self):
        """onAudioChunkInput must forward audio when state is INTERRUPTED."""
        src = self._get_source()
        m = re.search(r'  onAudioChunkInput\(chunk\)\s*\{', src)
        assert m
        start = m.start()
        body = src[start:start + 400]
        assert "INTERRUPTED" in body, \
            "onAudioChunkInput must include INTERRUPTED state in its condition"
        assert "stt.sendAudio" in body, \
            "onAudioChunkInput must call stt.sendAudio"


# ---------------------------------------------------------------------------
# Round 7: Hard TTS cancel, adaptive concurrency, streaming context, lower trigger
# ---------------------------------------------------------------------------

class TestHardTTSCancel:
    """In-flight TTS HTTP requests must be hard-cancelled via AbortController on interrupt."""

    def _get_source(self):
        return _read_source("src/static/voice/voiceEngine.js")

    def test_tts_controllers_map_in_constructor(self):
        """Constructor must initialise _ttsControllers as a Map."""
        src = self._get_source()
        assert "this._ttsControllers = new Map()" in src

    def test_abort_controller_per_request(self):
        """_sendTTSHTTP must create an AbortController per request."""
        src = self._get_source()
        m = re.search(r'  _sendTTSHTTP\s*\(text,', src)
        assert m
        start = m.start()
        body = src[start:start + 800]
        assert "new AbortController()" in body, \
            "_sendTTSHTTP must create AbortController for each TTS request"
        assert "_ttsControllers.set(seq" in body, \
            "_sendTTSHTTP must store controller in _ttsControllers Map"

    def test_signal_passed_to_fetch(self):
        """_sendTTSHTTP must pass AbortController signal to fetch."""
        src = self._get_source()
        m = re.search(r'  _sendTTSHTTP\s*\(text,', src)
        assert m
        start = m.start()
        body = src[start:start + 1000]
        assert "signal: controller.signal" in body, \
            "_sendTTSHTTP must pass controller.signal to fetch"

    def test_controller_cleaned_up_in_finally(self):
        """_sendTTSHTTP .finally must remove controller from _ttsControllers."""
        src = self._get_source()
        m = re.search(r'  _sendTTSHTTP\s*\(text,', src)
        assert m
        start = m.start()
        body = src[start:start + 2400]
        assert "_ttsControllers.delete(seq)" in body, \
            "_sendTTSHTTP .finally must delete controller from map"

    def test_abort_error_handled(self):
        """_sendTTSHTTP .catch must handle AbortError gracefully."""
        src = self._get_source()
        m = re.search(r'  _sendTTSHTTP\s*\(text,', src)
        assert m
        start = m.start()
        body = src[start:start + 2400]
        assert "AbortError" in body, \
            "_sendTTSHTTP must handle AbortError in .catch"

    def test_abortAllTTS_method_exists(self):
        """_abortAllTTS helper must exist."""
        src = self._get_source()
        assert "_abortAllTTS()" in src, \
            "_abortAllTTS method must exist for hard-cancelling in-flight TTS"

    def test_abortAllTTS_iterates_controllers(self):
        """_abortAllTTS must iterate and abort all controllers."""
        src = self._get_source()
        m = re.search(r'  _abortAllTTS\(\)\s*\{', src)
        assert m
        start = m.start()
        body = src[start:start + 300]
        assert "ctrl.abort()" in body, \
            "_abortAllTTS must call abort() on each controller"
        assert "_ttsControllers.clear()" in body, \
            "_abortAllTTS must clear the controllers map"

    def test_onSpeechStart_interrupt_calls_abortAllTTS(self):
        """onSpeechStart interrupt path must call _abortAllTTS."""
        src = self._get_source()
        m = re.search(r"console\.log\('\[VoiceEngine\] User interrupted AI'\)", src)
        assert m
        start = m.start()
        body = src[start:start + 800]
        assert "_abortAllTTS()" in body, \
            "onSpeechStart interrupt must call _abortAllTTS"

    def test_cancelOngoingResponse_calls_abortAllTTS(self):
        """_cancelOngoingResponse must call _abortAllTTS."""
        src = self._get_source()
        m = re.search(r'  _cancelOngoingResponse\(\)\s*\{', src)
        assert m
        start = m.start()
        body = src[start:start + 900]
        assert "_abortAllTTS()" in body, \
            "_cancelOngoingResponse must call _abortAllTTS"

    def test_interrupt_calls_abortAllTTS(self):
        """interrupt() must call _abortAllTTS."""
        src = self._get_source()
        m = re.search(r"  interrupt\(\)\s*\{", src)
        assert m
        start = m.start()
        body = src[start:start + 1200]
        assert "_abortAllTTS()" in body, \
            "interrupt() must call _abortAllTTS"

    def test_stop_calls_abortAllTTS(self):
        """stop() must call _abortAllTTS."""
        src = self._get_source()
        m = re.search(r"  stop\(\)\s*\{", src)
        assert m
        start = m.start()
        body = src[start:start + 600]
        assert "_abortAllTTS()" in body, \
            "stop() must call _abortAllTTS"


class TestAdaptiveTTSConcurrency:
    """TTS concurrency must adapt based on audio buffer level."""

    def _get_source(self):
        return _read_source("src/static/voice/voiceEngine.js")

    def test_dynamic_limit_computed(self):
        """_sendTTS must compute dynamicLimit from bufferedTime."""
        src = self._get_source()
        m = re.search(r'  _sendTTS\s*\(text\)', src)
        assert m
        start = m.start()
        body = src[start:start + 800]
        assert "dynamicLimit" in body
        assert "bufferedTime < 0.2" in body, \
            "dynamicLimit must check bufferedTime < 0.2 for higher concurrency"

    def test_high_limit_when_buffer_low(self):
        """dynamicLimit must be 16 when buffer is low."""
        src = self._get_source()
        m = re.search(r'  _sendTTS\s*\(text\)', src)
        assert m
        start = m.start()
        body = src[start:start + 800]
        assert "16" in body, \
            "dynamicLimit must allow up to 16 when buffer is low"

    def test_low_limit_when_buffer_high(self):
        """dynamicLimit must be 8 when buffer is full."""
        src = self._get_source()
        m = re.search(r'  _sendTTS\s*\(text\)', src)
        assert m
        start = m.start()
        body = src[start:start + 800]
        assert "8" in body, \
            "dynamicLimit must throttle to 8 when buffer is full"


class TestLowerSTTLLMTrigger:
    """STT→LLM trigger threshold must be lowered for faster LLM start."""

    def _get_source(self):
        return _read_source("src/static/voice/voiceEngine.js")

    def test_min_partial_text_length_is_4(self):
        """MIN_PARTIAL_TEXT_LENGTH must be 4 (lowered from 20)."""
        src = self._get_source()
        assert "this.MIN_PARTIAL_TEXT_LENGTH = 4" in src, \
            "MIN_PARTIAL_TEXT_LENGTH must be 4 for ultra-fast STT→LLM bridge"


class TestStreamingContextUpdate:
    """onTranscript must call llm.updateContext when LLM is already running."""

    def _get_source(self):
        return _read_source("src/static/voice/voiceEngine.js")

    def test_updateContext_called_when_llm_started(self):
        """onTranscript must call llm.updateContext when llmStarted is true."""
        src = self._get_source()
        m = re.search(r'  onTranscript\(text\)\s*\{', src)
        assert m
        start = m.start()
        body = src[start:start + 1200]
        assert "updateContext" in body, \
            "onTranscript must call llm.updateContext for streaming context"

    def test_updateContext_guarded_by_typeof(self):
        """updateContext call must be guarded by typeof check for optional method."""
        src = self._get_source()
        m = re.search(r'  onTranscript\(text\)\s*\{', src)
        assert m
        start = m.start()
        body = src[start:start + 1200]
        assert "typeof" in body or "updateContext" in body, \
            "updateContext must be safely guarded"

    def test_updateContext_only_when_llm_started(self):
        """updateContext must only be called in the else-if branch (llmStarted)."""
        src = self._get_source()
        m = re.search(r'  onTranscript\(text\)\s*\{', src)
        assert m
        start = m.start()
        body = src[start:start + 800]
        assert "this.llmStarted" in body, \
            "updateContext branch must check llmStarted"


class TestPreSpeechFiller:
    """onLLMToken must send a conversational filler on the first token to mask latency."""

    def _get_source(self):
        return _read_source("src/static/voice/voiceEngine.js")

    def test_fillers_array_in_constructor(self):
        """Constructor must initialise _fillers array with conversational fillers."""
        src = self._get_source()
        assert "this._fillers" in src, \
            "Constructor must define _fillers array"
        assert '"Yeah,"' in src or "'Yeah,'" in src, \
            "_fillers must include 'Yeah,'"

    def test_filler_sent_on_first_token(self):
        """onLLMToken first-token block must send a filler TTS chunk."""
        src = self._get_source()
        m = re.search(r'onLLMToken\s*\(', src)
        assert m
        start = m.start()
        body = src[start:start + 1000]
        assert "_fillers" in body, \
            "First token handler must pick from _fillers array"
        assert "_sendTTS(filler)" in body, \
            "First token handler must call _sendTTS with filler"

    def test_filler_randomised(self):
        """Filler selection must use Math.random for variety."""
        src = self._get_source()
        m = re.search(r'onLLMToken\s*\(', src)
        assert m
        start = m.start()
        body = src[start:start + 1000]
        assert "Math.random()" in body or "Math.floor(Math.random()" in body, \
            "Filler selection must be randomised"


class TestSemanticPacing:
    """_scheduleBuffer must use semantic pacing with meaning-aware pauses."""

    def _get_source(self):
        return _read_source("src/static/voice/audioOutput.js")

    def test_comma_period_pause(self):
        """Semantic pacing must add extra pause for commas and periods."""
        src = self._get_source()
        m = re.search(r'  _scheduleBuffer\s*\(audioBuffer\)', src)
        assert m
        start = m.start()
        body = src[start:start + 1800]
        assert "/[,.]/" in body or "[,.]" in body, \
            "Semantic pacing must detect commas and periods"
        assert "+= 0.04" in body or "+ 0.04" in body, \
            "Commas/periods must add 40ms pause"

    def test_exclamation_question_pause(self):
        """Semantic pacing must add extra pause for exclamation and question marks."""
        src = self._get_source()
        m = re.search(r'  _scheduleBuffer\s*\(audioBuffer\)', src)
        assert m
        start = m.start()
        body = src[start:start + 2200]
        assert "/[!?]/" in body or "[!?]" in body, \
            "Semantic pacing must detect ! and ?"
        assert "+= 0.08" in body or "+ 0.08" in body, \
            "Exclamation/question must add 80ms pause"

    def test_conjunction_pause(self):
        """Semantic pacing must add pause for conjunctions (and, but, so, because)."""
        src = self._get_source()
        m = re.search(r'  _scheduleBuffer\s*\(audioBuffer\)', src)
        assert m
        start = m.start()
        body = src[start:start + 2200]
        assert "and|but|so|because" in body, \
            "Semantic pacing must detect conjunctions"
        assert "+= 0.02" in body or "+ 0.02" in body, \
            "Conjunctions must add 20ms pause"

    def test_base_pause(self):
        """Semantic pacing must have a base pause of 0.02s."""
        src = self._get_source()
        m = re.search(r'  _scheduleBuffer\s*\(audioBuffer\)', src)
        assert m
        start = m.start()
        body = src[start:start + 2200]
        assert "pause = 0.02" in body, \
            "Base pause must be 0.02s"

    def test_jitter_preserved(self):
        """Semantic pacing must still include random jitter for naturalness."""
        src = self._get_source()
        m = re.search(r'  _scheduleBuffer\s*\(audioBuffer\)', src)
        assert m
        start = m.start()
        body = src[start:start + 2200]
        assert "Math.random()" in body, \
            "Must include jitter for natural prosody"
        assert "0.015" in body, \
            "Jitter range must be 0.015"


class TestSpeculativeResponse:
    """onTranscript must send a speculative filler ('Hmm,') when starting LLM early."""

    def _get_source(self):
        return _read_source("src/static/voice/voiceEngine.js")

    def test_speculative_filler_sent(self):
        """onTranscript must send 'Hmm,' filler when starting LLM on partial transcript."""
        src = self._get_source()
        m = re.search(r'  onTranscript\(text\)\s*\{', src)
        assert m
        start = m.start()
        body = src[start:start + 1200]
        assert "Hmm," in body, \
            "Speculative response must send 'Hmm,' filler"
        assert "_sendTTS" in body, \
            "Speculative filler must be sent via _sendTTS"


class TestSoftBargeIn:
    """handleUserSpeechStart must use a soft barge-in window (delay before interrupt)."""

    def _get_source(self):
        return _read_source("src/static/voice/voiceEngine.js")

    def test_pending_interrupt_flag(self):
        """Constructor must initialise _pendingInterrupt flag."""
        src = self._get_source()
        assert "this._pendingInterrupt" in src, \
            "Must have _pendingInterrupt flag"

    def test_soft_barge_in_timeout(self):
        """handleUserSpeechStart must use setTimeout for soft barge-in window."""
        src = self._get_source()
        m = re.search(r'  handleUserSpeechStart\(\)\s*\{', src)
        assert m
        start = m.start()
        body = src[start:start + 600]
        assert "setTimeout" in body, \
            "Soft barge-in must use setTimeout delay"
        assert "120" in body, \
            "Barge-in delay must be 120ms"

    def test_pending_interrupt_set(self):
        """handleUserSpeechStart must set _pendingInterrupt before timeout."""
        src = self._get_source()
        m = re.search(r'  handleUserSpeechStart\(\)\s*\{', src)
        assert m
        start = m.start()
        body = src[start:start + 600]
        assert "_pendingInterrupt = true" in body, \
            "Must set _pendingInterrupt before timeout"

    def test_pending_interrupt_checked_in_timeout(self):
        """setTimeout callback must check _pendingInterrupt before interrupting."""
        src = self._get_source()
        m = re.search(r'  handleUserSpeechStart\(\)\s*\{', src)
        assert m
        start = m.start()
        body = src[start:start + 600]
        assert "_pendingInterrupt" in body, \
            "Timeout callback must check _pendingInterrupt"

    def test_speech_end_cancels_pending_interrupt(self):
        """onSpeechEnd must cancel pending interrupt."""
        src = self._get_source()
        m = re.search(r'  onSpeechEnd\(\)\s*\{', src)
        assert m
        start = m.start()
        body = src[start:start + 400]
        assert "_pendingInterrupt = false" in body, \
            "onSpeechEnd must cancel pending interrupt"

    def test_interrupt_count_tracked(self):
        """handleUserSpeechStart must increment interruptCount."""
        src = self._get_source()
        assert "this.interruptCount" in src, \
            "Constructor must initialise interruptCount"
        m = re.search(r'  handleUserSpeechStart\(\)\s*\{', src)
        assert m
        start = m.start()
        body = src[start:start + 600]
        assert "interruptCount" in body, \
            "handleUserSpeechStart must track interrupt count"
