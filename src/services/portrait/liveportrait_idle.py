"""LivePortrait idle loops for the live portrait: a recorded idle motion moves each portrait, ahead of a call.

FlashHead's silent renders barely move, and rarely blink (in a third of 14 s renders, measured 2026-11-21).
FlashHead has no head or eyelid control, so the idle loop has a different source. LivePortrait (KwaiVGI, MIT code and
weights: catalog entries ``liveportrait-code`` and ``liveportrait-weights``, installed unmodified and the code's
digests checked every time it loads) moves a still portrait by 3D keypoints. An idle motion recorded once (a person
sitting still, looking at the camera, not talking) is kept as each frame's change from its first frame: head pose,
expression, translation and scale (``IdleMotion``, made by ``scripts/portrait_idle_motion.py``). One ships with the
service (``assets/idle-motion.npz``, 237 frames); a user's own recording in the portrait models' folder replaces it.

It moves a portrait as follows:
- each frame's keypoints are the portrait's own plus that frame's change. The lips keep the portrait's expression, and
  LivePortrait's stitching network keeps the shoulders in place;
- the motion's loop is cut where it comes back closest to its first frame, and the rest of the change is ramped out,
  so the loop's last frame leads into its first (``close_loop``). Its first frame is the portrait's own pose, which is
  where FlashHead starts a reply;
- each frame also has an eyes-shut twin, from LivePortrait's eye retargeting network, for the browser's blinks.

A loop of about 9.5 s renders in about 5 s on the 4090, plus as long again for its twins, all at 512 px. The warp needs
about 0.7 GB of VRAM a frame, so frames render two at a time (2026-11-21 freeze: never spill into shared memory).
"""
from __future__ import annotations

import importlib
import importlib.util
import os
import sys
import types
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

CODE_MODEL = "liveportrait-code"
WEIGHTS_MODEL = "liveportrait-weights"
MODELS = (CODE_MODEL, WEIGHTS_MODEL)
# The idle motion's file: OMNIX_PORTRAIT_IDLE_MOTION, else the user's own (idle-motion.npz in the portrait models'
# folder, made by scripts/portrait_idle_motion.py), else the one shipped with the service.
MOTION_ENV = "OMNIX_PORTRAIT_IDLE_MOTION"
MOTION_FILE = "idle-motion.npz"
SHIPPED_MOTION = Path(__file__).resolve().parent / "assets" / MOTION_FILE
FPS = 25
KEYPOINTS = 21
# LivePortrait's keypoints for the lips (kept as the portrait's: FlashHead owns the mouth) and for the eyes.
LIP_KEYPOINTS = (6, 12, 14, 17, 19, 20)
EYE_KEYPOINTS = (11, 13, 15, 16, 18)
INPUT_SIZE = 256
BATCH = 2
# The eye retargeting network's eye-opening ratios: the portrait's eyes taken as open (0.35), and shut (0).
EYES_OPEN = 0.35
EYES_SHUT = 0.0
# A loop is at least MIN_LOOP_FRAMES (8 s) and at most MAX_FRAMES (30 s) long.
MIN_LOOP_FRAMES = 200
MAX_FRAMES = 750
# The largest change from the first frame an idle motion may hold: more is not sitting still.
MAX_POSE_DEGREES = 20.0
MAX_TRANSLATION = 0.3
MAX_SCALE = 0.3
MAX_EXPRESSION = 1.0
# Smoothing along time against the motion extractor's jitter (frames, odd): pose, translation and scale, expression.
SMOOTH_FRAMES = 5
SMOOTH_EXPRESSION_FRAMES = 3
# The weights of each part of a frame's distance from the first, for where the loop closes (about one unit each for
# a degree of pose, a hundredth of translation or scale, and 0.05 of expression outside the lips).
CLOSE_WEIGHTS = {"pose": 1.0, "t": 100.0, "scale": 100.0, "exp": 20.0}
PACKAGE = "omnix_liveportrait_modules"
WEIGHT_FILES = {
    "appearance": "liveportrait/base_models/appearance_feature_extractor.pth",
    "motion": "liveportrait/base_models/motion_extractor.pth",
    "warping": "liveportrait/base_models/warping_module.pth",
    "decoder": "liveportrait/base_models/spade_generator.pth",
    "retargeting": "liveportrait/retargeting_models/stitching_retargeting_module.pth",
}


class IdleMotionError(ValueError):
    """An idle motion file that is missing, malformed or does not sit still."""


@dataclass(frozen=True)
class IdleMotion:
    """Each frame's change from the motion's first frame (whose change is zero), as a closed loop at FPS."""

    pose: np.ndarray  # frames x 3: pitch, yaw and roll, in degrees
    exp: np.ndarray  # frames x 21 x 3: the keypoints' expression offsets
    t: np.ndarray  # frames x 2: the x and y translation
    scale: np.ndarray  # frames x 1: the relative change of scale

    @property
    def frames(self) -> int:
        return int(self.pose.shape[0])

    def validate(self) -> IdleMotion:
        frames = self.frames
        shapes = {"pose": (frames, 3), "exp": (frames, KEYPOINTS, 3), "t": (frames, 2), "scale": (frames, 1)}
        for name, shape in shapes.items():
            value = getattr(self, name)
            if value.shape != shape:
                raise IdleMotionError(f"the idle motion's {name} is {value.shape}, not {shape}")
            if not np.isfinite(value).all():
                raise IdleMotionError(f"the idle motion's {name} is not finite")
        if not MIN_LOOP_FRAMES <= frames <= MAX_FRAMES:
            raise IdleMotionError(f"the idle motion has {frames} frames, not {MIN_LOOP_FRAMES} to {MAX_FRAMES}")
        limits = {"pose": MAX_POSE_DEGREES, "t": MAX_TRANSLATION, "scale": MAX_SCALE, "exp": MAX_EXPRESSION}
        for name, limit in limits.items():
            if float(np.abs(getattr(self, name)).max()) > limit:
                raise IdleMotionError(f"the idle motion's {name} moves more than {limit} from its first frame")
        return self

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as handle:
            np.savez(handle, pose=self.pose, exp=self.exp, t=self.t, scale=self.scale, fps=np.array(FPS))

    @classmethod
    def load(cls, path: Path) -> IdleMotion:
        try:
            with np.load(path, allow_pickle=False) as data:
                if int(data["fps"]) != FPS:
                    raise IdleMotionError(f"the idle motion is at {int(data['fps'])} fps, not {FPS}")
                motion = cls(*(np.asarray(data[name], dtype=np.float32) for name in ("pose", "exp", "t", "scale")))
        except (OSError, KeyError, ValueError) as error:
            if isinstance(error, IdleMotionError):
                raise
            raise IdleMotionError(f"the idle motion {path.name} cannot be read: {error}") from error
        return motion.validate()


def user_motion_path() -> Path:
    """Where a user's own idle motion goes: the portrait models' folder."""
    from app.runtime.paths import resources_models_root

    return resources_models_root() / "portrait" / MOTION_FILE


def motion_path() -> Path:
    """Where the idle motion is: OMNIX_PORTRAIT_IDLE_MOTION, else the user's own if they made one, else the shipped
    one."""
    override = os.environ.get(MOTION_ENV, "").strip()
    if override:
        return Path(override)
    own = user_motion_path()
    return own if own.is_file() else SHIPPED_MOTION


def smooth(values: np.ndarray, frames: int) -> np.ndarray:
    """A moving average along the first axis over ``frames`` (odd), the ends repeated."""
    if frames <= 1:
        return values.astype(np.float32, copy=True)
    flat = values.reshape(values.shape[0], -1).astype(np.float64)
    half = frames // 2
    padded = np.concatenate([np.repeat(flat[:1], half, axis=0), flat, np.repeat(flat[-1:], half, axis=0)])
    sums = np.cumsum(np.concatenate([np.zeros((1, flat.shape[1])), padded]), axis=0)
    return ((sums[frames:] - sums[:-frames]) / frames).reshape(values.shape).astype(np.float32)


def relative_motion(pose: np.ndarray, exp: np.ndarray, t: np.ndarray, scale: np.ndarray) -> IdleMotion:
    """Each tracked frame's change from the first, smoothed: ``pose`` (frames x 3 degrees), ``exp`` (frames x 21 x
    3), ``t`` (frames x 2 or 3; only x and y are kept) and ``scale`` (frames x 1), as the motion extractor gives them.
    Not yet a loop (``close_loop``)."""
    return IdleMotion(pose=smooth(pose - pose[:1], SMOOTH_FRAMES),
                      exp=smooth(exp - exp[:1], SMOOTH_EXPRESSION_FRAMES),
                      t=smooth(t[:, :2] - t[:1, :2], SMOOTH_FRAMES),
                      scale=smooth(scale / scale[:1] - 1, SMOOTH_FRAMES))


def close_loop(motion: IdleMotion, *, min_loop: int = MIN_LOOP_FRAMES) -> IdleMotion:
    """The loop in a relative motion: it ends just before the frame, past ``min_loop``, closest to the first (lips
    left out), and the change at that frame is ramped out linearly, so the last frame leads into the first."""
    frames = motion.frames
    if frames <= min_loop:
        raise IdleMotionError(f"the idle motion has {frames} frames; a loop needs more than {min_loop}")
    face = [index for index in range(KEYPOINTS) if index not in LIP_KEYPOINTS]
    cost = (CLOSE_WEIGHTS["pose"] * np.abs(motion.pose).sum(axis=1)
            + CLOSE_WEIGHTS["t"] * np.abs(motion.t).sum(axis=1)
            + CLOSE_WEIGHTS["scale"] * np.abs(motion.scale)[:, 0]
            + CLOSE_WEIGHTS["exp"] * np.abs(motion.exp[:, face]).sum(axis=(1, 2)))
    end = min_loop + int(np.argmin(cost[min_loop:]))
    ramp = (np.arange(end, dtype=np.float32) / end)

    def closed(values: np.ndarray) -> np.ndarray:
        return (values[:end] - ramp.reshape(-1, *([1] * (values.ndim - 1))) * values[end]).astype(np.float32)

    return IdleMotion(pose=closed(motion.pose), exp=closed(motion.exp), t=closed(motion.t),
                      scale=closed(motion.scale))


def _import_upstream(code_dir: Path) -> dict[str, Any]:
    """Upstream's networks and camera helpers, imported from its folder as a package of their own (its modules
    import each other relatively; its folder is named ``src``, as Omnix's is, so it is never put on the path)."""
    modules = code_dir / "src" / "modules"
    if PACKAGE not in sys.modules:
        package = types.ModuleType(PACKAGE)
        package.__path__ = [str(modules)]  # type: ignore[attr-defined]
        sys.modules[PACKAGE] = package
    name = f"{PACKAGE}_camera"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, code_dir / "src" / "utils" / "camera.py")
        if spec is None or spec.loader is None:
            raise ImportError("LivePortrait's camera helpers cannot be loaded")
        camera = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(camera)
        sys.modules[name] = camera

    def load(module: str, attribute: str) -> Any:
        return getattr(importlib.import_module(f"{PACKAGE}.{module}"), attribute)

    return {"appearance": load("appearance_feature_extractor", "AppearanceFeatureExtractor"),
            "motion": load("motion_extractor", "MotionExtractor"),
            "warping": load("warping_network", "WarpingNetwork"),
            "decoder": load("spade_generator", "SPADEDecoder"),
            "retargeting": load("stitching_retargeting_network", "StitchingRetargetingNetwork"),
            "camera": sys.modules[name]}


def folders() -> dict[str, Path] | None:
    """The two LivePortrait folders, or None when either is not installed."""
    from services.portrait.float_runtime import model_folder

    found = {model_id: model_folder(model_id) for model_id in MODELS}
    if any(folder is None for folder in found.values()):
        return None
    return {model_id: folder for model_id, folder in found.items() if folder is not None}


class LivePortrait:
    """LivePortrait's networks on the GPU (about 0.5 GB), run at fp16 under autocast."""

    def __init__(self, model_folders: dict[str, Path]) -> None:
        import torch
        import yaml

        from services.portrait.float_runtime import verify_code

        code = model_folders[CODE_MODEL]
        verify_code(code, CODE_MODEL, "LivePortrait")
        upstream = _import_upstream(code)
        self.torch = torch
        self.camera = upstream["camera"]
        params = yaml.safe_load((code / "src" / "config" / "models.yaml").read_text(encoding="utf-8"))["model_params"]
        weights = model_folders[WEIGHTS_MODEL]

        def network(kind: str, key: str) -> Any:
            net = upstream[kind](**params[key])
            net.load_state_dict(torch.load(weights / WEIGHT_FILES[kind], map_location="cpu", weights_only=True))
            return net.to("cuda").eval().requires_grad_(False)

        self.appearance = network("appearance", "appearance_feature_extractor_params")
        self.motion_net = network("motion", "motion_extractor_params")
        self.warping = network("warping", "warping_module_params")
        self.decoder = network("decoder", "spade_generator_params")
        retargeting = torch.load(weights / WEIGHT_FILES["retargeting"], map_location="cpu", weights_only=True)
        retarget_params = params["stitching_retargeting_module_params"]

        def retarget(part: str, checkpoint_key: str) -> Any:
            net = upstream["retargeting"](**retarget_params[part])
            net.load_state_dict({key.replace("module.", ""): value
                                 for key, value in retargeting[checkpoint_key].items()})
            return net.to("cuda").eval().requires_grad_(False)

        self.stitching = retarget("stitching", "retarget_shoulder")
        self.eyes = retarget("eye", "retarget_eye")

    # --- the networks -------------------------------------------------------------------------------------

    def _input(self, rgb: np.ndarray) -> Any:
        torch = self.torch
        x = torch.from_numpy(np.ascontiguousarray(rgb)).to("cuda").permute(2, 0, 1)[None].float() / 255
        mode = "area" if rgb.shape[0] > INPUT_SIZE else "bilinear"
        return torch.nn.functional.interpolate(x, size=(INPUT_SIZE, INPUT_SIZE), mode=mode)

    def keypoints(self, x: Any) -> dict[str, Any]:
        """The motion extractor's reading of a 256 px input: pose in degrees, keypoints, expression, translation
        and scale."""
        torch = self.torch
        with torch.no_grad(), torch.autocast("cuda", dtype=torch.float16):
            info = self.motion_net(x)
        info = {key: value.float() for key, value in info.items()}
        for key in ("pitch", "yaw", "roll"):
            info[key] = self.camera.headpose_pred_to_degree(info[key])[:, None]
        info["kp"] = info["kp"].reshape(x.shape[0], -1, 3)
        info["exp"] = info["exp"].reshape(x.shape[0], -1, 3)
        return info

    @staticmethod
    def _transform(kp: Any, rotation: Any, exp: Any, scale: Any, t: Any) -> Any:
        moved = (kp @ rotation + exp) * scale[..., None]
        moved[:, :, 0:2] += t[:, None, 0:2]
        return moved

    def _stitch(self, kp_source: Any, kp_driving: Any) -> Any:
        batch, count = kp_source.shape[:2]
        delta = self.stitching(self.torch.cat([kp_source.view(batch, -1), kp_driving.view(batch, -1)], dim=1))
        kp = kp_driving + delta[..., :3 * count].reshape(batch, count, 3)
        kp[..., :2] += delta[..., 3 * count:3 * count + 2].reshape(batch, 1, 2)
        return kp

    def _warp(self, feature: Any, kp_source: Any, kp_driving: Any) -> Any:
        torch = self.torch
        with torch.autocast("cuda", dtype=torch.float16):
            warped = self.warping(feature, kp_source=kp_source, kp_driving=kp_driving)
            image = self.decoder(feature=warped["out"])
        return (image.float().clamp(0, 1) * 255).round().to(torch.uint8)

    # --- motion and loops ---------------------------------------------------------------------------------

    def extract(self, frames: Iterable[np.ndarray]) -> IdleMotion:
        """An idle motion (a closed loop) from a recording's face crops (RGB, square), read one frame at a time."""
        torch = self.torch
        pose, exp, t, scale = [], [], [], []
        with torch.no_grad():
            for rgb in frames:
                info = self.keypoints(self._input(rgb))
                pose.append(torch.cat([info["pitch"], info["yaw"], info["roll"]], dim=1)[0].cpu().numpy())
                exp.append(info["exp"][0].cpu().numpy())
                t.append(info["t"][0].cpu().numpy())
                scale.append(info["scale"][0].cpu().numpy())
        if len(pose) <= MIN_LOOP_FRAMES:
            raise IdleMotionError(f"the recording has {len(pose)} frames; an idle loop needs more than "
                                  f"{MIN_LOOP_FRAMES} ({MIN_LOOP_FRAMES / FPS:.0f} s)")
        relative = relative_motion(np.stack(pose), np.stack(exp), np.stack(t), np.stack(scale).reshape(-1, 1))
        return close_loop(relative).validate()

    def render(self, rgb: np.ndarray, motion: IdleMotion,
               adjust: Callable[[Any], Any] | None = None) -> tuple[Any, Any]:
        """The portrait (512 px RGB) moved by the motion: its idle loop and each frame's eyes-shut twin (both
        frames x 3 x 512 x 512 uint8, on the CPU). ``adjust`` takes each batch on the GPU (uint8, batch x 3 x 512 x
        512) and returns it changed, for the engine's colour matching."""
        torch = self.torch
        camera = self.camera
        with torch.no_grad():
            x = self._input(rgb)
            source = self.keypoints(x)
            with torch.autocast("cuda", dtype=torch.float16):
                feature = self.appearance(x).float()
            rotation = camera.get_rotation_matrix(source["pitch"], source["yaw"], source["roll"])
            kp_source = self._transform(source["kp"], rotation, source["exp"], source["scale"], source["t"])
            tensors = {name: torch.from_numpy(getattr(motion, name)).to("cuda")
                       for name in ("pose", "exp", "t", "scale")}
            lips = list(LIP_KEYPOINTS)
            idle, shut = [], []
            for first in range(0, motion.frames, BATCH):
                part = slice(first, min(motion.frames, first + BATCH))
                count = part.stop - part.start
                exp = source["exp"] + tensors["exp"][part]
                exp[:, lips] = source["exp"][:, lips]
                pose = tensors["pose"][part]
                moved_rotation = camera.get_rotation_matrix(source["pitch"][:, 0] + pose[:, 0],
                                                            source["yaw"][:, 0] + pose[:, 1],
                                                            source["roll"][:, 0] + pose[:, 2])
                t = source["t"].expand(count, -1).clone()
                t[:, :2] += tensors["t"][part]
                t[:, 2] = 0
                scale = source["scale"] * (1 + tensors["scale"][part])
                kp_s = kp_source.expand(count, -1, -1)
                kp_driving = self._stitch(kp_s, self._transform(source["kp"].expand(count, -1, -1), moved_rotation,
                                                                exp, scale, t))
                ratio = torch.tensor([[EYES_OPEN, EYES_OPEN, EYES_SHUT]], device="cuda").expand(count, -1)
                closing = self.eyes(torch.cat([kp_s.reshape(count, -1), ratio], dim=1)).reshape(count, -1, 3)
                features = feature.expand(count, -1, -1, -1, -1)
                opened = self._warp(features, kp_s, kp_driving)
                closed = self._warp(features, kp_s, kp_driving + closing)
                if adjust is not None:  # the twin takes its frame's adjustment, so only its eyes differ
                    adjusted = adjust(opened)
                    closed = (adjusted.short() + closed.short() - opened.short()).clamp(0, 255).to(torch.uint8)
                    opened = adjusted
                idle.append(opened.cpu())
                shut.append(closed.cpu())
        return torch.cat(idle), torch.cat(shut)


__all__ = ["CODE_MODEL", "IdleMotion", "IdleMotionError", "LivePortrait", "MODELS", "WEIGHTS_MODEL", "close_loop",
           "folders", "motion_path", "relative_motion", "smooth"]
