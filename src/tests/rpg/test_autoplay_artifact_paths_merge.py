from tests.rpg.autoplay_llm_campaign import _merge_artifact_paths


def test_merge_artifact_paths_handles_missing_or_empty_maps():
    paths = _merge_artifact_paths(
        None,
        {},
        {"summary": "resources/data/test-results/summary.json"},
    )

    assert paths == {
        "summary": "resources/data/test-results/summary.json",
    }


def test_merge_artifact_paths_stringifies_keys_and_values():
    paths = _merge_artifact_paths(
        {"zip": "results.zip"},
        {123: 456},
    )

    assert paths["zip"] == "results.zip"
    assert paths["123"] == "456"
