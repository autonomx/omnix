# The System Assistant's first-run defaults

The desktop app's setup offers these to the System Assistant (`app/platform/characters/assistant_defaults.py`).

- `portrait.png`: the assistant's live-portrait face, the image the owner chose for the installer on 2026-11-26.
- `Maya.wav` and `Maya.json`: the assistant's voice, Maya. It is a designed voice, not a recording of anyone:
  Qwen3-TTS 1.7B VoiceDesign spoke the reference passage from the description and seed in `Maya.json`
  (2026-11-26). The installer ships it as the library voice `Maya` (`desktop/staging/stage.py`), in place of
  the development checkout's own `resources/voice_clones/Maya.wav`, which is not distributed.
