from __future__ import annotations

from datetime import datetime, timezone

import pytest

Image = pytest.importorskip("PIL.Image")
ImageDraw = pytest.importorskip("PIL.ImageDraw")
ImageEnhance = pytest.importorskip("PIL.ImageEnhance")

from app.assets import AssetRecord, AssetType, SharedAssetStore
from app.characters.avatar_frame_stabilization import (
    AvatarFrameStabilizationError,
    avatar_frame_region,
    stabilize_generated_avatar_frame,
)


def _canonical_portrait():
    image = Image.new("RGB", (128, 128), (156, 166, 184))
    draw = ImageDraw.Draw(image)
    draw.ellipse((30, 12, 98, 116), fill=(224, 188, 165))
    draw.ellipse((43, 47, 53, 54), fill=(32, 34, 40))
    draw.ellipse((75, 47, 85, 54), fill=(32, 34, 40))
    draw.polygon(((64, 54), (59, 72), (68, 72)), fill=(198, 151, 134))
    draw.line((52, 78, 76, 78), fill=(118, 61, 68), width=3)
    draw.rectangle((34, 112, 94, 127), fill=(45, 52, 72))
    return image


def _shifted_dark_variant(base, *, offset_x: int = 3, offset_y: int = 2):
    darkened = ImageEnhance.Brightness(base).enhance(0.78)
    shifted = Image.new("RGB", base.size, (80, 85, 96))
    shifted.paste(darkened, (offset_x, offset_y))
    return shifted


def _store_reference(tmp_path, image) -> tuple[SharedAssetStore, str]:
    reference_path = tmp_path / "canonical.png"
    image.save(reference_path)
    store = SharedAssetStore(tmp_path / "assets" / "manifest.json")
    asset_id = "image:canonical-avatar"
    store.upsert_asset(
        AssetRecord(
            id=asset_id,
            owner_id="character:maya",
            module="character-avatar",
            type=AssetType.IMAGE,
            mime_type="image/png",
            storage_path=str(reference_path),
            created_at=datetime.now(timezone.utc).isoformat(),
        )
    )
    return store, asset_id


def test_mouth_stabilization_keeps_background_and_upper_face_pixel_identical(
    tmp_path,
) -> None:
    canonical = _canonical_portrait()
    generated = _shifted_dark_variant(canonical)
    draw = ImageDraw.Draw(generated)
    draw.ellipse((55, 75, 75, 85), fill=(120, 20, 32))
    output_path = tmp_path / "viseme-a.png"
    generated.save(output_path)
    store, reference_asset_id = _store_reference(tmp_path, canonical)

    metadata = stabilize_generated_avatar_frame(
        output_path,
        reference_asset_id=reference_asset_id,
        variant="A_soft",
        articulation_percent=15,
        store=store,
    )

    with Image.open(output_path) as stabilized_source:
        stabilized = stabilized_source.convert("RGB")
        assert stabilized.getpixel((8, 8)) == canonical.getpixel((8, 8))
        assert stabilized.getpixel((48, 50)) == canonical.getpixel((48, 50))
        assert stabilized.getpixel((64, 78)) != canonical.getpixel((64, 78))
    assert metadata["avatar_frame_stabilized"] is True
    assert metadata["avatar_stabilization_region"] == "mouth"
    assert metadata["avatar_articulation_percent"] == 15
    assert 0.4 <= metadata["avatar_articulation_blend_strength"] < 0.6
    assert abs(metadata["avatar_alignment_dx"]) <= 10
    assert abs(metadata["avatar_alignment_dy"]) <= 10


def test_blink_stabilization_changes_eyes_without_darkening_the_rest(tmp_path) -> None:
    canonical = _canonical_portrait()
    generated = _shifted_dark_variant(canonical, offset_x=-2, offset_y=1)
    draw = ImageDraw.Draw(generated)
    draw.line((40, 52, 52, 52), fill=(20, 20, 24), width=4)
    draw.line((72, 52, 84, 52), fill=(20, 20, 24), width=4)
    output_path = tmp_path / "blink.png"
    generated.save(output_path)
    store, reference_asset_id = _store_reference(tmp_path, canonical)

    metadata = stabilize_generated_avatar_frame(
        output_path,
        reference_asset_id=reference_asset_id,
        variant="blink_closed",
        store=store,
    )

    with Image.open(output_path) as stabilized_source:
        stabilized = stabilized_source.convert("RGB")
        assert stabilized.getpixel((8, 8)) == canonical.getpixel((8, 8))
        assert stabilized.getpixel((64, 78)) == canonical.getpixel((64, 78))
        assert stabilized.getpixel((48, 51)) != canonical.getpixel((48, 51))
    assert metadata["avatar_stabilization_region"] == "eyes"


def test_exaggerated_open_mouth_is_rejected_before_storage(tmp_path) -> None:
    canonical = _canonical_portrait()
    generated = canonical.copy()
    draw = ImageDraw.Draw(generated)
    draw.ellipse((48, 69, 80, 88), fill=(8, 8, 10))
    draw.rectangle((52, 70, 76, 75), fill=(242, 240, 234))
    output_path = tmp_path / "scream.png"
    generated.save(output_path)
    store, reference_asset_id = _store_reference(tmp_path, canonical)

    with pytest.raises(
        AvatarFrameStabilizationError,
        match="avatar_frame_quality_rejected",
    ):
        stabilize_generated_avatar_frame(
            output_path,
            reference_asset_id=reference_asset_id,
            variant="A_soft",
            articulation_percent=15,
            store=store,
        )


def test_only_animation_variants_are_stabilized() -> None:
    assert avatar_frame_region("mouth_wide") == "mouth"
    assert avatar_frame_region("MBP") == "mouth"
    assert avatar_frame_region("A_soft") == "mouth"
    assert avatar_frame_region("other_strong") == "mouth"
    assert avatar_frame_region("blink_closed") == "eyes"
    assert avatar_frame_region("expression_thinking") == "face"
    assert avatar_frame_region("outfit_alternate") is None
    assert avatar_frame_region("background_alternate") is None
    assert avatar_frame_region("base") is None
