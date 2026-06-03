from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NOTE = ROOT / "docs" / "plans" / "rpg_phase8_7_completion_note.md"


def test_phase8_7_completion_note_records_merge():
    note = NOTE.read_text(encoding="utf-8")
    assert "Phase 8.7" in note
    assert "Implementation PR: #238" in note
    assert "c26ee3a6710b95f76989964058fb80ff84ed5307" in note
    assert "75704c1ce38b442cf15f20b308374aba9766a745" in note
