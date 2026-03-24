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
        m = re.search(r'_sendTTSHTTP\s*\(.*?\)\s*\{.*?\n  \}', src, re.DOTALL)
        assert m, "_sendTTSHTTP method not found"
        body = m.group(0)
        assert "await fetch" not in body, \
            "_sendTTSHTTP must not use await fetch"
        assert ".then(" in body, \
            "_sendTTSHTTP must use .then() chain"

    # -- interrupt / reset --

    def test_interrupt_resets_audio(self):
        """interrupt() must call audioOutput.reset()."""
        src = self._get_source()
        m = re.search(r'  interrupt\s*\(\s*\)\s*\{.*?\n  \}', src, re.DOTALL)
        assert m, "interrupt method not found"
        body = m.group(0)
        assert "audioOutput.reset()" in body or "_cancelOngoingResponse" in body

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
        """_cancelOngoingResponse must call audioOutput.reset()."""
        src = self._get_source()
        m = re.search(r'_cancelOngoingResponse\s*\(\s*\)\s*\{.*?\n  \}', src, re.DOTALL)
        assert m
        body = m.group(0)
        assert "audioOutput.reset()" in body

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
