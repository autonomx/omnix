"""Voice design (Voice Studio Phase 3): a voice from a written description, saved like any clone.

``voice.design`` renders up to three candidates of a preview sentence, one per
seed, on the VoiceDesign engine. The job pins that engine, so the swap
controller loads it in place of the selected engine (a TTS job already running
keeps its engine; live speech interrupts the swap) and holds it for a couple of
minutes after each preview, so one session never swaps back and forth.

``voice.design.save`` renders a 15-20 s reference passage with the chosen
description and seed and stores it through the clone pipeline as a library
voice tagged ``source: designed``. The passage is its transcript, so engines
that clone from exact words (Fish S2 Pro) need no STT.
"""
from __future__ import annotations

import base64
import random
from datetime import datetime, timezone
from typing import Any

DESIGN_ENGINE = "qwen3-tts-voicedesign"
MAX_DESCRIPTION_CHARS = 600
MAX_PREVIEW_CHARS = 300
MAX_CANDIDATES = 3
DEFAULT_PREVIEW = "Hello! This is how I sound. I hope you like my voice."

# About 50 words each: 15-20 seconds of speech, with varied sounds for cloning.
REFERENCE_PASSAGES = {
    "en": ("The old lighthouse keeper climbed the stairs every evening at six. He checked the lamp, wiped the "
           "salt from the glass, and wrote a short note in his journal. Some nights the sea was calm and quiet; "
           "other nights, waves crashed against the rocks until morning. He never once missed his watch."),
    "de": ("Der alte Leuchtturmwärter stieg jeden Abend um sechs die Treppe hinauf. Er prüfte die Lampe, wischte "
           "das Salz vom Glas und schrieb eine kurze Notiz in sein Tagebuch. Manche Nächte war das Meer ruhig; "
           "in anderen schlugen die Wellen bis zum Morgen gegen die Felsen."),
    "fr": ("Le vieux gardien du phare montait l'escalier chaque soir à six heures. Il vérifiait la lampe, "
           "essuyait le sel sur la vitre et écrivait une courte note dans son carnet. Certaines nuits, la mer "
           "était calme; d'autres, les vagues frappaient les rochers jusqu'au matin."),
    "es": ("El viejo guardián del faro subía la escalera cada tarde a las seis. Revisaba la lámpara, limpiaba la "
           "sal del cristal y escribía una breve nota en su diario. Algunas noches el mar estaba en calma; otras, "
           "las olas golpeaban las rocas hasta el amanecer."),
    "it": ("Il vecchio guardiano del faro saliva le scale ogni sera alle sei. Controllava la lampada, puliva il "
           "sale dal vetro e scriveva una breve nota nel suo diario. Alcune notti il mare era calmo; altre, le "
           "onde si infrangevano sugli scogli fino al mattino."),
    "pt": ("O velho faroleiro subia as escadas todas as noites às seis. Verificava a lâmpada, limpava o sal do "
           "vidro e escrevia uma pequena nota no seu diário. Em algumas noites o mar estava calmo; em outras, as "
           "ondas batiam nas rochas até de manhã."),
}


class DesignRequestError(ValueError):
    """The request cannot be designed as asked; retrying cannot help."""


def _text(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _language(value: Any) -> str:
    code = str(value or "en").strip().lower().split("-")[0].split("_")[0]
    return code or "en"


def _description(payload: dict[str, Any]) -> str:
    description = _text(payload.get("description"), MAX_DESCRIPTION_CHARS + 1)
    if not description:
        raise DesignRequestError("Describe the voice to design")
    if len(description) > MAX_DESCRIPTION_CHARS:
        raise DesignRequestError(f"Keep the description under {MAX_DESCRIPTION_CHARS} characters")
    return description


def _seeds(payload: dict[str, Any]) -> list[int]:
    raw = payload.get("seeds")
    if raw in (None, [], ""):
        return [random.randrange(1, 2 ** 31) for _ in range(MAX_CANDIDATES)]
    if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_CANDIDATES:
        raise DesignRequestError(f"Ask for one to {MAX_CANDIDATES} seeds")
    try:
        seeds = [int(seed) for seed in raw]
    except (TypeError, ValueError) as exc:
        raise DesignRequestError("Seeds are whole numbers") from exc
    if any(not 0 <= seed < 2 ** 31 for seed in seeds):
        raise DesignRequestError("Seeds are between 0 and 2147483647")
    return seeds


def _design_engine() -> Any:
    from app.providers.service import pinned_tts_provider

    from .swap_controller import swaps_enabled

    if not swaps_enabled():
        raise DesignRequestError(
            "Voice design runs in the TTS service, which swaps the design model in; "
            "start Omnix with the TTS service and PostgreSQL")
    return pinned_tts_provider(DESIGN_ENGINE)


def _render(engine: Any, text: str, *, description: str, seed: int, language: str) -> tuple[bytes, float]:
    from .effects import to_mono_pcm16

    result = engine.generate_audio(text, language=language, instruct=description, seed=seed)
    if not isinstance(result, dict) or not result.get("success"):
        detail = str(result.get("error") or "") if isinstance(result, dict) else ""
        raise RuntimeError(f"Voice design failed{': ' + detail if detail else ''}")
    wav = to_mono_pcm16(base64.b64decode(result.get("audio_base64") or result.get("audio") or ""))
    return wav, float(result.get("duration") or 0.0)


def execute_design_job(job: Any, *, job_store: Any = None) -> dict[str, Any]:
    """Render a preview sentence once per seed: the candidates to choose from."""
    from app.assets import AssetRecord, AssetType, default_asset_store
    from app.jobs.inline_execution import require_execution_authority
    from app.providers.tts_priority import generation_class
    from app.runtime.paths import resources_data_root

    from .watermarking import mark

    payload = job.input_payload or {}
    description = _description(payload)
    language = _language(payload.get("language"))
    # Without a sentence of its own, a candidate speaks the language's reference passage: saving it then
    # keeps 15-20 s of this exact voice to clone from (a short preview clones less faithfully).
    preview = (_text(payload.get("preview_text"), MAX_PREVIEW_CHARS) or REFERENCE_PASSAGES.get(language)
               or DEFAULT_PREVIEW)
    seeds = _seeds(payload)
    engine = _design_engine()
    output_dir = resources_data_root() / "voice_studio" / "design"
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_job = "".join(char if char.isalnum() or char in "-_" else "-" for char in job.id)
    refs = []
    with generation_class("preview"):
        for index, seed in enumerate(seeds):
            wav, duration = _render(engine, preview, description=description, seed=seed, language=language)
            wav, watermark = mark(wav)
            path = output_dir / f"{safe_job}-{index + 1}.wav"
            require_execution_authority(job_store, job.id)
            path.write_bytes(wav)
            asset = default_asset_store().upsert_asset(AssetRecord(
                id=f"audio:voice-design-{safe_job}-{index + 1}",
                module="voice",
                type=AssetType.AUDIO,
                mime_type="audio/wav",
                storage_path=str(path),
                metadata={"title": f"Design candidate {index + 1}", "kind": "voice_design_candidate",
                          "description": description, "seed": seed, "language": language, "text": preview,
                          "engine": DESIGN_ENGINE, "duration": duration,
                          **({"watermark": watermark} if watermark else {})},
                source_job_id=job.id,
                created_at=datetime.now(timezone.utc).isoformat(),
                compat={"contract": "voice_design_candidate_v1"},
            ))
            refs.append({"type": "audio", "kind": "voice_design_candidate", "asset_id": asset.id,
                         "title": f"Candidate {index + 1}", "audio_url": f"/api/assets/{asset.id}/audio",
                         "mime_type": "audio/wav", "duration": duration, "seed": seed,
                         "description": description, "language": language})
    return {"content": f"{len(refs)} voice candidates", "log_message": "Voice candidates designed",
            "output_refs": refs}


def _chosen_candidate(asset_id: str) -> tuple[bytes, str, float, dict[str, Any]]:
    """The candidate the person heard and chose: its audio, exact words, length and design record."""
    from app.assets import default_asset_store
    from app.assets.content import read_asset_bytes

    asset = default_asset_store().get_asset(asset_id)
    if asset is None or asset.metadata.get("kind") != "voice_design_candidate":
        raise DesignRequestError("Choose one of this workspace's design candidates")
    text = _text(asset.metadata.get("text"), MAX_PREVIEW_CHARS)
    if not text:
        raise DesignRequestError("That candidate has no recorded words; design it again")
    return (read_asset_bytes(asset, max_bytes=50 * 1024 * 1024), text, float(asset.metadata.get("duration") or 0.0),
            dict(asset.metadata))


def execute_design_save_job(job: Any, *, job_store: Any = None) -> dict[str, Any]:
    """Save the chosen candidate as a library voice (its own audio and words are the clone reference).

    Re-rendering with the same description and seed does not give the same voice on other words (a
    real-model check measured a speaker similarity of 0.31), so the voice saved is the one the person
    heard. Without a candidate (older callers), the reference passage is rendered with the seed.
    """
    from app.providers.qwen3_voice_design_provider import DESIGN_DEFAULTS, design_model_revision

    from .jobs import execute_clone_profile

    payload = job.input_payload or {}
    description = _description(payload)
    seeds = _seeds({"seeds": [payload.get("seed")]} if payload.get("seed") not in (None, "") else {})
    name = _text(payload.get("profile_name"), 80)
    if not name:
        raise DesignRequestError("Name the voice")
    language = _language(payload.get("language"))
    candidate = _text(payload.get("candidate_asset_id"), 200)
    if candidate:
        wav, passage, duration, made = _chosen_candidate(candidate)
        # The voice is the candidate: its language, description and seed, whatever the form shows now.
        return _save_designed(job, job_store, name=name, language=_language(made.get("language") or language),
                              description=str(made.get("description") or description),
                              seed=int(made["seed"]) if made.get("seed") is not None else seeds[0],
                              wav=wav, passage=passage, duration=duration, notes=payload.get("notes"),
                              defaults=DESIGN_DEFAULTS, revision=design_model_revision(),
                              save=execute_clone_profile)
    reference_passage = REFERENCE_PASSAGES.get(language)
    if reference_passage is None:
        raise DesignRequestError(f"No reference passage for {language!r} yet; design in "
                                 + ", ".join(sorted(REFERENCE_PASSAGES)))
    engine = _design_engine()
    from app.providers.tts_priority import generation_class

    with generation_class("offline"):
        wav, duration = _render(engine, reference_passage, description=description, seed=seeds[0],
                                language=language)
    return _save_designed(job, job_store, name=name, language=language, description=description, seed=seeds[0],
                          wav=wav, passage=reference_passage, duration=duration, notes=payload.get("notes"),
                          defaults=DESIGN_DEFAULTS, revision=design_model_revision(), save=execute_clone_profile)


def _save_designed(job: Any, job_store: Any, *, name: str, language: str, description: str, seed: int, wav: bytes,
                   passage: str, duration: float, notes: Any, defaults: dict[str, Any], revision: str,
                   save: Any) -> dict[str, Any]:
    design = {"description": description, "seed": seed, "language": language, "engine": DESIGN_ENGINE,
              "model_revision": revision, "parameters": dict(defaults), "reference_seconds": round(duration, 2)}
    clone_payload = {
        "profile_name": name,
        "language": language,
        "quality": "Draft",  # a synthetic reference has no room noise to check for
        "notes": _text(notes, 500) or f"Designed: {description}",
        "reference_text": passage,
        "source_kind": "designed",
        "source_file_name": f"{name}.wav",
        "provider_id": DESIGN_ENGINE,
        "design": design,
    }
    return save(job, clone_payload, wav, job_store=job_store)


def blend_engine_id() -> str:
    """The first catalogued engine that blends speaker embeddings (``VOICE_BLEND``), or empty."""
    from app.providers.catalog import VOICE_BLEND, specs

    return next((spec.id for spec in specs("tts") if VOICE_BLEND in spec.capabilities), "")


def _blend_parts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw = payload.get("voices")
    if not isinstance(raw, list) or not 2 <= len(raw) <= 4:
        raise DesignRequestError("Blend two to four library voices")
    parts = []
    for item in raw:
        voice = _text(item.get("voice") if isinstance(item, dict) else "", 200)
        try:
            weight = float(item.get("weight", 0)) if isinstance(item, dict) else 0.0
        except (TypeError, ValueError):
            weight = 0.0
        if not voice.startswith("voice-cloning:") or not 0 < weight <= 1:
            raise DesignRequestError("Each blended voice is a library voice with a weight above 0 and up to 1")
        parts.append({"speaker": voice, "weight": round(weight, 3)})
    if len({part["speaker"] for part in parts}) != len(parts):
        raise DesignRequestError("Blend different voices")
    return parts


def execute_blend_job(job: Any, *, job_store: Any = None) -> dict[str, Any]:
    """``voice.blend`` (§5): a library voice between two to four others, by mixing their speaker embeddings.

    The engine that exposes embeddings (``VOICE_BLEND``) reads the reference passage from the weighted
    mix; that recording, with the passage as its words, becomes an ordinary library voice, so it then
    renders on every engine.
    """
    from app.providers.service import pinned_tts_provider
    from app.providers.tts_priority import generation_class

    from .effects import to_mono_pcm16
    from .jobs import execute_clone_profile

    payload = job.input_payload or {}
    parts = _blend_parts(payload)
    name = _text(payload.get("profile_name"), 80)
    if not name:
        raise DesignRequestError("Name the voice")
    language = _language(payload.get("language"))
    passage = REFERENCE_PASSAGES.get(language)
    if passage is None:
        raise DesignRequestError(f"No reference passage for {language!r} yet; blend in "
                                 + ", ".join(sorted(REFERENCE_PASSAGES)))
    engine_id = blend_engine_id()
    if not engine_id:
        raise DesignRequestError("No installed engine can blend voices")
    engine = pinned_tts_provider(engine_id)
    with generation_class("offline"):
        result = engine.generate_audio(passage, speaker=parts[0]["speaker"], language=language, speaker_blend=parts)
    if not isinstance(result, dict) or not result.get("success"):
        detail = str(result.get("error") or "") if isinstance(result, dict) else ""
        raise RuntimeError(f"Blending failed{': ' + detail if detail else ''}")
    wav = to_mono_pcm16(base64.b64decode(result.get("audio_base64") or result.get("audio") or ""))
    clone_payload = {
        "profile_name": name,
        "language": language,
        "quality": "Draft",  # a synthetic reference has no room noise to check for
        "notes": _text(payload.get("notes"), 500) or "Blended: " + ", ".join(
            f"{part['speaker'].removeprefix('voice-cloning:')} {part['weight']:g}" for part in parts),
        "reference_text": passage,
        "source_kind": "blended",
        "source_file_name": f"{name}.wav",
        "provider_id": engine_id,
        "blend": {"voices": parts, "engine": engine_id, "language": language,
                  "reference_seconds": round(float(result.get("duration") or 0.0), 2)},
    }
    return execute_clone_profile(job, clone_payload, wav, job_store=job_store)


__all__ = [
    "DESIGN_ENGINE",
    "DesignRequestError",
    "REFERENCE_PASSAGES",
    "execute_design_job",
    "blend_engine_id",
    "execute_blend_job",
    "execute_design_save_job",
]
