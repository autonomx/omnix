"""Portrait images for the live portrait service: limits, decoding and upstream FLOAT's face crop.

The gateway sends the image of a pack's ``base_asset_id``; it never comes from the browser. Byte and pixel
limits are checked before the image is decoded. The crop follows upstream ``generate.py``'s ``process_img``:
detect on a copy scaled to 360 px high (letterboxed onto one canvas size), take the first face scoring over
0.95, square it at 1.6 times the
larger half-side around the face's centre (padding with black past the edges), and resize to 512 px.
Resizing uses Pillow (box filter down, bicubic up) where upstream uses OpenCV's area and cubic filters.
"""
from __future__ import annotations

import io
from collections.abc import Callable, Sequence

import numpy as np

MAX_IMAGE_BYTES = 12 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
OUTPUT_SIZE = 512
DETECT_HEIGHT = 360
DETECT_WIDTH = 640
MIN_SCORE = 0.95
CROP_SCALE = 1.6

# Detect faces in an RGB image; returns (x1, y1, x2, y2, score) boxes.
Detector = Callable[[np.ndarray], Sequence[Sequence[float]]]


class PortraitImageError(ValueError):
    """The image cannot be used as a portrait; the message says why."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def decode_image(payload: bytes) -> np.ndarray:
    """RGB pixels (height x width x 3, uint8), refusing oversized files before decoding them."""
    from PIL import Image, UnidentifiedImageError

    if not payload:
        raise PortraitImageError("image_empty", "The portrait image is empty")
    if len(payload) > MAX_IMAGE_BYTES:
        raise PortraitImageError("image_too_large", f"The portrait image is over {MAX_IMAGE_BYTES // 2**20} MB")
    try:
        with Image.open(io.BytesIO(payload)) as image:
            width, height = image.size
            if width * height > MAX_IMAGE_PIXELS:
                raise PortraitImageError("image_too_large", f"The portrait image is over {MAX_IMAGE_PIXELS:,} pixels")
            return np.asarray(image.convert("RGB"))
    except (UnidentifiedImageError, OSError) as exc:
        raise PortraitImageError("image_unreadable", "The portrait image could not be read") from exc


def _resize(pixels: np.ndarray, width: int, height: int) -> np.ndarray:
    from PIL import Image

    shrink = width < pixels.shape[1]
    resample = Image.Resampling.BOX if shrink else Image.Resampling.BICUBIC
    return np.asarray(Image.fromarray(pixels).resize((width, height), resample))


def face_box(image: np.ndarray, detect: Detector) -> tuple[int, int, int, int]:
    """The first confident face, in the image's own pixels.

    The detector always sees one canvas size (``DETECT_HEIGHT`` x ``DETECT_WIDTH``): the image is scaled to
    fit it, 360 px high as upstream scales it unless that would be too wide, and padded with black on the
    right and bottom. On the GPU every new input size costs seconds of one-off setup.
    """
    height, width = image.shape[:2]
    scale = min(DETECT_HEIGHT / height, DETECT_WIDTH / width)
    small = _resize(image, max(1, round(width * scale)), max(1, round(height * scale)))
    canvas = np.zeros((DETECT_HEIGHT, DETECT_WIDTH, 3), dtype=np.uint8)
    canvas[: small.shape[0], : small.shape[1]] = small
    faces = [box for box in detect(canvas) if box[4] > MIN_SCORE]
    if not faces:
        raise PortraitImageError("no_face", "No face was found in the portrait image")
    x1, y1, x2, y2 = (int(value / scale) for value in faces[0][:4])
    return x1, y1, x2, y2


def crop_square(image: np.ndarray, box: tuple[int, int, int, int]) -> np.ndarray:
    """The square crop around a face box, padded with black past the edges, at ``OUTPUT_SIZE``."""
    x1, y1, x2, y2 = box
    half = int(max((y2 - y1) / 2, (x2 - x1) / 2) * CROP_SCALE)
    if half <= 0:
        raise PortraitImageError("no_face", "The face in the portrait image is too small")
    centre_y, centre_x = (y1 + y2) // 2 + half, (x1 + x2) // 2 + half
    padded = np.pad(image, ((half, half), (half, half), (0, 0)), mode="constant")
    crop = padded[centre_y - half:centre_y + half, centre_x - half:centre_x + half]
    return _resize(np.ascontiguousarray(crop), OUTPUT_SIZE, OUTPUT_SIZE)


def portrait_pixels(payload: bytes, detect: Detector) -> np.ndarray:
    """The 512 px face crop FLOAT encodes, from an uploaded image."""
    image = decode_image(payload)
    return crop_square(image, face_box(image, detect))


__all__ = [
    "MAX_IMAGE_BYTES", "MAX_IMAGE_PIXELS", "OUTPUT_SIZE", "PortraitImageError", "crop_square", "decode_image",
    "face_box", "portrait_pixels",
]
