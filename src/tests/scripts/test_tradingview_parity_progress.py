from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts.tradingview_parity_progress import done_work_packages, expand_work_packages, replace_block

ROOT = Path(__file__).resolve().parents[3]


def test_status_cells_expand_to_work_packages() -> None:
    assert expand_work_packages("TVP-2.1 + 2.3 + 2.4") == ["2.1", "2.3", "2.4"]
    assert expand_work_packages("TVP-5.1–5.3") == ["5.1", "5.2", "5.3"]
    assert expand_work_packages("TVP-0.5a") == ["0.5a"]
    assert expand_work_packages("TVP-8.1 (wave 1 part)") == ["8.1"]


def test_only_rows_marked_done_count() -> None:
    roadmap = "\n".join([
        "## 9. Progress",
        "| WP | Status | Branch | Notes |",
        "|---|---|---|---|",
        "| TVP-1.1 + 1.2 | **Done** | x | y |",
        "| TVP-0.4 | **Merged** (first part) | x | y |",
        "| TVP-0.5a | In progress | x | y |",
        "",
        "## 10. Sources",
        "| TVP-9.9 | **Done** | outside section 9 |",
    ])
    assert done_work_packages(roadmap) == ["1.1", "1.2"]


def test_a_package_with_any_row_not_done_is_not_done() -> None:
    roadmap = "\n".join([
        "## 9. Progress",
        "| WP | Status | Branch | Notes |",
        "|---|---|---|---|",
        "| TVP-9.1 | **Partly done** | x | y |",
        "| TVP-9.1 (fundamental fields) | **Done** | x | y |",
        "| TVP-9.2 | **Done** | x | y |",
    ])
    assert done_work_packages(roadmap) == ["9.2"]


def test_blocks_are_replaced_between_their_markers() -> None:
    document = "a\n<!-- x:start -->\nold\n<!-- x:end -->\nb"
    assert replace_block(document, "x", "new") == "a\n<!-- x:start -->\nnew\n<!-- x:end -->\nb"


def test_the_roadmap_progress_is_current() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "tradingview_parity_progress.py"), "--check"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=False,
    )
    assert result.returncode == 0, result.stderr
