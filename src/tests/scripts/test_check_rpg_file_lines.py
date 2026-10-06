from __future__ import annotations

from scripts.check_rpg_file_lines import DEFAULT_LIMIT, find_oversized_files


def test_rpg_file_budget_uses_global_1200_line_limit(tmp_path) -> None:
    assert DEFAULT_LIMIT == 1200

    accepted = tmp_path / "src" / "app" / "apps" / "rpg" / "within_budget.py"
    accepted.parent.mkdir(parents=True)
    accepted.write_text("\n".join("pass" for _ in range(DEFAULT_LIMIT)), encoding="utf-8")

    rejected = tmp_path / "src" / "app" / "apps" / "rpg" / "over_budget.py"
    rejected.write_text("\n".join("pass" for _ in range(DEFAULT_LIMIT + 1)), encoding="utf-8")

    findings = find_oversized_files(
        [accepted.parent],
        root=tmp_path,
        extensions=(".py",),
    )

    assert [(finding.path, finding.lines, finding.limit) for finding in findings] == [
        ("src/app/apps/rpg/over_budget.py", DEFAULT_LIMIT + 1, DEFAULT_LIMIT)
    ]
