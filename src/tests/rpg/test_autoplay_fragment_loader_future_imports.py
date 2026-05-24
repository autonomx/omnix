from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Callable, List


def _load_combiner() -> Callable[[List[Path]], str]:
    module_path = Path(__file__).with_name("autoplay_llm_campaign.py")
    spec = importlib.util.spec_from_file_location("autoplay_llm_campaign_loader_under_test", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load autoplay loader module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    combiner = getattr(module, "_combine_autoplay_campaign_fragments", None)
    if not callable(combiner):
        raise RuntimeError("_combine_autoplay_campaign_fragments missing from autoplay loader module")
    return combiner


def test_autoplay_fragment_combiner_hoists_future_imports(tmp_path) -> None:
    combine_autoplay_campaign_fragments = _load_combiner()
    early = tmp_path / "000_early_runtime_guard.pyfrag"
    later = tmp_path / "100_runtime_core.pyfrag"
    early.write_text("import atexit\nX = 1\n", encoding="utf-8")
    later.write_text("from __future__ import annotations\nY: list[str] = []\n", encoding="utf-8")

    combined = combine_autoplay_campaign_fragments([early, later])

    lines = combined.splitlines()
    assert lines[0] == "from __future__ import annotations"
    assert combined.count("from __future__ import annotations") == 1
    assert combined.index("from __future__ import annotations") < combined.index("import atexit")
    compile(combined, "combined_test.py", "exec")


def test_autoplay_fragment_combiner_dedupes_multiple_future_imports(tmp_path) -> None:
    combine_autoplay_campaign_fragments = _load_combiner()
    first = tmp_path / "001_first.pyfrag"
    second = tmp_path / "002_second.pyfrag"
    first.write_text("from __future__ import annotations\nA = 1\n", encoding="utf-8")
    second.write_text("from __future__ import annotations\nB = 2\n", encoding="utf-8")

    combined = combine_autoplay_campaign_fragments([first, second])

    assert combined.count("from __future__ import annotations") == 1
    compile(combined, "combined_test.py", "exec")
