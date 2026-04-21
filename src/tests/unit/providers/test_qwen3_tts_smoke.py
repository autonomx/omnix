from __future__ import annotations

import traceback
import pytest


@pytest.mark.smoke
def test_qwen3_import_chain():
    """
    FAIL FAST if any vendored Qwen3 import chain is broken.

    This catches:
    - missing transformers symbols (e.g. MimiConfig)
    - missing deps (sox, onnxruntime, etc)
    - bad vendor packaging
    """

    try:
        from app.providers.vendor.qwen_tts import Qwen3TTSModel  # noqa
    except Exception as e:
        pytest.fail(
            "Qwen3 import chain failed:\n"
            f"{type(e).__name__}: {e}\n\n"
            f"{traceback.format_exc(limit=10)}"
        )


@pytest.mark.smoke
def test_faster_qwen3_provider_init():
    """
    Ensures provider can be constructed with config.

    This catches:
    - constructor mismatches
    - config schema issues
    """

    from app.providers.faster_qwen3_tts_provider import FasterQwen3TTSProvider

    provider = FasterQwen3TTSProvider(config={})
    assert provider is not None


@pytest.mark.smoke
def test_qwen3_model_load_cpu_path():
    """
    Critical smoke test:
    - calls _get_model()
    - forces full vendored model load path
    - MUST fail here instead of inside the app

    This is the test that replaces "click Speak and hope".
    """

    from app.providers.faster_qwen3_tts_provider import FasterQwen3TTSProvider

    provider = FasterQwen3TTSProvider(
        config={
            "device": "cpu",   # force CPU-safe path
        }
    )

    try:
        model = provider._get_model()
    except Exception as e:
        pytest.fail(
            "Qwen3 model load failed:\n"
            f"{type(e).__name__}: {e}\n\n"
            f"{traceback.format_exc(limit=10)}"
        )

    assert model is not None


@pytest.mark.smoke
def test_qwen3_generate_minimal_call(monkeypatch):
    """
    Optional but VERY useful:
    verifies generation path wiring without heavy compute.

    We monkeypatch the model to avoid real inference cost.
    """

    from app.providers.faster_qwen3_tts_provider import FasterQwen3TTSProvider

    provider = FasterQwen3TTSProvider(config={"device": "cpu"})

    # Replace heavy model with stub AFTER load succeeds
    model = provider._get_model()

    class DummyModel:
        def generate(self, *args, **kwargs):
            return b"\x00\x00"  # fake audio bytes

    provider._model_loader.model = DummyModel()

    try:
        out = provider.generate_audio(
            text="hello",
            speaker="test",
            language="en"
        )
    except Exception as e:
        pytest.fail(
            "Qwen3 generate_audio path failed:\n"
            f"{type(e).__name__}: {e}\n\n"
            f"{traceback.format_exc(limit=10)}"
        )

    assert out is not None