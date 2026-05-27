from __future__ import annotations

import json
from pathlib import Path


_FRAGMENT = (
    Path(__file__).resolve().parent
    / "autoplay_llm_campaign_parts"
    / "zzzzzzzzzzzzzzzzzzzzzzz_bundle_ao7_hard_manifest_atexit_order.pyfrag"
)


def _load_bundle_ao7_namespace(extra_globals=None):
    namespace = {"__name__": "_bundle_ao7_hard_manifest_atexit_order_test"}
    if extra_globals:
        namespace.update(extra_globals)
    exec(compile(_FRAGMENT.read_text(encoding="utf-8"), str(_FRAGMENT), "exec"), namespace, namespace)
    return namespace


def _write_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _seed_recovered_manifest(directory: Path, ok: bool = True):
    _write_json(directory / "nonfatal-finalization-recovery-summary.json", {"ok": True, "nonfatal_finalization_recovered": True})
    _write_json(
        directory / "artifact-manifest.json",
        {
            "ok": ok,
            "advisory_only": True,
            "nonfatal_finalization_recovered_manifest_tolerance": True,
            "checks": {
                "artifact_export_invariant_tolerated": True,
                "bundle_ao2_recovery_evidence_present": True,
                "top_level_recovered_manifest_consistency_ok": True,
            },
        },
    )
    _write_json(
        directory / "essential-mirror-consistency-summary.json",
        {
            "ok": True,
            "artifact_manifest_valid": True,
            "missing_core_files": [],
            "core_presence": {"artifact-manifest.json": True},
            "raw_file_presence": {"artifact-manifest.json": True},
        },
    )


def test_bundle_ao7_runs_hard_atexit_then_ao6_final_pass(tmp_path):
    parent = tmp_path / "autoplay-output"
    unzipped = parent / "autoplay-campaign-results-unzipped"
    for directory in (parent, unzipped):
        _seed_recovered_manifest(directory, ok=True)

    def hard_atexit():
        # Simulate the legacy hard manifest atexit clobbering unzipped ok:false.
        manifest = json.loads((unzipped / "artifact-manifest.json").read_text(encoding="utf-8"))
        manifest["ok"] = False
        manifest["source"] = "bundle_d_hard_artifact_manifest_finalizer"
        _write_json(unzipped / "artifact-manifest.json", manifest)
        return {"ok": False, "legacy_write": True}

    def ao6_finalizer(output_dir: str):
        for directory in (parent, unzipped):
            manifest = json.loads((directory / "artifact-manifest.json").read_text(encoding="utf-8"))
            manifest["ok"] = True
            manifest["bundle_ao6_atexit_final_pass_applied"] = True
            _write_json(directory / "artifact-manifest.json", manifest)
        return {"ok": True, "result_count": 2, "output_dir": output_dir}

    namespace = _load_bundle_ao7_namespace(
        {
            "_manifest_hard_atexit_run": hard_atexit,
            "_bundle_ao6_finalize_output_dir": ao6_finalizer,
            "BUNDLE_AO6_LAST_OUTPUT_DIR": str(parent),
        }
    )

    namespace["_manifest_hard_atexit_run"]()

    manifest = json.loads((unzipped / "artifact-manifest.json").read_text(encoding="utf-8"))
    sidecar = json.loads((unzipped / "hard-manifest-atexit-order-recovery-summary.json").read_text(encoding="utf-8"))
    assert manifest["ok"] is True
    assert manifest["bundle_ao6_atexit_final_pass_applied"] is True
    assert sidecar["ok"] is True
    assert sidecar["hard_manifest_atexit_wrapped"] is True


def test_bundle_ao7_writes_summary_to_parent_and_unzipped(tmp_path):
    parent = tmp_path / "autoplay-output"
    unzipped = parent / "autoplay-campaign-results-unzipped"
    for directory in (parent, unzipped):
        directory.mkdir(parents=True, exist_ok=True)

    namespace = _load_bundle_ao7_namespace({"BUNDLE_AO6_LAST_OUTPUT_DIR": str(parent)})
    summary = namespace["_bundle_ao7_write_summary"](
        str(parent),
        {"ok": False},
        {"ok": True, "result_count": 2},
    )

    assert summary["ok"] is True
    for directory in (parent, unzipped):
        path = directory / "hard-manifest-atexit-order-recovery-summary.json"
        assert path.exists()
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["ao6_final_pass_result"]["ok"] is True


def test_bundle_ao7_uses_recorded_output_dir_priority():
    namespace = _load_bundle_ao7_namespace(
        {
            "BUNDLE_AO6_LAST_OUTPUT_DIR": "primary-output",
            "BUNDLE_AO5_LAST_OUTPUT_DIR": "secondary-output",
            "BUNDLE_AO2_LAST_OUTPUT_DIR": "tertiary-output",
        }
    )

    assert namespace["_bundle_ao7_output_dir"]() == "primary-output"


def test_bundle_ao7_handles_hard_atexit_error_and_still_runs_ao6(tmp_path):
    parent = tmp_path / "autoplay-output"
    unzipped = parent / "autoplay-campaign-results-unzipped"
    unzipped.mkdir(parents=True)

    def hard_atexit():
        raise NameError("__file__ is not defined")

    def ao6_finalizer(output_dir: str):
        return {"ok": True, "output_dir": output_dir}

    namespace = _load_bundle_ao7_namespace(
        {
            "_manifest_hard_atexit_run": hard_atexit,
            "_bundle_ao6_finalize_output_dir": ao6_finalizer,
            "BUNDLE_AO6_LAST_OUTPUT_DIR": str(parent),
        }
    )

    namespace["_manifest_hard_atexit_run"]()

    result = namespace["BUNDLE_AO7_LAST_ATEXIT_ORDER_RECOVERY_RESULT"]
    assert result["ok"] is True
    assert "hard_manifest_atexit_error_before_ao7" in result["ao6_final_pass_result"]


def test_bundle_ao7_noops_without_output_dir():
    namespace = _load_bundle_ao7_namespace()

    result = namespace["_bundle_ao7_run_ao6_final_pass"]("")

    assert result["ok"] is False
    assert "output_dir" in result["error"]
