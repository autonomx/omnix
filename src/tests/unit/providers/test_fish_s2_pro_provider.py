from __future__ import annotations

import base64
import io
import json
import wave
from contextlib import contextmanager
from types import SimpleNamespace

import numpy as np
import pytest

from app.providers import fish_s2_pro_provider as fish


def _wav(samples: int = 4410, rate: int = 44_100) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(rate)
        wav_file.writeframes(b"\x01\x00" * samples)
    return buffer.getvalue()


class FakeHttp:
    def __init__(self, body: bytes = b"", status: int = 200, chunks: list[bytes] | None = None):
        self.body, self.status, self.chunks = body, status, chunks or []
        self.posts: list[dict] = []

    def get(self, url, timeout=None):
        return SimpleNamespace(status_code=200)

    def post(self, url, json=None):
        self.posts.append({"url": url, "json": json})
        return SimpleNamespace(status_code=self.status, content=self.body, text="")

    @contextmanager
    def stream(self, method, url, json=None):
        self.posts.append({"url": url, "json": json})
        yield SimpleNamespace(status_code=self.status, iter_bytes=lambda: iter(self.chunks), read=lambda: b"", text="")

    def close(self):
        pass


@pytest.fixture
def voice(tmp_path, monkeypatch):
    sample = tmp_path / "Jinx.wav"
    sample.write_bytes(_wav(rate=24_000))
    (tmp_path / "Jinx.json").write_text(json.dumps({"ref_text": "Words in the sample."}), encoding="utf-8")
    monkeypatch.setattr(fish, "clone_reference", lambda speaker: (str(sample), "") if speaker == "voice-cloning:jinx" else (None, ""))
    monkeypatch.setattr(fish, "generation_slot", contextmanager(lambda: (yield)))
    return sample


def _provider(http: FakeHttp) -> fish.FishS2ProTTSProvider:
    provider = fish.FishS2ProTTSProvider({"port": 5999})
    provider._http_client = http
    return provider



@pytest.fixture(autouse=True)
def _host_memory_unknown(monkeypatch):
    """These tests are about the server's lifecycle, not this machine's free memory."""
    monkeypatch.setattr("app.providers.host_memory.available_commit_bytes", lambda: None)

def test_synthesis_sends_the_voice_sample_with_its_transcript(voice):
    http = FakeHttp(_wav(samples=22_050))
    result = _provider(http).generate_audio("[whisper] Hello.", speaker="voice-cloning:jinx", temperature=0.5)

    assert result["success"] is True
    assert result["sample_rate"] == 44_100
    assert result["duration"] == pytest.approx(0.5)
    assert base64.b64decode(result["audio"]) == http.body
    request = http.posts[0]["json"]
    assert http.posts[0]["url"] == "http://127.0.0.1:5999/v1/tts"
    assert request["text"] == "[whisper] Hello."
    assert request["references"][0]["text"] == "Words in the sample."
    with wave.open(io.BytesIO(base64.b64decode(request["references"][0]["audio"]))) as reference:
        assert reference.getframerate() == 24_000
    assert request["temperature"] == 0.5
    assert request["use_memory_cache"] == "on"
    assert result["generation_parameters_used"]["temperature"] == 0.5


def test_a_voice_without_a_transcript_fails_before_calling_the_server(voice):
    (voice.parent / "Jinx.json").unlink()
    http = FakeHttp(_wav())

    result = _provider(http).generate_audio("Hello.", speaker="voice-cloning:jinx")

    assert result["success"] is False
    assert "no reference transcript" in result["error"]
    assert http.posts == []


def test_a_server_error_is_a_failed_synthesis(voice):
    result = _provider(FakeHttp(status=500)).generate_audio("Hello.", speaker="voice-cloning:jinx")

    assert result["success"] is False
    assert "500" in result["error"]


def test_streaming_decodes_pcm_after_the_wav_header_across_chunk_boundaries(voice):
    header = _wav(samples=0)[:44]
    pcm = (np.array([0, 16384, -16384], dtype="<i2")).tobytes()
    stream = header + pcm
    chunks = [stream[:10], stream[10:45], stream[45:]]

    out = list(_provider(FakeHttp(chunks=chunks)).generate_audio_stream("Hi.", speaker="voice-cloning:jinx"))

    audio = np.concatenate([chunk for chunk, _rate, _timing in out])
    assert [rate for _chunk, rate, _timing in out] == [44_100] * len(out)
    assert audio.tolist() == pytest.approx([0.0, 0.5, -0.5])
    assert "provider_entry_to_first_audio_ms" in out[0][2]


def test_resolved_parameters_name_the_codec_rate_for_speech_budgets():
    resolved = fish.FishS2ProTTSProvider({}).resolve_generation_parameters({"seed": 7, "max_new_tokens": 300})

    assert resolved["seed"] == 7
    assert resolved["max_new_tokens"] == 300
    assert resolved["temperature"] == fish.DEFAULT_FISH_SETTINGS["temperature"]
    assert resolved["codec_steps_per_second"] == fish.FISH_CODEC_STEPS_PER_SECOND
    assert resolved["_generation_strategy_revision"] == fish.FishS2ProTTSProvider.generation_strategy_revision


def test_stop_ends_a_server_left_by_an_earlier_owner(tmp_path, monkeypatch):
    killed: list[int] = []
    monkeypatch.setattr(fish, "_stop_process_tree", killed.append)
    provider = fish.FishS2ProTTSProvider({})
    pid_file = tmp_path / "fish.pid"
    pid_file.write_text("4242", encoding="utf-8")
    monkeypatch.setattr(provider, "_pid_path", lambda: pid_file)

    assert provider.stop() is True
    assert killed == [4242]
    assert not pid_file.exists()


def test_start_reuses_a_server_that_is_already_serving(monkeypatch):
    provider = _provider(FakeHttp())
    monkeypatch.setattr(provider, "_launch_and_wait", lambda: pytest.fail("must not launch a second server"))

    assert provider.start()["running"] is True


def test_a_failed_start_reports_the_cause_and_cleans_up(monkeypatch):
    provider = fish.FishS2ProTTSProvider({})
    monkeypatch.setattr(provider, "_server_healthy", lambda: False)
    monkeypatch.setattr(provider, "_launch_and_wait", lambda: (_ for _ in ()).throw(RuntimeError("weights are missing")))
    terminated: list[bool] = []
    monkeypatch.setattr(provider, "_terminate", lambda: terminated.append(True))

    state = provider.start()

    assert state["running"] is False
    assert "weights are missing" in state["error"]
    assert terminated == [True]


def test_local_artifacts_need_the_weights_and_the_codec(tmp_path, monkeypatch):
    from app.providers.tts_artifacts import LocalArtifactsUnavailable

    monkeypatch.setattr("app.settings.access.load_settings", lambda: {"fish-s2-pro": {"checkpoint_dir": str(tmp_path)}})
    (tmp_path / "model-00001-of-00002.safetensors").write_bytes(b"w")
    with pytest.raises(LocalArtifactsUnavailable, match="incomplete"):
        fish.FishS2ProTTSProvider.local_model_artifacts()

    (tmp_path / "codec.pth").write_bytes(b"c")
    artifacts = fish.FishS2ProTTSProvider.local_model_artifacts()
    assert artifacts.model_id == fish.MODEL_ID
    assert artifacts.directory == tmp_path.resolve()


def test_the_server_command_points_at_the_checkpoint_and_its_codec(tmp_path):
    provider = fish.FishS2ProTTSProvider({"checkpoint_dir": str(tmp_path), "python": "fishpython", "port": 5123})

    command = provider._server_command()

    assert command[0] == "fishpython"
    # Omnix's wrapper loads the model without fish-speech's 20 GB float32 random init.
    assert command[3] == str(fish._SERVER_WRAPPER) and fish._SERVER_WRAPPER.is_file()
    assert command[command.index("--max-seq-len") + 1] == "12288"
    assert command[command.index("--listen") + 1] == "127.0.0.1:5123"
    assert command[command.index("--llama-checkpoint-path") + 1] == str(tmp_path.resolve())
    assert command[command.index("--decoder-checkpoint-path") + 1] == str(tmp_path.resolve() / "codec.pth")
    assert "--compile" not in command


def test_a_server_that_dies_while_loading_reports_its_exit_code(tmp_path, monkeypatch):
    checkpoint = tmp_path / "ckpt"
    checkpoint.mkdir()
    (checkpoint / "codec.pth").write_bytes(b"c")
    code = tmp_path / "fish-speech"
    (code / "tools").mkdir(parents=True)
    (code / "tools" / "api_server.py").write_text("", encoding="utf-8")
    provider = fish.FishS2ProTTSProvider({"checkpoint_dir": str(checkpoint), "code_dir": str(code), "python": "py"})
    monkeypatch.setattr(provider, "_log_path", lambda: tmp_path / "fish.log")
    monkeypatch.setattr(provider, "_pid_path", lambda: tmp_path / "fish.pid")
    monkeypatch.setattr(provider, "_server_healthy", lambda: False)
    crashed = SimpleNamespace(pid=7, poll=lambda: -1073741819)  # 0xc0000005, as Windows reports it
    monkeypatch.setattr(fish.subprocess, "Popen", lambda *args, **kwargs: crashed)

    with pytest.raises(RuntimeError, match="exit code 0xc0000005"):
        provider._launch_and_wait()
