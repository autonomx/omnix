from __future__ import annotations

import json
from pathlib import Path


_FRAGMENT = (
    Path(__file__).resolve().parent
    / "autoplay_llm_campaign_parts"
    / "zzzzzzzzzzz_bundle_ak_slim_unzipped_mirror_and_progression_sidecars.pyfrag"
)


def _load_bundle_ak_namespace(extra_globals=None):
    namespace = {"__name__": "_bundle_ak_progression_sidecar_inclusion_test"}
    if extra_globals:
        namespace.update(extra_globals)
    exec(compile(_FRAGMENT.read_text(encoding="utf-8"), str(_FRAGMENT), "exec"), namespace, namespace)
    return namespace


def _write_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def test_bundle_ak_copies_progression_and_readiness_sidecars_into_unzipped(tmp_path):
    namespace = _load_bundle_ak_namespace()
    parent = tmp_path / "autoplay-output"
    mirror = parent / "autoplay-campaign-results-unzipped"
    mirror.mkdir(parents=True)
    _write_json(parent / "one-thousand-turn-progression-graph.json", {"format_version": "graph", "ok": True})
    _write_json(parent / "one-thousand-turn-progression-graph-summary.json", {"format_version": "graph_summary", "ok": True})
    _write_json(parent / "one-thousand-turn-readiness-truth-summary.json", {"format_version": "truth", "ok": False})

    summary = namespace["_bundle_ak_finalize_unzipped_mirror"](parent)

    assert summary["ok"] is True
    assert summary["progression_graph_present"] is True
    assert summary["progression_graph_summary_present"] is True
    assert (mirror / "one-thousand-turn-progression-graph.json").exists()
    assert (mirror / "one-thousand-turn-progression-graph-summary.json").exists()
    assert (mirror / "one-thousand-turn-readiness-truth-summary.json").exists()
    assert "one-thousand-turn-progression-graph.json" in summary["present_one_thousand_turn_sidecars"]
    assert "one-thousand-turn-readiness-truth-summary.json" in summary["present_one_thousand_turn_sidecars"]


def test_bundle_ak_write_text_wrapper_triggers_sidecar_inclusion(tmp_path):
    _load_bundle_ak_namespace()
    parent = tmp_path / "autoplay-output"
    mirror = parent / "autoplay-campaign-results-unzipped"
    mirror.mkdir(parents=True)
    parent.mkdir(parents=True, exist_ok=True)

    (parent / "one-thousand-turn-progression-graph.json").write_text(
        json.dumps({"ok": True}),
        encoding="utf-8",
    )

    assert (mirror / "one-thousand-turn-progression-graph.json").exists()
    assert (mirror / "one-thousand-turn-slim-unzipped-mirror-summary.json").exists()


def test_bundle_ak_summary_is_written_to_parent_and_unzipped(tmp_path):
    namespace = _load_bundle_ak_namespace()
    parent = tmp_path / "autoplay-output"
    mirror = parent / "autoplay-campaign-results-unzipped"
    mirror.mkdir(parents=True)
    _write_json(parent / "one-thousand-turn-readiness-aggregator-summary.json", {"ok": False})

    summary = namespace["_bundle_ak_finalize_unzipped_mirror"](mirror)

    assert summary["present_one_thousand_turn_sidecar_count"] >= 1
    assert (parent / "one-thousand-turn-slim-unzipped-mirror-summary.json").exists()
    assert (mirror / "one-thousand-turn-slim-unzipped-mirror-summary.json").exists()
    assert (mirror / "one-thousand-turn-readiness-aggregator-summary.json").exists()
