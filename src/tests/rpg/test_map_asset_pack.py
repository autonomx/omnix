from __future__ import annotations

from pathlib import Path

from app.assets import default_asset_store
from app.assets.rpg_map_pack import curated_rpg_map_asset_ids, curated_rpg_map_assets
from app.rpg.map_repository import default_map_repository


def test_curated_asset_pack_files_exist_and_are_trusted_immutable_svg() -> None:
    assets = curated_rpg_map_assets()

    assert assets
    assert [asset.id for asset in assets] == list(curated_rpg_map_asset_ids())
    assert all(asset.mime_type == "image/svg+xml" for asset in assets)
    assert all(asset.metadata.get("trusted_svg") is True for asset in assets)
    assert all(asset.metadata.get("immutable") is True for asset in assets)
    assert all(Path(asset.storage_path).is_file() for asset in assets)


def test_every_default_map_art_reference_resolves_through_shared_asset_store() -> None:
    referenced_ids: set[str] = set()
    for definition in default_map_repository().list():
        if definition.background:
            referenced_ids.add(definition.background.asset_id)
        referenced_ids.update(
            item.sprite.asset_id
            for item in definition.objects
            if item.sprite is not None
        )
    indexed_ids = {asset.id for asset in default_asset_store().list_assets().assets}

    assert referenced_ids
    assert referenced_ids <= indexed_ids


def test_map_asset_records_do_not_expose_storage_paths_in_definition_contracts() -> None:
    for definition in default_map_repository().list():
        assert "storage_path" not in repr(definition)
        if definition.background:
            assert definition.background.asset_id.startswith("asset:rpg-map:")
        assert all(
            item.sprite is None or item.sprite.asset_id.startswith("asset:rpg-map:")
            for item in definition.objects
        )
