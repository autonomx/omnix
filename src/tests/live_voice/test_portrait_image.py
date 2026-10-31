"""Portrait images for the live portrait service: limits, face choice and upstream FLOAT's crop."""
from __future__ import annotations

import io

import numpy as np
import pytest
from PIL import Image

from services.portrait.portrait_image import (
    MAX_IMAGE_BYTES,
    OUTPUT_SIZE,
    PortraitImageError,
    crop_square,
    decode_image,
    face_box,
    portrait_pixels,
)


def _png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.mark.parametrize(("make", "code"), [
    (lambda: b"", "image_empty"),
    (lambda: b"x" * (MAX_IMAGE_BYTES + 1), "image_too_large"),
    (lambda: b"not an image at all", "image_unreadable"),
], ids=["empty", "too-many-bytes", "unreadable"])
def test_unusable_uploads_are_refused_before_decoding(make, code: str) -> None:
    with pytest.raises(PortraitImageError) as raised:
        decode_image(make())
    assert raised.value.code == code


def test_an_image_over_the_pixel_limit_is_refused_from_its_header() -> None:
    huge = _png(Image.new("1", (7_000, 6_000)))  # 42 MP, a few kB on disk
    with pytest.raises(PortraitImageError) as raised:
        decode_image(huge)
    assert raised.value.code == "image_too_large"


def test_an_image_past_pils_own_bomb_limit_is_refused_as_too_large_not_an_error() -> None:
    # Review finding (2026-10-31): PIL raises DecompressionBombError itself past twice its pixel limit, which
    # escaped as a 500. A PNG header claiming 20,000 x 20,000 pixels is enough: PIL checks before decoding.
    import struct
    import zlib

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    header = struct.pack(">IIBBBBB", 20_000, 20_000, 8, 2, 0, 0, 0)
    bomb = bytes([0x89]) + b"PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IEND", b"")
    with pytest.raises(PortraitImageError) as raised:
        decode_image(bomb)
    assert raised.value.code == "image_too_large"


def test_the_first_confident_face_is_used_in_the_images_own_pixels() -> None:
    image = np.zeros((720, 1280, 3), dtype=np.uint8)
    seen: list[tuple[int, ...]] = []

    def detect(small: np.ndarray):
        seen.append(small.shape)
        return [(10, 10, 20, 20, 0.5), (100, 50, 200, 170, 0.99), (300, 50, 340, 90, 0.98)]

    assert face_box(image, detect) == (200, 100, 400, 340)  # the 0.5 face is skipped; 360 px back to 720 px
    assert seen == [(360, 640, 3)]
    with pytest.raises(PortraitImageError) as raised:
        face_box(image, lambda small: [(1, 1, 5, 5, 0.9)])
    assert raised.value.code == "no_face"


def test_detection_always_sees_one_canvas_size_whatever_the_images_shape() -> None:
    seen: list[tuple[int, ...]] = []

    def detect(canvas: np.ndarray):
        seen.append(canvas.shape)
        return [(64, 32, 128, 96, 0.99)]

    # A wide panorama is scaled to fit 640 px across (0.32), not to 360 px high.
    assert face_box(np.zeros((400, 2000, 3), dtype=np.uint8), detect) == (200, 100, 400, 300)
    face_box(np.zeros((1200, 900, 3), dtype=np.uint8), detect)
    assert seen == [(360, 640, 3), (360, 640, 3)]


def test_the_crop_is_a_square_around_the_face_padded_black_past_the_edges() -> None:
    image = np.full((400, 600, 3), 200, dtype=np.uint8)
    centred = crop_square(image, (250, 150, 350, 250))
    assert centred.shape == (OUTPUT_SIZE, OUTPUT_SIZE, 3) and centred.min() == 200
    at_edge = crop_square(image, (0, 0, 100, 100))
    assert at_edge.shape == (OUTPUT_SIZE, OUTPUT_SIZE, 3)
    assert at_edge[0, 0].tolist() == [0, 0, 0] and at_edge[-1, -1].tolist() == [200, 200, 200]


def test_an_upload_becomes_a_512_px_face_crop() -> None:
    photo = _png(Image.new("RGB", (900, 1200), (120, 90, 60)))
    pixels = portrait_pixels(photo, lambda small: [(80, 100, 190, 230, 0.99)])
    assert pixels.shape == (OUTPUT_SIZE, OUTPUT_SIZE, 3) and pixels.dtype == np.uint8
