import zipfile
from pathlib import Path

from tests.rpg import interactive_intent_matrix_zip as runner


def test_phase13_49_zip_matrix_output_creates_upload_ready_archive(tmp_path: Path):
    output_root = tmp_path / "matrix-output"
    scenario_dir = output_root / "quest_no_backed_state"
    scenario_dir.mkdir(parents=True)
    (output_root / "interactive-intent-matrix-summary.json").write_text("{}", encoding="utf-8")
    (scenario_dir / "interactive-transcript.json").write_text("[]", encoding="utf-8")

    zip_path = runner.zip_matrix_output(output_root)

    assert zip_path == output_root.with_suffix(".zip").resolve()
    assert zip_path.exists()
    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())
    assert "interactive-intent-matrix-summary.json" in names
    assert "quest_no_backed_state/interactive-transcript.json" in names


def test_phase13_49_zip_matrix_output_respects_explicit_zip_path(tmp_path: Path):
    output_root = tmp_path / "matrix-output"
    output_root.mkdir()
    (output_root / "artifact.txt").write_text("ok", encoding="utf-8")
    zip_path = tmp_path / "custom" / "matrix.zip"

    created = runner.zip_matrix_output(output_root, zip_path)

    assert created == zip_path.resolve()
    assert created.exists()
