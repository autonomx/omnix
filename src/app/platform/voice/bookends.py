"""Opening and closing a studio take: a short synthesized sting before and after it, and a bed of room tone.

Both are opt-in per render (``bookends`` and ``room_tone`` in the payload) and deterministic: the sting is a
fixed arpeggio and the room tone comes from a fixed seed, so the same take always masters to the same bytes.
They are applied to the assembled take before the effects chain and the volume setting, so the sting is
mastered with the voices. Studio renders only: podcasts use them, live speech never does.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .effects import read_mono, write_mono

# The sting's loudness follows the take: its RMS sits this far under the voices' speaking level, so it is clearly
# heard and frames the episode without being louder than a line. (A fixed -20 dBFS peak played ~16 dB under the
# voices and was easy to miss.) Its peak never passes STING_MAX_PEAK_DBFS.
STING_UNDER_SPEECH_DB = 6.0
STING_MAX_PEAK_DBFS = -3.0
# A take with no speech to measure (all silence) gets the sting at this peak.
STING_PEAK_DBFS = -20.0
# Speaking level: the RMS of the 50 ms frames louder than the floor, so pauses don't pull it down.
_LEVEL_FRAME_SECONDS = 0.05
_LEVEL_FLOOR_DBFS = -45.0
# Room tone is barely there: it fills the digital silence between lines so pauses sound like a room.
ROOM_TONE_RMS_DBFS = -60.0
ROOM_TONE_SEED = 20261124
# The room tone is one tile of noise repeated (see ``room_tone``).
ROOM_TONE_TILE_SECONDS = 30.0
# Silence between the sting and the first line, and between the last line and the closing sting.
INTRO_GAP_SECONDS = 0.4
OUTRO_GAP_SECONDS = 0.8

# A major chord (A3, C#4, E4, A4) played upward to open and downward to close.
_CHORD_HZ = (220.0, 277.18, 329.63, 440.0)
_NOTE_SPACING_SECONDS = 0.18
_NOTE_SECONDS = 2.4
_FADE_SECONDS = 0.02


@dataclass(frozen=True)
class Bookended:
    wav_bytes: bytes
    # Seconds added before the first line; timeline entries shift by this much.
    lead_seconds: float


def _db_to_amplitude(dbfs: float) -> float:
    return float(10.0 ** (dbfs / 20.0))


def active_level_dbfs(samples: np.ndarray, rate: int) -> float | None:
    """The RMS of the sound's audible frames in dBFS, or None when nothing rises above the floor."""
    frame = max(1, int(rate * _LEVEL_FRAME_SECONDS))
    count = samples.size // frame
    if not count:
        return None
    levels = np.sqrt(np.mean(samples[:count * frame].reshape(count, frame) ** 2, axis=1))
    audible = levels[levels > _db_to_amplitude(_LEVEL_FLOOR_DBFS)]
    if not audible.size:
        return None
    return float(20.0 * np.log10(np.sqrt(np.mean(audible ** 2))))


def sting_for(samples: np.ndarray, rate: int, *, rising: bool) -> np.ndarray:
    """The sting leveled to the take: its RMS (over its whole length; it has no pauses) ``STING_UNDER_SPEECH_DB``
    under the take's speaking level, its peak no higher than ``STING_MAX_PEAK_DBFS``."""
    speech = active_level_dbfs(samples, rate)
    if speech is None:
        return sting(rate, rising=rising)
    shape = sting(rate, rising=rising, peak_dbfs=0.0)
    rms = float(np.sqrt(np.mean(shape ** 2))) or 1.0
    gain = min(_db_to_amplitude(speech - STING_UNDER_SPEECH_DB) / rms,
               _db_to_amplitude(STING_MAX_PEAK_DBFS) / (float(np.max(np.abs(shape))) or 1.0))
    return shape * gain


def sting(rate: int, *, rising: bool = True, peak_dbfs: float = STING_PEAK_DBFS) -> np.ndarray:
    """A soft arpeggiated chord, about three seconds, peaking at ``peak_dbfs``."""
    notes = _CHORD_HZ if rising else tuple(reversed(_CHORD_HZ))
    length = int(rate * (_NOTE_SPACING_SECONDS * (len(notes) - 1) + _NOTE_SECONDS))
    out = np.zeros(length, dtype=np.float64)
    note_length = int(rate * _NOTE_SECONDS)
    t = np.arange(note_length) / rate
    attack = np.minimum(1.0, t / 0.03)
    decay = np.exp(-t * 2.2)
    for position, frequency in enumerate(notes):
        # A sine with a quiet octave gives a soft bell rather than a test tone.
        tone = np.sin(2 * np.pi * frequency * t) + 0.25 * np.sin(2 * np.pi * 2 * frequency * t)
        start = int(rate * _NOTE_SPACING_SECONDS * position)
        out[start:start + note_length] += tone * attack * decay
    fade = max(1, int(rate * _FADE_SECONDS))
    out[-fade:] *= np.linspace(1.0, 0.0, fade)
    peak = float(np.max(np.abs(out))) or 1.0
    return out * (_db_to_amplitude(peak_dbfs) / peak)


def room_tone(length: int, rate: int) -> np.ndarray:
    """Seeded, darkened noise at ``ROOM_TONE_RMS_DBFS`` RMS (energy mostly under ~1 kHz, like a quiet room).

    It is made once as a tile of at most ``ROOM_TONE_TILE_SECONDS`` and repeated: filtering in the frequency domain
    is circular, so the tile loops without a seam, and an hour-long episode no longer transforms an hour of noise
    (gigabytes of spectra)."""
    if length <= 0:
        return np.zeros(0, dtype=np.float64)
    tile_length = min(length, max(1, int(rate * ROOM_TONE_TILE_SECONDS)))
    noise = np.random.default_rng(ROOM_TONE_SEED).standard_normal(tile_length)
    spectrum = np.fft.rfft(noise)
    frequencies = np.fft.rfftfreq(tile_length, 1.0 / rate)
    spectrum *= 1.0 / (1.0 + (frequencies / 900.0) ** 2)
    tile = np.fft.irfft(spectrum, n=tile_length)
    rms = float(np.sqrt(np.mean(tile ** 2))) or 1.0
    tile *= _db_to_amplitude(ROOM_TONE_RMS_DBFS) / rms
    return tile if tile_length == length else np.resize(tile, length)


def add_bookends(wav_bytes: bytes, *, stings: bool, tone: bool) -> Bookended:
    """The take with a sting before and after it and/or room tone under it; unchanged when both are off."""
    if not stings and not tone:
        return Bookended(wav_bytes=wav_bytes, lead_seconds=0.0)
    samples, rate = read_mono(wav_bytes)
    lead = 0.0
    if stings:
        opening = sting_for(samples, rate, rising=True)
        closing = sting_for(samples, rate, rising=False)
        intro_gap = np.zeros(int(rate * INTRO_GAP_SECONDS))
        outro_gap = np.zeros(int(rate * OUTRO_GAP_SECONDS))
        samples = np.concatenate([opening, intro_gap, samples, outro_gap, closing])
        lead = (opening.size + intro_gap.size) / rate
    if tone:
        samples = samples + room_tone(samples.size, rate)
    return Bookended(wav_bytes=write_mono(samples, rate), lead_seconds=lead)
