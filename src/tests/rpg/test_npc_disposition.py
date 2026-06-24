from __future__ import annotations

from app.rpg.npc_disposition import (
    DispositionDelta,
    NpcDisposition,
    apply_disposition_deltas,
    companion_eligible,
    memory_summary_from_disposition,
    price_adjustment_percent,
)


def test_neutral_disposition_has_all_axes() -> None:
    disposition = NpcDisposition.neutral("bran")

    assert disposition.value("trust") == 0
    assert disposition.value("resentment") == 0
    assert disposition.as_dict()["npc_id"] == "bran"


def test_apply_disposition_deltas_is_pure_and_reportable() -> None:
    original = NpcDisposition.neutral("bran")
    deltas = (
        DispositionDelta("bran", "trust", 12, "paid_room", "event-1"),
        DispositionDelta("bran", "loyalty", 4, "helped_tavern", "event-2"),
        DispositionDelta("elara", "trust", 99, "wrong_npc", "event-3"),
    )

    updated, report = apply_disposition_deltas(original, deltas)

    assert original.value("trust") == 0
    assert updated.value("trust") == 12
    assert updated.value("loyalty") == 4
    assert report.changed_axes() == ("trust", "loyalty")
    assert len(report.as_dict()["applied"]) == 2


def test_disposition_deltas_are_clamped() -> None:
    updated, _ = apply_disposition_deltas(
        NpcDisposition.neutral("aldric"),
        (DispositionDelta("aldric", "suspicion", 500, "caught_stealing", "event-1"),),
    )

    assert updated.value("suspicion") == 100


def test_companion_eligibility_uses_thresholds() -> None:
    disposition, _ = apply_disposition_deltas(
        NpcDisposition.neutral("bran"),
        (
            DispositionDelta("bran", "trust", 30, "helped", "event-1"),
            DispositionDelta("bran", "loyalty", 12, "stood_by", "event-2"),
        ),
    )

    assert companion_eligible(disposition) is True


def test_price_adjustment_uses_trust_resentment_and_fear() -> None:
    friendly, _ = apply_disposition_deltas(
        NpcDisposition.neutral("elara"),
        (DispositionDelta("elara", "trust", 40, "repeat_customer", "event-1"),),
    )
    hostile, _ = apply_disposition_deltas(
        NpcDisposition.neutral("elara"),
        (
            DispositionDelta("elara", "resentment", 40, "threatened", "event-1"),
            DispositionDelta("elara", "fear", 24, "intimidated", "event-2"),
        ),
    )

    assert price_adjustment_percent(friendly) < 0
    assert price_adjustment_percent(hostile) > 0


def test_memory_summary_is_compact_and_state_based() -> None:
    disposition, _ = apply_disposition_deltas(
        NpcDisposition.neutral("bran"),
        (DispositionDelta("bran", "trust", 20, "paid_debt", "event-1"),),
    )

    assert memory_summary_from_disposition(disposition) == "bran disposition toward the player: trust +20."
