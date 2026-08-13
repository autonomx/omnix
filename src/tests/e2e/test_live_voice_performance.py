"""Five-turn hardware benchmark driver for the real Omnix live-voice path.

This test is intentionally local/self-hosted only. It replaces getUserMedia's
microphone track with a programmable WebAudio MediaStream, then feeds the
committed examples/voice/interaction-1.wav ... interaction-5.wav one at a time.
Each next utterance waits for the preceding assistant response stream and audio
playback to finish before the next WAV is injected.

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
EXPECTED_PROVIDER = os.environ.get("OMNIX_LIVE_VOICE_EXPECTED_PROVIDER", "cerebras").strip().casefold()
_RESPONSE_TIMEOUT_MS = 90_000
_STABLE_LISTENING_MS = 1_200

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

  const benchmarkEvents = { finals: [], perfFinals: [], turnFinished: [] };
  window.__omnixBenchmarkEvents = benchmarkEvents;
  window.addEventListener('omnix:live-stt-speculation-final', (event) => {
    const detail = event?.detail ?? {};
    benchmarkEvents.finals.push({
      text: String(detail.text ?? ''),
      segment_id: String(detail.segmentId ?? ''),
      source_sequence: Number(detail.sourceSequence),
    });
  });
  window.addEventListener('omnix:assistant-voice-perf', (event) => {
    const detail = event?.detail ?? {};
    if (detail.stage !== 'stt_final_received') return;
    benchmarkEvents.perfFinals.push({
      turn_id: String(detail.turnId ?? ''),
      transcript_chars: Number(detail.transcriptChars ?? detail.transcript_chars),
    });
  });
  window.addEventListener('omnix:live-call-diagnostic', (event) => {
    const detail = event?.detail ?? {};
    if (detail.event !== 'turn_finished') return;
    benchmarkEvents.turnFinished.push({ trace_id: String(detail.traceId ?? '') });
  });
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


def _voice_mode(page) -> str:
    return str(
        page.locator(".assistant-voice-orb").first.get_attribute("data-voice-mode") or ""
    ).strip()


def _settings_provider(payload: object) -> str:
    if not isinstance(payload, dict):
        return ""
    nested = payload.get("settings")
    if isinstance(nested, dict):
        candidate = nested.get("provider")
        if candidate:
            return str(candidate).strip().casefold()
    return str(payload.get("provider") or "").strip().casefold()


def _assert_expected_provider(context, app_base_url: str) -> None:
    response = context.request.get(f"{app_base_url}/api/settings", timeout=15_000)
    if not response.ok:
        pytest.fail(f"Could not read Omnix provider settings: HTTP {response.status}")
    try:
        payload = response.json()
    except Exception as exc:
        pytest.fail(f"Could not decode /api/settings response: {exc}")
    provider = _settings_provider(payload)
    if EXPECTED_PROVIDER and provider != EXPECTED_PROVIDER:
        pytest.fail(
            "Live Voice benchmark provider preflight failed: "
            f"expected {EXPECTED_PROVIDER!r}, active provider is {provider or '<unknown>'!r}. "
            "Select the expected provider in Omnix (and ensure its local API key is available) "
            "before running the benchmark."
        )


def _wait_for_speaking(page, *, timeout_ms: int = _RESPONSE_TIMEOUT_MS) -> None:
    page.wait_for_function(
        """() => document.querySelector('.assistant-voice-orb')?.dataset.voiceMode === 'speaking'""",
        timeout=timeout_ms,
    )


def _wait_for_stable_listening(
    page,
    *,
    timeout_ms: int = _RESPONSE_TIMEOUT_MS,
    stable_ms: int = _STABLE_LISTENING_MS,
) -> None:
    """Require a continuous non-speaking window, not a transient inter-clause pause."""

    deadline = time.monotonic() + timeout_ms / 1000
    stable_since: float | None = None
    while time.monotonic() < deadline:
        mode = _voice_mode(page)
        if mode and mode != "speaking":
            if stable_since is None:
                stable_since = time.monotonic()
            elif (time.monotonic() - stable_since) * 1000 >= stable_ms:
                return
        else:
            stable_since = None
        page.wait_for_timeout(100)
    pytest.fail(
        f"Live Voice did not remain non-speaking for {stable_ms} ms within {timeout_ms} ms; "
        f"last voice mode={_voice_mode(page)!r}"
    )


def _settle_initial_greeting(page) -> None:
    # Give the optional greeting enough time to start. If it does, wait until the
    # call is continuously idle so interaction-1 cannot land in an inter-clause pause.
    page.wait_for_timeout(2_000)
    if _voice_mode(page) == "speaking":
        _wait_for_stable_listening(page, timeout_ms=60_000)
    else:
        _wait_for_stable_listening(page, timeout_ms=15_000)


def _persist_manifest(path: Path, manifest: dict[str, object]) -> None:
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


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

    interactions: list[dict[str, object]] = []
    manifest: dict[str, object] = {
        "schema_version": 1,
        "started_at_utc": _utc_now(),
        "app_base_url": app_base_url,
        "expected_provider": EXPECTED_PROVIDER,
        "audio_files": [str(path.resolve()) for path in audio_paths],
        "interactions": interactions,
    }
    _persist_manifest(manifest_path, manifest)

    try:
        page.goto(f"{app_base_url}/chatbot", wait_until="domcontentloaded", timeout=30_000)
        live_card = page.locator(".assistant-live-card")
        expect(live_card).to_be_visible(timeout=30_000)
        _assert_expected_provider(context, app_base_url)

        auto_speak = page.locator('.assistant-voice-toggle input[type="checkbox"]')
        if auto_speak.count() and not auto_speak.is_checked():
            auto_speak.check()

        live_card.get_by_role("button", name="Start Call").click()
        expect(live_card.locator("header strong")).to_have_text("Connected", timeout=30_000)
        page.evaluate("() => window.__omnixBenchmarkMic.resume()")
        _settle_initial_greeting(page)

        for index, audio_path in enumerate(audio_paths, start=1):
            encoded = base64.b64encode(audio_path.read_bytes()).decode("ascii")
            interaction_started = _utc_now()
            wall_started = time.perf_counter()
            event_counts = page.evaluate(
                """() => ({
                  finals: window.__omnixBenchmarkEvents.finals.length,
                  perfFinals: window.__omnixBenchmarkEvents.perfFinals.length,
                  turnFinished: window.__omnixBenchmarkEvents.turnFinished.length,
                })"""
            )
            manifest["active_interaction_index"] = index
            manifest["active_audio_file"] = str(audio_path.resolve())
            _persist_manifest(manifest_path, manifest)

            playback = page.evaluate(
                "(encoded) => window.__omnixBenchmarkMic.playWavBase64(encoded)",
                encoded,
            )

            # Observe real audio and the controller's terminal turn diagnostic
            # before accepting an idle window. This works for both canonical chat
            # requests and speculative streams promoted without a second request.
            _wait_for_speaking(page)
            page.wait_for_function(
                "counts => window.__omnixBenchmarkEvents.turnFinished.length > counts.turnFinished",
                arg=event_counts,
                timeout=_RESPONSE_TIMEOUT_MS,
            )
            _wait_for_stable_listening(page)

            page.wait_for_function(
                """counts => (
                  window.__omnixBenchmarkEvents.finals.length > counts.finals
                  && window.__omnixBenchmarkEvents.perfFinals.length > counts.perfFinals
                )""",
                arg=event_counts,
                timeout=15_000,
            )
            final_event = page.evaluate(
                "counts => window.__omnixBenchmarkEvents.finals[counts.finals]",
                event_counts,
            )
            perf_final = page.evaluate(
                "counts => window.__omnixBenchmarkEvents.perfFinals[counts.perfFinals]",
                event_counts,
            )

            transcript = str(final_event.get("text") or "").strip()
            turn_id = str(perf_final.get("turn_id") or "").strip() or None
            interactions.append(
                {
                    "index": index,
                    "audio_file": str(audio_path.resolve()),
                    "interaction_started_at_utc": interaction_started,
                    "interaction_completed_at_utc": _utc_now(),
                    "wall_elapsed_ms": round((time.perf_counter() - wall_started) * 1000, 3),
                    "microphone_playback": playback,
                    "transcript": transcript,
                    "live_voice_turn_id": turn_id,
                }
            )
            manifest["interactions"] = interactions
            manifest.pop("active_interaction_index", None)
            manifest.pop("active_audio_file", None)
            _persist_manifest(manifest_path, manifest)

        manifest["completed_at_utc"] = _utc_now()
        manifest["completed"] = True
        _persist_manifest(manifest_path, manifest)

        assert len(interactions) == 5
        assert all(str(item.get("transcript") or "").strip() for item in interactions), (
            "Every benchmark WAV must produce a non-empty submitted transcript"
        )

        live_card.get_by_role("button", name="End Call").click()
        expect(live_card.get_by_role("button", name="Start Call")).to_be_visible(timeout=10_000)
    except Exception:
        manifest["interactions"] = interactions
        manifest["completed_at_utc"] = _utc_now()
        manifest["completed"] = False
        manifest["failure_voice_mode"] = _voice_mode(page)
        _persist_manifest(manifest_path, manifest)
        raise
    finally:
        context.close()
        browser.close()
