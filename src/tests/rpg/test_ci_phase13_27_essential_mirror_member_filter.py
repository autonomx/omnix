import zipfile
from pathlib import Path

from tests.rpg.autoplay.essential_mirror_member_filter import (
    filter_essential_mirror_member_names,
    install_essential_mirror_member_filter,
)


def test_phase13_27_filters_review_artifact_member_names():
    names = [
        "summary.json",
        "review-artifacts/summary.json/part_0001.json",
        "nested/review-artifacts/full-transcript.json/rows_0001.json",
        "artifact-manifest.json",
    ]
    assert filter_essential_mirror_member_names(names) == ["summary.json", "artifact-manifest.json"]


def test_phase13_27_installed_filter_applies_only_to_autoplay_results_zip(tmp_path: Path):
    install_essential_mirror_member_filter()
    target_zip = tmp_path / "autoplay-campaign-results.zip"
    other_zip = tmp_path / "other.zip"
    members = {
        "summary.json": "{}",
        "review-artifacts/summary.json/part_0001.json": "{}",
        "artifact-manifest.json": "{}",
    }
    for path in (target_zip, other_zip):
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for name, text in members.items():
                zf.writestr(name, text)

    with zipfile.ZipFile(target_zip, "r") as zf:
        assert zf.namelist() == ["summary.json", "artifact-manifest.json"]
        assert [info.filename for info in zf.infolist()] == ["summary.json", "artifact-manifest.json"]

    with zipfile.ZipFile(other_zip, "r") as zf:
        assert "review-artifacts/summary.json/part_0001.json" in zf.namelist()
