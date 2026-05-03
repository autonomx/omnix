from pathlib import Path

from tests.rpg.manual.constants import TEST_RESULTS_ROOT
from tests.rpg.manual.output_artifacts import (
    _should_include_in_results_zip,
    clear_test_results_root,
)
from tests.rpg.manual.output_state import _OUTPUTS


def test_clear_test_results_root_removes_stale_files():
    TEST_RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    stale = TEST_RESULTS_ROOT / "stale-old-run.txt"
    stale.write_text("old", encoding="utf-8")

    stale_dir = TEST_RESULTS_ROOT / "old-html"
    stale_dir.mkdir(parents=True, exist_ok=True)
    (stale_dir / "index.html").write_text("<html></html>", encoding="utf-8")

    clear_test_results_root()

    assert TEST_RESULTS_ROOT.exists()
    assert not stale.exists()
    assert not stale_dir.exists()


def test_clear_test_results_root_preserves_gitkeep():
    TEST_RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    gitkeep = TEST_RESULTS_ROOT / ".gitkeep"
    gitkeep.write_text("", encoding="utf-8")

    clear_test_results_root()

    assert gitkeep.exists()


def test_clear_test_results_root_clears_output_buffers():
    from tests.rpg.manual import output_artifacts

    output_artifacts._emit("hello", channel="service_summary")
    assert _OUTPUTS

    clear_test_results_root()

    assert not _OUTPUTS


def test_results_zip_excludes_zip_files():
    zip_path = TEST_RESULTS_ROOT / "old.zip"
    zip_path.write_text("fake", encoding="utf-8")
    assert not _should_include_in_results_zip(zip_path)