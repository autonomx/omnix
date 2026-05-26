from __future__ import annotations

import json
from pathlib import Path


_FRAGMENT = (
    Path(__file__).resolve().parent
    / "autoplay_llm_campaign_parts"
    / "zzzzzzzzzzzzzzzz_bundle_ao_nonfatal_endurance_finalization.pyfrag"
)


def _load_bundle_ao_namespace(extra_globals=None):
    namespace = {"__name__": "_bundle_ao_nonfatal_endurance_finalization_test"}
    if extra_globals:
        namespace.update(extra_globals)
    exec(compile(_FRAGMENT.read_text(encoding="utf-8"), str(_FRAGMENT), "exec"), namespace, namespace)
    return namespace


def test_bundle_ao_parses_background_verifier_counts():
    namespace = _load_bundle_ao_namespace()

    warning = namespace["_bundle_ao_background_verifier_warning"](
        "background_presentation_not_turn_bound_verified:expected_count=250:event_count=200:turn_bound_verified_count=200:legacy_observed_count=0:rejected_count=0:orphaned_count=0"
    )

    assert warning["code"] == "background_presentation_not_turn_bound_verified"
    assert warning["expected_count"] == 250
    assert warning["turn_bound_verified_count"] == 200
    assert warning["missing_turn_bound_verification_count"] == 50
    assert warning["counts"]["event_count"] == 200
    assert warning["advisory_only"] is True


def test_bundle_ao_downgrades_background_verifier_runtime_error_to_warning():
    def failing_verifier(_summary):
        raise RuntimeError(
            "background_presentation_not_turn_bound_verified:expected_count=250:event_count=200:turn_bound_verified_count=200:legacy_observed_count=0:rejected_count=0:orphaned_count=0"
        )

    namespace = _load_bundle_ao_namespace({"_assert_turn_bound_attachment_verified": failing_verifier})
    summary = {"turns_executed": 250}

    result = namespace["_assert_turn_bound_attachment_verified"](summary)

    assert result is None
    assert summary["nonfatal_endurance_warning_count"] == 1
    assert summary["background_presentation_turn_bound_verification_advisory_only"] is True
    warning = summary["nonfatal_endurance_warnings"][0]
    assert warning["missing_turn_bound_verification_count"] == 50


def test_bundle_ao_does_not_swallow_unrelated_runtime_errors():
    def failing_verifier(_summary):
        raise RuntimeError("real_runtime_failure:combat_state_corrupt")

    namespace = _load_bundle_ao_namespace({"_assert_turn_bound_attachment_verified": failing_verifier})

    try:
        namespace["_assert_turn_bound_attachment_verified"]({})
    except RuntimeError as exc:
        assert "combat_state_corrupt" in str(exc)
    else:
        raise AssertionError("unrelated runtime error should still raise")


def test_bundle_ao_deduplicates_repeated_warning_attachment():
    namespace = _load_bundle_ao_namespace()
    summary = {}
    warning = namespace["_bundle_ao_background_verifier_warning"](
        "background_presentation_not_turn_bound_verified:expected_count=250:event_count=200:turn_bound_verified_count=200"
    )

    namespace["_bundle_ao_attach_nonfatal_warning"](summary, warning)
    namespace["_bundle_ao_attach_nonfatal_warning"](summary, warning)

    assert summary["nonfatal_endurance_warning_count"] == 1
    assert len(summary["nonfatal_endurance_warnings"]) == 1


def test_bundle_ao_writes_warning_sidecars_to_parent_and_unzipped(tmp_path):
    parent = tmp_path / "autoplay-output"
    unzipped = parent / "autoplay-campaign-results-unzipped"
    unzipped.mkdir(parents=True)
    namespace = _load_bundle_ao_namespace({"RESULT_DIR_FOR_TEST": str(parent)})
    summary = {"result_dir": str(parent)}
    warning = namespace["_bundle_ao_background_verifier_warning"](
        "background_presentation_not_turn_bound_verified:expected_count=250:event_count=200:turn_bound_verified_count=200"
    )

    namespace["_bundle_ao_attach_nonfatal_warning"](summary, warning)

    for directory in (parent, unzipped):
        path = directory / "nonfatal-endurance-warnings-summary.json"
        assert path.exists()
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["warning_count"] == 1
        assert payload["warnings"][0]["missing_turn_bound_verification_count"] == 50


def test_bundle_ao_manifest_finalizer_refreshes_sidecar_after_finalize(tmp_path):
    parent = tmp_path / "autoplay-output"
    unzipped = parent / "autoplay-campaign-results-unzipped"
    unzipped.mkdir(parents=True)

    def hard_finalizer():
        return {"ok": True}

    namespace = _load_bundle_ao_namespace({"_manifest_hard_finalize_latest": hard_finalizer, "RESULT_DIR_FOR_TEST": str(parent)})
    namespace["BUNDLE_AO_LAST_NONFATAL_ENDURANCE_WARNING"] = namespace["_bundle_ao_background_verifier_warning"](
        "background_presentation_not_turn_bound_verified:expected_count=250:event_count=200:turn_bound_verified_count=200"
    )

    result = namespace["_manifest_hard_finalize_latest"]()

    assert result["ok"] is True
    assert (unzipped / "nonfatal-endurance-warnings-summary.json").exists()
