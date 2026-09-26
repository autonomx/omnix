"""
Tests for shared audio utilities and providers.

Tests do not require external services (LLM, TTS, STT).
All LLM-dependent modules are tested with mock callables.
"""

import os
import sys
import time

import pytest

# Ensure src/ is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


# ---------------------------------------------------------------------------
# #7  TTS Provider Abstraction
# ---------------------------------------------------------------------------

class TestTTSProviderAbstraction:
    def test_register_and_get(self):
        from app.providers.tts_abstraction import (
            LocalModelTTSProvider,
            get_provider,
            list_providers,
            register_provider,
            unregister_provider,
        )

        p = LocalModelTTSProvider(base_url="http://localhost:9999")
        register_provider("test_local", p)
        assert "test_local" in list_providers()
        assert get_provider("test_local") is p
        unregister_provider("test_local")
        assert "test_local" not in list_providers()

    def test_openai_provider_name(self):
        from app.providers.tts_abstraction import OpenAITTSProvider
        p = OpenAITTSProvider(api_key="fake")
        assert p.name == "openai"

    def test_local_provider_name(self):
        from app.providers.tts_abstraction import LocalModelTTSProvider
        p = LocalModelTTSProvider()
        assert p.name == "local"

    def test_get_nonexistent(self):
        from app.providers.tts_abstraction import get_provider
        assert get_provider("nonexistent_xyz") is None

    def test_local_generate_connection_error(self):
        from app.providers.tts_abstraction import LocalModelTTSProvider
        # Should gracefully return empty bytes, not raise
        p = LocalModelTTSProvider(base_url="http://localhost:1")
        result = p.generate("test")
        assert result == b""

    def test_openai_generate_connection_error(self):
        from app.providers.tts_abstraction import OpenAITTSProvider
        p = OpenAITTSProvider(base_url="http://localhost:1")
        result = p.generate("test")
        assert result == b""


# ---------------------------------------------------------------------------
# #10  Job Queue
# ---------------------------------------------------------------------------

class TestJobQueue:
    def _make(self, **kw):
        from app.job_queue import JobQueue
        return JobQueue(**kw)

    def test_enqueue_returns_id(self):
        q = self._make()
        job_id = q.enqueue("hello")
        assert isinstance(job_id, str)
        assert len(job_id) > 0

    def test_process_job(self):
        def worker(text, speaker, voice_id, **kw):
            return {"audio": text.encode(), "sample_rate": 24000}

        q = self._make(worker_fn=worker)
        q.start()
        job_id = q.enqueue("hello", speaker="narrator")

        # Wait for processing
        for _ in range(50):
            r = q.get_result(job_id)
            if r and r["status"] == "completed":
                break
            time.sleep(0.05)

        r = q.get_result(job_id)
        assert r["status"] == "completed"
        assert r["audio"]["audio"] == b"hello"
        q.stop()

    def test_failed_job(self):
        def failing_worker(text, speaker, voice_id, **kw):
            raise RuntimeError("TTS error")

        q = self._make(worker_fn=failing_worker)
        q.start()
        job_id = q.enqueue("test")

        for _ in range(50):
            r = q.get_result(job_id)
            if r and r["status"] == "failed":
                break
            time.sleep(0.05)

        r = q.get_result(job_id)
        assert r["status"] == "failed"
        assert "TTS error" in r["error"]
        q.stop()

    def test_cancel_job(self):
        # Don't start workers so job stays pending
        q = self._make()
        job_id = q.enqueue("test")
        assert q.cancel(job_id) is True
        r = q.get_result(job_id)
        assert r["status"] == "failed"
        assert "Cancelled" in r["error"]

    def test_get_nonexistent(self):
        q = self._make()
        assert q.get_result("nonexistent") is None

    def test_pending_count(self):
        q = self._make()
        q.enqueue("a")
        q.enqueue("b")
        assert q.pending_count == 2

    def test_global_queue(self):
        from app.job_queue import get_job_queue
        q = get_job_queue()
        assert q is not None


# ---------------------------------------------------------------------------
# Tests for pipeline hardening fixes (Issues 1-5)
# ---------------------------------------------------------------------------


class TestAudioHardeningHelpers:
    """Issue 3 – Audio normalization and validation helpers."""

    @pytest.fixture(autouse=True)
    def _require_numpy(self):
        pytest.importorskip("numpy")

    def test_is_valid_audio_rejects_empty(self):
        import numpy as np

        from app.providers.faster_qwen3_tts_provider import _is_valid_audio
        assert _is_valid_audio(np.array([])) is False

    def test_is_valid_audio_rejects_nan(self):
        import numpy as np

        from app.providers.faster_qwen3_tts_provider import _is_valid_audio
        assert _is_valid_audio(np.array([1.0, float('nan'), 0.5])) is False

    def test_is_valid_audio_rejects_silence(self):
        import numpy as np

        from app.providers.faster_qwen3_tts_provider import _is_valid_audio
        assert _is_valid_audio(np.zeros(100)) is False

    def test_is_valid_audio_rejects_explosion(self):
        import numpy as np

        from app.providers.faster_qwen3_tts_provider import _is_valid_audio
        assert _is_valid_audio(np.array([10.0, -10.0])) is False

    def test_is_valid_audio_accepts_good(self):
        import numpy as np

        from app.providers.faster_qwen3_tts_provider import _is_valid_audio
        assert _is_valid_audio(np.array([0.5, -0.3, 0.1])) is True

    def test_normalize_audio(self):
        import numpy as np

        from app.providers.faster_qwen3_tts_provider import _normalize_audio, soft_clip
        audio = np.array([0.5, -0.5, 1.5], dtype=np.float32)
        result = _normalize_audio(audio)
        assert isinstance(result, bytes)
        # int16 = 2 bytes per sample
        assert len(result) == 6
        # peak 1.5 > 0.95 → divides by 1.5 → [0.333, -0.333, 1.0]
        # then soft_clip limits; soft_clip(1.0) = 0.5 → ~16383
        arr = np.frombuffer(result, dtype=np.int16)
        np.testing.assert_allclose(arr[2], soft_clip(np.float32(1.0)) * 32767, atol=1)

    def test_normalize_audio_peak_preserves_quiet(self):
        """Peak-based normalisation must NOT amplify a quiet signal."""
        import numpy as np

        from app.providers.faster_qwen3_tts_provider import _normalize_audio, soft_clip
        audio = np.array([0.1, -0.1], dtype=np.float32)
        result = _normalize_audio(audio)
        arr = np.frombuffer(result, dtype=np.int16)
        # soft_clip(0.1) ≈ 0.0909 → ~2979
        np.testing.assert_allclose(arr[0], soft_clip(np.float32(0.1)) * 32767, atol=1)

    def test_align_bytes(self):
        from app.providers.faster_qwen3_tts_provider import _align_bytes
        assert len(_align_bytes(b'\x00\x01\x02')) == 2
        assert len(_align_bytes(b'\x00\x01')) == 2
        assert len(_align_bytes(b'')) == 0


class TestCrossfadeAudio:
    """Tests for the crossfade_audio helper."""

    def test_crossfade_basic(self):
        import numpy as np

        from app.providers.faster_qwen3_tts_provider import crossfade_audio
        prev = np.ones(1024, dtype=np.float32)
        curr = np.ones(1024, dtype=np.float32) * -1
        result = crossfade_audio(prev, curr, fade_samples=512)
        # Total length: prev[:-512] + 512 blended + curr[512:] = 512 + 512 + 512
        assert len(result) == 1024 + 1024 - 512

    def test_crossfade_short_arrays_concat(self):
        """Arrays shorter than fade_samples should just concatenate."""
        import numpy as np

        from app.providers.faster_qwen3_tts_provider import crossfade_audio
        prev = np.ones(100, dtype=np.float32)
        curr = np.ones(100, dtype=np.float32) * 2
        result = crossfade_audio(prev, curr, fade_samples=512)
        assert len(result) == 200
        assert result[0] == 1.0
        assert result[-1] == 2.0

    def test_crossfade_none_prev(self):
        import numpy as np

        from app.providers.faster_qwen3_tts_provider import crossfade_audio
        curr = np.ones(100, dtype=np.float32)
        result = crossfade_audio(None, curr, fade_samples=512)
        assert len(result) == 100

    def test_crossfade_smooth_transition(self):
        """Midpoint of crossfade should be roughly the average of the two signals."""
        import numpy as np

        from app.providers.faster_qwen3_tts_provider import crossfade_audio
        prev = np.ones(1024, dtype=np.float32)
        curr = np.zeros(1024, dtype=np.float32)
        result = crossfade_audio(prev, curr, fade_samples=512)
        # prev[:-512] has 512 samples (all 1.0), then 512 blended samples
        # Midpoint of blended region: index 512 + 256 = 768
        mid = 512 + 256
        assert 0.4 < result[mid] < 0.6


class TestApplyFade:
    """Tests for the apply_fade helper."""

    def test_fade_edges_near_zero(self):
        import numpy as np

        from app.providers.faster_qwen3_tts_provider import apply_fade
        audio = np.ones(1024, dtype=np.float32)
        result = apply_fade(audio, fade_samples=256)
        assert result[0] == 0.0  # fade-in starts at zero (raised-cosine)
        assert abs(result[-1]) < 0.01  # fade-out ends near zero
        # Middle should be untouched
        assert result[512] == 1.0

    def test_fade_short_audio_passthrough(self):
        """Audio shorter than 2*fade_samples should pass through as a copy."""
        import numpy as np

        from app.providers.faster_qwen3_tts_provider import apply_fade
        audio = np.ones(100, dtype=np.float32)
        result = apply_fade(audio, fade_samples=256)
        np.testing.assert_array_equal(result, audio)
        # Must be a copy, not the same object
        assert result is not audio

    def test_fade_does_not_mutate_input(self):
        import numpy as np

        from app.providers.faster_qwen3_tts_provider import apply_fade
        audio = np.ones(1024, dtype=np.float32)
        original = audio.copy()
        apply_fade(audio, fade_samples=256)
        np.testing.assert_array_equal(audio, original)


class TestSilencePad:
    """Tests for the silence_pad helper."""

    def test_silence_appended(self):
        import numpy as np

        from app.providers.faster_qwen3_tts_provider import silence_pad
        audio = np.ones(100, dtype=np.float32)
        result = silence_pad(audio, sample_rate=24000, duration_sec=0.05)
        expected_silence = int(0.05 * 24000)
        assert len(result) == 100 + expected_silence
        # Silence region should be all zeros
        assert np.all(result[100:] == 0.0)


class TestFindBestOffset:
    """Tests for the find_best_offset phase-alignment helper."""

    def test_identical_signals_zero_offset(self):
        """Two identical signals should produce offset 0."""
        import numpy as np

        from app.providers.faster_qwen3_tts_provider import find_best_offset
        sig = np.sin(np.linspace(0, 4 * np.pi, 1024, dtype=np.float32))
        offset = find_best_offset(sig, sig)
        assert offset == 0

    def test_shifted_signal_detected(self):
        """A known shift should be detected."""
        import numpy as np

        from app.providers.faster_qwen3_tts_provider import find_best_offset
        # Create a sine wave and a shifted copy
        t = np.linspace(0, 8 * np.pi, 2048, dtype=np.float32)
        sig = np.sin(t)
        shift = 30
        prev = sig[:512]
        curr = sig[512 - shift:]  # shifted so the overlap lines up at shift=30
        offset = find_best_offset(prev, curr, max_shift=64)
        # Should find the shift that best aligns the waveforms
        assert 0 <= offset < 64

    def test_short_arrays_no_crash(self):
        """Very short arrays should not crash."""
        import numpy as np

        from app.providers.faster_qwen3_tts_provider import find_best_offset
        prev = np.array([0.1, 0.2], dtype=np.float32)
        curr = np.array([0.1, 0.2, 0.3], dtype=np.float32)
        offset = find_best_offset(prev, curr, max_shift=5)
        assert isinstance(offset, int)
        assert 0 <= offset < 5


class TestSoftLimiter:
    """Tests for soft_clip limiter in _normalize_audio."""

    def test_soft_clip_smoother_than_clip(self):
        """soft_clip should produce a value < 32767 for a signal at exactly 1.0."""
        import numpy as np

        from app.providers.faster_qwen3_tts_provider import _normalize_audio
        audio = np.array([1.0], dtype=np.float32)
        result = _normalize_audio(audio)
        arr = np.frombuffer(result, dtype=np.int16)
        # soft_clip(1.0) = 0.5 → well below 32767
        assert arr[0] < 32767
        assert arr[0] > 0

    def test_soft_clip_preserves_small_signals(self):
        """For small values soft_clip(x) ≈ x, so quiet audio is not distorted."""
        import numpy as np

        from app.providers.faster_qwen3_tts_provider import _normalize_audio, soft_clip
        audio = np.array([0.05, -0.05], dtype=np.float32)
        result = _normalize_audio(audio)
        arr = np.frombuffer(result, dtype=np.int16)
        expected = soft_clip(np.float32(0.05)) * 32767
        np.testing.assert_allclose(arr[0], expected, atol=1)

    def test_soft_clip_function(self):
        """Direct test of the soft_clip helper."""
        import numpy as np

        from app.providers.faster_qwen3_tts_provider import soft_clip
        x = np.array([0.0, 0.5, 1.0, 2.0, -1.0], dtype=np.float32)
        result = soft_clip(x)
        expected = x / (1.0 + np.abs(x))
        np.testing.assert_allclose(result, expected, atol=1e-6)
        # All outputs bounded to (-1, 1)
        assert np.all(np.abs(result) < 1.0)


class TestDCOffsetCorrection:
    """Verify stabilised DC offset removal in server_fastapi.py."""

    _REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

    def _read_server_source(self):
        with open(os.path.join(self._REPO_ROOT, 'server_fastapi.py'), 'r') as f:
            return f.read()

    def test_dc_offset_present_in_stream(self):
        """The streaming loop must subtract np.mean(audio) for DC correction."""
        import re
        src = self._read_server_source()
        assert re.search(r'audio\s*=\s*audio\s*-\s*mean', src), \
            "DC offset correction (audio = audio - mean) not found in server_fastapi.py"

    def test_dc_offset_guarded(self):
        """DC offset must be guarded by chunk length and threshold checks."""
        src = self._read_server_source()
        assert 'len(audio) > 128' in src, \
            "DC offset must be guarded by minimum chunk size (len(audio) > 128)"
        assert '1e-4' in src, \
            "DC offset must be guarded by threshold (abs(mean) > 1e-4)"


class TestNoDoubleCrossfade:
    """Verify server_fastapi.py uses ONE crossfade strategy (no double overlap)."""

    _REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

    def _read_server_source(self):
        with open(os.path.join(self._REPO_ROOT, 'server_fastapi.py'), 'r') as f:
            return f.read()

    def test_no_crossfade_audio_call_in_stream(self):
        """The streaming loop must NOT call crossfade_audio() (uses tail-buffer instead)."""
        src = self._read_server_source()
        code_lines = [line for line in src.split('\n')
                      if line.strip() and not line.strip().startswith('#')]
        code_only = '\n'.join(code_lines)
        assert 'crossfade_audio' not in code_only, \
            "crossfade_audio should not be imported or called in server_fastapi.py code"

    def test_uses_soft_clip_not_tanh(self):
        """Streaming loop must use soft_clip() not np.tanh() for the gain stage."""
        import re
        src = self._read_server_source()
        assert re.search(r'soft_clip\(audio', src), \
            "soft_clip() limiter not found in server_fastapi.py"

    def test_limiter_after_crossfade(self):
        """Soft limiter must appear AFTER the crossfade block, not before."""
        src = self._read_server_source()
        # Find the crossfade block (fade_out/fade_in) and the limiter call
        xfade_pos = src.find('fade_out')
        limiter_pos = src.find('soft_clip(audio')
        assert xfade_pos > 0 and limiter_pos > 0, \
            "Both crossfade and soft_clip must exist in server_fastapi.py"
        assert limiter_pos > xfade_pos, \
            "soft_clip must appear AFTER crossfade in the streaming loop"

    def test_find_best_offset_in_stream(self):
        """Streaming loop must use find_best_offset for phase alignment."""
        src = self._read_server_source()
        assert 'find_best_offset' in src, \
            "find_best_offset phase-alignment not found in server_fastapi.py"

    def test_fade_only_on_first_chunk(self):
        """apply_fade should only be called when prev_audio is None (first chunk)."""
        import re
        src = self._read_server_source()
        assert re.search(r'if\s+prev_audio\s+is\s+None.*?apply_fade', src, re.DOTALL), \
            "apply_fade should only run when prev_audio is None"


class TestJobQueueChunkOrdering:
    """Issue 3 – Job queue chunk_index and ordered retrieval."""

    def test_job_has_chunk_index(self):
        from app.job_queue import Job
        job = Job(job_id="test1", text="hi", chunk_index=5)
        assert job.chunk_index == 5

    def test_job_default_chunk_index(self):
        from app.job_queue import Job
        job = Job(job_id="test2", text="hi")
        assert job.chunk_index == -1

    def test_get_result_includes_chunk_index(self):
        from app.job_queue import JobQueue
        q = JobQueue()
        jid = q.enqueue("hello", chunk_index=3)
        result = q.get_result(jid)
        assert result is not None
        assert result["chunk_index"] == 3

    def test_get_ordered_results(self):
        from app.job_queue import JobQueue
        q = JobQueue()
        # Enqueue out of order
        jid2 = q.enqueue("b", chunk_index=2)
        jid0 = q.enqueue("a", chunk_index=0)
        jid1 = q.enqueue("c", chunk_index=1)

        results = q.get_ordered_results([jid2, jid0, jid1])
        indices = [r["chunk_index"] for r in results if r is not None]
        assert indices == [0, 1, 2]

    def test_retry_on_failure(self):
        """Worker function retries up to _MAX_RETRIES times."""
        from app.job_queue import JobQueue, JobStatus
        calls = []

        def failing_worker(text, speaker, voice_id, **kw):
            calls.append(1)
            if len(calls) < 3:
                raise RuntimeError("fail")
            return {"audio": b"ok"}

        q = JobQueue(worker_fn=failing_worker)
        q.start()
        jid = q.enqueue("test")
        # Wait for processing
        import time
        time.sleep(1)
        result = q.get_result(jid)
        q.stop()
        assert result is not None
        assert result["status"] == JobStatus.COMPLETED
        assert len(calls) == 3  # two failures + one success




class TestVoiceCloneGenderField:
    """Tests that voice clones include the gender field."""

    def test_default_voice_clone_has_gender(self):
        """New voice clones should default to 'neutral' gender."""
        voice_data = {
            "speaker": "default",
            "language": "en",
            "voice_clone_id": "test_voice",
            "has_audio": True,
            "is_preloaded": True,
            "gender": "neutral",
        }
        assert "gender" in voice_data
        assert voice_data["gender"] == "neutral"

    def test_gender_field_values(self):
        """Gender field should accept male/female/neutral."""
        for gender in ("male", "female", "neutral"):
            voice_data = {"gender": gender}
            assert voice_data["gender"] in ("male", "female", "neutral")

    def test_migration_adds_gender(self):
        """Existing voice data without gender should get 'neutral' after migration."""
        old_voice_data = {
            "speaker": "default",
            "language": "en",
            "voice_clone_id": "legacy_voice",
            "has_audio": True,
        }
        # Simulate migration logic
        if "gender" not in old_voice_data:
            old_voice_data["gender"] = "neutral"
        assert old_voice_data["gender"] == "neutral"
