"""FLOAT for the live portrait service: upstream's modules, Omnix's streaming wrapper around them.

Upstream's code (catalog entry ``float-code``) and weights (``float``) are installed unmodified at pinned
digests; the code's digests are checked again every time it loads. The service imports upstream's top-level
``models`` and ``options`` packages from that folder. Nothing upstream is patched (ADR-0015): the model here
is Omnix's own module tree built from upstream's classes, with three of its parts Omnix's own:

- the audio encoder loads wav2vec2 with eager attention, because upstream's forward asks for attention
  outputs, which current transformers refuses under SDPA; its parameter names match upstream's checkpoint;
- the timestep embedder keeps its frequency table on the GPU (upstream copies it from the CPU on every call,
  which a CUDA graph capture does not allow);
- the decoder's flow layers build their sampling grid once per size on the GPU (upstream rebuilds it with
  NumPy on every call, which leaves decoding CPU-bound).

Each window's Euler solve (torchdiffeq's fixed-grid Euler, as upstream uses it) runs as one captured CUDA
graph. Phase 0 measured these: the same motion latents as upstream's eager path, 23 ms per pass at nfe 7.
The emotion is a label (no speech-to-emotion model is loaded).

Each portrait also gets an idle loop (``idle_frames``): about 12 s of silence rendered from the rest pose, cut to
the loop ``services.portrait.idle_loop`` chooses, rendered once per quality level and kept with the portrait.
"""
from __future__ import annotations

import argparse
import importlib
import logging
import math
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn.functional as F
from torch import nn

from services.helper_models import HelperUnavailable
from app.conversation.portrait_stream_contract import QUALITY_LEVELS
from services.portrait.scheduler import SAMPLES_PER_FRAME, PassPlan

logger = logging.getLogger(__name__)

CODE_MODEL = "float-code"
WEIGHTS_MODEL = "float"
AUDIO_MODEL = "wav2vec2-base-960h"
DETECTOR_MODEL = "s3fd-face-detector"
REQUIRED_MODELS = (CODE_MODEL, WEIGHTS_MODEL, AUDIO_MODEL, DETECTOR_MODEL)
EMOTIONS = ("angry", "disgust", "fear", "happy", "neutral", "sad", "surprise")
DEFAULT_NFE = 7
FRAME_SIZE = 512
IDLE_SEED = 7_919
# The allocator's ceiling (OMNIX_PORTRAIT_VRAM_CAP_MB). On Windows the driver backs VRAM past the card with host
# memory instead of failing, and cuDNN sizes a convolution's workspace from the free VRAM PyTorch reports. Uncapped,
# the face detector's warm-up once took 15 GB of VRAM and ran from host memory, its process unkillable (2026-10-30).
# Capped, cuDNN's large-workspace algorithms fail to allocate and it picks another; the load peaks at 3.5 GB.
VRAM_CAP_MB = 4096
# The end-of-reply transition back to the idle loop's first frame: at most twice the idle loop's frame-to-frame motion
# (about 0.25 in FLOAT's motion space), in 6 to 20 frames, eased in and out.
TRANSITION_STEP = 0.5
TRANSITION_MIN_FRAMES = 6
TRANSITION_MAX_FRAMES = 20


class PortraitModelMissing(HelperUnavailable):
    """A portrait model is not installed, or its files do not match the catalog; the message says which."""


def model_folder(model_id: str) -> Path | None:
    """Where an installed portrait model's files are: the desktop snapshot, or ``resources/models/portrait``."""
    from app.models.catalog import load
    from app.models.local import installed_snapshot
    from app.runtime.paths import resources_models_root

    snapshot = installed_snapshot(model_id)
    if snapshot is not None:
        return snapshot
    folder = resources_models_root() / "portrait" / load().model(model_id).folder_name
    return folder if folder.is_dir() else None


def cap_vram() -> int:
    """Cap this process's CUDA allocator before anything is allocated; returns the cap in MB."""
    from app.config.env import env_int

    cap_mb = env_int("OMNIX_PORTRAIT_VRAM_CAP_MB", VRAM_CAP_MB, minimum=1024, maximum=65_536)
    total = torch.cuda.get_device_properties(0).total_memory
    torch.cuda.set_per_process_memory_fraction(min(1.0, cap_mb * 2**20 / total))
    return cap_mb


def required_folders() -> dict[str, Path]:
    folders, missing = {}, []
    for model_id in REQUIRED_MODELS:
        folder = model_folder(model_id)
        if folder is None:
            missing.append(model_id)
        else:
            folders[model_id] = folder
    if missing:
        raise PortraitModelMissing("Install the live portrait's models from Settings, Models: " + ", ".join(missing))
    return folders


def verify_code(folder: Path) -> None:
    """Upstream's source files must match their catalogued digests before they are imported."""
    from app.models.catalog import load
    from app.models.downloads import sha256_file

    for item in load().model(CODE_MODEL).files:
        path = folder / item.path
        if not path.is_file() or sha256_file(path) != item.sha256:
            raise PortraitModelMissing(f"FLOAT's code file {item.path} is missing or changed; reinstall {CODE_MODEL}")


# --- Omnix's parts of the model ----------------------------------------------------------------------


class GpuTimestepEmbedder(nn.Module):
    """Upstream's TimestepEmbedder with its sinusoid frequency table kept on the GPU (same arithmetic)."""

    def __init__(self, upstream: nn.Module, max_period: int = 10_000) -> None:
        super().__init__()
        self.mlp = upstream.mlp
        size = int(upstream.frequency_embedding_size)
        half = size // 2
        freqs = torch.exp(-math.log(max_period) * torch.arange(start=0, end=half, dtype=torch.float32) / half)
        self.register_buffer("freqs", freqs, persistent=False)
        self.odd = size % 2 == 1

    def forward(self, t: torch.Tensor) -> torch.Tensor:
        args = t[:, None].float() * self.freqs[None]
        embedding = torch.cat([torch.cos(args), torch.sin(args)], dim=-1)
        if self.odd:
            embedding = torch.cat([embedding, torch.zeros_like(embedding[:, :1])], dim=-1)
        return self.mlp(embedding)


class CachedGridToFlow(nn.Module):
    """Upstream's ToFlow with its sampling grid built once per size on the GPU (same arithmetic)."""

    def __init__(self, upstream: nn.Module) -> None:
        super().__init__()
        self.conv = upstream.conv
        self.bias = upstream.bias
        self.upsample = getattr(upstream, "upsample", None)
        self._grids: dict[tuple[int, torch.device], torch.Tensor] = {}

    def _grid(self, size: int, device: torch.device) -> torch.Tensor:
        key = (size, device)
        if key not in self._grids:
            line = torch.linspace(-1, 1, size, dtype=torch.float64)
            grid_x, grid_y = torch.meshgrid(line, line, indexing="xy")
            self._grids[key] = torch.stack([grid_x, grid_y], dim=2).float().unsqueeze(0).to(device)
        return self._grids[key]

    def forward(self, input: torch.Tensor, style: torch.Tensor, feat: torch.Tensor,  # noqa: A002 - upstream's
                skip: torch.Tensor | None = None):
        out = self.conv(input, style) + self.bias
        if skip is not None:
            out = out + self.upsample(skip)
        sampler = torch.tanh(out[:, 0:2, :, :])
        mask = torch.sigmoid(out[:, 2:3, :, :])
        flow = sampler.permute(0, 2, 3, 1) + self._grid(input.size(2), input.device).expand(input.size(0), -1, -1, -1)
        feat_warp = F.grid_sample(feat, flow, align_corners=False) * mask
        return feat_warp, feat_warp + input * (1.0 - mask), out, flow


class AudioEncoder(nn.Module):
    """wav2vec2 (all hidden layers) and upstream's projection, one feature per video frame."""

    def __init__(self, wav2vec_model: type, wav2vec_dir: Path, dim_w: int) -> None:
        super().__init__()
        self.wav2vec2 = wav2vec_model.from_pretrained(str(wav2vec_dir), local_files_only=True,
                                                      attn_implementation="eager")
        self.wav2vec2.requires_grad_(False)
        self.audio_projection = nn.Sequential(nn.Linear(12 * 768, dim_w), nn.LayerNorm(dim_w), nn.SiLU())

    def forward(self, audio: torch.Tensor, frames: int) -> torch.Tensor:
        hidden = self.wav2vec2(audio, seq_len=frames, output_hidden_states=True).hidden_states
        stacked = torch.stack(hidden[1:], dim=1).permute(0, 2, 1, 3)
        return self.audio_projection(stacked.reshape(stacked.shape[0], stacked.shape[1], -1))


class FloatModel(nn.Module):
    """Upstream's motion autoencoder and FMT, with Omnix's audio encoder; parameter names as in float.pth."""

    def __init__(self, upstream: dict[str, Any], opt: Any, wav2vec_dir: Path) -> None:
        super().__init__()
        self.motion_autoencoder = upstream["Generator"](size=opt.input_size, style_dim=opt.dim_w, motion_dim=opt.dim_m)
        self.audio_encoder = AudioEncoder(upstream["Wav2VecModel"], wav2vec_dir, opt.dim_w)
        self.fmt = upstream["FlowMatchingTransformer"](opt)

    def use_omnix_parts(self) -> None:
        self.fmt.t_embedder = GpuTimestepEmbedder(self.fmt.t_embedder)
        decoder = self.motion_autoencoder.dec
        decoder.to_flows = nn.ModuleList(CachedGridToFlow(layer) for layer in decoder.to_flows)


def _import_upstream(code_dir: Path) -> dict[str, Any]:
    path = str(code_dir)
    if path not in sys.path:
        sys.path.insert(0, path)
    generator = importlib.import_module("models.float.generator")
    fmt = importlib.import_module("models.float.FMT")
    wav2vec = importlib.import_module("models.wav2vec2")
    options = importlib.import_module("options.base_options")
    return {"Generator": generator.Generator, "FlowMatchingTransformer": fmt.FlowMatchingTransformer,
            "Wav2VecModel": wav2vec.Wav2VecModel, "BaseOptions": options.BaseOptions}


# --- the window solve --------------------------------------------------------------------------------


class WindowSolver:
    """One window's Euler solve captured as a CUDA graph; inputs are copied into static tensors."""

    def __init__(self, model: FloatModel, opt: Any, nfe: int) -> None:
        self.model, self.opt = model, opt
        window, carry, dim = opt.wav2vec_sec * opt.fps, opt.num_prev_frames, opt.dim_w
        self.window, self.carry = int(window), int(carry)
        self.x0 = torch.zeros(1, self.window, dim, device="cuda")
        self.wa = torch.zeros(1, self.window, dim, device="cuda")
        self.prev_x = torch.zeros(1, self.carry, dim, device="cuda")
        self.prev_wa = torch.zeros(1, self.carry, dim, device="cuda")
        self.wr = torch.zeros(1, dim, device="cuda")  # FMT adds the sequence axis itself
        self.we = torch.zeros(1, 1, len(EMOTIONS), device="cuda")
        self.times = torch.linspace(0, 1, nfe, device="cuda")
        self.out = torch.zeros_like(self.x0)
        self.lock = threading.Lock()
        stream = torch.cuda.Stream()
        stream.wait_stream(torch.cuda.current_stream())
        with torch.cuda.stream(stream):
            for _ in range(3):
                self._run()
        torch.cuda.current_stream().wait_stream(stream)
        self.graph = torch.cuda.CUDAGraph()
        with torch.cuda.graph(self.graph):
            self._run()

    def _run(self) -> None:
        x = self.x0
        for index in range(self.times.shape[0] - 1):
            velocity = self.model.fmt.forward_with_cfv(
                t=self.times[index:index + 1], x=x, wa=self.wa, wr=self.wr, we=self.we,
                prev_x=self.prev_x, prev_wa=self.prev_wa,
                a_cfg_scale=self.opt.a_cfg_scale, r_cfg_scale=self.opt.r_cfg_scale, e_cfg_scale=self.opt.e_cfg_scale,
            )[:, self.carry:]
            x = x + (self.times[index + 1] - self.times[index]) * velocity
        self.out.copy_(x)

    def __call__(self, wa: torch.Tensor, prev_x: torch.Tensor, prev_wa: torch.Tensor, wr: torch.Tensor,
                 we: torch.Tensor, seed: int) -> torch.Tensor:
        with self.lock:  # one set of static inputs: streams take turns
            generator = torch.Generator("cuda").manual_seed(seed)
            self.x0.copy_(torch.randn(1, self.window, self.opt.dim_w, device="cuda", generator=generator))
            for static, value in ((self.wa, wa), (self.prev_x, prev_x), (self.prev_wa, prev_wa), (self.wr, wr),
                                  (self.we, we)):
                static.copy_(value)
            self.graph.replay()
            return self.out.clone()


# --- the runtime -------------------------------------------------------------------------------------


@dataclass
class Portrait:
    """One portrait's encoding: FLOAT's identity latent, its decoder features and its motion reference."""

    key: str
    s_r: torch.Tensor
    s_r_feats: list[torch.Tensor]
    r_s: torch.Tensor
    # The idle loop's motion latents, and its JPEG frames by quality level (made on first use); its frames with the
    # eyes shut, likewise.
    idle: torch.Tensor | None = None
    idle_jpegs: dict[int, list[bytes]] = field(default_factory=dict)
    blink_jpegs: dict[int, list[bytes]] = field(default_factory=dict)
    # The silence features the idle loop was rendered with (a carry's audio half when a reply starts from it).
    idle_wa: torch.Tensor | None = None


def emotion_vector(label: str) -> torch.Tensor:
    index = EMOTIONS.index(label if label in EMOTIONS else "neutral")
    return F.one_hot(torch.tensor(index, device="cuda"), num_classes=len(EMOTIONS)).float().view(1, 1, -1)


class FloatRuntime:
    """The loaded model, its window solver, the face detector and the encoded portraits."""

    def __init__(self, folders: dict[str, Path], *, nfe: int = DEFAULT_NFE, buffer_frames: int = 100,
                 decode_batch: int = 4) -> None:
        # The longest buffer a pass uses: 50 frames of context before the window and the 50-frame window.
        self.buffer_frames = buffer_frames
        self.decode_batch = decode_batch
        self.vram_cap_mb = cap_vram()
        verify_code(folders[CODE_MODEL])
        upstream = _import_upstream(folders[CODE_MODEL])
        self.opt = upstream["BaseOptions"]().initialize(argparse.ArgumentParser()).parse_args([])
        self.opt.rank, self.opt.ngpus, self.opt.nfe = 0, 1, nfe
        self.lock = threading.Lock()
        model = FloatModel(upstream, self.opt, folders[AUDIO_MODEL])
        state = torch.load(folders[WEIGHTS_MODEL] / "float.pth", map_location="cpu", weights_only=True)
        # As upstream loads it: every parameter but wav2vec2's (from its own checkpoint) comes from float.pth.
        missing = [name for name, _ in model.named_parameters()
                   if name not in state and not name.startswith("audio_encoder.wav2vec2.")]
        if missing:
            raise PortraitModelMissing(f"float.pth does not fit FLOAT's code: {len(missing)} weights missing")
        parameters = dict(model.named_parameters())
        with torch.no_grad():
            for name, value in state.items():
                if name in parameters:
                    parameters[name].copy_(value)
        del state
        model.use_omnix_parts()
        self.model = model.requires_grad_(False).to("cuda").eval()
        from services.portrait.idle_loop import EYELID_DIRECTION

        with torch.no_grad():  # the direction a blink moves along (a unit vector in motion space)
            self.eyelid = self.model.motion_autoencoder.dec.direction(None)[:, EYELID_DIRECTION].contiguous()
        self.detector_path = folders[DETECTOR_MODEL] / "s3fd-619a316812.pth"
        self._detector: Any = None
        self.portraits: dict[str, Portrait] = {}
        with torch.no_grad():
            self.solver = WindowSolver(self.model, self.opt, nfe)
            self._warm()

    @property
    def window(self) -> int:
        return self.solver.window

    def detect(self, rgb: np.ndarray) -> list[list[float]]:
        if self._detector is None:
            from face_alignment.detection.sfd.sfd_detector import SFDDetector

            self._detector = SFDDetector(device="cuda", path_to_detector=str(self.detector_path))
        # S3FD was trained on BGR images (face_alignment flips RGB before detecting).
        return [list(box) for box in self._detector.detect_from_image(np.ascontiguousarray(rgb[..., ::-1]))]

    @torch.no_grad()
    def prepare(self, key: str, payload: bytes) -> Portrait:
        """Crop and encode a portrait once per key (tenant, image digest, model revision)."""
        from services.portrait.portrait_image import portrait_pixels

        with self.lock:
            if key in self.portraits:
                return self.portraits[key]
        return self.encode(key, portrait_pixels(payload, self.detect))

    @torch.no_grad()
    def encode(self, key: str, pixels: np.ndarray) -> Portrait:
        """Encode an already cropped 512 px RGB portrait."""
        image = torch.from_numpy(pixels.astype(np.float32) / 127.5 - 1.0).permute(2, 0, 1).unsqueeze(0).cuda()
        s_r, _, s_r_feats = self.model.motion_autoencoder.enc(image, input_target=None)
        r_s_lambda = self.model.motion_autoencoder.enc.fc(s_r)
        portrait = Portrait(key, s_r, s_r_feats, self.model.motion_autoencoder.dec.direction(r_s_lambda))
        with self.lock:
            self.portraits[key] = portrait
        return portrait

    def _warm(self) -> None:
        """Run every network once at the one input shape it will see (each new shape costs seconds once)."""
        self.features(np.zeros(max(self.buffer_frames, 1) * SAMPLES_PER_FRAME, dtype=np.float32))
        self.resample(np.zeros(2_400, dtype=np.float32), 24_000)  # the TTS rate: builds the sinc kernel once
        blank = self.encode("warm-up", np.zeros((512, 512, 3), dtype=np.uint8))
        zeros = torch.zeros(self.decode_batch, self.opt.dim_w, device="cuda")
        for level, (size, _, _) in enumerate(QUALITY_LEVELS):  # each frame size once
            if all(item[0] != size for item in QUALITY_LEVELS[:level]):
                self.render(blank, zeros, level)
        self.forget("warm-up")
        from services.portrait.portrait_image import DETECT_HEIGHT, DETECT_WIDTH

        self.detect(np.zeros((DETECT_HEIGHT, DETECT_WIDTH, 3), dtype=np.uint8))

    def forget(self, key: str) -> None:
        with self.lock:
            self.portraits.pop(key, None)

    @torch.no_grad()
    def features(self, audio: np.ndarray) -> torch.Tensor:
        """Projected wav2vec2 features, one per video frame, for a buffer normalized as a whole.

        Every buffer is given to wav2vec2 at one length, ``buffer_frames``, with silence before it: each new
        input length costs about 0.4 s of one-off convolution setup on the GPU (Phase 1 runtime check), and
        a pass's buffer grows over an output's first passes. The silence is added after normalization.
        """
        frames = len(audio) // SAMPLES_PER_FRAME
        normalized = (audio[: frames * SAMPLES_PER_FRAME] - audio.mean()) / np.sqrt(audio.var() + 1e-7)
        lead = max(0, self.buffer_frames - frames) * SAMPLES_PER_FRAME
        padded = np.concatenate([np.zeros(lead, dtype=np.float32), normalized.astype(np.float32)])
        tensor = torch.from_numpy(padded).unsqueeze(0).cuda()
        return self.model.audio_encoder(tensor, len(padded) // SAMPLES_PER_FRAME)[:, -frames:]

    @torch.no_grad()
    def render(self, portrait: Portrait, latents: torch.Tensor, level: int = 0) -> list[bytes]:
        """JPEG frames for motion latents (frames x dim), at a quality level's size and JPEG quality.

        Encoded on the CPU (libjpeg-turbo, about 2 ms a frame): torchvision's GPU encoder returned noise for
        some frames of a batch in the Phase 1 runtime check (2026-10-29), which SyncNet scored as lost sync.
        """
        from torchvision.io import encode_jpeg

        size, _, quality = QUALITY_LEVELS[level]
        pixels = self.render_pixels(portrait, latents)
        if size != FRAME_SIZE:
            pixels = F.interpolate(pixels.float(), size=(size, size), mode="bilinear", antialias=True,
                                   align_corners=False).round().clamp(0, 255).to(torch.uint8)
        return [bytes(encode_jpeg(frame, quality=quality).numpy()) for frame in pixels.cpu()]

    @torch.no_grad()
    def idle_latents(self, portrait: Portrait) -> torch.Tensor:
        """The portrait's idle loop: silence rendered window after window from the rest pose, then cut."""
        from services.portrait.idle_loop import IDLE_RENDER_FRAMES, choose_loop

        if portrait.idle is not None:
            return portrait.idle
        carry, dim = self.solver.carry, self.opt.dim_w
        silence = self.features(np.zeros(self.buffer_frames * SAMPLES_PER_FRAME, dtype=np.float32))[0, -self.window:]
        neutral = emotion_vector("neutral")
        prev_x = torch.zeros(carry, dim, device="cuda")  # the rest pose: the source portrait itself
        prev_wa = torch.zeros(carry, dim, device="cuda")
        windows = []
        for index in range(math.ceil(IDLE_RENDER_FRAMES / self.window)):
            sample = self.solver(silence[None], prev_x[None], prev_wa[None], portrait.r_s, neutral,
                                 IDLE_SEED + index)[0]
            windows.append(sample)
            prev_x, prev_wa = sample[-carry:], silence[-carry:]
        latents = torch.cat(windows)
        start, stop = choose_loop(latents.cpu().numpy())
        portrait.idle = latents[start:stop].clone()
        portrait.idle_wa = silence[-carry:].clone()
        return portrait.idle

    def idle_frames(self, portrait: Portrait, level: int = 0) -> list[bytes]:
        """The idle loop's JPEG frames at a quality level (rendered once per portrait and level)."""
        from services.portrait.idle_loop import idle_frame_step

        if level not in portrait.idle_jpegs:
            step = idle_frame_step(level)
            portrait.idle_jpegs[level] = self.render(portrait, self.idle_latents(portrait)[::step], level)
        return portrait.idle_jpegs[level]

    def blink_frames(self, portrait: Portrait, level: int = 0) -> list[bytes]:
        """Each idle loop frame with its eyes shut, in the same order: the browser blinks by fading a loop frame into
        its twin and back."""
        from services.portrait.idle_loop import eyes_shut, idle_frame_step

        if level not in portrait.blink_jpegs:
            loop = self.idle_latents(portrait)[::idle_frame_step(level)]
            portrait.blink_jpegs[level] = self.render(portrait, eyes_shut(loop, self.eyelid), level)
        return portrait.blink_jpegs[level]

    @torch.no_grad()
    def render_pixels(self, portrait: Portrait, latents: torch.Tensor) -> torch.Tensor:
        """RGB frames (frames x 3 x 512 x 512, uint8) for motion latents, decoded ``decode_batch`` at a time.

        A short batch is filled with copies of its last latent and the extras are dropped: the decoder
        then only ever sees one batch size (a new one costs about 28 s of one-off setup on the 4090).
        """
        frames = latents.shape[0]
        pixels_out = []
        for start in range(0, frames, self.decode_batch):
            chunk = latents[start:start + self.decode_batch]
            real = chunk.shape[0]
            if real < self.decode_batch:
                chunk = torch.cat([chunk, chunk[-1:].expand(self.decode_batch - real, -1)])
            feats = [item.expand(self.decode_batch, *item.shape[1:]) for item in portrait.s_r_feats]
            images, _ = self.model.motion_autoencoder.dec(portrait.s_r + chunk, alpha=None, feats=feats)
            pixels_out.append(((images[:real].clamp(-1, 1) + 1) * 127.5).to(torch.uint8))
        return torch.cat(pixels_out)

    def session(self, portrait: Portrait, emotion: str = "neutral") -> FloatSession:
        return FloatSession(self, portrait, emotion_vector(emotion))

    def portrait(self, key: str) -> Portrait | None:
        with self.lock:
            return self.portraits.get(key)

    @staticmethod
    def resample(audio: np.ndarray, rate: int) -> np.ndarray:
        """16 kHz audio for the scheduler, band-limited (torchaudio's sinc resampler, on the CPU)."""
        from services.portrait.scheduler import SAMPLE_RATE

        if rate == SAMPLE_RATE or len(audio) == 0:
            return audio.astype(np.float32, copy=False)
        import torchaudio.functional as audio_functional

        return audio_functional.resample(torch.from_numpy(audio.astype(np.float32)), rate, SAMPLE_RATE).numpy()


class FloatSession:
    """The scheduler's MotionSession for one portrait: committed latents and audio features, frame by frame."""

    def __init__(self, runtime: FloatRuntime, portrait: Portrait, we: torch.Tensor) -> None:
        self.runtime, self.portrait, self.we = runtime, portrait, we
        dim = runtime.opt.dim_w
        self.latents = torch.zeros(0, dim, device="cuda")
        self.feats = torch.zeros(0, dim, device="cuda")
        self.level = 0  # the call's quality level (the service's ``quality`` message sets it)

    @torch.no_grad()
    def run_pass(self, audio: np.ndarray, plan: PassPlan, seed: int) -> None:
        runtime, window, carry = self.runtime, self.runtime.window, self.runtime.solver.carry
        wa = runtime.features(audio)[0, plan.start - plan.buffer_start:]
        if wa.shape[0] < window:  # beyond the audio: upstream pads by replicating the last feature
            wa = torch.cat([wa, wa[-1:].expand(window - wa.shape[0], -1)], dim=0)
        wa = wa[:window]
        prev_x, prev_wa = self.latents[plan.carry_start:plan.start], self.feats[plan.carry_start:plan.start]
        if prev_x.shape[0] < carry:
            lead_x, lead_wa = self._lead_in(carry - prev_x.shape[0])
            prev_x, prev_wa = torch.cat([lead_x, prev_x]), torch.cat([lead_wa, prev_wa])
        sample = runtime.solver(wa[None], prev_x[None], prev_wa[None], self.portrait.r_s, self.we, seed)[0]
        self.latents = torch.cat([self.latents[:plan.start], sample[:plan.commit]])
        self.feats = torch.cat([self.feats[:plan.start], wa[:plan.commit]])

    def _lead_in(self, frames: int) -> tuple[torch.Tensor, torch.Tensor]:
        """What a reply's motion continues from: the idle loop leading into its first frame.

        The browser holds the idle loop on that frame once the user stops speaking, so the reply's first frame is
        one step from the one on screen. From the rest pose (zeros, as upstream starts) it was 12 to 20 idle steps
        away, and the browser's crossfade between the two showed a double face (owner's rating, 2026-10-30).
        """
        idle, idle_wa = self.portrait.idle, self.portrait.idle_wa
        dim = self.runtime.opt.dim_w
        if idle is None or idle_wa is None or idle.shape[0] < 2:
            zeros = torch.zeros(frames, dim, device="cuda")
            return zeros, zeros
        # The loop wraps from its last frame to its first: the frames before frame 0 are its last ones.
        lead = torch.cat([idle[-(frames - 1):], idle[:1]]) if frames > 1 else idle[:1]
        return lead[-frames:], idle_wa[-frames:]

    @torch.no_grad()
    def transition(self) -> list[bytes]:
        """Frames from the reply's last pose to the idle loop's first, rendered in motion space (never a pixel blend).

        The browser plays them as the reply ends, then resumes the idle loop from its first frame.
        """
        idle = self.portrait.idle
        if idle is None or self.latents.shape[0] == 0:
            return []
        start, end = self.latents[-1], idle[0]
        distance = float(torch.linalg.norm(end - start))
        count = min(TRANSITION_MAX_FRAMES, max(TRANSITION_MIN_FRAMES, math.ceil(distance / TRANSITION_STEP)))
        progress = torch.arange(1, count + 1, device="cuda", dtype=start.dtype) / (count + 1)
        eased = progress * progress * (3 - 2 * progress)  # smoothstep: no jolt at either end
        latents = start[None] + eased[:, None] * (end - start)[None]
        step = QUALITY_LEVELS[self.level][1]
        return self.runtime.render(self.portrait, latents[::step], self.level)

    def decode(self, start: int, stop: int) -> list[bytes | None]:
        """JPEG frames for [start, stop); at a level that sends every other frame, None for the others."""
        step = QUALITY_LEVELS[self.level][1]
        kept = [index for index in range(start, stop) if index % step == 0]
        if not kept:
            return [None] * (stop - start)
        jpegs = iter(self.runtime.render(self.portrait, self.latents[kept], self.level))
        return [next(jpegs) if index % step == 0 else None for index in range(start, stop)]

    def reset(self) -> None:
        self.latents = self.latents[:0]
        self.feats = self.feats[:0]

    def spawn(self) -> FloatSession:
        session = FloatSession(self.runtime, self.portrait, self.we)
        session.level = self.level
        return session


__all__ = [
    "CODE_MODEL", "DEFAULT_NFE", "EMOTIONS", "FloatRuntime", "FloatSession", "Portrait", "PortraitModelMissing",
    "REQUIRED_MODELS", "TRANSITION_MAX_FRAMES", "TRANSITION_MIN_FRAMES", "model_folder", "required_folders",
    "verify_code",
]
