from __future__ import annotations

from app.jobs.image_inline import IMAGE_GENERATION_CONCURRENCY, _IMAGE_GENERATION_SLOTS


def test_image_generation_has_two_provider_slots() -> None:
    acquired = 0
    try:
        for _ in range(IMAGE_GENERATION_CONCURRENCY):
            assert _IMAGE_GENERATION_SLOTS.acquire(blocking=False)
            acquired += 1

        assert IMAGE_GENERATION_CONCURRENCY == 2
        assert not _IMAGE_GENERATION_SLOTS.acquire(blocking=False)
    finally:
        for _ in range(acquired):
            _IMAGE_GENERATION_SLOTS.release()
