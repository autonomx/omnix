# Omnix Desktop App Roadmap

**Revision 4, 2026-10-22. Status: implemented on branch `electron`; see §11 for results and open items.** A standalone Omnix desktop app for Windows and
macOS, shipped as a small installer. On first run it guides the user through downloading the GPU runtime and the
AI models their machine can run. The browser deployment stays as it is; the desktop app is an additional way to run
Omnix. Review history is in §10.

## 1. Goal

A user downloads one installer of a few hundred MB, installs it, and has a working Omnix with no Docker, no Python,
no PostgreSQL and no Conda to set up. Chat works right away with a provider API key. A setup screen then shows what
the machine can run: voice input, voice output, transcription, image generation. The user picks what to download,
accepts each model's licence, and Omnix fetches the runtime and weights in the background. The same screen stays
available later under Settings → Models.

## 2. Owner decisions

| ID | Decision |
|----|----------|
| D-1 | **Additional to the web app, in this repository.** The desktop app runs the same `web` build against a local gateway. It lives in `desktop/` in the Omnix repository; unlike MarketPulse it is not a fork, and nothing is synced. |
| D-2 | **The installer has no models and no GPU runtime.** It ships the Electron shell, CPython, PostgreSQL, the gateway, the web build, and a few small prebuilt wheels (§4.3). |
| D-3 | **Guided setup.** A setup screen detects the hardware and offers runtime packs and model packs with sizes, requirements and a compatibility verdict for this machine. The user chooses; nothing large is downloaded without a choice. |
| D-4 | **The user accepts each model's licence in the app** before it is downloaded, and the acceptance is recorded. This replaces today's Voice Studio rule, which asks only for gated or non-commercial models, so there is one rule everywhere (§4.5). |
| D-5 | **macOS speech-to-text uses Parakeet-MLX** (owner decision, 2026-10-21). |
| D-6 | **One shared Torch layer** (`torch` and `torchaudio`) for every GPU service on a platform, with per-service overlays (§4.3). Phase 0 confirms it before anything is built on it. |
| D-7 | **One model catalog.** `src/app/models/catalog.json` grows into catalog v2 (§4.6) and absorbs the Voice Studio speech-model registry, so every model has a pinned revision, file hashes, licence, requirements and platform variants. The schema change is accepted. |
| D-8 | **Windows first, then macOS on Apple Silicon** (§7 Q-1 covers Intel Macs). |
| D-9 | **MarketPulse's shell and staging are the starting point.** Copy `desktop/` and `build/stage.py` from MarketPulse and adapt them. Pull shared code into a common package only after both apps settle. |

## 3. Facts the plan rests on

Checked against `main` at `341229c74b` on 2026-10-22.

**Model management today.** There are three downloaders, and the plan merges the first two:

1. **`app.models`** (Docker deployment). `src/app/models/catalog.json` pins a Hugging Face commit per model and the
   SHA-256 and size of every file a service reads. `python -m app.models download [ids] [--service tts|stt|image]`
   fills the Hugging Face cache, points its `main` ref at the pinned commit, and the services run with
   `HF_HUB_OFFLINE=1` (`docs/roadmap/DECISIONS.md`, WP-11.1). `verify()` re-checks the hashes.
2. **The Voice Studio speech-model manager.**
   - `src/app/platform/voice/model_catalog.py` (`SpeechModel`) lists TTS, STT and audio models with licence,
     `commercial_use`, `gated`, `size_gb`, `vram_gb`, residency and capabilities.
   - `model_install.py` runs `models.install` / `models.remove` as jobs (owner or admin). It resolves the revision
     (mostly `main`) to a commit at install time, downloads into `resources/models/<kind>/<repo>`, and writes the
     acceptance, licence and commit into `.omnix-model.json`. It has no file hashes.
   - The Hugging Face token is stored through `provider_secret_store.save_model_hub_token`
     (`PUT /api/voice/models/hub-token`). Models are listed at `GET /api/voice/models`.
   - The UI is `web/src/features/voice/SpeechModelsPanel.tsx`: Install, Update, Remove, an accept checkbox, and setup
     commands.
3. **Memory v2 embeddings** (`assistant_memory/v2/embeddings.py`): its own pinned revision and SHA-256 checks, under
   `resources_models_root()`. It stays as it is.

The image service has its own download route (`platform/image/downloads.py`): `snapshot_download` of a `repo_id`
from user settings, with no revision and no hashes.

**Sizes** (sum of the catalogued files in `app.models`, plus `SpeechModel.size_gb` estimates):

| Model | Used for | Download |
|-------|----------|----------|
| `nemotron-speech-streaming-en-0.6b` + `parakeet-realtime-eou-120m-v1` | Live voice input. Both load together: Nemotron gives the transcript and the EOU model detects the end of an utterance (`nemotron_eou_streaming.py:277-298`). | 2.47 + 0.46 = 2.93 GB |
| `qwen3-tts-12hz-0.6b-base` | Voice output | 2.52 GB |
| `parakeet-tdt-0.6b-v3`, `titanet-large`, `sortformer-4spk-v1` (non-commercial) | STT page: transcription, word timestamps, diarization | ≈2.4, 0.1, 0.5 GB (estimates; not yet hashed) |
| `flux2-klein-4b` | Image generation | 16.0 GB |
| `flux2-klein-base-4b` | Image generation (base) | 16.0 GB. Its text encoder and VAE are byte-identical to `flux2-klein-4b`, but the Hugging Face cache stores them per repository. |

**Service locks.**
- **Torch.** Every GPU service lock (STT, TTS, image, audio, omnivoice) pins `torch==2.6.0+cu124` and
  `torchaudio==2.6.0+cu124`. STT, image and audio also pin `torchvision==0.21.0+cu124`; TTS and omnivoice do not.
- **The owner's TTS environment is not on the lock.** `rpg-tts` runs torch and torchaudio `2.5.1+cu124`, although
  `tts.lock.txt` pins 2.6.0. TTS on 2.6.0 has not run on this workstation; DT-0.1 is its first run.
- **Other pins differ**, so one combined environment does not work:

  | Package | TTS | STT | Image | Omnivoice |
  |---------|-----|-----|-------|-----------|
  | numpy | 1.26.4 | 2.4.6 | 1.26.4 | 2.4.6 |
  | transformers | 4.57.3 | 4.57.6 | 4.57.6 | 5.20.2 |
  | huggingface-hub | 0.34.6 | 0.36.2 | 0.36.2 | 2.2.0 |
  | accelerate | 1.12.0 | 1.15.0 | 1.12.0 | 1.15.0 |
  | filelock / fsspec (Torch's own dependencies) | 3.32.7 / 2026.9.0 | 4.0.6 / 2024.12.0 | — | 4.2.4 / 2026.9.0 |

- **How the Windows locks are built.** They are compiled against the PyTorch CUDA 12.4 index (`--extra-index-url
  https://download.pytorch.org/whl/cu124 --generate-hashes`). The Windows CUDA wheels carry the CUDA libraries inside
  `torch/lib`; the user needs an NVIDIA driver, not the CUDA Toolkit.
- **The STT lock also pins `cuda-bindings==13.4.3` and `cuda-pathfinder`** (CUDA 13 Python bindings, used by NeMo).
- **Some STT packages ship only as source archives** (no wheels on PyPI): `antlr4-python3-runtime==4.9.3`,
  `wget==3.2`, and possibly `kaldi-python-io` and `sox`. A plain `pip install` builds them on the user's machine.
- **The image service runs on the gateway's interpreter.** `image.in` starts with `-r requirements/gateway.in`, and
  in `src/app/config/launcher.py` the `app` role (`RPG_FLUX_PYTHON`) is the interpreter for both the gateway and the
  image service. So the developer launcher cannot point the image service at a separate pack. The desktop supervisor
  starts services itself (§4.2).
- **The launcher wires the services' environment** (`composition/launcher/service_manager.py`):
  - **Token.** It issues `OMNIX_SERVICE_TOKEN` to each service; `ModelServiceMiddleware` (`security/service_token.py`)
    refuses every call but `/health` without it.
  - **Run token key.** It removes `OMNIX_RUN_TOKEN_KEY` from service processes.
  - **Ports and URLs.** It sets `OMNIX_TTS_URL` / `OMNIX_STT_URL` / `OMNIX_IMAGE_URL` / `OMNIX_IMAGE_ENABLED` for the
    gateway, and the service ports and `OMNIX_IMAGE_SERVICE_MODE=1` for the services.
  - **Model folder.** It sets `OMNIX_TTS_MODEL_DIR` / `OMNIX_QWEN3_TTS_MODEL_DIR`, defaulting to the checkout's
    `resources/models/tts/…`.
  - **Port killing.** It sets `OMNIX_LAUNCHER_KILL_PORT=1`, with which `tts_server.py` kills whatever process owns its
    port.
  - **Database.** The TTS, STT and image services also open PostgreSQL (device permits, settings) and need
    `OMNIX_DATABASE_URL`.
- **Weights are read two ways.** Live STT loads by repository id from the Hugging Face cache
  (`nemotron_eou_streaming.py:292,297`); TTS loads from the folder in `OMNIX_TTS_MODEL_DIR`.

**Hardware and devices.**
- `src/app/providers/gpu_report.py` imports Torch. The setup screen runs before any Torch is installed, so it needs a
  Torch-free probe (§4.4).
- The Qwen3-TTS loader (`providers/vendor/qwen3_tts/loader.py:215-232`) accepts `cuda`, `cpu` and `mps`. It defaults
  to CUDA and falls back to CPU; it never chooses MPS by itself.
- The only registered Qwen3-TTS providers are `faster-qwen3-tts` and the VoiceDesign provider
  (`providers/catalog.py:108,120`). The faster provider uses CUDA graphs only on a CUDA device
  (`vendor/faster_qwen3_tts/model.py:452-453`), so on `mps` they are off with no extra switch.

**Desktop seams already on `main`** (merged from MarketPulse 2026-10-17):
- `OMNIX_RESOURCES_DIR` (`runtime/paths.py`)
- the Keychain secret backend (`security/keychain.py`) and DPAPI stores at overridable paths
- desktop Google sign-in and `OMNIX_AUTH_LAUNCHER_FIRST_PASSWORD`
- `web/src/shared/desktopBridge.ts`

**MarketPulse's measured sizes** (trading-only reduced mirror, 2026-10-17): 161 MB installer, 571 MB installed,
16 s from start to ready. MarketPulse's `build/stage.py` prunes pip and setuptools from the staged interpreter and
isolates it with `python311._pth`.

**Agents and trading.**
- **Agents.** Sandboxed write-capable agent runs need Docker and an image built from
  `deploy/docker/agent-sandbox.Dockerfile`. Read-only runs already work on the host without Docker
  (`agent_runtime/isolation.py:333-335`). `OMNIX_AGENT_ALLOW_UNSANDBOXED` exists. The launcher sets
  `OMNIX_AGENT_DEFAULT_REPOSITORY` to the checkout root.
- **Trading.** The research handoff importer is on unless `OMNIX_TRADING_PROSPECTIVE_GAP_HANDOFF_IMPORT=0`
  (`prospective_gap_inputs.py:228`).

**Pages.** `/models` is the LLM provider and model page (`/api/models`, `settings:*` permissions), not a weights
manager.

## 4. Architecture

### 4.1 What ships and what is downloaded

| Piece | How the user gets it | Size |
|-------|----------------------|------|
| Electron shell, CPython 3.11, PostgreSQL 17, gateway, web build | Installer | 250–350 MB download (estimate; measured in DT-3.4) |
| Prebuilt wheels for source-only packages, the `installer` wheel, all desktop lock files and catalog v2 | Installer | small |
| **ffmpeg** (an LGPL build, pinned and hashed, with its licence in `NOTICE`) | Installer: core features need it without any pack (STT upload decoding, transcription, audiobook and voice export, dubbing) | tracked in DT-3.4 |
| Memory v2 embeddings | Installer, or the first item of setup (its existing pinned downloader) | small |
| **GPU runtime**: the Torch layer (§4.3) | Setup screen, pulled in by the first model that needs it | Windows CUDA: about 2.5 GB download; macOS: small |
| **Service runtimes**: the STT, TTS and image overlays | Setup screen, pulled in by their models | measured in DT-0.1 |
| **Models** (weights) | Setup screen, from Hugging Face at the pinned revision | §3 table |
| NVIDIA driver | The user, from NVIDIA; the setup screen links to it | — |
| Chat model | An API key (OpenRouter, Cerebras, OpenAI-compatible…) or a user-run LM Studio / llama.cpp; an in-app GGUF pack is Phase 9 | — |

### 4.2 Runtime process model

The MarketPulse model (its roadmap §4.3) carries over: a Python supervisor in a kill-on-close Job Object (Windows)
or a process group (macOS), with Electron as a thin client over its stdin and stdout. The supervisor builds every
service command itself; it does not use `app.composition.launcher`.

```
Omnix.exe (Electron main: windows, tray, bridge)
  └─ python -m app.desktop.supervise             JSON events on stdout, commands on stdin
       ├─ pg_ctl → postgres                       bundled PG 17, data dir, 127.0.0.1:<pg-port>
       ├─ migrate (owner role), then run_omnix_gateway.py (omnix_app role, 127.0.0.1:<http-port>)
       │    └─ job worker (pack installs run here, §4.3)
       ├─ stt service    python -m app.desktop.service_boot stt     only when the voice-input bundle is installed
       ├─ tts service    python -m app.desktop.service_boot tts     only when a TTS model is installed
       └─ image service  python -m app.desktop.service_boot image   only when an image model is installed
```

- **Every service runs on the bundled interpreter.** `app.desktop.service_boot` builds the service's `sys.path` and
  runs its existing entry point (§4.3):
  - STT and TTS through their `main()`, which reads the port variables;
  - the image service through `uvicorn.run` on its app, with the port.

  Services are never started through console scripts, because those would skip `service_boot`.
- Startup, migration snapshots, persisted ports, log rotation and shutdown work as in MarketPulse.
- Installing a pack does not restart the gateway. The supervisor starts the matching service once the pack is
  verified and headroom allows (§4.4), and stops it when the pack is removed.
- GPU sharing between services keeps using the PostgreSQL device permits (WP-6.2).
- **Environment contract.** The supervisor builds every child's environment from scratch, not from the user's
  shell, and replaces what `service_manager.py` does for the developer launcher:

  | Variable | Gateway and job worker | Model services |
  |----------|------------------------|----------------|
  | `OMNIX_SERVICE_TOKEN` | set (one per install, DPAPI or Keychain) | set, the same token |
  | `OMNIX_RUN_TOKEN_KEY` | set | **removed** |
  | `OMNIX_DATABASE_URL` | `omnix_app` role | `omnix_app` role (device permits and settings, under RLS as today) |
  | `OMNIX_TTS_URL`, `OMNIX_STT_URL`, `OMNIX_IMAGE_URL`, `OMNIX_IMAGE_ENABLED` | the persisted service ports, or empty when the pack is absent | — |
  | `OMNIX_GATEWAY_TTS_HTTP` | `1`: the gateway has no Torch, and without this the worker role builds the Qwen provider in-process (`config/runtime.py:263-268`), as `docker-compose.yml` already avoids | — |
  | `OMNIX_FFMPEG` | the bundled ffmpeg | the bundled ffmpeg (STT decodes uploads with it) |
  | `OMNIX_TTS_PORT`, `OMNIX_STT_PORT`, image port, `OMNIX_IMAGE_SERVICE_MODE=1` | — | the persisted ports (chosen once, never the developer defaults 5101/5201/5301) |
  | `OMNIX_LAUNCHER_KILL_PORT` | — | `0`: a busy port is an error, never a reason to kill another process |
  | `OMNIX_TTS_MODEL_DIR`, `OMNIX_QWEN3_TTS_MODEL_DIR` | — | the pinned snapshot folder in the Hugging Face cache (§4.6) |
  | `HF_HUB_CACHE`, `HF_HUB_OFFLINE=1` | the packs' cache | the packs' cache |
  | `OMNIX_RESOURCES_DIR` and every other data path | the desktop data folder (§4.9) | the same |
  | `OMNIX_TRADING_PROSPECTIVE_GAP_HANDOFF_IMPORT` | `0` | — |
  | `OMNIX_AGENT_ALLOW_UNSANDBOXED` | `false` | — |
  | `OMNIX_AGENT_DEFAULT_REPOSITORY` | not set | — |
  | Agent broker and model-gateway URLs, sandbox names | the persisted gateway port; desktop-specific names (§4.8) | — |

  DT-3.3 checks the contract: the services start, authenticate and reach the database with nothing inherited from a
  developer shell, and with a developer Omnix running on the same machine.

### 4.3 Packs and the shared Torch layer

**Two kinds of pack.**

- **Runtime packs** are Python wheels pinned by the lock files that ship in the installer.
- **Model packs** are weights from Hugging Face at catalog v2's pinned revision, checked against its SHA-256 values.

Every model declares the runtime packs it needs, so picking a model adds its runtime to the selection.

**What the layer contains.**

- The **Torch layer** is exactly `torch` and `torchaudio`, installed without their dependencies.
- Apart from `torchvision`, whose compiled `_C` must match Torch (see below), nothing else in the locks is ABI-bound
  to Torch: torchmetrics, lightning and NeMo are pure Python, and deepfilterlib links numpy, not Torch.
- Torch's own dependencies (filelock, fsspec, sympy, networkx, jinja2, typing_extensions) stay in each overlay,
  because the services pin different versions of them.
- `torchvision` stays in the overlays that already lock it (STT, image, audio). It is small. Putting it in the layer
  would make it importable in TTS and omnivoice, whose locks have no Pillow, and it would switch on transformers'
  torchvision code paths there. Because it is ABI-bound, gate item 4 checks that its pin matches the layer's Torch.
- The layer is per platform: `torch-2.6.0-cu124-win-x64`, `torch-2.6.0-macos-arm64`.

**The overlays.**

- An **overlay** is a service lock with the Torch lines removed. It is installed with no dependency resolution: the
  locks are already fully resolved, so this installs exactly the locked set, numpy and transformers included at that
  service's versions.
- **Overlays are derived, not maintained.** A script generates each overlay lock from `src/services/<service>/*.lock.txt`
  by dropping `torch` and `torchaudio`. A gate check (§6) fails if an overlay differs from its source lock in
  anything else.

**Import path.**

- **`app.desktop.service_boot` sets `sys.path` in code:** the standard library, the overlay, the Torch layer, then
  the `app` source.
  - It **removes the interpreter's own `site-packages`**, which holds the gateway lock (huggingface-hub 2.0.0, numpy
    2.4.6…). Otherwise anything missing from an overlay would silently load the gateway's version, and a smoke test
    could pass on an incomplete overlay.
  - A DT-3.3 test asserts that no module in a service process was loaded from the gateway's `site-packages`.
- The interpreter's `._pth` (Windows) still decides where the standard library is. `service_boot` replaces only the
  package paths. This needs no `PYTHON*` variables (which `._pth` ignores) and no venvs (which don't combine reliably
  with it), and it works the same way on macOS. No venvs, no per-service interpreter copies, no `.pth` files.
- Torch's `.dist-info` lives in the layer, so `importlib.metadata` version checks (transformers, accelerate, NeMo)
  still find it.
- On Windows, `torch/__init__.py` registers its own `lib` folder for DLL loading, so the layer works from any path,
  including after the packs folder moves to another drive.
- **CUDA DLLs outside Torch.** `cuda-pathfinder` (STT) searches site-packages for CUDA DLLs, which in this layout
  live in the layer's `torch/lib`. DT-0.1 checks that NeMo's code paths that use `cuda-bindings` (CUDA 13 bindings)
  work against the cu124 DLLs, and whether they raise the driver minimum. If they do, the plan pins them off or
  documents the higher driver floor.

**Installing without pip at runtime.**

- The staged interpreter has no pip (MarketPulse prunes it, and pip misbehaves under `._pth`). Pip also cannot resume
  a 2.5 GB wheel across restarts.
- **Download.** The pack job fetches each wheel itself: the URL comes from the lock (PyPI or download.pytorch.org),
  the download resumes into a staging folder, and the file is checked against the lock's hash.
- **Install.** It installs the verified wheels with the pure-Python `installer` package (PyPA's wheel installer,
  shipped as a wheel in the installer) into the pack folder.
  - `installer`'s `purelib`, `platlib`, `scripts` and `data` paths all map inside the pack.
  - The only path-configuration `.pth` a locked wheel installs is setuptools' `distutils-precedence.pth`. Ignoring it
    is harmless on Python 3.11, since the pack folder is not a site directory.
- **Source-only packages** (`antlr4-python3-runtime`, `wget`, and any others DT-0.1 finds) are built into wheels at
  release time, hashed, and shipped in the installer. Nothing is ever built on the user's machine, so no build tools
  are needed and nothing unhashed is fetched.

**Savings and the constraint.**

- A user who installs voice input, voice output and image generation downloads Torch once instead of three times:
  about 5 GB less to download on Windows, and more on disk. DT-0.1 measures the real numbers.
- Torch is upgraded for every service at once, in one release, with all locks recompiled together. That is already
  how the locks are maintained; the §6 lock check keeps it so.

**Install, verify, remove.**

- Each pack downloads into a staging folder, is verified, then is renamed into place. A pack is either complete or
  absent.
- Downloads resume after a restart or a lost connection.
- **Manifest.** Each installed pack has a manifest next to it: pack id, version, the source lock's hash, file hashes,
  and the catalog revision. For weights, this extends today's `.omnix-model.json`. At startup the supervisor checks
  manifests, not every byte; "Verify" in Settings → Models runs a full hash check.
- Removing a pack that another pack needs is refused, with the reason (for example, the Torch layer while TTS is
  installed).
- **App updates and packs.** Each app version names the pack versions it expects. If an update changes a runtime lock,
  the app keeps the working services on the old pack until the user downloads the new one, then switches atomically.

**Supply-chain boundary.**

- Runtime packs are executable code. Their hashes come only from the lock files and catalog that ship inside the
  signed installer; nothing that lists hashes is fetched at runtime, and a download whose hash is not in the shipped
  files is refused.
- The catalog and locks change only through app updates.
- Omnix hosts only the small prebuilt wheels, and they ship inside the installer. Torch, the other wheels and the
  weights come from their upstream indexes.

### 4.4 Hardware detection (no Torch)

The probe runs in the gateway's environment and reports facts; the setup screen turns them into verdicts using
catalog v2's requirements (§4.6).

| Fact | Windows | macOS |
|------|---------|-------|
| GPU, VRAM, driver | `nvidia-smi --query-gpu=name,memory.total,memory.free,driver_version --format=csv` (NVML as fallback); other adapters through WMI (`Win32_VideoController`), so AMD and Intel GPUs show as "no CUDA" | Apple Silicon generation from `sysctl machdep.cpu.brand_string`; `hw.optional.arm64` |
| Memory | Total and available physical memory, and **commit headroom** (commit limit minus commit charge) | `hw.memsize`; unified memory is shared with the GPU |
| Disk | Free space on the packs volume | Free space on the packs volume |

- **Driver check.** CUDA 12.x minor-version compatibility needs NVIDIA driver 528.33 or newer on Windows, and CUDA
  12.4's own driver is 551.61. DT-0.1 confirms the minimum the pinned Torch and the STT lock's `cuda-bindings` need,
  and the result goes into catalog v2. A driver that is too old shows "Update your NVIDIA driver" with a link to
  NVIDIA. Omnix never installs drivers.
- **Memory headroom matters.** Loading Fish S2 Pro on this workstation committed about 24 GB and exhausted Windows'
  commit limit, freezing the PC. Before starting a service or loading a model, the app checks committed-memory and
  VRAM headroom against the model's measured requirement. If there isn't enough, it refuses with a clear message
  instead of trying.

### 4.5 Setup screen and Settings → Models

The setup screen opens after the first sign-in. Afterwards it is Settings → Models, which grows out of Voice Studio's
`SpeechModelsPanel` and takes over image models too. The panel moves into Settings and Voice Studio links to it. The
LLM page at `/models` is unchanged and links across.

```
Set up Omnix                     RTX 4080 · 16 GB VRAM · driver 560 ✓ · 64 GB RAM · 410 GB free

[Recommended for this PC]  [Minimal]  [Custom]

Voice input (live voice in chat)
  ☑ Nemotron streaming 0.6B + Parakeet realtime EOU 120M    2.9 GB   ✓ fits
Voice output
  ☑ Qwen3-TTS 0.6B                                          2.5 GB   ✓ fits
Transcription (STT page)
  ☐ Parakeet-TDT 0.6B v3 + TitaNet speaker embeddings       2.5 GB   ✓ fits
  ☐ Sortformer diarizer (non-commercial licence)            0.5 GB   ✓ fits
Image generation
  ☐ FLUX.2 klein 4B                                        16.0 GB   ⚠ tight on free VRAM
Local chat model
  Use an API key — Settings → Providers

Models 5.4 GB · GPU runtime 2.5 GB · voice-input and voice-output runtimes (sizes from DT-0.1)
Total: about 7.9 GB plus the service runtimes             [Skip for now]  [Review licences & download]
```

- **Bundles, not single files.** A capability is one item. Voice input installs Nemotron and the EOU model together,
  because live voice needs both.
- **Presets.** *Recommended* picks the best bundle per capability that fits this machine. *Minimal* picks nothing.
  *Custom* lets the user choose freely.
- **Verdicts.** Each item shows ✓ fits, ⚠ fits with a warning (tight VRAM, slow on CPU), or ✗ unavailable, with the
  reason ("needs an NVIDIA GPU", "not available on macOS"). Unavailable items stay visible.
- **Licences (D-4).**
  - "Review licences & download" lists each selected model's licence: name, link, the text at the pinned revision,
    and any output terms (non-commercial, attribution). The user accepts each one.
  - The same rule replaces Voice Studio's current one (accept only gated or non-commercial models).
  - Acceptance is recorded in PostgreSQL (§4.6); the manifest only mirrors it.
  - **Gated repositories.** The item says so and links to the Hugging Face page for accepting there. The token goes
    through the existing `save_model_hub_token` store and route.
  - Runtime packs list their main licences (PyTorch, NeMo) for information.
- **Progress.** Installs run as `models.install` jobs in the job worker, with progress on the existing event stream.
  They continue while the screen is closed and after a restart. The tray shows overall progress.
- **Later.** Settings → Models adds Remove, Verify, Update, disk usage per pack, moving the packs folder, and "update
  available" when an app update expects a newer pack.
- **Features adapt.** A backend capability endpoint reports which capabilities are installed and running. Where one is
  missing, the UI offers the download in place: the chat mic button says "Download voice input", and Voice Studio and
  the STT page say which bundle they need. Nothing fails silently.
- **Readiness comes from the pack manifests** in desktop mode. Today `model_install.service_environment` judges
  readiness from the launcher's Conda paths and offers `conda create` commands. The panel hides Install while that
  environment is missing (`SpeechModelsPanel.tsx:78`), which would hide it on every desktop install.
- **Authority.**
  - Model installs keep today's rule: owner or admin.
  - **Runtime packs are executable code**, so installing, updating or removing them is owner-only, under a new
    permission, `models:runtimes:admin`:
    - it goes in `_ADMIN_EXCLUDED` (`permissions.py`), so the admin role does not get it;
    - it is checked at job submission, because installs are `models.install` jobs submitted through `/api/jobs`,
      where members hold `jobs:submit`. Route entries alone don't enforce it.
  - **An admin who picks a model whose runtime is missing** gets a refusal that names the runtime and says the owner
    must install it. Nothing is queued on the owner's behalf.
  - Guests see the status, never the controls.
  - In the desktop app the image service takes its model only from catalog v2, never from a `repo_id` in settings.

### 4.6 Catalog v2

`catalog.json` gains a version, runtimes, bundles and per-model platform variants, and absorbs `SpeechModel`'s fields
(licence, `commercial_use`, `gated`, output terms, residency, capabilities). `voice/model_catalog.py` becomes a reader
of catalog v2, so Voice Studio, the STT page and the desktop share one list. A sketch:

```json
{
  "catalog_version": 2,
  "runtimes": {
    "torch-win-cu124": {
      "platform": "windows-x64", "accelerator": "cuda",
      "lock": "requirements/desktop/torch.win-cu124.lock.txt",
      "requires": {"nvidia_driver_min": "551.61"},
      "licences": ["BSD-3-Clause (PyTorch)"]
    },
    "stt-win": {
      "platform": "windows-x64", "base": "torch-win-cu124",
      "overlay_of": "src/services/stt/stt.lock.txt"
    },
    "stt-mlx-mac": {
      "platform": "macos-arm64",
      "lock": "requirements/desktop/stt.macos-arm64.lock.txt"
    }
  },
  "bundles": {
    "voice-input": {
      "capability": "live_stt", "label": "Voice input",
      "variants": [
        {"platform": "windows-x64", "models": ["nemotron-speech-streaming-en-0.6b", "parakeet-realtime-eou-120m-v1"],
         "runtime": "stt-win", "min_vram_mb": null, "min_commit_mb": null},
        {"platform": "macos-arm64", "models": ["parakeet-mlx-…"], "runtime": "stt-mlx-mac"}
      ],
      "recommended_rank": 1
    }
  },
  "models": {
    "parakeet-realtime-eou-120m-v1": {
      "repo": "nvidia/parakeet_realtime_eou_120m-v1", "revision": "a7e2b46…",
      "files": {"…": {"sha256": "…", "size": 460062720}},
      "licence": {"id": "…", "url": "…", "commercial_use": true, "gated": false, "output_terms": ""}
    }
  }
}
```

- **Requirements are measured, not guessed.** `min_vram_mb` and `min_commit_mb` come from DT-0.4. `null` means
  "not measured", and the setup screen shows those items with a warning.
- **Every Hugging Face model gets a pinned commit and file hashes,** including the speech models that now install
  from `main`. The audio models that their own packages fetch on first use (`source="package"`) cannot be pinned this
  way. They stay out of the desktop catalog until Phase 9.
- **Ids are mapped.** The two catalogs name the same model differently (`qwen3-tts-0.6b-base` in `SpeechModel`,
  `qwen3-tts-12hz-0.6b-base` in `app.models`). DT-1.1 keeps one id per model and maps the old ones, so settings and
  markers that hold the other id keep working.
- **Weights live in the Hugging Face cache** (decided):
  - The `app.models` downloader already writes the cache and pins its `main` ref.
  - Live STT loads by repository id from it.
  - `HF_HUB_OFFLINE=1` assumes it.
  - TTS gets the pinned snapshot folder inside the cache through `OMNIX_TTS_MODEL_DIR`, so no loader changes.

  DT-1.1 moves Voice Studio's `resources/models/<kind>/<repo>` installs into the cache (or re-downloads them), and
  their `.omnix-model.json` acceptances are copied into the acceptance table.
- The Docker deployment's `python -m app.models download --service …` keeps working on v2: Linux CUDA is just another
  platform.
- **Licence acceptances** go in a new table (migration under `src/app/persistence/migrations`): user, model, licence
  id, pinned revision, time. A catalog update that changes a licence or revision asks again.
- **Licences to confirm** in DT-1.3, from each model card at the pinned revision:

  | Model | Licence | Status |
  |-------|---------|--------|
  | Qwen3-TTS 0.6B | Apache-2.0 | in `SpeechModel` today |
  | Parakeet-TDT 0.6B v3, TitaNet | CC-BY-4.0 (attribution) | in `SpeechModel` today |
  | Sortformer 4spk v1 | CC-BY-NC-4.0 | in `SpeechModel` today |
  | Nemotron streaming 0.6B, Parakeet realtime EOU 120M | expected: NVIDIA open model licence | confirm |
  | FLUX.2 klein 4B | expected: Apache-2.0 for the 4B variants | confirm; check gating |
  | Parakeet-MLX library and its MLX weights | licensed separately | confirm |

### 4.7 macOS model set

- **Voice input and transcription: Parakeet-MLX (D-5).** It runs on MLX, not Torch, so its runtime (`stt-mlx-mac`)
  does not need the Torch layer. Its weights are an MLX conversion of a Parakeet model, pinned and hashed like every
  other model. The natural pairing is the MLX conversion of Parakeet-TDT 0.6B v3, the model the STT page already
  uses on Windows.
  - **Behaviour gap to close.** On Windows, live voice relies on the realtime EOU model to report that the user has
    finished speaking (`nemotron_eou_streaming.py`, `live_stt_contracts.py`). Parakeet-MLX transcribes but may not
    emit that signal. DT-8.2 decides how to detect the end of an utterance on Mac (silence/VAD endpointing) so the
    live voice contract holds on both platforms. Until then, Mac live voice uses push-to-talk.
  - Diarization (TitaNet, Sortformer) is NeMo-only and not on Mac in v1.
- **Voice output: Qwen3-TTS on MPS.** It uses the `faster-qwen3-tts` provider with the device set explicitly to
  `mps`, since the loader never selects MPS on its own. CUDA graphs are off automatically on a non-CUDA device.
  DT-0.3 tests quality and speed.
- **Image: FLUX.2 klein on MPS is later** (Phase 9). About 16 GB of weights means it is realistic only on Macs with
  plenty of unified memory, and it is untested.
- The macOS TTS runtime uses the same layer-and-overlay layout and `service_boot`, so there is one code path.

### 4.8 Accounts, LLM, agents, trading

- **Accounts:** as MarketPulse §4.7 (first-run login code, owner sets email and password, optional desktop Google).
  The seams are already on `main`.
- **LLM:** provider keys in the secret store (DPAPI on Windows, Keychain on macOS). LM Studio or llama.cpp run by the
  user also works. An in-app GGUF pack is Phase 9.
- **Agents:**
  - **Read-only runs** work on the host as they do today without Docker.
  - **Write-capable runs** need Docker. The installer ships `deploy/docker/agent-sandbox.Dockerfile`, and when Docker
    is present, Settings offers "Build the agent sandbox" (`python -m app.platform.agent_runtime.sandbox build`).
    Without Docker, write-capable runs are unavailable, and the UI says why.
    - **Layout.** `sandbox.py:31` finds the Dockerfile as `parents[4]/deploy/docker`, so staging keeps that relative
      layout.
    - **Separate names.** The desktop uses its own sandbox image, network and broker-relay container names.
      - Only the image is configurable today (`OMNIX_AGENT_DOCKER_IMAGE`). `SANDBOX_NETWORK` and `RELAY_CONTAINER`
        are constants (`isolation.py:40-41`), and the relay name is built into the sandbox's URL rewrite.
      - The relay is force-removed when its routes differ (`isolation.py:179-185`), so a desktop install and a
        developer Omnix would otherwise keep replacing each other's relay.
      - Making both names configurable is a code change in an authority-sensitive area. It is its own work item
        (DT-3.5), with focused isolation tests.
    - **URLs.** The broker and model-gateway URLs point at the persisted gateway port, not the `127.0.0.1:8000`
      default (`isolation.py:250-251`).
  - The supervisor forces `OMNIX_AGENT_ALLOW_UNSANDBOXED=false` and sets no default repository; the user picks a
    workspace for each run.
- **Trading:** available as research, with no broker connection and no order authority until the user connects
  their own broker (AGENTS.md "Trading"). The supervisor turns the research handoff importer off
  (`OMNIX_TRADING_PROSPECTIVE_GAP_HANDOFF_IMPORT=0`).
- **Pack installs never change capabilities.** Installing a model makes a provider available; it does not grant any
  capability, profile or approval.

### 4.9 Data locations

| Windows | macOS | Contents |
|---------|-------|----------|
| `%LOCALAPPDATA%\Programs\Omnix\` | `/Applications/Omnix.app` | The app, prebuilt wheels, locks, catalog; read-only at runtime |
| `%LOCALAPPDATA%\OmnixDesktop\pgdata\` | `~/Library/Application Support/OmnixDesktop/pgdata/` | PostgreSQL cluster |
| `…\OmnixDesktop\packs\runtimes\<id>\` | same layout | Torch layer and overlays |
| `…\OmnixDesktop\packs\models\` | same layout | Weights: the Hugging Face cache (`HF_HUB_CACHE`) |
| `…\OmnixDesktop\packs\staging\` | same layout | Partial downloads |
| `…\OmnixDesktop\resources\` | same layout | `OMNIX_RESOURCES_DIR`: blobs, assets, caches |
| `…\OmnixDesktop\logs\`, `snapshots\`, `backups\`, `secrets\` | same layout | As MarketPulse §4.5 |

- The data folder is `OmnixDesktop`, not `Omnix`, so the desktop app never reads or rotates the secrets of a
  developer Omnix on the same machine. A test gates this, as in MarketPulse.
- **Packs can live on another drive.** Settings → Models can move `packs\`, because models alone can reach tens of
  GB. Nothing stores absolute pack paths except the supervisor's settings, so a move is: stop the services, move the
  folder, update the setting, start the services.
- Uninstall keeps data and packs unless the user ticks "Remove my data and downloaded models".

## 5. Phases

Each phase ends with a gate; a phase is done when its gate passes.

### Phase 0: Spikes (decide before building)

- **DT-0.1 Shared Torch on Windows.**
  - Write the overlay-derivation script (it is reused in DT-1.2).
  - Install the Torch layer once and the STT, TTS and image overlays on top, using `service_boot` path wiring and
    wheel installation through `installer` from locally downloaded wheels.
  - Weights go in a scratch Hugging Face cache through the existing `app.models` downloader.
  - This is the first run of TTS on Torch 2.6.0 on this workstation (§3).
  - List every source-only package and build its wheel.
  - Check NeMo's `cuda-bindings` / `cuda-pathfinder` paths against the layer.
  - Record download and installed sizes per pack, and the driver minimum.
- **DT-0.2 Parakeet-MLX on the owner's Mac.** Streaming latency and accuracy against the Windows models on the same
  clips, and how to detect the end of an utterance.
- **DT-0.3 Qwen3-TTS on MPS.** Load, speed and quality with `faster-qwen3-tts` on `mps`.
- **DT-0.4 Requirements.** Peak VRAM, RAM and commit charge for each bundle and model in its service, measured one at
  a time with headroom checked first.

**Gate:**
- With the shared layer, each service's real-model smoke test passes through its existing entry point: TTS speaks,
  live STT returns a transcript and an end-of-utterance, and the image service generates one picture.
- The numbers are recorded in §11, and D-6 is confirmed or revised.

### Phase 1: Catalog v2

- **DT-1.1 Schema and readers.**
  - Write the catalog v2 schema (§4.6) and its loader.
  - Make `voice/model_catalog.py` read from v2.
  - Keep the `app.models` CLI working.
  - Map the model ids between the two catalogs.
  - Migrate Voice Studio's folder installs, and their marker acceptances, into the Hugging Face cache and the
    acceptance table (§4.6).
- **DT-1.2 Desktop locks.** The Torch layer per platform, and the overlays generated by the DT-0.1 script. Also the
  macOS locks: the Torch layer, TTS, and `stt-mlx-mac`.
- **DT-1.3 Pins and licences.** A pinned commit and file hashes for every speech model that now installs from
  `main`. Licence records confirmed (§4.6 table), with output terms and gating.
- **DT-1.4 Downloader.**
  - Resumable wheel and weight downloads into staging, hash checks, staging-then-rename.
  - Installation with `installer`.
  - The Hugging Face token through the existing store.

**Gate:**
- The catalog tests pass, and Voice Studio's model list is unchanged apart from the new pins.
- A dry run installs and verifies one model and one overlay into a scratch folder.
- An interrupted download resumes and still verifies.
- A tampered file, or a wheel whose hash is not in the shipped lock, is refused.

### Phase 2: Backend: probe, jobs, routes

- **DT-2.1 Hardware probe.** The Torch-free probe (§4.4), with fixtures for no GPU, AMD only, an old NVIDIA driver,
  and Apple Silicon.
- **DT-2.2 Jobs.** Extend `models.install` / `models.remove` to bundles and runtime packs, with progress events,
  cancellation and dependency rules.
- **DT-2.3 Migration.** The licence-acceptance table (§4.6). The database is authoritative for acceptance, and pack
  presence on disk is authoritative for "installed".
- **DT-2.4 Routes.**
  - Hardware, catalog-with-verdicts, install, remove, verify and capabilities, extending `/api/voice/models` into a
    general models API.
  - The new `models:runtimes:admin` permission: in `_ADMIN_EXCLUDED`, and checked at `models.install` job submission
    for runtime packs.
  - Readiness taken from the pack manifests in desktop mode (§4.5).
  - The image service's settings-driven download replaced by catalog v2 in desktop mode.

**Gate:**
- Focused pytest coverage, plus PostgreSQL tests on the scratch test database.
- A guest cannot install, remove or accept licences.
- An admin cannot install a runtime pack, whether through the models routes or by submitting a `models.install` job
  directly to `/api/jobs`.
- A model install without a recorded acceptance for its pinned revision is refused.
- Killing the job worker mid-install leaves no half-installed pack, and the job resumes after a restart.

### Phase 3: Embedded runtime and supervisor (Windows x64)

- **DT-3.1 Staging.** `build/stage.py` adapted from MarketPulse:
  - CPython, `requirements/gateway.lock.txt`, PostgreSQL 17, the `app` source and the web build;
  - a pinned LGPL ffmpeg build;
  - licences, the prebuilt wheels and the `installer` wheel;
  - the desktop locks and catalog v2;
  - `deploy/docker/agent-sandbox.Dockerfile` at its relative path;
  - `build-info.json`.

  pip stays pruned; packs never need it.
- **DT-3.2 Supervisor.** `app.desktop.supervise` adapted from `marketpulse.supervise`: the §4.2 order, Job Object,
  ports, snapshots, and forced environment.
- **DT-3.3 Services.**
  - `app.desktop.service_boot`, with the stripped `sys.path` (§4.3).
  - The environment contract (§4.2).
  - Supervisor hooks that start or stop a model service when its packs appear or go away, and check headroom before a
    start.
  - **Tests:**
    - a service process loads nothing from the gateway's `site-packages`;
    - services start, authenticate and reach the database with an empty inherited environment;
    - a busy service port is reported, never killed;
    - the gateway and job worker never import `torch`, and a TTS request goes to the TTS service;
    - STT decodes a non-WAV upload and an audiobook export runs, both with the bundled ffmpeg.
- **DT-3.4 Data paths and size.** The data paths (§4.9), the test that no default `%LOCALAPPDATA%\Omnix` path is
  used, and a size report for the staged runtime and installer.
- **DT-3.5 Agent sandbox names.**
  - Make the sandbox network and broker-relay container names configurable in `agent_runtime/isolation.py`, including
    the relay name in the sandbox URL rewrite. The defaults stay as today.
  - The desktop sets its own names, broker and model-gateway URLs.
  - Focused isolation tests: a desktop relay and a developer relay coexist without either removing the other, and
    neither the sandbox's network reach nor its capabilities widen.

**Gate:**
- On a clean Windows account with no Python, PostgreSQL or Docker, the headless supervisor migrates and reaches
  `/ready`. It does the same with a developer Omnix running on the same machine, without touching that Omnix's
  ports, relay or data.
- Installing a voice-output pack through the API starts the TTS service, which speaks.
- The supervisor stops cleanly, and killing it leaves no child processes.

### Phase 4: Electron shell

- **DT-4.1 Shell.** `desktop/` from MarketPulse: windows, splash and error views, navigation rules, preload bridge,
  hardening and fuses, tray.
- **DT-4.2 Microphone.** The microphone permission is allowed for the gateway origin only. Live voice needs it, and
  MarketPulse's permission handler allows only notifications and clipboard.
- **DT-4.3 Smoke suite.** The Playwright-for-Electron suite.

**Gate:** the smoke suite covers startup to sign-in to chat. The mic permission is granted to the app origin and
refused elsewhere, external links open outside the app, and quitting leaves no processes.

### Phase 5: Setup screen and Settings → Models

- **DT-5.1 Setup screen** (§4.5): presets, bundles, verdicts, totals, licence review and acceptance, progress.
- **DT-5.2 Settings → Models**, grown from `SpeechModelsPanel`: image models, remove, verify, update, disk usage,
  moving the packs folder. Voice Studio links to it.
- **DT-5.3 Features adapt to capabilities:** the chat mic button, Voice Studio, the STT page and image generation.

**Gate:**
- Vitest coverage for verdicts, presets, bundles and licence gating.
- An Electron run on the owner's PC goes from the recommended preset to working voice input and output in chat.
- A machine without an NVIDIA GPU sees the GPU items greyed with the reason, and Omnix still works with an API key.

### Phase 6: Windows packaging, signing, updates (first release)

- **DT-6.1 Installer.** electron-builder NSIS per-user install; uninstall keeps data and packs by default.
- **DT-6.2 Code signing** (Azure Trusted Signing or an OV certificate) before any build leaves the owner's machines.
- **DT-6.3 Updates.** `electron-updater` from a public release feed. On update: snapshot, migrate, and restore on
  failure, as MarketPulse does. Each app version names the pack versions it expects (§4.3).
- **DT-6.4 Export diagnostics:** logs, versions, the hardware probe, pack manifests, no secrets.

**Gate:**
- On a clean Windows 11 machine with an NVIDIA GPU: install, first run, recommended setup, voice chat.
- Upgrading keeps data and packs.
- An update that changes a runtime lock keeps the old pack working until the new one is installed.

### Phase 7: Hardening from first-release feedback

Real-world failures from Phase 6 go here: antivirus quarantining DLLs, proxies, very slow links, small disks.

### Phase 8: macOS

- **DT-8.1 Runtime.** Staging for macOS arm64, Keychain secrets, process-group supervision.
- **DT-8.2 Voice input.** The Parakeet-MLX runtime and service, with end-of-utterance detection that meets the live
  voice contract (§4.7).
- **DT-8.3 Voice output.** Qwen3-TTS on MPS through the same layout.
- **DT-8.4 Signing and permissions.**
  - Developer ID signing, hardened runtime, notarization, built on the owner's Mac.
  - The microphone: `NSMicrophoneUsageDescription` in `Info.plist`, the
    `com.apple.security.device.audio-input` entitlement, and the shell's permission handler from DT-4.2.

**Gate:** the Phase 6 gate repeated on a clean Apple Silicon Mac, with Parakeet-MLX voice input and Qwen3-TTS
output in live voice chat. The first mic use shows the macOS permission prompt with Omnix's text.

### Phase 9: Later

- In-app local chat model pack (llama.cpp with CUDA or Metal, a GGUF picked on the setup screen).
- FLUX.2 klein on Apple Silicon, if measurements show it fits.
- Further packs: the Qwen3-TTS 1.7B VoiceDesign model, omnivoice (non-commercial), the audio service, and Fish S2
  Pro (only with strict headroom checks). Before they become packs, the audio models that their packages fetch on
  first use need pinning in catalog v2.
- Thin-client mode: the same shell connects to an existing Omnix server.

## 6. Gate set (every release)

1. Focused pytest for `app.models`, the voice model catalog and install jobs, the probe and the routes. PostgreSQL
   tests on the scratch test database.
2. `ruff check` on changed Python paths.
3. `npm --prefix web run test -- <setup and models tests>` and `npm --prefix web run build`.
4. **Lock consistency.**
   - Every overlay equals its source service lock minus `torch` and `torchaudio`.
   - Every service lock pins the Torch layer's exact versions, and every `torchvision` pin is the one built for that
     Torch.
   - Every source-only package has a shipped, hashed wheel.
5. **Real-model smoke test** (the DT-0.1 gate) on the owner's GPU machine whenever any service lock, the Torch layer
   or catalog v2's pins change.
6. A headless supervisor start on a fresh data folder.
7. The Electron smoke suite.
8. Release only: install, upgrade and recovery checks on clean Windows (and macOS from Phase 8).

## 7. Owner questions

| # | Question | Answer |
|---|----------|--------|
| Q-1 | Support Intel Macs? Core only (API-key chat) is cheap; GPU packs on Intel Macs are not planned. | open |
| Q-2 | Which workspaces does desktop v1 show? Chat, voice, memory and STT are assumed; RPG, Storyteller, Audiobook, Podcast and Trading research too? | open |
| Q-3 | App name and data folder name (`Omnix` / `OmnixDesktop` assumed). | open |
| Q-4 | Release feed: a public releases repository or an HTTPS bucket? The updater must read it without a token. | open |
| Q-5 | Signing identities for Windows and macOS (shared with MarketPulse?). | open |
| Q-6 | Gated models | answered by the code: the user's own Hugging Face token, through the existing hub-token store (§4.5) |

## 8. Risks

| # | Risk | Mitigation |
|---|------|------------|
| R-1 | The shared Torch layer breaks a service in a way import checks miss | Real-model smoke tests in DT-0.1 and in gate item 5 on every lock change |
| R-2 | A wheel is missing for the platform (source-only packages), or NeMo's install is fragile on Windows | DT-0.1 lists them; they are prebuilt and shipped; gate item 4 |
| R-3 | NeMo's CUDA 13 bindings need a newer driver than cu124 Torch | DT-0.1 checks; the minimum goes into catalog v2 |
| R-4 | The user's NVIDIA driver is too old, or there is no NVIDIA GPU | The probe and verdicts say so up front; the core app works without a GPU |
| R-5 | Downloads of many GB fail, stall, or fill the disk | Own resumable downloads, staging folder, disk check before start, packs folder on another drive |
| R-6 | Antivirus quarantines or slows DLLs in packs | Signed app; packs only from official indexes; diagnostics show quarantined files; Phase 7 |
| R-7 | A pinned Hugging Face revision or file disappears upstream | Downloads fail with a clear message; the catalog is updated through an app release. A mirror is out of scope for v1. |
| R-8 | Licence terms change, or a model becomes gated | Acceptance is recorded per revision; a catalog update re-prompts |
| R-9 | Loading a model exhausts memory and freezes the PC | Headroom checks before start (§4.4), with requirements measured in DT-0.4 |
| R-10 | Parakeet-MLX cannot meet the live voice end-of-utterance contract | DT-0.2 and DT-8.2; push-to-talk on Mac until then |
| R-11 | Merging the two catalogs regresses Voice Studio's model management | DT-1.1 gate: Voice Studio's list is unchanged apart from the pins; the existing voice tests keep passing |
| R-12 | Installer size grows with the full gateway dependency set | Measured in DT-3.4 and tracked, not a gate; later slimming as in MarketPulse Phase 12 |

## 9. Out of scope for v1

- Installing NVIDIA drivers or the CUDA Toolkit.
- AMD (ROCm/DirectML) and Intel GPU acceleration on Windows.
- Hosting or mirroring Torch, other upstream wheels or model weights.
- Running write-capable agents without the Docker sandbox.
- LAN access to the desktop install from other devices.
- Linux desktop packages (the Docker deployment covers Linux).
- Diarization on macOS.

## 10. Review log

**Revision 1 → 2 (2026-10-22), from an independent review against `main`:**
- Added the existing Voice Studio speech-model manager (catalog, `models.*` jobs, `.omnix-model.json`, hub token,
  `SpeechModelsPanel`). Catalog v2 now absorbs it (D-7), instead of planning a second model manager.
- Live voice input needs Nemotron and the Parakeet EOU model together. The setup screen offers bundles, and the
  totals are corrected.
- `RPG_FLUX_PYTHON` is the gateway's interpreter, not the image service's. The desktop supervisor now starts services
  itself through `service_boot`.
- Packs install without pip: own resumable wheel downloads plus PyPA `installer`. Source-only STT packages are
  prebuilt and shipped, so nothing unhashed is fetched or built on the user's machine.
- The Torch layer is exactly `torch` and `torchaudio`; torchvision and Torch's dependencies stay in the overlays.
  Path wiring is one bootstrap module on both platforms (the `.pth` and per-service `._pth` options are dropped).
- Overlays are derived from the service locks and gated, rather than kept as separate locks.
- Added NeMo's CUDA 13 bindings to the driver check, and corrected the Qwen3-TTS-on-MPS path.
- Authority: runtime packs are owner-only under a new permission, model installs stay owner-or-admin, and the image
  service no longer downloads a settings-supplied repository in the desktop app.
- The supervisor forces the trading importer off, unsandboxed agents off and no default repository. Read-only agent
  runs work without Docker, and the sandbox Dockerfile ships.
- Sequencing: the supervisor hooks moved to Phase 3, and a real-model smoke test was added to the gate set.
- Added the macOS microphone entitlement and usage text, and the STT page's models (Parakeet-TDT v3, TitaNet,
  Sortformer).
- Corrected: audio also pins torchvision; the Torch wheel is over GitHub's 2 GB limit, not close to it; the
  `onnxruntime-gpu` claim was removed.

**Revision 2 → 3 (2026-10-22), second review pass:**
- Added the environment contract (§4.2) that replaces what the developer launcher sets:
  - the service token and database URL;
  - the run token key removed from services;
  - persisted ports both ways;
  - `KILL_PORT=0`, so the desktop never kills a developer Omnix's service;
  - the TTS model folder;
  - desktop-specific agent sandbox names and URLs.
- `service_boot` strips the interpreter's `site-packages` (the gateway's packages), so an incomplete overlay cannot
  pass a smoke test. A test asserts it.
- Weights location decided: the Hugging Face cache, with TTS pointed at the pinned snapshot folder. DT-1.1 only
  migrates Voice Studio's folder installs and their marker acceptances.
- The permission split is enforced at job submission and through `_ADMIN_EXCLUDED`, not only by route entries.
  Desktop readiness comes from pack manifests rather than the Conda environments.
- Corrected: no separate "plain" Qwen3-TTS provider exists, and the faster provider turns CUDA graphs off on `mps` by
  itself. torchvision is ABI-bound, and gate item 4 checks it. The owner's TTS environment runs Torch 2.5.1, not the
  lock's 2.6.0. Corrected the mock-up totals. Package-sourced audio models are out of the desktop catalog, and model
  ids are mapped between the two catalogs.

**Revision 3 → 4 (2026-10-22), third review pass:**
- The gateway gets `OMNIX_GATEWAY_TTS_HTTP=1`. Without it, the worker role builds the Qwen TTS provider in-process,
  and that fails because the gateway has no Torch. A DT-3.3 test checks the gateway never imports `torch`.
- ffmpeg ships in the installer (pinned LGPL build), and `OMNIX_FFMPEG` is set for the gateway, the job worker and
  the STT service.
- Separate agent sandbox names need a code change: new work item DT-3.5, with isolation tests.
- The reviewer confirmed that TTS loads unchanged from the Hugging Face cache snapshot: the catalog's files match the
  working local folder, and Windows copies instead of symlinks are handled.
- After this pass the reviewer reported no remaining high or medium issues.

## 11. Status

**2026-10-22: Phases 0-6 and 8 are built on branch `electron`. Windows was checked on the owner's PC (RTX 4090,
driver 617.42). The Mac items need the owner's Mac. Signing and the release feed wait on Q-4 and Q-5.**

### Phase 0 results (DT-0.1, DT-0.4)

- **Shared Torch works (D-6 confirmed).** The layer is `torch` and `torchaudio` 2.6.0+cu124, with the three overlays
  on top. It ran on the staged python-build-standalone 3.11 through `service_boot`, with the gateway's
  `site-packages` stripped. Every gate check passed:
  - TTS spoke;
  - live STT returned partials, an end-of-utterance and the right transcript, and batch STT agreed;
  - FLUX.2 klein generated a picture.
- **Source-only packages.** Four are prebuilt into `requirements/desktop/wheelhouse`, hashed and shipped: antlr4,
  kaldi-python-io, sox and wget.
- **NeMo's CUDA bindings (R-3).**
  - The STT overlay keeps NeMo's `cuda-bindings` 13.4.3 and `cuda-pathfinder`.
  - On this PC (driver 617.42, new enough for CUDA 13), live and batch STT ran.
  - Not checked yet: a driver older than CUDA 13's (below 580), where NeMo should fall back from CUDA-graph decoding.
  - The verdicts check the Torch layer's minimum, 528.33 (551.61 recommended). That stays an open item until a run
    on such a driver.
- **Downloads per pack (Windows x64).** The layers and overlays are summed from `requirements/desktop/packs`. The
  models are their pinned files.

  | Pack | Download |
  |------|----------|
  | Torch layer | 2,419 MiB |
  | STT overlay | 286 MiB |
  | TTS overlay | 154 MiB |
  | Image overlay | 189 MiB |
  | Nemotron streaming 0.6B | 2,358 MiB |
  | Parakeet realtime EOU | 439 MiB |
  | Qwen3-TTS 0.6B | 2,400 MiB |
  | Parakeet-TDT v3 | 2,393 MiB |
  | TitaNet | 97 MiB |
  | FLUX.2 klein 4B | 15,240 MiB |

  So voice input plus output is 2.9 GB of runtimes and 5.2 GB of models.
- **Measured peaks, one service at a time.** Catalog v2's `min_vram_mb` / `min_commit_mb` add headroom to these.

  | Service | VRAM | Commit | Catalog: voice-input / voice-output / transcription / image (MiB) |
  |---------|------|--------|---------------------------------------------------------------------|
  | TTS | 2.8 GB | 6.3 GB | 3584 / 8192 (voice-output) |
  | STT | 3.6 GB | 7.2 GB | 4608 / 9216 (voice-input), 4096 / 9216 (transcription) |
  | FLUX | 15.6 GB | 17.8 GB | 16384 / 22528 |

- **Mac spikes not run.** DT-0.2 and DT-0.3 need the owner's Mac. The Mac locks resolve: the Torch layer, TTS on
  MPS, and Parakeet-MLX with mlx/onnxruntime wheels. Those wheels need macOS 14, so the macOS minimum is 14.0.

### Sizes (DT-3.4)

- **Staged runtime:** 557 MiB. That is python 287, PostgreSQL 68, ffmpeg (LGPL, BtbN 8.1.3) 128, app 68 (36 of
  source, the rest its shipped bytecode) and web 7; the gateway's site-packages bytecode is staged but not shipped.
- **Unsigned NSIS installer:** 253.2 MiB, and 882.4 MiB installed (236.8 and 838.5 before the app and standard
  library shipped their bytecode). MarketPulse's reduced mirror is 161 MB and 571 MB.
- **Pack install time:** compiling a pack's bytecode at install adds about two minutes to the Torch layer and the
  overlays (6.2 min for voice input and output, downloads included, against 4.2 before).
- **Start time:** the first start (initdb plus every migration) reaches the setup screen in about 25 s, and a later
  start reaches chat in about 15 s.

### Gates

| Phase | Status | Notes |
|-------|--------|-------|
| 0 | Windows: passed. Mac: open | Results above. |
| 1 | Passed, one item dropped | Voice Studio's list is unchanged apart from the pins. Catalog, lock, download, resume and tamper tests pass. The DT-1.1 migration of Voice Studio's folder installs into the Hugging Face cache was not built (see Deviations). |
| 2 | Passed | Members and guests are refused at submission, through the routes and `/api/jobs` alike. The runtimes the submitter may change are written into the stored job, so an admin's job never installs or removes a runtime when it runs, even after an app update or a removal changed what it would touch. A bundle the verdicts call unavailable is refused at submission. An acceptance is per model, revision and licence (migration 0169 widened 0168's key); its RLS and acceptance tests ran on the scratch PostgreSQL. A worker killed mid-unpack leaves no pack, and the job's retry after an expired lease completes it. |
| 3 | Passed on this PC | Clean-account check pending on a second machine. Covered on this PC: the headless supervisor from a fresh data folder, on ports and sandbox names of its own; the service boot isolation test; busy ports reported, never killed; graceful stop, then restarts after 30, 60 and 120 s; models load one at a time (a service not ready after 10 minutes stops holding the others), with a loading service's memory reserved. FLUX loads only when the image view loads it, and that load is refused with the reason when less than its measured 22 GB of commit (or its VRAM) is free. The gateway cannot import Torch: its staged lock pins none, which a test checks. Not tested: STT decoding a non-WAV upload and an audiobook export with the bundled ffmpeg (only the environment is asserted). |
| 4 | Passed | The 10-test Electron smoke suite covers splash, setup screen, first password, mic audio-only, links, the model pack API, crash reload, tray, clean quit and the installer's `--quit`. 12 shell unit tests also pass. |
| 5 | Passed on this PC (2026-10-22) | `desktop/tests/realmodels.spec.ts` on a fresh data folder: the setup screen's recommended preset (narrowed to voice input and output, so FLUX is not loaded beside them) downloads the runtimes (2.9 GB), installs the bundles and starts both services in 6.2 min; a speech job completes through the TTS service; a live call in chat hears Chromium's fake microphone, ends the utterance and sends the transcript to chat in 13 s. The run found and fixed four bugs: the hardware probe's lost NVML environment, chat's firewall blocking `/api/stt`, first-run bytecode compilation breaking the speech service, and health counted before the models loaded. Vitest covers verdicts, presets, bundles, licence gating and the member view; GPU items are greyed with the reason without an NVIDIA GPU. |
| 6 | Built, not released | The NSIS installer builds unsigned. A runtime update keeps the old pack running; the supervisor stops its services only while the new one replaces it (tested in the pack store and the planner). An overlay records the Torch layer it was built on and never runs on another: after a layer update, the other bundles show an update and their services wait for it. Signing (DT-6.2) is wired for Azure Artifact Signing or a certificate, and needs Q-5. The updater reads a public feed (Q-4). The clean-machine install and upgrade checks follow signing. |
| 7 | Not applicable yet | It waits for first-release feedback. |
| 8 | Built, not verified | Covered: macOS staging, Keychain, process groups (each service in its own session, signalled as a group) and a parent watch that stops a service whose supervisor died (Windows uses the Job Object), the Parakeet-MLX service with energy end-of-utterance (protocol tests on Windows), Qwen3-TTS on `mps`, the entitlements and usage text. Mac runs are needed for DT-0.2, DT-0.3 and the Phase 8 gate. |
| 9 | Later | — |

### Deviations from the plan

- **Wheel installer.** Packs install through our own wheel installer (`app/models/wheels.py`), not PyPA
  `installer`, because PyTorch's wheels list files their RECORD omits. The installer accepts unlisted files, hashes
  everything it writes and rewrites RECORD, so the verify job checks every file a wheel installed. The bytecode
  Omnix compiles into a pack at install is not in RECORD and is not verified.
- **Bytecode is compiled ahead.** Packs are compiled at install, and the app source and standard library at
  staging (shipped, unchecked-hash); model services run with `PYTHONDONTWRITEBYTECODE` and without the shared
  cache prefix. On Windows a speech service that compiled its imports on its first run stopped accepting
  connections (the first live call after the setup screen never connected; a restarted service worked; deleting
  only the bytecode cache reproduced it). The mechanism inside the event loop is not understood; the first run no
  longer compiles anything.
- **Live voice reaches the speech proxy.** Chat's view API firewall did not list `/api/stt`, so the authority probe
  and the live socket were refused in the browser (also on `main`); chat now lists it.
- **Pytorch download host.** The pytorch index serves wheels from `download-r2.pytorch.org`, so that host is on the
  download allow-list.
- **Licence migration number.** The acceptance migration is `0168` in the voice feature folder, because 0166 and
  0167 were already applied in the live database.
- **Staged voice samples.** Staging ships only `voice_clones/default_ref.wav`. The repository's other voice samples
  are recordings of real people and are not staged.
- **Mac end-of-utterance.** The Mac service detects it from audio energy (700 ms of silence after 250 ms of speech,
  with an adaptive noise floor), not from a model. DT-0.2 decides whether that is good enough or push-to-talk stays.

- **Voice Studio folder installs.** DT-1.1's migration of Voice Studio's `resources/models/<kind>/...` installs and
  their `.omnix-model.json` acceptances into the Hugging Face cache was dropped. The desktop app never had those
  folders, and outside it Voice Studio keeps installing as before, now with pinned revisions, digest checks and
  acceptances recorded in the table.
- **`.pth` files run.** `service_boot` adds pack folders with `site.addsitedir`, so `.pth` files inside packs run
  (§4.3 said none). The packs come only from hashed wheels, and some wheels need theirs.
- **Gateway online.** The gateway and job worker do not get `HF_HUB_OFFLINE=1` (§4.2 lists it): the job worker
  downloads the packs. Model services are offline.
- **Embedding model without acceptance.** The memory embedding model downloads on first start without a licence
  prompt (D-4 says every model). It is part of the core app, like the gateway's own packages, not a model pack.
- **Not built from §4.5 / DT-5.2:** download progress in the tray, and a link from Voice Studio to Settings, Models.

### Open items for the owner

- **Q-1 to Q-5** (§7): Intel Macs, workspaces shown, names, release feed, signing identities.
- **Mac runs:** DT-0.2, DT-0.3, DT-8.x, and the Mac ffmpeg pin. No LGPL arm64 build is pinned yet.
- **`default_ref.wav`:** confirm its provenance before the first public build.
- **Clean-machine checks:** the clean Windows account (Phase 3) and the clean machine (Phase 6 gate).
- **Older NVIDIA driver:** a voice-input run on a driver below 580, to confirm NeMo's fallback (R-3).
### Known low-severity items (implementation review round 3)

- Verify checks every file a wheel installed, not the bytecode Omnix compiles into a pack.
- The shipped app bytecode is unchecked-hash: an update that replaced `.py` files but not their `.pyc` would run the
  old code. The installer replaces the whole install folder, so this needs a partial update to happen.
- A service that never gets ready keeps reporting "starting" (after ten minutes it no longer holds the others back).
- The STT proxy waits 10 s for the speech service and the browser 5 s; a speech service slower than that to accept
  fails the call (none was, once first-run bytecode compilation stopped).
- Migration 0169 is a `contract` migration: an Omnix older than it refuses a database that has it.

### Implementation review log

Three rounds with an independent review agent against `git diff main...electron` (2026-10-22):

- **Round 1:** 2 High, 6 Medium, 9 Low. The highs were concurrent overlay installs deleting each other's wheels, and
  model services loading at once past the memory headroom. Fixed in `7479a08f20`, along with:
  - runtime authority bound to the stored job;
  - pack removal and update while a service runs;
  - macOS supervision;
  - the configuration registry;
  - the packs folder move;
  - the setup screen for members and guests.
- **Round 2:** the round-1 fixes held; it found new issues, fixed in `8706f320ac`:
  - New: install-time bytecode went to the job worker's cache prefix, image models loaded outside the memory check,
    and services wrote bytecode into the install folder.
  - Regressions: a never-ready service blocked the others, stale overlays ran on a new Torch layer, re-acceptance
    after a licence change could not be recorded, and the disk check refused installed bundles.
- **Round 3:** every round-2 item fixed. One Medium: a packs folder moved across drives loses timestamp-checked
  bytecode. Fixed with unchecked-hash pack bytecode and timestamp-preserving copies, along with the cheap lows:
  - a half-removed model's retry;
  - overlays installed before base locks were recorded;
  - a failed image preload reporting not ready;
  - 0169's phase label.

  The reviewer judged the remaining items minor (above).
