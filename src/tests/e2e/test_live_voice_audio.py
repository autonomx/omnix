"""End-to-end Live Voice test using spoken audio as the microphone source.

Start the local Parakeet STT service, gateway, and Vite web app, then run:

    python run_playwright_tests.py --suite live_voice --headed --no-report

By default on Windows, the test synthesizes "How's it going?" with the local
System.Speech voice and feeds the resulting WAV into Chromium as a microphone.
To use a specific MP3 or WAV instead, pass ``--live-voice-audio PATH`` to the
runner or set ``OMNIX_LIVE_VOICE_AUDIO`` before invoking pytest directly.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request
import wave
from pathlib import Path
from urllib.parse import urlparse

import pytest
from playwright.sync_api import Playwright, expect

RUN_LIVE_TEST = os.environ.get("OMNIX_RUN_LIVE_VOICE_AUDIO", "0") == "1"
TEST_PHRASE = "How's it going?"


def _synthesize_windows_audio(tmp_path: Path) -> Path:
    powershell = (
        shutil.which("powershell")
        or shutil.which("powershell.exe")
        or shutil.which("pwsh")
    )
    if not powershell:
        pytest.fail(
            "No audio file was supplied and PowerShell is unavailable. "
            "Pass --live-voice-audio PATH to the test runner."
        )

    output_path = tmp_path / "hows-it-going-sapi.wav"
    escaped_path = str(output_path.resolve()).replace("'", "''")
    escaped_phrase = TEST_PHRASE.replace("'", "''")
    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$voice = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$voice.SetOutputToWaveFile('{escaped_path}'); "
        f"$voice.Speak('{escaped_phrase}'); "
        "$voice.Dispose();"
    )
    result = subprocess.run(
        [powershell, "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.fail(f"Windows speech synthesis failed: {result.stderr.strip()}")
    if not output_path.exists() or output_path.stat().st_size <= 44:
        pytest.fail("Windows speech synthesis did not create a valid WAV file")
    return output_path


def _pad_pcm_wav(source_path: Path, output_path: Path) -> Path:
    try:
        with wave.open(str(source_path), "rb") as source:
            params = source.getparams()
            frames = source.readframes(source.getnframes())
    except (wave.Error, OSError) as exc:
        pytest.fail(f"Could not read WAV microphone source {source_path}: {exc}")

    frame_width = params.sampwidth * params.nchannels
    leading_silence = b"\0" * int(params.framerate * 0.75) * frame_width
    trailing_silence = b"\0" * int(params.framerate * 2.0) * frame_width
    with wave.open(str(output_path), "wb") as output:
        output.setparams(params)
        output.writeframes(leading_silence)
        output.writeframes(frames)
        output.writeframes(trailing_silence)
    return output_path


def _convert_audio_with_ffmpeg(source_path: Path, output_path: Path) -> Path:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.fail(
            f"ffmpeg is required to use {source_path.suffix or 'this audio format'} as test input. "
            "Install ffmpeg or pass a PCM WAV file."
        )

    result = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(source_path),
            "-af",
            "adelay=750:all=1,apad=pad_dur=2",
            "-ar",
            "48000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.fail(f"ffmpeg could not prepare fake microphone audio: {result.stderr.strip()}")
    if not output_path.exists() or output_path.stat().st_size <= 44:
        pytest.fail("ffmpeg produced an empty fake microphone WAV file")
    return output_path


def _prepare_fake_microphone_wav(tmp_path: Path) -> Path:
    configured_path = os.environ.get("OMNIX_LIVE_VOICE_AUDIO", "").strip()
    source_path = Path(configured_path).expanduser() if configured_path else _synthesize_windows_audio(tmp_path)
    if not source_path.exists():
        pytest.fail(f"Live Voice audio input does not exist: {source_path}")

    output_path = tmp_path / "hows-it-going-fake-mic.wav"
    if source_path.suffix.lower() == ".wav" and not shutil.which("ffmpeg"):
        return _pad_pcm_wav(source_path, output_path)
    return _convert_audio_with_ffmpeg(source_path, output_path)


def _assert_stt_ready(stt_base_url: str) -> None:
    health_url = f"{stt_base_url.rstrip('/')}/health"
    try:
        with urllib.request.urlopen(health_url, timeout=10) as response:
            payload = json.load(response)
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        pytest.fail(f"Parakeet STT is not reachable at {health_url}: {exc}")

    details = payload.get("details") if isinstance(payload, dict) else None
    if not isinstance(details, dict) or details.get("model_loaded") is not True:
        pytest.fail(f"Parakeet STT responded but the model is not loaded: {payload!r}")


def _headed_mode(request: pytest.FixtureRequest) -> bool:
    try:
        return bool(request.config.getoption("--headed"))
    except ValueError:
        return False


def _is_chat_message_request(url: str, method: str) -> bool:
    return method == "POST" and urlparse(url).path.endswith("/messages")


@pytest.mark.e2e
@pytest.mark.skipif(
    not RUN_LIVE_TEST,
    reason="Run through --suite live_voice or set OMNIX_RUN_LIVE_VOICE_AUDIO=1",
)
def test_live_voice_uses_spoken_audio_as_fake_microphone(
    playwright: Playwright,
    request: pytest.FixtureRequest,
    tmp_path: Path,
) -> None:
    app_base_url = os.environ.get("OMNIX_BASE_URL", "http://127.0.0.1:5173").rstrip("/")
    stt_base_url = os.environ.get("OMNIX_STT_URL", "http://127.0.0.1:5201").rstrip("/")
    _assert_stt_ready(stt_base_url)
    wav_path = _prepare_fake_microphone_wav(tmp_path)

    parsed_app_url = urlparse(app_base_url)
    app_origin = f"{parsed_app_url.scheme}://{parsed_app_url.netloc}"
    browser = playwright.chromium.launch(
        headless=not _headed_mode(request),
        args=[
            "--use-fake-ui-for-media-stream",
            "--use-fake-device-for-media-stream",
            f"--use-file-for-fake-audio-capture={wav_path.resolve()}",
            "--autoplay-policy=no-user-gesture-required",
        ],
    )
    context = browser.new_context()
    context.grant_permissions(["microphone"], origin=app_origin)
    page = context.new_page()

    try:
        page.goto(f"{app_base_url}/chatbot", wait_until="domcontentloaded", timeout=30_000)
        live_card = page.locator(".assistant-live-card")
        expect(live_card).to_be_visible(timeout=30_000)

        with page.expect_request(
            lambda candidate: _is_chat_message_request(candidate.url, candidate.method),
            timeout=120_000,
        ) as message_request_info:
            live_card.get_by_role("button", name="Start Call").click()
            expect(live_card.locator("header strong")).to_have_text("Connected", timeout=15_000)

            page.wait_for_function(
                """() => {
                    const card = document.querySelector('.assistant-live-card');
                    if (!card) return false;
                    const level = Number.parseFloat(card.style.getPropertyValue('--voice-level') || '0');
                    return card.dataset.voiceInput === 'active' || level >= 0.14;
                }""",
                timeout=20_000,
            )

        message_request = message_request_info.value
        message_payload = message_request.post_data_json
        transcript_text = str(message_payload.get("content", "")).lower()
        normalized = re.sub(r"[^a-z0-9]+", " ", transcript_text).strip()
        assert "going" in normalized, f"Expected 'going' in automatically sent transcript, got: {transcript_text!r}"
        assert "how" in normalized or "hows" in normalized, (
            f"Expected 'how' in automatically sent transcript, got: {transcript_text!r}"
        )

        live_card.get_by_role("button", name="End Call").click()
        expect(live_card.get_by_role("button", name="Start Call")).to_be_visible(timeout=10_000)
    finally:
        context.close()
        browser.close()
