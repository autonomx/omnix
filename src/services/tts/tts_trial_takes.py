"""Takes of test lines from a clip that is not a library voice, measured: how much of each was spoken.

A clone's sample is tried in a few sections this way, and the clone keeps the section whose takes speak best (the
clone job's ``clip_selection``). On 2026-11-05 a clip of Jinx cut to end on a whole word went from 26 silent takes in
240 to 3 in 180; this does that choice for every new voice.

Takes use the live call's settings, so they fail the way live phrases would. Live speech always goes first: each take
waits for a batch-priority device permit.
"""
from __future__ import annotations

import asyncio
import base64
import io
import tempfile
import wave
from pathlib import Path
from typing import Annotated, Any

import numpy as np
# At module level: the route's annotations are strings (postponed), resolved against this module's names.
from fastapi import File, Form, HTTPException, UploadFile

# As a live call asks for a phrase (live_voice speech settings): the takes should fail as live phrases would.
TRIAL_SETTINGS: dict[str, Any] = {
    "chunk_size": 4, "temperature": 0.6, "top_k": 20, "top_p": 0.85, "repetition_penalty": 1.05,
    "append_silence": False,
}
MAX_TRIAL_TAKES = 64
MAX_TRIAL_LINE_CHARS = 200
_FRAME_SECONDS = 0.08
_QUIET_RMS = 0.015
_LIKENESS_RATE = 16_000


def token_budget(text: str) -> int:
    """The live path's budget for a phrase of this length (12.5 codec steps a second)."""
    return max(24, round(41 + (len(text) - 15) * 1.167))


def measure(audio: np.ndarray, rate: int) -> dict[str, float]:
    """Seconds, seconds with voice in them, and the quiet before the voice starts."""
    frame = max(1, int(rate * _FRAME_SECONDS))
    usable = len(audio) // frame * frame
    if not usable:
        return {"seconds": round(len(audio) / max(1, rate), 3), "voiced_seconds": 0.0, "lead_seconds": 0.0}
    levels = np.sqrt((audio[:usable].reshape(-1, frame).astype(np.float64) ** 2).mean(axis=1))
    voiced = levels >= _QUIET_RMS
    lead_frames = int(np.argmax(voiced)) if voiced.any() else len(levels)
    return {
        "seconds": round(len(audio) / rate, 3),
        "voiced_seconds": round(float(voiced.sum()) * _FRAME_SECONDS, 3),
        "lead_seconds": round(lead_frames * _FRAME_SECONDS, 3),
    }


def wav_16k(audio: np.ndarray, rate: int) -> bytes:
    """The take as 16 kHz mono PCM, for a speaker embedding against the sample (small enough to send back)."""
    if rate != _LIKENESS_RATE and len(audio):
        positions = np.linspace(0, len(audio) - 1, int(len(audio) * _LIKENESS_RATE / rate))
        audio = np.interp(positions, np.arange(len(audio)), audio)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(_LIKENESS_RATE)
        target.writeframes((np.clip(audio, -1.0, 1.0) * 32767).astype("<i2").tobytes())
    return buffer.getvalue()


def render_take(provider: Any, reference: str, ref_text: str, text: str, language: str) -> tuple[np.ndarray, int]:
    """One take of ``text`` in the voice of the clip at ``reference``."""
    chunks: list[np.ndarray] = []
    rate = 24_000
    for chunk, chunk_rate, _timing in provider.generate_audio_stream(
        text=text, speaker=None, language=language, reference_audio=reference, ref_text=ref_text,
        max_new_tokens=token_budget(text),
        # The route holds the take's permit: the engine taking its own waited for itself (DevicePermitUnavailable).
        _device_permit_held=True,
        **TRIAL_SETTINGS,
    ):
        if chunk is None:
            continue
        rate = int(chunk_rate or rate)
        chunks.append(np.asarray(chunk, dtype=np.float32).reshape(-1))
    return (np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)), rate


def parse_lines(raw: str, takes: int) -> list[str]:
    """The test lines, checked: a JSON list of short strings, at most MAX_TRIAL_TAKES takes in all."""
    import json

    lines = json.loads(raw)
    if not isinstance(lines, list) or not lines or not all(isinstance(line, str) and line.strip() for line in lines):
        raise ValueError("phrases must be a non-empty list of text")
    if any(len(line) > MAX_TRIAL_LINE_CHARS for line in lines) or not 1 <= takes <= 4:
        raise ValueError("a test line is too long, or takes is not 1 to 4")
    if len(lines) * takes > MAX_TRIAL_TAKES:
        raise ValueError(f"at most {MAX_TRIAL_TAKES} takes")
    return [line.strip() for line in lines]


TRIAL_TAKE_PERMIT_SECONDS = 120.0


def install_trial_takes(app: Any, server: Any) -> None:
    """Add ``POST /api/tts/trial_takes`` to the TTS service. ``server`` is the service module, read per request."""
    @app.post("/api/tts/trial_takes")
    async def trial_takes(
        file: Annotated[UploadFile, File()],
        phrases: Annotated[str, Form()],
        ref_text: Annotated[str, Form()] = "",
        takes: Annotated[int, Form()] = 2,
        language: Annotated[str, Form()] = "English",
    ) -> dict[str, Any]:
        """Takes of test lines from a clip that is not a library voice, each measured.

        The clip is never saved as a voice: it lives in a temporary folder for the request, and what the engine
        prepared for it is dropped afterwards. Answers travel as 200 envelopes, as the model-service middleware
        replaces error bodies: ``trial_unsupported`` (the loaded engine cannot clone from a given clip) and ``busy``
        (live speech kept the engine longer than a take may wait).
        """
        audio = await file.read(server._MAX_VOICE_CLONE_BYTES + 1)
        if not audio or len(audio) > server._MAX_VOICE_CLONE_BYTES:
            raise HTTPException(status_code=422, detail="reference_audio_required")
        try:
            lines = parse_lines(phrases, takes)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        provider = server._TTS_PROVIDER
        if provider is None or not getattr(provider, "supports_reference_trials", False):
            return {"ok": False, "code": "trial_unsupported", "engine": server._TTS_PROVIDER_NAME}
        results: list[dict[str, Any]] = []
        with tempfile.TemporaryDirectory(prefix="omnix-tts-trial-") as folder:
            reference = str(Path(folder) / "reference.wav")
            Path(reference).write_bytes(audio)
            try:
                for line_index, text in enumerate(lines):
                    for take in range(takes):
                        # One take at a time, each behind live speech in the permit queue.
                        permit = server.device_permit_slot(
                            "tts", priority="batch", timeout_seconds=TRIAL_TAKE_PERMIT_SECONDS,
                        )
                        try:
                            await server._enter_device_permit(permit)
                        except server.DevicePermitError:
                            return {"ok": False, "code": "busy"}
                        try:
                            try:
                                server._begin_generation()
                            except server.EngineLoading:
                                return {"ok": False, "code": "busy"}
                            try:
                                samples, rate = await server._synthesis().run(
                                    render_take, provider, reference, ref_text, text, language,
                                )
                            finally:
                                server._end_generation()
                        finally:
                            await asyncio.to_thread(permit.__exit__, None, None, None)
                        results.append({
                            "line": line_index, "take": take, "text_chars": len(text), **measure(samples, rate),
                            "audio_16k": base64.b64encode(wav_16k(samples, rate)).decode("ascii"),
                        })
            finally:
                await asyncio.to_thread(provider.forget_reference, reference)
        return {"ok": True, "engine": server._TTS_PROVIDER_NAME, "takes": results}


__all__ = [
    "MAX_TRIAL_TAKES", "TRIAL_SETTINGS", "install_trial_takes", "measure", "parse_lines", "render_take",
    "token_budget", "wav_16k",
]
