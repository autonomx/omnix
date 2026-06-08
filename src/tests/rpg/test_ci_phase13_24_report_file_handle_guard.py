import json
from pathlib import Path

from app.rpg.autoplay_report_materialization_guard import (
    REPORT_JSON_NAME,
    _GuardedReportFile,
)


def test_phase13_24_report_file_handle_caps_large_text_write(tmp_path: Path):
    path = tmp_path / REPORT_JSON_NAME
    with path.open("w", encoding="utf-8") as raw:
        guarded = _GuardedReportFile(raw, path, binary=False, encoding="utf-8")
        guarded.write('{"rows": [')
        guarded.write('"x"' * (26 * 1024 * 1024))
        guarded.write(']}')
        guarded.close()

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["capped"] is True
    assert payload["artifact_name"].endswith(REPORT_JSON_NAME)
    assert path.stat().st_size < 4096


def test_phase13_24_report_file_handle_allows_small_text_write(tmp_path: Path):
    path = tmp_path / REPORT_JSON_NAME
    with path.open("w", encoding="utf-8") as raw:
        guarded = _GuardedReportFile(raw, path, binary=False, encoding="utf-8")
        guarded.write('{"ok": true}')
        guarded.close()

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload == {"ok": True}
