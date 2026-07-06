from __future__ import annotations

import threading
from pathlib import Path
from types import SimpleNamespace

from app.image.providers import flux_klein_provider as flux_module
from app.image.providers.flux_klein_provider import FluxKleinImageProvider


class _FakeImage:
    def __init__(
        self,
        *,
        finalizing: threading.Event | None = None,
        release: threading.Event | None = None,
    ) -> None:
        self.finalizing = finalizing
        self.release = release

    def save(self, destination, *, format: str) -> None:
        assert format == "PNG"
        if self.finalizing is not None:
            self.finalizing.set()
        if self.release is not None:
            assert self.release.wait(timeout=3)
        Path(destination).write_bytes(b"fake-png")


class _FakePipeline:
    def __init__(self, finalizing: threading.Event, release: threading.Event) -> None:
        self.calls = 0
        self.second_call_started = threading.Event()
        self.finalizing = finalizing
        self.release = release

    def __call__(self, **_kwargs):
        self.calls += 1
        if self.calls == 1:
            image = _FakeImage(finalizing=self.finalizing, release=self.release)
        else:
            self.second_call_started.set()
            image = _FakeImage()
        return SimpleNamespace(images=[image])


def test_generate_keeps_single_flight_lock_through_png_finalization(monkeypatch, tmp_path) -> None:
    finalizing = threading.Event()
    release = threading.Event()
    pipeline = _FakePipeline(finalizing, release)
    provider = FluxKleinImageProvider()

    monkeypatch.setattr(provider, "_ensure_pipeline", lambda: pipeline)
    monkeypatch.setattr(flux_module, "generated_images_root", lambda: tmp_path)
    monkeypatch.setattr(flux_module, "_release_generation_memory", lambda: None)

    results = []

    def generate() -> None:
        results.append(
            provider.generate(
                {
                    "prompt": "A moonlit keep",
                    "width": 256,
                    "height": 256,
                    "num_inference_steps": 2,
                }
            )
        )

    first = threading.Thread(target=generate)
    second = threading.Thread(target=generate)
    first.start()
    assert finalizing.wait(timeout=3)

    second.start()
    assert not pipeline.second_call_started.wait(timeout=0.2)

    release.set()
    first.join(timeout=3)
    second.join(timeout=3)

    assert not first.is_alive()
    assert not second.is_alive()
    assert pipeline.second_call_started.is_set()
    assert pipeline.calls == 2
    assert len(results) == 2
    assert all(result.ok for result in results)
