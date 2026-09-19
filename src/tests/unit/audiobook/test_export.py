from __future__ import annotations

import io
import wave
from array import array

import pytest

from app.audiobook.export import (concatenate_chapters, ffmetadata,
                                  ffmpeg_command, freeze_manifest, manifest_hash)


def _wav(frames: int, rate: int = 16000) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(rate)
        writer.writeframes(array("h", [1000] * frames).tobytes())
    return output.getvalue()


def test_frozen_manifest_binds_ordered_chapters_and_metadata() -> None:
    chapter = {"id": "one", "title": "The Beginning", "duration_seconds": 1.25,
               "render_ids": ["render-1"], "assembly_key": "assembly-1"}
    manifest = freeze_manifest(
        project={"id": "project", "title": "Book", "author": "Writer",
                 "language": "en", "cast": [{"name": "Narrator"}]},
        source={"id": "source", "canonical_hash": "hash"},
        chapters=[chapter, {**chapter, "id": "two", "title": "Next; Part", "duration_seconds": 2.5}],
        format="m4b", encoder_version="ffmpeg version 7", settings={"codec": "aac"},
    )
    frozen_hash = manifest_hash(manifest)
    assert frozen_hash != manifest_hash({**manifest, "title": "Changed"})
    metadata = ffmetadata(manifest)
    assert "START=0\nEND=1250\ntitle=The Beginning" in metadata
    assert "START=1250\nEND=3750\ntitle=Next\\; Part" in metadata
    assert "narrator=Narrator" in metadata


def test_book_wav_concatenates_without_resampling() -> None:
    combined = concatenate_chapters([_wav(1600), _wav(800)])
    with wave.open(io.BytesIO(combined), "rb") as reader:
        assert reader.getnframes() == 2400
        assert reader.getframerate() == 16000
    with pytest.raises(ValueError, match="sample rates"):
        concatenate_chapters([_wav(1600), _wav(800, rate=24000)])


def test_m4b_command_maps_chapters_cover_and_codec() -> None:
    command = ffmpeg_command(
        "ffmpeg", input_wav="input.wav", metadata_path="meta.ffmeta",
        output_path="book.m4b", format="m4b", cover_path="cover.jpg",
    )
    assert command[-1] == "book.m4b"
    assert command[command.index("-map_chapters") + 1] == "1"
    assert command[command.index("-c:a") + 1] == "aac"
    assert "attached_pic" in command
