from __future__ import annotations

from scripts.character_mode_stage6_preflight import run_preflight


def test_character_stage6_preflight_passes_content_free_contract() -> None:
    report = run_preflight()

    assert report["decision"] == "pass"
    assert all(check["status"] == "pass" for check in report["checks"])
    assert [check["id"] for check in report["checks"]] == [
        "sync.disabled",
        "storage.missing_nonfatal",
        "import.review_first_idempotent",
        "owner.binding",
        "export.filtered_idempotent",
        "rollback.non_destructive",
    ]
