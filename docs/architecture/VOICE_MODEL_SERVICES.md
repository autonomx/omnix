# Voice model services

Every speech model that a Voice Studio phase adds runs in a model service, never in the worker process. Examples are ASR alignment, diarization, separation, enhancement, watermarking and OmniVoice. This rule is new with the Voice Studio parity roadmap (Phase 1 §4). ADR 0012 still lets a worker run local TTS in-process, but new models do not.

## A new service has

| Piece | Where | Precedent |
| --- | --- | --- |
| Its code | `src/services/<service>/<service>_server.py`, a FastAPI app | `src/services/tts/tts_server.py` |
| Its environment | `src/services/<service>/<service>.in`, compiled to `<service>.lock.txt` and `<service>.linux.lock.txt` | `src/services/stt/stt.in`, `src/services/audio/audio.in` |
| A conda environment | Built from the lock file by the setup scripts, never inside Docker Desktop | `rpg-tts`, `rpg-stt`, `fish-speech` |
| Launcher role | An interpreter role in `app/config/launcher.py` and a `ServiceSpec` with a fixed port in `app/composition/launcher/service_manager.py` | `tts` on 5101, `stt` on 5201 |
| Runtime URL | `OMNIX_<SERVICE>_URL` in the runtime config, with a required-service policy (ADR 0012) | `OMNIX_TTS_URL` |
| Authentication | `ModelServiceMiddleware`; callers send `service_headers()` | Every service |
| Errors the caller acts on | Return `200 {"ok": false, "code", "message"}` with a message written by the service. `ModelServiceMiddleware` replaces every 4xx/5xx body with `{"error": <status code>}`, so a `detail` never arrives; validation errors stay plain 400s | `/transcribe/timed`, the audio service |
| GPU arbitration | Report VRAM in `/health` (`gpu.vram_free_bytes`). Load through the swap controller, or as an exempt helper that fails fast when VRAM is short | The TTS service's `/api/tts/engine/swap` |

## Weights versus environments

- **Weights:** the Models tool installs these through the `models.install` job (`app/platform/voice/model_install.py`). Each model is listed with its licence in `app/platform/voice/model_catalog.py`. Weights come from the Hugging Face hub, pinned to the commit the requested revision resolves to, under `resources/models/<kind>/<repository name>`.
- **Environments:** the setup scripts and lock files build these. The install job never installs packages. When a model's environment is missing, the Models tool shows what to set up instead of an install button.
- **Shared environments:** where its torch version matches, a new model joins an existing service environment instead of adding one. For example, the diarizer and Parakeet-TDT share the STT environment.

## On one 24 GB GPU: swap, don't stack

| Kind of model | Examples | How it loads |
| --- | --- | --- |
| Resident | The selected TTS engine, live STT, a local LLM | Stays loaded. The local LLM is never swapped. |
| Swapped | VoiceDesign; OmniVoice when it isn't the selected engine | The swap controller loads it in place of the selected engine, under a fenced lease, and restores the engine afterwards. Live speech interrupts a swap. |
| Exempt helpers | Batch transcription and diarization, AudioSeal, the vocal-separation model, speech enhancement | Load beside the resident set when free VRAM allows, fail fast when it does not, and unload after an idle timeout (`services/helper_models.py`). Push-to-talk warms the batch transcription model (`POST /transcribe/timed/warm`) when a composer opens; it unloads on the same timeout. |

Host memory limits a swap as much as VRAM:
- On Windows, Fish S2 Pro's server takes about 24 GB of commit charge while it loads and serves.
- On the 4090 host, swapping it in beside resident services exhausted the commit limit, and the machine became unusable.
- The Fish provider and the swap controller refuse such a load quickly, with a reason, when host memory (plus 2 GB) is short. The TTS service reports host memory in `/health` (`host.commit_free_bytes`).

The controller, the live-session lease and the swap requests are described in the roadmap (Phase 1 §6) and implemented in `app/platform/voice/swap_controller.py` and `app/persistence/tts_swap.py`.

## Engines in their own environment

An engine whose dependencies cannot share the TTS environment runs as a child server of the process that owns TTS:
- OmniVoice uses `app/providers/child_model_server.py` (`ManagedChildServer`).
- Fish S2 Pro has the same lifecycle in its provider.

`start` launches the server and waits for its model; `stop` ends the process and releases its GPU memory. So the picker and the swap controller need nothing special. The child binds to loopback and requires the per-launch token its provider generates.

