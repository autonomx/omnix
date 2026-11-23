"""The prospective-gap prediction versions after v4, in the order the runtime runs them.

Each version is research only: a frozen shadow spec, and for v42 on an action policy whose watch, action and
authorization records are measured in the session ledger, never sent as orders. A version names the versions it
consumes (v43 overlays v42's forecast and reads v42's action), and the registry keeps a consumer after what it
consumes. ``spec_records`` is what a premarket freeze writes for the versions before it reads a single bar: each
spec, then its action policy, under the record kinds and idempotency suffixes the ledger has always used.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, NamedTuple

from pydantic import BaseModel

from .canonical import canonical_sha256
from .prospective_gap_repository import ProspectiveRecordKind
from .prospective_prediction_v41 import DEFAULT_V41_SPEC
from .prospective_prediction_v42 import DEFAULT_V42_SPEC
from .prospective_prediction_v42_action import DEFAULT_V42_ACTION_POLICY
from .prospective_prediction_v43 import DEFAULT_V43_SPEC
from .prospective_prediction_v43_action import DEFAULT_V43_ACTION_POLICY

ACTION_SPEC_STATE = "FORWARD_SHADOW_ACTIVE"


@dataclass(frozen=True)
class PredictionVersion:
    name: str
    spec: Any  # a frozen spec model with ``activation_state`` and ``implementation_fingerprint``
    spec_instrument_id: str
    spec_kind: ProspectiveRecordKind
    action_policy: BaseModel | None = None
    action_kind: ProspectiveRecordKind | None = None
    consumes: tuple[str, ...] = ()

    @property
    def action_instrument_id(self) -> str:
        return f"__action_spec_{self.name}__"


class SpecRecord(NamedTuple):
    instrument_id: str
    kind: ProspectiveRecordKind
    payload: BaseModel
    state: str
    idempotency_suffix: str


V41 = PredictionVersion("v41", DEFAULT_V41_SPEC, "__research_spec__", "v41_shadow_spec")
V42 = PredictionVersion(
    "v42", DEFAULT_V42_SPEC, "__research_spec_v42__", "v42_shadow_spec",
    action_policy=DEFAULT_V42_ACTION_POLICY, action_kind="v42_action_spec",
)
V43 = PredictionVersion(
    "v43", DEFAULT_V43_SPEC, "__research_spec_v43__", "v43_shadow_spec",
    action_policy=DEFAULT_V43_ACTION_POLICY, action_kind="v43_action_spec", consumes=("v42",),
)
PREDICTION_VERSIONS: tuple[PredictionVersion, ...] = (V41, V42, V43)


def _check_order(versions: tuple[PredictionVersion, ...]) -> None:
    seen: set[str] = set()
    for version in versions:
        missing = [name for name in version.consumes if name not in seen]
        if missing:
            raise ValueError(f"{version.name} consumes {missing} before they run")
        seen.add(version.name)


_check_order(PREDICTION_VERSIONS)


def spec_records(versions: tuple[PredictionVersion, ...] = PREDICTION_VERSIONS) -> tuple[SpecRecord, ...]:
    rows: list[SpecRecord] = []
    for version in versions:
        rows.append(SpecRecord(
            version.spec_instrument_id, version.spec_kind, version.spec, version.spec.activation_state,
            version.spec.implementation_fingerprint,
        ))
        if version.action_policy is not None and version.action_kind is not None:
            rows.append(SpecRecord(
                version.action_instrument_id, version.action_kind, version.action_policy, ACTION_SPEC_STATE,
                canonical_sha256(version.action_policy.model_dump(mode="json")),
            ))
    return tuple(rows)


__all__ = ["ACTION_SPEC_STATE", "PREDICTION_VERSIONS", "PredictionVersion", "SpecRecord", "V41", "V42", "V43",
           "spec_records"]
