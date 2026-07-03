"""End-to-end live voice test using a bundled spoken MP3 fixture.

Run the local Parakeet STT service, gateway, and Vite web app, then execute:

    set OMNIX_RUN_LIVE_VOICE_AUDIO=1
    set OMNIX_BASE_URL=http://127.0.0.1:5173
    set OMNIX_STT_URL=http://127.0.0.1:5201
    python run_playwright_tests.py --suite live_voice --headed --no-report

The test decodes ``hows-it-going.mp3.b64``, converts it to a Chromium-compatible
WAV microphone source, starts a real Live Voice call, verifies the input meter
reacts, and waits for a user transcript containing "How's it going?".
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

import pytest
from playwright.sync_api import Playwright, expect

AUDIO_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "audio" / "hows-it-going.mp3.b64"
AUDIO_SHA256 = "493cb931c93f7fd6d90f31180e171ccebc924a17290fa8a744d3ec978d86a919"
RUN_LIVE_TEST = os.environ.get("OMNIX_RUN_LIVE_VOICE_AUDIO", "0") == "1"


def _load_mp3_fixture() -> bytes:
    encoded = "".join(AUDIO_FIXTURE.read_text(encoding="ascii").split())
    return base64.b64decode(encoded, validate=True)


def _prepare_fake_microphone_wav(tmp_path: Path) -> Path:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.fail("ffmpeg is required to convert the MP3 fixture into Chromium fake microphone WAV input")

    mp3_path = tmp_path / "hows-it-going.mp3"
    wav_path = tmp_path / "hows-it-going-fake-mic.wav"
    mp3_path.write_bytes(_load_mp3_fixture())

    result = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(mp3_path),
            "-af",
            "atempo=0.9,adelay=500:all=1,apad=pad_dur=2",
            "-ar",
            "48000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(wav_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.fail(f"ffmpeg could not prepare fake microphone audio: {result.stderr.strip()}")
    if not wav_path.exists() or wav_path.stat().st_size <= 44:
        pytest.fail("ffmpeg produced an empty fake microphone WAV file")
    return wav_path


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


def test_hows_it_going_audio_fixture_is_stable() -> None:
    audio = _load_mp3_fixture()
    assert audio.startswith(b"ID3")
    assert len(audio) == 5840
    assert hashlib.sha256(audio).hexdigest() == AUDIO_SHA256


@pytest.mark.e2e
@pytest.mark.skipif(
    not RUN_LIVE_TEST,
    reason="Set OMNIX_RUN_LIVE_VOICE_AUDIO=1 to run the real microphone/STT browser test",
)
def test_live_voice_uses_mp3_as_fake_microphone(
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

        user_transcript = live_card.locator(".assistant-voice-transcript p.user").last
        expect(user_transcript).to_be_visible(timeout=120_000)
        transcript_text = user_transcript.inner_text().lower()
        normalized = re.sub(r"[^a-z0-9]+", " ", transcript_text).strip()
        assert "going" in normalized, f"Expected 'going' in live transcript, got: {transcript_text!r}"
        assert "how" in normalized or "hows" in normalized, (
            f"Expected 'how' in live transcript, got: {transcript_text!r}"
        )

        live_card.get_by_role("button", name="End Call").click()
        expect(live_card.get_by_role("button", name="Start Call")).to_be_visible(timeout=10_000)
    finally:
        context.close()
        browser.close()
