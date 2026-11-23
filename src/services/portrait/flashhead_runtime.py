"""SoulX-FlashHead Lite for the live portrait service: upstream's modules, Omnix's streaming wrapper around them.

The second live portrait engine, chosen over FLOAT in Settings, Assistant (spike: docs/measurements/
flashhead-lite-spike-2026-11-21.json: closer lip-sync, about twice FLOAT's GPU time). Upstream's code (catalog entry
``flashhead-code``) and weights (``flashhead-lite``) are installed unmodified at pinned digests; the code's digests
are checked again every time it loads. Nothing upstream is patched (ADR-0015): the service imports upstream's model,
VAE, audio encoder and colour matching, and this module does what upstream's pipeline class does, as a stream:

- a pass generates 33 frames from the 9 frames before it (encoded by the VAE as its 2 motion latents) and 8 s of
  audio ending where its new frames end, in 4 denoising steps (upstream's schedule, shifted by 5); its 24 new frames
  are colour-matched to the portrait and the scheduler keeps the first ``commit`` of them;
- the motion before a reply's first frame is the idle loop leading into its first frame, which the browser holds once
  the user stops speaking (as FLOAT's does).

Upstream's pipeline module is never imported: it imports mediapipe for its face crop (0.74 GB of commit) and
``torch.distributed``'s multi-GPU parts. xfuser (multi-GPU sequence parallel, whose import fails on Windows) is given a
stand-in that refuses every call, and so is pyloudnorm when it is not installed (only upstream's unused loudness
helper calls it). Eager PyTorch only (no ``torch.compile``: the service's torch has no Triton on Windows); the spike
measured about 0.3 s a pass eager on the 4090.

The idle loop and its eyes-shut twins come from LivePortrait when its models are installed (``liveportrait_idle``;
an idle motion ships with the service): a recorded idle motion moves the portrait, and LivePortrait's eye retargeting shuts each
frame's eyes. The loop's first frame is the portrait's own pose, where a reply starts; its frames are colour-matched to
the portrait as FlashHead's own are.

Without them, the loop is FlashHead's own silence. That motion blinks by itself, but rarely in silence (in a third of
14 s renders, measured 2026-11-21, and a loop may hold none), so the browser's blinks need eyes-shut twins as FLOAT's
do. FlashHead has no eyelid control: a twin is the loop frame with the area around its eyes taken from a silent
render's own blink (``blink_frame``), the idle loop's render or, ahead of a call, another seed's (``find_blink``); it
lines up because every silent render starts from the portrait and the head barely moves in silence (0 px over a
loop). A portrait without a clear blink (dark glasses, say) keeps the loop's frames as their own twins (fading a frame
into itself changes nothing).
"""
from __future__ import annotations

import collections
import importlib
import importlib.util
import logging
import sys
import threading
import types
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn.functional as F

from app.conversation.portrait_stream_contract import PORTRAIT_START_RULES, QUALITY_LEVELS
from services.portrait.float_runtime import (AUDIO_MODEL, DETECTOR_MODEL, FRAME_SIZE, FloatRuntime,
                                             cap_vram, encode_jpegs, verify_code)
from services.portrait.float_runtime import required_folders as _required_folders
from services.portrait.scheduler import SAMPLES_PER_FRAME, PassPlan, StreamSettings

logger = logging.getLogger(__name__)

CODE_MODEL = "flashhead-code"
WEIGHTS_MODEL = "flashhead-lite"
REQUIRED_MODELS = (CODE_MODEL, WEIGHTS_MODEL, AUDIO_MODEL, DETECTOR_MODEL)
# The allocator's ceiling (OMNIX_PORTRAIT_VRAM_CAP_MB; see float_runtime.VRAM_CAP_MB): the spike's peak was 5.5 GB.
VRAM_CAP_MB = 7168
DTYPE = torch.bfloat16
# Upstream's settings (flash_head/configs/infer_params.yaml): 33 frames a pass, 2 motion latents (9 frames: the VAE's
# temporal stride is 8), 8 s of audio, 4 steps at upstream's timesteps shifted by 5, full colour correction.
FRAMES = 33
MOTION_FRAMES = 9
NEW_FRAMES = FRAMES - MOTION_FRAMES
AUDIO_FRAMES = 200
TIMESTEPS = (1000.0, 750.0, 500.0, 250.0, 0.0)
SHIFT = 5.0
NUM_TIMESTEPS = 1000.0
COLOR_STRENGTH = 1.0
# Each frame takes wav2vec2's states for itself and the two frames on either side (upstream's get_audio_embedding).
AUDIO_NEIGHBOURS = 2
IDLE_SEED = 7_919
# The idle loop: about 14.4 s of silence rendered (15 passes) and a loop of at least 8 s cut from it, past the first
# pass. A reply starts from the loop's own last frames (``lead``), never from the picture, so unlike FLOAT's the loop
# need not stay near the picture: kept near it, it was the stillest 4 s of the render, without a blink, and looked
# like the picture itself (owner report, 2026-11-21). Silence blinks and sways by itself every few seconds.
IDLE_RENDER_PASSES = 15
IDLE_MIN_LOOP_FRAMES = 200
# The render's own blink, for the loop's eyes-shut twins: the frame whose eye band (rows and columns as fractions of
# the frame) differs most from the render's median, where the eye band changes BLINK_MIN_RISE times as much, against
# the rest of the frame, as it usually does, and the change is over within BLINK_HALF_FRAMES either side (a blink, not
# a look away). Eye bands are compared at BLINK_BAND_SIZE px square.
BLINK_ROWS = (0.25, 0.55)
BLINK_COLUMNS = (0.25, 0.75)
BLINK_BAND_SIZE = 128
BLINK_MIN_RISE = 1.6
BLINK_HALF_FRAMES = 8
# Silent renders with other seeds that ``find_blink`` tries, ahead of a call, when the idle loop's render has no blink.
BLINK_SEARCH_SEEDS = 2
TRANSITION_SEED = 104_729
# Committed frames a session keeps on the GPU (about 0.8 MB each): a pass needs the 9 before it, and a speculative
# prefix rewinds at most a pass or two.
KEEP_FRAMES = 150
# The end-of-reply transition: silence rendered on from the reply's last frames, cut at the frame (after the first
# TRANSITION_MIN_FRAMES) closest to the idle loop's first, whose last TRANSITION_BLEND_FRAMES fade into it.
TRANSITION_MIN_FRAMES = 6
TRANSITION_BLEND_FRAMES = 4
# Encoded portraits kept: the reference latent, the idle loop's JPEGs, and until those are made its raw frames on the
# CPU (0.8 MB each, 200 or more a loop and as many eyes-shut twins with LivePortrait: 300 MB or more a portrait;
# review 2026-11-22: kept for good, four portraits held over a gigabyte of host commit; ``release_frames``).
MAX_PORTRAITS = 4
# The scheduler's settings for FlashHead's windows: 24 new frames a pass from the 9 before them, the first pass 8
# frames (the spike: the same lip-sync, the first frame ~0.56 s after the audio starts), no lookahead (a pass's
# 8 s of audio ends with its window), and a pass taking about 0.35 s eager. The browser holds a start up to the
# engine's ``PORTRAIT_START_RULES`` hold, so the play estimate before its first report does too.
STREAM_SETTINGS = StreamSettings(window=NEW_FRAMES, carry=MOTION_FRAMES, first_hop=8, hop=NEW_FRAMES, lookahead=0,
                                 context=AUDIO_FRAMES - NEW_FRAMES, decode_batch=8, pass_seconds=0.35,
                                 render_ahead_seconds=1.5,
                                 start_hold_seconds=PORTRAIT_START_RULES["flashhead-lite"][0] / 1000)


def required_folders() -> dict[str, Path]:
    return _required_folders(REQUIRED_MODELS)


def load_liveportrait() -> tuple[Any, Any]:
    """LivePortrait and the idle motion it moves portraits by, or (None, None) when either is not installed or
    cannot load: the idle loop is then FlashHead's own (see the module notes)."""
    from services.portrait import liveportrait_idle

    path = liveportrait_idle.motion_path()
    model_folders = liveportrait_idle.folders()
    if model_folders is None or not path.is_file():
        logger.info("flashhead idle loops: FlashHead's own (LivePortrait %s, idle motion %s)",
                    "installed" if model_folders else "not installed", "found" if path.is_file() else "not found")
        return None, None
    try:
        motion = liveportrait_idle.IdleMotion.load(path)
        networks = liveportrait_idle.LivePortrait(model_folders)
    except Exception:  # noqa: BLE001 - an optional engine: the portrait still serves with FlashHead's own idle loop
        logger.exception("flashhead idle loops: LivePortrait failed to load; using FlashHead's own")
        return None, None
    logger.info("flashhead idle loops: LivePortrait, idle motion of %d frames (%s)", motion.frames, path)
    return networks, motion


def _install_stand_ins() -> None:
    """Stand-ins for the two imports upstream's modules make but a single GPU never calls (see the module notes)."""
    def unavailable(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("FlashHead's multi-GPU sequence parallel is not available in the portrait service")

    if "xfuser" not in sys.modules and importlib.util.find_spec("xfuser") is None:
        distributed = types.ModuleType("xfuser.core.distributed")
        for name in ("get_sequence_parallel_rank", "get_sequence_parallel_world_size", "get_sp_group",
                     "init_distributed_environment", "initialize_model_parallel"):
            setattr(distributed, name, unavailable)
        long_ctx = types.ModuleType("xfuser.core.long_ctx_attention")
        long_ctx.xFuserLongContextAttention = unavailable  # type: ignore[attr-defined]
        root, core = types.ModuleType("xfuser"), types.ModuleType("xfuser.core")
        root.core, core.distributed, core.long_ctx_attention = core, distributed, long_ctx  # type: ignore[attr-defined]
        sys.modules.update({"xfuser": root, "xfuser.core": core, "xfuser.core.distributed": distributed,
                            "xfuser.core.long_ctx_attention": long_ctx})
    if "pyloudnorm" not in sys.modules and importlib.util.find_spec("pyloudnorm") is None:
        loudness = types.ModuleType("pyloudnorm")
        loudness.Meter = unavailable  # type: ignore[attr-defined]
        sys.modules["pyloudnorm"] = loudness


def _import_upstream(code_dir: Path) -> dict[str, Any]:
    _install_stand_ins()
    if str(code_dir) not in sys.path:
        sys.path.insert(0, str(code_dir))
    model = importlib.import_module("flash_head.src.modules.flash_head_model")
    vae = importlib.import_module("flash_head.ltx_video.ltx_vae")
    wav2vec = importlib.import_module("flash_head.audio_analysis.wav2vec2")
    utils = importlib.import_module("flash_head.utils.utils")
    return {"model": model.WanModelAudioProject, "vae": vae.LtxVAE, "wav2vec": wav2vec.Wav2Vec2Model,
            "match_colors": utils.match_and_blend_colors_torch}


def shifted_timesteps(device: str = "cuda") -> list[torch.Tensor]:
    """Upstream's timesteps for 4 steps, through its timestep_transform (shift 5)."""
    out = []
    for value in TIMESTEPS:
        t = torch.tensor([value], device=device) / NUM_TIMESTEPS
        out.append(SHIFT * t / (1 + (SHIFT - 1) * t) * NUM_TIMESTEPS)
    return out


def audio_buffer(audio: np.ndarray, plan: PassPlan) -> np.ndarray:
    """The pass's 8 s of 16 kHz audio, ending where its new frames end: silence before the output's audio and
    after what has arrived (the scheduler's padding past ``buffer_end`` is dropped)."""
    end = plan.start + NEW_FRAMES
    real = audio[: max(0, plan.buffer_end - plan.buffer_start) * SAMPLES_PER_FRAME].astype(np.float32, copy=False)
    buffer = np.zeros(AUDIO_FRAMES * SAMPLES_PER_FRAME, dtype=np.float32)
    offset = (plan.buffer_start - (end - AUDIO_FRAMES)) * SAMPLES_PER_FRAME
    if offset < 0:  # a context longer than the buffer: its oldest audio is dropped
        real, offset = real[-offset:], 0
    real = real[: len(buffer) - offset]
    buffer[offset:offset + len(real)] = real
    return buffer


def frame_features(pixels: torch.Tensor, reference: torch.Tensor) -> np.ndarray:
    """Small per-frame vectors (frames x 3072) of how far each frame is from the portrait, for ``choose_loop``."""
    small = F.interpolate(pixels.float(), size=(32, 32), mode="area")
    ref = F.interpolate(reference.float(), size=(32, 32), mode="area")
    return (small - ref).flatten(1).cpu().numpy()


def eye_bands(pixels: torch.Tensor) -> tuple[np.ndarray, np.ndarray]:
    """Each frame's grey eye band (frames x BLINK_BAND_SIZE x BLINK_BAND_SIZE) and the whole grey frame at the same
    scale, for ``blink_frame``."""
    grey = F.interpolate(pixels.float().mean(dim=1, keepdim=True), size=(BLINK_BAND_SIZE * 2, BLINK_BAND_SIZE * 2),
                         mode="area")[:, 0]
    size = grey.shape[-1]
    rows = slice(int(size * BLINK_ROWS[0]), int(size * BLINK_ROWS[1]))
    columns = slice(int(size * BLINK_COLUMNS[0]), int(size * BLINK_COLUMNS[1]))
    band = F.interpolate(grey[:, None, rows, columns], size=(BLINK_BAND_SIZE, BLINK_BAND_SIZE), mode="area")[:, 0]
    return band.cpu().numpy(), grey.cpu().numpy()


def blink_frame(bands: np.ndarray, frames: np.ndarray, *, skip: int = NEW_FRAMES) -> int | None:
    """The frame of a silent render where its eyes are shut (``eye_bands``' two arrays), or None when it has no clear
    blink: past its first ``skip`` frames (still the picture), the eye band's change from the median frame, against the
    whole frame's, at least BLINK_MIN_RISE times its usual ratio, and down to below 60% of it BLINK_HALF_FRAMES either
    side."""
    if bands.shape[0] < skip + 2 * BLINK_HALF_FRAMES + 1:
        return None
    eye = np.abs(bands - np.median(bands, axis=0)).mean(axis=(1, 2))
    whole = np.abs(frames - np.median(frames, axis=0)).mean(axis=(1, 2))
    rise = (eye / np.maximum(whole, 1e-3)) / max(float(np.median(eye / np.maximum(whole, 1e-3))), 1e-3)
    best: int | None = None
    for index in range(max(skip, BLINK_HALF_FRAMES), bands.shape[0] - BLINK_HALF_FRAMES):
        brief = max(eye[index - BLINK_HALF_FRAMES], eye[index + BLINK_HALF_FRAMES]) < 0.6 * eye[index]
        if rise[index] >= BLINK_MIN_RISE and brief and (best is None or eye[index] > eye[best]):
            best = index
    return best


def idle_loop_bounds(features: np.ndarray, *, skip: int = NEW_FRAMES,
                     min_loop: int = IDLE_MIN_LOOP_FRAMES) -> tuple[int, int]:
    """The idle loop ``[start, stop)`` in a silent render's ``frame_features``: past its first ``skip`` frames (the
    first pass, still the picture), at least ``min_loop`` frames long (shorter when the render is), and ending on the
    frame closest to its first, wherever in the render that is."""
    from services.portrait.idle_loop import choose_loop

    skip = max(0, min(skip, int(features.shape[0]) - 2))
    kept = features[skip:]
    start, stop = choose_loop(kept, span=int(kept.shape[0]), min_loop=min_loop)
    return skip + start, skip + stop


@dataclass
class FlashHeadPortrait:
    """One portrait's encoding: its colour reference, its reference latent and its idle loop."""

    key: str
    cond: torch.Tensor  # 1 x 3 x 1 x 512 x 512 in [-1, 1] (bf16, on the GPU)
    ref_latent: torch.Tensor  # 128 x 5 x 16 x 16 (bf16, on the GPU)
    reference: torch.Tensor  # 1 x 3 x 512 x 512 uint8 (on the GPU): the portrait itself
    # The idle loop's frames (uint8, on the CPU), the 9 frames that lead into its first frame and that frame (on the
    # GPU), the render's eyes-shut frame and its eyes-open frame BLINK_HALF_FRAMES before (uint8, on the CPU; None
    # without a clear blink), and its JPEG frames and eyes-shut twins by quality level (made on first use).
    idle: torch.Tensor | None = None
    # LivePortrait's eyes-shut twin of every idle loop frame (uint8, on the CPU), when it made the loop.
    twins: torch.Tensor | None = None
    shut: torch.Tensor | None = None
    opened: torch.Tensor | None = None
    blink_searched: bool = False
    lead: torch.Tensor | None = None
    idle_first: torch.Tensor | None = None
    idle_jpegs: dict[int, list[bytes]] = field(default_factory=dict)
    blink_jpegs: dict[int, list[bytes]] = field(default_factory=dict)
    # The raw frames above were given up (``release_frames``): another level is encoded from level 0's JPEGs.
    released: bool = False


def decode_jpegs(jpegs: list[bytes]) -> torch.Tensor:
    """RGB pixels (frames x 3 x height x width, uint8, on the CPU) from JPEG frames."""
    from torchvision.io import decode_jpeg

    return torch.stack([decode_jpeg(torch.frombuffer(bytearray(jpeg), dtype=torch.uint8)) for jpeg in jpegs])


class FlashHeadRuntime:
    """The loaded model, VAE and audio encoder, the face detector and the encoded portraits."""

    stream_settings = STREAM_SETTINGS
    resample = staticmethod(FloatRuntime.resample)

    def __init__(self, folders: dict[str, Path]) -> None:
        self.vram_cap_mb = cap_vram(VRAM_CAP_MB)
        verify_code(folders[CODE_MODEL], CODE_MODEL, "FlashHead")
        upstream = _import_upstream(folders[CODE_MODEL])
        weights = folders[WEIGHTS_MODEL]
        self.lock = threading.Lock()
        # Loaded straight to bf16 (upstream loads float32 and then casts: the same weights, twice the host memory).
        self.model = upstream["model"].from_pretrained(str(weights / "Model_Lite"), torch_dtype=DTYPE)
        self.model = self.model.eval().requires_grad_(False).to(device="cuda", dtype=DTYPE)
        self.vae = upstream["vae"](pretrained_model_type_or_path=str(weights / "VAE_LTX"), dtype=DTYPE, device="cuda")
        self.audio_encoder = upstream["wav2vec"].from_pretrained(str(folders[AUDIO_MODEL]),
                                                                 local_files_only=True).to("cuda")
        self.audio_encoder.feature_extractor._freeze_parameters()
        self.match_colors = upstream["match_colors"]
        config = self.model.config
        self.latent_shape = (config.out_dim, (FRAMES - 1) // config.vae_stride[0] + 1,
                             FRAME_SIZE // config.vae_stride[1], FRAME_SIZE // config.vae_stride[2])
        self.timesteps = shifted_timesteps()
        offsets = torch.arange(-AUDIO_NEIGHBOURS, AUDIO_NEIGHBOURS + 1)
        self.centres = (torch.arange(AUDIO_FRAMES - FRAMES, AUDIO_FRAMES)[:, None] + offsets[None]).clamp(
            0, AUDIO_FRAMES - 1).cuda()
        self.detector = _Detector(folders[DETECTOR_MODEL] / "s3fd-619a316812.pth")
        self.liveportrait, self.idle_motion = load_liveportrait()
        self.portraits: collections.OrderedDict[str, FlashHeadPortrait] = collections.OrderedDict()
        with torch.no_grad():
            self.silence = self.context(np.zeros(AUDIO_FRAMES * SAMPLES_PER_FRAME, dtype=np.float32))
            self._warm()

    def detect(self, rgb: np.ndarray) -> list[list[float]]:
        return self.detector(rgb)

    def _warm(self) -> None:
        """Every network once at the one input shape it will see, each JPEG size once, and the detector."""
        self.resample(np.zeros(2_400, dtype=np.float32), 24_000)
        blank = self.encode("warm-up", np.zeros((FRAME_SIZE, FRAME_SIZE, 3), dtype=np.uint8))
        generator = torch.Generator(device="cuda").manual_seed(0)
        frames = self.generate(blank, self.encode_motion(blank.reference.expand(MOTION_FRAMES, -1, -1, -1), generator),
                               self.silence, generator)
        for level, (size, _, _) in enumerate(QUALITY_LEVELS):
            if all(item[0] != size for item in QUALITY_LEVELS[:level]):
                encode_jpegs(frames[:1], level)
        self.forget("warm-up")
        from services.portrait.portrait_image import DETECT_HEIGHT, DETECT_WIDTH

        self.detect(np.zeros((DETECT_HEIGHT, DETECT_WIDTH, 3), dtype=np.uint8))

    # --- the networks -------------------------------------------------------------------------------------

    @torch.no_grad()
    def context(self, buffer: np.ndarray) -> torch.Tensor:
        """The audio conditioning for a pass's 33 frames from its 8 s buffer (upstream's preprocess_audio and
        get_audio_embedding): 1 x 33 x 5 x 12 x 768."""
        normalized = (buffer - buffer.mean()) / np.sqrt(buffer.var() + 1e-7)  # wav2vec2's feature extractor
        tensor = torch.from_numpy(normalized.astype(np.float32)).unsqueeze(0).cuda()
        states = self.audio_encoder(tensor, seq_len=AUDIO_FRAMES, output_hidden_states=True).hidden_states
        embedding = torch.stack(states[1:], dim=1).squeeze(0).permute(1, 0, 2)  # frames x layers x dim
        return embedding[self.centres][None].contiguous()

    @torch.no_grad()
    def encode_motion(self, pixels: torch.Tensor, generator: torch.Generator) -> torch.Tensor:
        """The VAE's latents (128 x frames' latents x 16 x 16) for uint8 frames (frames x 3 x 512 x 512)."""
        video = (pixels.to(DTYPE) / 127.5 - 1.0).permute(1, 0, 2, 3).unsqueeze(0)
        latents = self.vae.model.encode(video, return_dict=False)[0].sample(generator)
        return self.vae.normalize_latents(latents)[0]

    @torch.no_grad()
    def generate(self, portrait: FlashHeadPortrait, motion: torch.Tensor, context: torch.Tensor,
                 generator: torch.Generator) -> torch.Tensor:
        """One pass's 33 frames (33 x 3 x 512 x 512 uint8, on the GPU), as upstream's generate makes them."""
        noise = torch.randn(self.latent_shape, dtype=DTYPE, device="cuda", generator=generator)
        motion_latents = motion.shape[1]
        for index in range(len(self.timesteps) - 1):
            noise[:, :motion_latents] = motion
            flow = self.model(x=noise.unsqueeze(0), timestep=self.timesteps[index], context=context,
                              y=portrait.ref_latent.unsqueeze(0))[0]
            t_now = (self.timesteps[index][:, None, None, None] / NUM_TIMESTEPS).to(DTYPE)
            t_next = (self.timesteps[index + 1][:, None, None, None] / NUM_TIMESTEPS).to(DTYPE)
            x_0 = noise - flow * t_now
            noise = (1 - t_next) * x_0 + t_next * torch.randn(x_0.size(), dtype=x_0.dtype, device="cuda",
                                                                generator=generator)
        noise[:, :motion_latents] = motion
        video = self.match_colors(self.vae.decode(noise), portrait.cond, COLOR_STRENGTH)
        return ((video[0].float() + 1) * 127.5).round().clamp(0, 255).to(torch.uint8).permute(1, 0, 2, 3)

    # --- portraits ----------------------------------------------------------------------------------------

    @torch.no_grad()
    def prepare(self, key: str, payload: bytes) -> FlashHeadPortrait:
        """Crop and encode a portrait once per key (tenant, image digest, engine and its code revision)."""
        from services.portrait.portrait_image import portrait_pixels

        with self.lock:
            if key in self.portraits:
                self.portraits.move_to_end(key)
                return self.portraits[key]
        return self.encode(key, portrait_pixels(payload, self.detect))

    @torch.no_grad()
    def encode(self, key: str, pixels: np.ndarray) -> FlashHeadPortrait:
        """Encode an already cropped 512 px RGB portrait (upstream's prepare_params for one image)."""
        reference = torch.from_numpy(np.ascontiguousarray(pixels)).permute(2, 0, 1).unsqueeze(0).cuda()
        cond = (reference.to(DTYPE) / 127.5 - 1.0).unsqueeze(2)
        generator = torch.Generator(device="cuda").manual_seed(IDLE_SEED)
        latents = self.vae.model.encode(cond.repeat(1, 1, FRAMES, 1, 1), return_dict=False)[0].sample(generator)
        portrait = FlashHeadPortrait(key, cond, self.vae.normalize_latents(latents)[0], reference)
        with self.lock:
            self.portraits[key] = portrait
            self.portraits.move_to_end(key)
            while len(self.portraits) > MAX_PORTRAITS:
                self.portraits.popitem(last=False)
        return portrait

    def forget(self, key: str) -> None:
        with self.lock:
            self.portraits.pop(key, None)

    def portrait(self, key: str) -> FlashHeadPortrait | None:
        with self.lock:
            if key in self.portraits:
                self.portraits.move_to_end(key)
            return self.portraits.get(key)

    @torch.no_grad()
    def silent_render(self, portrait: FlashHeadPortrait, seed: int) -> tuple[torch.Tensor, np.ndarray, int | None]:
        """IDLE_RENDER_PASSES of silence from the portrait itself: the frames (uint8, on the CPU), their
        ``frame_features`` and the frame of its blink (``blink_frame``), if it has one."""
        generator = torch.Generator(device="cuda").manual_seed(seed)
        motion = portrait.ref_latent[:, :1]  # upstream's start: the portrait's own first latent
        rendered, features, bands, greys = [], [], [], []
        for _ in range(IDLE_RENDER_PASSES):
            frames = self.generate(portrait, motion, self.silence, generator)
            rendered.append(frames[MOTION_FRAMES:].cpu())
            features.append(frame_features(frames[MOTION_FRAMES:], portrait.reference))
            band, grey = eye_bands(frames[MOTION_FRAMES:])
            bands.append(band)
            greys.append(grey)
            motion = self.encode_motion(frames[-MOTION_FRAMES:], generator)
        return torch.cat(rendered), np.concatenate(features), blink_frame(np.concatenate(bands), np.concatenate(greys))

    @staticmethod
    def keep_blink(portrait: FlashHeadPortrait, render: torch.Tensor, shut: int | None) -> None:
        """Keep a silent render's blink, its eyes-shut frame and the eyes-open one before it, for the twins."""
        if shut is not None and portrait.shut is None:
            portrait.shut = render[shut:shut + 1].clone()
            portrait.opened = render[shut - BLINK_HALF_FRAMES:shut - BLINK_HALF_FRAMES + 1].clone()
            portrait.blink_jpegs.clear()

    @torch.no_grad()
    def find_blink(self, portrait: FlashHeadPortrait) -> None:
        """When the idle loop's render has no blink, look for one in up to BLINK_SEARCH_SEEDS more silent renders
        (about 7.5 s each; owner report 2026-11-21: the model blinks in one 14 s render of three). Only ahead of a
        call: in a call the GPU thread is the reply's."""
        if portrait.blink_searched:  # before the loop's pixels: once searched, they may have been given up
            return
        self.idle_pixels(portrait)
        if portrait.blink_searched or portrait.twins is not None:
            return
        portrait.blink_searched = True
        for seed in range(IDLE_SEED + 1, IDLE_SEED + 1 + BLINK_SEARCH_SEEDS):
            if portrait.shut is not None:
                return
            render, _, shut = self.silent_render(portrait, seed)
            self.keep_blink(portrait, render, shut)
            logger.info("flashhead blink search: seed %d, blink frame %s", seed, shut)

    @torch.no_grad()
    def idle_pixels(self, portrait: FlashHeadPortrait) -> torch.Tensor:
        """The portrait's idle loop: silence rendered pass after pass from the portrait itself, then cut where its
        last frame comes back closest to its first (``idle_loop_bounds``)."""
        if portrait.idle is not None:
            return portrait.idle
        if portrait.released:  # given up once encoded: level 0's frames (every idle_frame_step(0)th) stand in
            return decode_jpegs(portrait.idle_jpegs[0])
        idle = self.liveportrait_idle(portrait)
        if idle is None:
            render, features, shut = self.silent_render(portrait, IDLE_SEED)
            start, stop = idle_loop_bounds(features)
            idle = render[start:stop].clone()
            self.keep_blink(portrait, render, shut)
            logger.info("flashhead idle loop: %d frames, blink frame %s", idle.shape[0], shut)
        lead =torch.cat([idle[-(MOTION_FRAMES - 1):], idle[:1]]) if idle.shape[0] >= MOTION_FRAMES else None
        portrait.lead = lead.cuda() if lead is not None else None
        portrait.idle_first = idle[:1].cuda()
        portrait.idle = idle
        return idle

    @torch.no_grad()
    def liveportrait_idle(self, portrait: FlashHeadPortrait) -> torch.Tensor | None:
        """The idle loop LivePortrait moves the portrait into, colour-matched to the portrait, with its eyes-shut
        twins kept; None without LivePortrait or when its render fails (the loop is then FlashHead's own)."""
        if self.liveportrait is None or self.idle_motion is None:
            return None

        def match(frames: torch.Tensor) -> torch.Tensor:
            video = (frames.float() / 127.5 - 1.0).permute(1, 0, 2, 3).unsqueeze(0)
            matched = self.match_colors(video, portrait.cond.float(), COLOR_STRENGTH)
            return ((matched[0] + 1) * 127.5).round().clamp(0, 255).to(torch.uint8).permute(1, 0, 2, 3)

        pixels = portrait.reference[0].permute(1, 2, 0).cpu().numpy()
        try:
            idle, twins = self.liveportrait.render(pixels, self.idle_motion, match)
        except Exception:  # noqa: BLE001 - the optional engine failed (out of memory, say): FlashHead's own loop
            logger.exception("flashhead idle loop: LivePortrait's render failed; using FlashHead's own")
            torch.cuda.empty_cache()
            return None
        torch.cuda.empty_cache()  # back to FlashHead's passes the warp's activations (about 0.7 GB a frame)
        portrait.twins = twins
        portrait.blink_searched = True
        portrait.blink_jpegs.clear()
        logger.info("flashhead idle loop: LivePortrait, %d frames", idle.shape[0])
        return idle

    def idle_frames(self, portrait: FlashHeadPortrait, level: int = 0) -> list[bytes]:
        """The idle loop's JPEG frames at a quality level (rendered once per portrait and level)."""
        from services.portrait.idle_loop import idle_frame_step

        if level not in portrait.idle_jpegs:
            step = idle_frame_step(level) // (idle_frame_step(0) if portrait.released else 1)
            portrait.idle_jpegs[level] = encode_jpegs(self.idle_pixels(portrait)[::step].cuda(), level)
            self.release_frames(portrait)
        return portrait.idle_jpegs[level]

    def blink_frames(self, portrait: FlashHeadPortrait, level: int = 0) -> list[bytes]:
        """Each idle loop frame with its eyes shut, in the same order: LivePortrait's twin when it made the loop,
        otherwise the frame with the area around its eyes (``eye_region_mask``) from the render's own blink. Without a
        clear blink, the frame itself."""
        from services.portrait.idle_loop import eye_region_mask, idle_frame_step

        if level not in portrait.blink_jpegs:
            if portrait.released:  # level 0's twins, already made, stand in for the raw frames given up
                twins = decode_jpegs(portrait.blink_jpegs[0])[::idle_frame_step(level) // idle_frame_step(0)]
                portrait.blink_jpegs[level] = encode_jpegs(twins.cuda(), level)
                return portrait.blink_jpegs[level]
            idle = self.idle_pixels(portrait)
            if portrait.twins is not None:
                portrait.blink_jpegs[level] = encode_jpegs(portrait.twins[::idle_frame_step(level)].cuda(), level)
            elif portrait.shut is None or portrait.opened is None:
                portrait.blink_jpegs[level] = self.idle_frames(portrait, level)
            else:
                opened = idle[::idle_frame_step(level)].float()
                shut = portrait.shut.float()
                mask = torch.from_numpy(eye_region_mask((shut - portrait.opened.float())[0].abs().mean(dim=0)
                                                        .numpy()))
                twins = (opened + (shut - opened) * mask).round().clamp(0, 255).to(torch.uint8)
                portrait.blink_jpegs[level] = encode_jpegs(twins.cuda(), level)
            self.release_frames(portrait)
        return portrait.blink_jpegs[level]

    @staticmethod
    def release_frames(portrait: FlashHeadPortrait) -> None:
        """Give up the loop's raw frames, its twins and the blink's frames once level 0's JPEGs of both are made and
        no blink search is left to change them (``MAX_PORTRAITS``). The GPU's lead-in and first frame stay."""
        if portrait.blink_searched and 0 in portrait.idle_jpegs and 0 in portrait.blink_jpegs:
            portrait.idle = portrait.twins = portrait.shut = portrait.opened = None
            portrait.released = True

    @staticmethod
    def rendered_idle_level(portrait: FlashHeadPortrait) -> int | None:
        """The best quality level whose idle loop and blink twins are both rendered already, if any."""
        return next((level for level in sorted(portrait.idle_jpegs) if level in portrait.blink_jpegs), None)

    def session(self, portrait: FlashHeadPortrait, emotion: str = "neutral") -> FlashHeadSession:
        """A stream's session; FlashHead takes no emotion."""
        del emotion
        return FlashHeadSession(self, portrait)


class _Detector:
    """S3FD on the GPU, loaded on first use (as FLOAT's runtime does)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._detector: Any = None

    def __call__(self, rgb: np.ndarray) -> list[list[float]]:
        if self._detector is None:
            from face_alignment.detection.sfd.sfd_detector import SFDDetector

            self._detector = SFDDetector(device="cuda", path_to_detector=str(self.path))
        # S3FD was trained on BGR images (face_alignment flips RGB before detecting).
        return [list(box) for box in self._detector.detect_from_image(np.ascontiguousarray(rgb[..., ::-1]))]


class FlashHeadSession:
    """The scheduler's MotionSession for one portrait: the output's latest committed frames, on the GPU."""

    def __init__(self, runtime: FlashHeadRuntime, portrait: FlashHeadPortrait) -> None:
        self.runtime, self.portrait = runtime, portrait
        self.pixels = torch.zeros(0, 3, FRAME_SIZE, FRAME_SIZE, dtype=torch.uint8, device="cuda")
        self.base = 0  # the output frame ``pixels[0]`` is
        self.level = 0

    @property
    def end(self) -> int:
        return self.base + self.pixels.shape[0]

    def _lead(self, frames: int) -> torch.Tensor:
        """The ``frames`` frames before the output's first: the idle loop leading into its first frame, or the
        portrait itself before the loop is made."""
        lead = self.portrait.lead
        if lead is None:
            return self.portrait.reference.expand(frames, -1, -1, -1)
        return lead[-frames:]

    def motion(self, start: int, generator: torch.Generator) -> torch.Tensor:
        """The motion latents a pass from frame ``start`` continues from: the 9 frames before it."""
        if start == 0 and self.portrait.lead is None:
            return self.portrait.ref_latent[:, :1]  # upstream's start, before the idle loop exists
        first = max(start - MOTION_FRAMES, self.base)
        have = self.pixels[first - self.base:start - self.base] if start > self.base else self.pixels[:0]
        missing = MOTION_FRAMES - have.shape[0]
        frames = torch.cat([self._lead(missing), have]) if missing else have
        return self.runtime.encode_motion(frames, generator)

    @torch.no_grad()
    def run_pass(self, audio: np.ndarray, plan: PassPlan, seed: int) -> None:
        runtime = self.runtime
        generator = torch.Generator(device="cuda").manual_seed(seed)
        self.rewind(plan.start)
        motion = self.motion(plan.start, generator)
        frames = runtime.generate(self.portrait, motion, runtime.context(audio_buffer(audio, plan)), generator)
        if self.pixels.shape[0] == 0:
            self.base = plan.start
        self.pixels = torch.cat([self.pixels, frames[MOTION_FRAMES:MOTION_FRAMES + plan.commit]])
        if (excess := self.pixels.shape[0] - KEEP_FRAMES) > 0:
            self.pixels, self.base = self.pixels[excess:], self.base + excess

    def decode(self, start: int, stop: int) -> list[bytes | None]:
        """JPEG frames for [start, stop); at a level that sends every other frame, None for the others (and for a
        frame no longer kept)."""
        step = QUALITY_LEVELS[self.level][1]
        kept = [index for index in range(start, stop) if index % step == 0 and self.base <= index < self.end]
        if not kept:
            return [None] * (stop - start)
        jpegs = dict(zip(kept, encode_jpegs(self.pixels[[index - self.base for index in kept]], self.level)))
        return [jpegs.get(index) for index in range(start, stop)]

    @torch.no_grad()
    def transition(self) -> list[bytes]:
        """Frames from the reply's last frame to the idle loop's first: silence rendered on from the reply, cut at the
        frame closest to the loop's first, its last few faded into it. The browser plays them as the reply ends,
        then resumes the idle loop from its first frame."""
        target = self.portrait.idle_first
        if target is None or self.pixels.shape[0] == 0:
            return []
        runtime = self.runtime
        generator = torch.Generator(device="cuda").manual_seed(TRANSITION_SEED + self.end)
        frames = runtime.generate(self.portrait, self.motion(self.end, generator), runtime.silence,
                                  generator)[MOTION_FRAMES:]
        distance = np.linalg.norm(frame_features(frames, target), axis=1)
        count = TRANSITION_MIN_FRAMES + int(np.argmin(distance[TRANSITION_MIN_FRAMES - 1:]))
        sequence = frames[:count].float()
        blend = min(TRANSITION_BLEND_FRAMES, count)
        progress = torch.arange(1, blend + 1, device="cuda", dtype=torch.float32) / (blend + 1)
        eased = (progress * progress * (3 - 2 * progress))[:, None, None, None]
        sequence[-blend:] = sequence[-blend:] + eased * (target.float() - sequence[-blend:])
        step = QUALITY_LEVELS[self.level][1]
        return encode_jpegs(sequence[::step].round().clamp(0, 255).to(torch.uint8), self.level)

    def reset(self) -> None:
        self.pixels, self.base = self.pixels[:0], 0

    def rewind(self, frames: int) -> None:
        if frames <= self.base:
            self.pixels, self.base = self.pixels[:0], frames
        else:
            self.pixels = self.pixels[:frames - self.base]

    def spawn(self) -> FlashHeadSession:
        session = FlashHeadSession(self.runtime, self.portrait)
        session.level = self.level
        return session


__all__ = ["CODE_MODEL", "FlashHeadPortrait", "FlashHeadRuntime", "FlashHeadSession", "REQUIRED_MODELS",
           "STREAM_SETTINGS", "VRAM_CAP_MB", "WEIGHTS_MODEL", "audio_buffer", "required_folders",
           "shifted_timesteps"]
