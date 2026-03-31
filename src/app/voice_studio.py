"""
Voice Studio Blueprint - Generate TTS audio with emotion controls.
Provides a POST /api/voice_studio/generate endpoint.
"""

import base64
import json
import os

from flask import Blueprint, jsonify, request

import app.shared as shared

voice_studio_bp = Blueprint("voice_studio", __name__)

EMOTION_MAP = {
    "neutral": {"speed": 1.0, "pitch": 0},
    "calm": {"speed": 0.9, "pitch": -1},
    "happy": {"speed": 1.1, "pitch": 2},
    "sad": {"speed": 0.85, "pitch": -2},
    "angry": {"speed": 1.2, "pitch": 1},
    "dramatic": {"speed": 0.95, "pitch": -1},
}

MAX_TEXT_LENGTH = 2000
SPEED_MIN = 0.7
SPEED_MAX = 1.5
PITCH_MIN = -5
PITCH_MAX = 5


@voice_studio_bp.route("/api/voice_studio/generate", methods=["POST"])
def generate_voice():
    data = request.json or {}

    text = data.get("text", "").strip()
    voice_id = data.get("voice_id")
    emotion = data.get("emotion", "neutral")

    # --- validation ---
    if not text:
        return jsonify({"success": False, "error": "Text is required"}), 400

    if len(text) > MAX_TEXT_LENGTH:
        return jsonify({"success": False, "error": f"Text must be {MAX_TEXT_LENGTH} characters or fewer"}), 400

    if not voice_id:
        return jsonify({"success": False, "error": "Voice is required"}), 400

    try:
        speed = float(data.get("speed", 1.0))
        pitch = float(data.get("pitch", 0))
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": "Speed and pitch must be numbers"}), 400

    if not (SPEED_MIN <= speed <= SPEED_MAX):
        return jsonify({"success": False, "error": f"Speed must be between {SPEED_MIN} and {SPEED_MAX}"}), 400

    if not (PITCH_MIN <= pitch <= PITCH_MAX):
        return jsonify({"success": False, "error": f"Pitch must be between {PITCH_MIN} and {PITCH_MAX}"}), 400

    # Apply emotion fallback if user didn't tweak controls
    if emotion in EMOTION_MAP:
        emo = EMOTION_MAP[emotion]
        if speed == 1.0:
            speed = emo["speed"]
        if pitch == 0:
            pitch = emo["pitch"]

    try:
        # Resolve speaker from voice_id via shared custom_voices
        clean_speaker = voice_id.replace(" (Custom)", "").strip()
        voice_clone_id = shared.custom_voices.get(clean_speaker, {}).get("voice_clone_id")
        final_speaker = voice_clone_id if voice_clone_id else clean_speaker

        tts_provider = shared.get_tts_provider()
        if not tts_provider:
            return jsonify({"success": False, "error": "No TTS provider available"}), 500

        # Generate audio via the existing TTS provider
        # Include speed, pitch, and emotion for providers that support them
        gen_kwargs = {"text": text, "speaker": final_speaker, "language": "en",
                      "speed": speed, "pitch": pitch, "emotion": emotion}

        if hasattr(tts_provider, "generate_tts"):
            result = tts_provider.generate_tts(**gen_kwargs)
        elif hasattr(tts_provider, "generate_audio"):
            result = tts_provider.generate_audio(**gen_kwargs)
        else:
            return jsonify({"success": False, "error": "TTS provider missing generation method"}), 500

        if not result or not result.get("success"):
            return jsonify({"success": False, "error": result.get("error", "TTS generation failed") if result else "TTS generation failed"}), 500

        audio_b64 = result.get("audio", "")

        return jsonify({
            "success": True,
            "audio_base64": audio_b64,
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@voice_studio_bp.route("/api/voice_studio/voices", methods=["GET"])
def list_voices():
    """Return available voices for the Voice Studio dropdown."""
    voices = []

    # Pull from shared custom_voices
    for vid, vdata in shared.custom_voices.items():
        voices.append({
            "id": vid,
            "name": vid,
            "gender": vdata.get("gender", "neutral"),
        })

    # Also try to include TTS provider built-in speakers
    tts_provider = shared.get_tts_provider()
    if tts_provider:
        try:
            if hasattr(tts_provider, "get_speakers"):
                for s in tts_provider.get_speakers():
                    sid = s.get("id", s.get("name", ""))
                    if sid and not any(v["id"] == sid for v in voices):
                        voices.append({"id": sid, "name": s.get("name", sid), "gender": "neutral"})
            elif hasattr(tts_provider, "get_voices"):
                for s in tts_provider.get_voices():
                    sid = s.get("id", s.get("name", ""))
                    if sid and not any(v["id"] == sid for v in voices):
                        voices.append({"id": sid, "name": s.get("name", sid), "gender": "neutral"})
        except Exception:
            pass

    # Ensure at least one default voice is available
    if not voices:
        voices.append({"id": "default", "name": "Default", "gender": "neutral"})

    return jsonify({"success": True, "voices": voices})


@voice_studio_bp.route("/api/voice_clone", methods=["POST"])
def create_voice_clone():
    """Create a new voice clone from uploaded audio."""
    try:
        voice_id = request.form.get("voice_id") or request.form.get("name")
        gender = request.form.get("gender", "neutral")
        language = request.form.get("language", "en")
        ref_text = request.form.get("ref_text", "")

        if not voice_id:
            return jsonify({"success": False, "error": "Voice name is required"}), 400

        if gender not in ("male", "female", "neutral"):
            gender = "neutral"

        voice_id_clean = voice_id.strip()

        # Save audio file if provided
        clones_dir = shared.VOICE_CLONES_DIR
        os.makedirs(clones_dir, exist_ok=True)

        audio_file = request.files.get("file")
        if audio_file:
            audio_bytes = audio_file.read()
            if audio_bytes:
                wav_path = os.path.join(clones_dir, f"{voice_id_clean}.wav")
                with open(wav_path, "wb") as f:
                    f.write(audio_bytes)

                tts_provider = shared.get_tts_provider()
                if tts_provider and hasattr(tts_provider, "voice_clone"):
                    tts_provider.voice_clone(voice_id_clean, audio_bytes, ref_text)

        # Register in custom_voices
        shared.custom_voices[voice_id_clean] = {
            "speaker": "default",
            "language": language,
            "voice_clone_id": voice_id_clean,
            "has_audio": True,
            "is_preloaded": True,
            "gender": gender,
        }

        with open(shared.VOICE_CLONES_FILE, "w") as wf:
            json.dump(shared.custom_voices, wf, indent=2)

        return jsonify({"success": True, "voice_id": voice_id_clean})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
