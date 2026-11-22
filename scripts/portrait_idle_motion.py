"""Make the live portrait's idle motion from a recording of someone sitting still (LivePortrait idle loops).

Record 10-15 s at 25 fps, if you can: head and shoulders, looking at the camera, not talking, blinking as usual,
in even light. The script finds the face in the first frame, crops every frame around it the way a portrait is
cropped, reads each frame's head pose and expression with LivePortrait, and saves the change from the first frame as
a closed loop (``services.portrait.liveportrait_idle``). It is saved in the portrait models' folder, where the
FlashHead engine prefers it to the shipped motion from its next start.

    <portrait interpreter> scripts/portrait_idle_motion.py clip.mp4 [--start 2] [--end 14] [--out PATH]

Run it with the portrait service's interpreter (it needs torch, OpenCV, face_alignment and the LivePortrait models),
while no call is running: it caps its VRAM at 3 GB and reads the video one frame at a time.
"""
from __future__ import annotations

import argparse
import sys
from collections.abc import Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

VRAM_CAP_MB = 3072


def frames(path: Path, start: float, end: float | None, fps: int) -> Iterator:
    """The recording's RGB frames between ``start`` and ``end`` seconds, at ``fps`` (the nearest frame to each
    output time), one at a time."""
    import cv2

    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise SystemExit(f"cannot open {path}")
    source_fps = capture.get(cv2.CAP_PROP_FPS) or fps
    index, wanted = 0, start
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                return
            time = index / source_fps
            index += 1
            if end is not None and time >= end:
                return
            if time + 0.5 / source_fps < wanted:
                continue
            wanted += 1 / fps
            yield cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    finally:
        capture.release()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("video", type=Path)
    parser.add_argument("--start", type=float, default=0.0, help="seconds into the recording to start")
    parser.add_argument("--end", type=float, default=None, help="seconds into the recording to stop")
    parser.add_argument("--out", type=Path, default=None, help="the motion file (default: the portrait models' folder)")
    args = parser.parse_args()

    import numpy as np

    from services.portrait import liveportrait_idle
    from services.portrait.float_runtime import DETECTOR_MODEL, cap_vram, model_folder
    from services.portrait.portrait_image import crop_square, face_box

    cap_vram(VRAM_CAP_MB)
    model_folders = liveportrait_idle.folders()
    detector_folder = model_folder(DETECTOR_MODEL)
    if model_folders is None or detector_folder is None:
        raise SystemExit("Install the FlashHead live portrait's models (with LivePortrait) from Settings, Models first")
    from face_alignment.detection.sfd.sfd_detector import SFDDetector

    detector = SFDDetector(device="cuda", path_to_detector=str(detector_folder / "s3fd-619a316812.pth"))

    def detect(rgb: np.ndarray) -> list[list[float]]:
        return [list(box) for box in detector.detect_from_image(np.ascontiguousarray(rgb[..., ::-1]))]

    stream = frames(args.video, args.start, args.end, liveportrait_idle.FPS)
    first = next(stream, None)
    if first is None:
        raise SystemExit("the recording has no frames in that range")
    box = face_box(first, detect)

    def crops() -> Iterator[np.ndarray]:
        yield crop_square(first, box)
        for frame in stream:
            yield crop_square(frame, box)

    motion = liveportrait_idle.LivePortrait(model_folders).extract(crops())
    out = args.out or liveportrait_idle.user_motion_path()
    motion.save(out)
    print(f"saved {motion.frames} frames ({motion.frames / liveportrait_idle.FPS:.1f} s) to {out}; largest change "
          f"from the first frame: pose {np.abs(motion.pose).max():.1f} degrees, translation {np.abs(motion.t).max():.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
