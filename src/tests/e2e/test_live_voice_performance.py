"""Five-turn hardware benchmark driver for the real Omnix live-voice path.

This test is intentionally local/self-hosted only.  It replaces getUserMedia's
microphone track with a programmable WebAudio MediaStream, then feeds the
committed examples/voice/interaction-1.wav ... interaction-5.wav one at a time.
Each next utterance waits for the preceding assistant response to finish.

Use scripts/run_live_voice_performance_benchmark.py instead of invoking this
file directly; the runner performs service preflight and analyzes resources/logs.
"""

from __future__ import annotations

import base64
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import pytest
from playwright.sync_api import Playwright, expect

RUN_BENCHMARK = os.environ.get("OMNIX_RUN_LIVE_VOICE_PERFORMANCE", "0") == "1"
ROOT_DIR = Path(__file__).resolve().parents[3]
DEFAULT_AUDIO_DIR = ROOT_DIR / "examples" / "voice"

_PROGRAMMABLE_MIC_INIT = r"""
(() => {
  const mediaDevices = navigator.mediaDevices;
  if (!mediaDevices || typeof mediaDevices.getUserMedia !== 'function') {
    throw new Error('programmable_microphone_media_devices_unavailable');
  }
  const originalGetUserMedia = mediaDevices.getUserMedia.bind(mediaDevices);
  const AudioContextCtor = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextCtor) throw new Error('programmable_microphone_audio_context_unavailable');

  const context = new AudioContextCtor({ sampleRate: 48000 });
  const destination = context.createMediaStreamDestination();
  const state = { source: null, playIndex: 0 };

  mediaDevices.getUserMedia = async (constraints) => {
    if (constraints && constraints.audio) {
      return new MediaStream(destination.stream.getAudioTracks());
    }
    return originalGetUserMedia(constraints);
  };

  window.__omnixBenchmarkMic = {
    async playWavBase64(encoded) {
      if (state.source) {
        try { state.source.stop(); } catch (_) {}
        try { state.source.disconnect(); } catch (_) {}
        state.source = null;
      }
      const binary = atob(encoded);
      const bytes = new Uint8Array(binary.length);
      for (let index = 0; index < binary.length; index += 1) {
        bytes[index] = binary.charCodeAt(index);
      }
      const audioBuffer = await context.decodeAudioData(bytes.buffer.slice(0));
      await context.resume();
      const source = context.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(destination);
      state.source = source;
      state.playIndex += 1;
      const startedAtMs = performance.now();
      await new Promise((resolve, reject) => {
        source.onended = resolve;
        try { source.start(); } catch (error) { reject(error); }
      });
      try { source.disconnect(); } catch (_) {}
      if (state.source === source) state.source = null;
      return {
        play_index: state.playIndex,
        duration_ms: audioBuffer.duration * 1000,
        started_at_ms: startedAtMs,
        ended_at_ms: performance.now(),
        context_state: context.state,
        context_sample_rate: context.sampleRate,
      };
    },
    async resume() {
      await context.resume();
      return { state: context.state, sample_rate: context.sampleRate };
    },
  };
})();
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _headed_mode(request: pytest.FixtureRequest) -> bool:
    try:
        return bool(request.config.getoption("--headed"))
    except ValueError:
        return False


def _audio_paths() -> list[Path]:
    configured = os.environ.get("OMNIX_LIVE_VOICE_BENCHMARK_AUDIO_DIR", "").strip()
    audio_dir = Path(configured).expanduser() if configured else DEFAULT_AUDIO_DIR
    paths = [audio_dir / f"interaction-{index}.wav" for index in range(1, 6)]
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        pytest.fail(f"Missing benchmark audio files: {missing}")
    return paths


def _is_live_chat_stream_request(url: str, method: str) -> bool:
    return method == "POST" and urlparse(url).path.endswith("/messages/stream")


def _voice_mode(page) -> str:
    return str(
        page.locator(".assistant-voice-orb").first.get_attribute("data-voice-mode") or ""
    ).strip()


def _wait_for_response_cycle(page, *, timeout_ms: int = 90_000) -> None:
    page.wait_for_function(
        """() => document.querySelector('.assistant-voice-orb')?.dataset.voiceMode === 'speaking'""",
        timeout=timeout_ms,
    )
    page.wait_for_function(
        """() => document.querySelector('.assistant-voice-orb')?.dataset.voiceMode !== 'speaking'""",
        timeout=timeout_ms,
    )


def _settle_initial_greeting(page) -> None:
    # Give the optional greeting enough time to start. If it does, wait for it to
    # finish so interaction-1 is never treated as an interruption of the greeting.
    page.wait_for_timeout(2_000)
    if _voice_mode(page) == "speaking":
        page.wait_for_function(
            """() => document.querySelector('.assistant-voice-orb')?.dataset.voiceMode !== 'speaking'""",
            timeout=60_000,
        )
    page.wait_for_timeout(500)


@pytest.mark.e2e
@pytest.mark.skipif(
    not RUN_BENCHMARK,
    reason="Run through scripts/run_live_voice_performance_benchmark.py",
)
def test_five_turn_live_voice_hardware_performance(
    playwright: Playwright,
    request: pytest.FixtureRequest,
) -> None:
    app_base_url = os.environ.get("OMNIX_BASE_URL", "http://127.0.0.1:5173").rstrip("/")
    manifest_path = Path(
        os.environ.get(
            "OMNIX_LIVE_VOICE_BENCHMARK_MANIFEST",
            ROOT_DIR / "resources" / "logs" / "live-voice-benchmark-manifest.json",
        )
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    audio_paths = _audio_paths()
    parsed_app_url = urlparse(app_base_url)
    app_origin = f"{parsed_app_url.scheme}://{parsed_app_url.netloc}"

    browser = playwright.chromium.launch(
        headless=not _headed_mode(request),
        args=["--autoplay-policy=no-user-gesture-required"],
    )
    context = browser.new_context()
    context.grant_permissions(["microphone"], origin=app_origin)
    page = context.new_page()
    page.add_init_script(_PROGRAMMABLE_MIC_INIT)

    manifest: dict[str, object] = {
        "schema_version": 1,
        "started_at_utc": _utc_now(),
        "app_base_url": app_base_url,
        "audio_files": [str(path.resolve()) for path in audio_paths],
        "interactions": [],
    }

    try:
        page.goto(f"{app_base_url}/chatbot", wait_until="domcontentloaded", timeout=30_000)
        live_card = page.locator(".assistant-live-card")
        expect(live_card).to_be_visible(timeout=30_000)

        auto_speak = page.locator('.assistant-voice-toggle input[type="checkbox"]')
        if auto_speak.count() and not auto_speak.is_checked():
            auto_speak.check()

        live_card.get_by_role("button", name="Start Call").click()
        expect(live_card.locator("header strong")).to_have_text("Connected", timeout=30_000)
        page.evaluate("() => window.__omnixBenchmarkMic.resume()")
        _settle_initial_greeting(page)

        interactions: list[dict[str, object]] = []
        for index, audio_path in enumerate(audio_paths, start=1):
            encoded = base64.b64encode(audio_path.read_bytes()).decode("ascii")
            interaction_started = _utc_now()
            wall_started = time.perf_counter()

            with page.expect_request(
                lambda candidate: _is_live_chat_stream_request(candidate.url, candidate.method),
                timeout=45_000,
            ) as stream_request_info:
                playback = page.evaluate(
                    "(encoded) => window.__omnixBenchmarkMic.playWavBase64(encoded)",
                    encoded,
                )

            stream_request = stream_request_info.value
            try:
                payload = stream_request.post_data_json
            except Exception:
                payload = {}
            if not isinstance(payload, dict):
                payload = {}

            _wait_for_response_cycle(page)
            page.wait_for_timeout(250)

            transcript = str(payload.get("content") or "").strip()
            turn_id = str(payload.get("live_voice_turn_id") or "").strip() or None
            interactions.append(
                {
                    "index": index,
                    "audio_file": str(audio_path.resolve()),
                    "interaction_started_at_utc": interaction_started,
                    "interaction_completed_at_utc": _utc_now(),
                    "wall_elapsed_ms": round((time.perf_counter() - wall_started) * 1000, 3),
                    "microphone_playback": playback,
                    "request_url": stream_request.url,
                    "transcript": transcript,
                    "live_voice_turn_id": turn_id,
                }
            )

        manifest["interactions"] = interactions
        manifest["completed_at_utc"] = _utc_now()
        manifest["completed"] = True
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

        assert len(interactions) == 5
        assert all(str(item.get("transcript") or "").strip() for item in interactions), (
            "Every benchmark WAV must produce a non-empty submitted transcript"
        )

        live_card.get_by_role("button", name="End Call").click()
        expect(live_card.get_by_role("button", name="Start Call")).to_be_visible(timeout=10_000)
    except Exception:
        manifest["completed_at_utc"] = _utc_now()
        manifest["completed"] = False
        manifest["failure_voice_mode"] = _voice_mode(page)
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        raise
    finally:
        context.close()
        browser.close()
