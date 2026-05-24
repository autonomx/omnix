from __future__ import annotations

from pathlib import Path

from rpg.autoplay_llm_campaign import _combine_autoplay_campaign_fragments


def test_autoplay_fragment_combiner_hoists_future_imports(tmp_path) -> None:
    early = tmp_path / "000_early_runtime_guard.pyfrag"
    later = tmp_path / "100_runtime_core.pyfrag"
    early.write_text("import atexit\nX = 1\n", encoding="utf-8")
    later.write_text("from __future__ import annotations\nY: list[str] = []\n", encoding="utf-8")

    combined = _combine_autoplay_campaign_fragments([early, later])

    lines = combined.splitlines()
    assert lines[0] == "from __future__ import annotations"
    assert combined.count("from __future__ import annotations") == 1
    assert combined.index("from __future__ import annotations") < combined.index("import atexit")
    compile(combined, "combined_test.py", "exec")


def test_autoplay_fragment_combiner_dedupes_multiple_future_imports(tmp_path) -> None:
    first = tmp_path / "001_first.pyfrag"
    second = tmp_path / "002_second.pyfrag"
    first.write_text("from __future__ import annotations\nA = 1\n", encoding="utf-8")
    second.write_text("from __future__ import annotations\nB = 2\n", encoding="utf-8")

    combined = _combine_autoplay_campaign_fragments([first, second])

    assert combined.count("from __future__ import annotations") == 1
    compile(combined, "combined_test.py", "exec")
