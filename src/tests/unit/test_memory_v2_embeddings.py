"""The Memory v2 embedding model: pinned download, verification, and opt-out."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.assistant_memory_v2 import embeddings


def test_without_the_model_there_is_no_embedder(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OMNIX_MEMORY_EMBEDDING_MODEL_DIR", str(tmp_path / "absent"))

    assert embeddings.model_installed() is False
    assert embeddings.default_embedder() is None


def test_embeddings_can_be_turned_off(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OMNIX_MEMORY_EMBEDDINGS", "0")

    assert embeddings.embeddings_enabled() is False
    assert embeddings.default_embedder() is None


def test_a_download_with_the_wrong_checksum_is_refused(monkeypatch, tmp_path: Path) -> None:
    fetched = tmp_path / "hub" / "model.onnx"
    fetched.parent.mkdir()
    fetched.write_bytes(b"not the model")

    def fake_download(repo, filename, revision):
        assert repo == embeddings.MODEL_REPO and revision == embeddings.MODEL_REVISION
        return str(fetched)

    monkeypatch.setattr("huggingface_hub.hf_hub_download", fake_download)

    with pytest.raises(RuntimeError, match="memory_embedding_checksum_mismatch"):
        embeddings.download_model(tmp_path / "model")
    assert not (tmp_path / "model" / "model.onnx").exists()


@pytest.mark.skipif(
    not embeddings.model_installed(Path(os.environ.get("OMNIX_MEMORY_EMBEDDING_MODEL_DIR", "/nonexistent"))),
    reason="the e5 model is not installed (python -m app.assistant_memory_v2.embeddings download)",
)
def test_the_real_model_puts_a_paraphrase_next_to_its_memory() -> None:
    embedder = embeddings.default_embedder()
    assert embedder is not None
    memories = embedder.embed(["My car is a 2019 Subaru Outback", "My dog is a border collie named Juno"], kind="passage")
    question = embedder.embed(["What vehicle do I own?"], kind="query")[0]

    similarities = memories @ question
    assert memories.shape == (2, embeddings.DIMENSIONS)
    assert similarities[0] > similarities[1]
