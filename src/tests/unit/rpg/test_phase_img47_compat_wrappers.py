from app.rpg.visual.asset_store import (
    cleanup_unused_assets,
    get_asset_manifest,
    save_asset_bytes,
)
from app.rpg.visual.job_queue import (
    enqueue_visual_job,
    list_visual_jobs,
    normalize_visual_queue,
)
from app.rpg.visual.queue_runner import run_one_queued_job
from app.rpg.visual.runtime_status import (
    validate_flux_klein_runtime,
    validate_visual_runtime,
)


def test_asset_store_wrapper_exports_legacy_names():
    assert callable(save_asset_bytes)
    assert callable(get_asset_manifest)
    assert callable(cleanup_unused_assets)


def test_job_queue_wrapper_exports_legacy_names():
    assert callable(enqueue_visual_job)
    assert callable(list_visual_jobs)
    assert callable(normalize_visual_queue)


def test_queue_runner_wrapper_exports_legacy_name():
    assert callable(run_one_queued_job)


def test_runtime_status_wrapper_exports_legacy_names():
    assert callable(validate_flux_klein_runtime)
    assert callable(validate_visual_runtime)
