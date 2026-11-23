from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json

import pytest

from app.apps.trading.canonical import canonical_sha256, optional_decimal, require_utc


def test_the_digest_is_the_recorded_form() -> None:
    # Stored digests were made with exactly this expression; a change here re-keys every record.
    payload = {"b": [1, 2.5, None], "a": "é", "when": datetime(2026, 1, 2, tzinfo=timezone.utc), "price": Decimal("1.10")}
    recorded = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
    assert canonical_sha256(payload) == recorded
    assert canonical_sha256({"x": 1}) == "5041bf1f713df204784353e82f6a4a535931cb64f1f4b4a5aeaffcb720918b22"


def test_a_naive_timestamp_is_refused_with_the_callers_message() -> None:
    eastern = timezone(timedelta(hours=-5))
    assert require_utc(datetime(2026, 1, 2, 4, tzinfo=eastern)) == datetime(2026, 1, 2, 9, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="^timestamp_must_be_timezone_aware$"):
        require_utc(datetime(2026, 1, 2))
    with pytest.raises(ValueError, match="^control_replay_timestamp_requires_timezone$"):
        require_utc(datetime(2026, 1, 2), error="control_replay_timestamp_requires_timezone")


@pytest.mark.parametrize(("value", "expected"), [("1.25", Decimal("1.25")), (3, Decimal("3")), (None, None), ("", None), ("n/a", None)])
def test_an_unreadable_decimal_reads_as_no_value(value: object, expected: Decimal | None) -> None:
    assert optional_decimal(value) == expected
