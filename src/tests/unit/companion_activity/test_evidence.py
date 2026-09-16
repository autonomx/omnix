from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.companion_activity.contracts import (
    EvidenceLink,
    EvidenceProposition,
    derive_proposition,
    inherit_evidence_policy,
)

NOW = datetime(2026, 9, 14, 22, 30, tzinfo=timezone.utc)


def proposition(
    proposition_id: str,
    *,
    trust_level: str,
    sensitivity: str = "normal",
    source_kind: str = "external",
    links: tuple[EvidenceLink, ...] = (),
) -> EvidenceProposition:
    return EvidenceProposition(
        proposition_id=proposition_id,
        subject="activity:1",
        predicate="current_objective",
        value="beat Malenia",
        source_kind=source_kind,
        trust_level=trust_level,
        confidence=0.94,
        sensitivity=sensitivity,
        links=links,
        observed_at=NOW,
    )


def test_repetition_never_upgrades_external_untrusted_provenance() -> None:
    first = proposition("p1", trust_level="external_untrusted", sensitivity="sensitive")
    second = proposition("p2", trust_level="external_untrusted", sensitivity="sensitive")
    derived = derive_proposition(
        proposition_id="p3",
        subject="activity:1",
        predicate="current_objective",
        value="beat Malenia",
        confidence=0.99,
        source_kind="assistant",
        observed_at=NOW,
        links=(
            EvidenceLink(ref="p1", relation="derived_from"),
            EvidenceLink(ref="p2", relation="derived_from"),
        ),
        propositions_by_id={"p1": first, "p2": second},
    )

    assert derived.confidence == 0.99
    assert derived.trust_level == "external_untrusted"
    assert derived.sensitivity == "sensitive"


def test_derived_policy_uses_weakest_trust_and_strongest_sensitivity() -> None:
    external = proposition("external", trust_level="external_untrusted")
    user = proposition(
        "user",
        trust_level="user_explicit",
        sensitivity="secret",
        source_kind="user",
    )
    derived = derive_proposition(
        proposition_id="derived",
        subject="activity:1",
        predicate="current_objective",
        value="beat Malenia",
        confidence=1.0,
        source_kind="assistant",
        observed_at=NOW,
        links=(
            EvidenceLink(ref="external", relation="supports"),
            EvidenceLink(ref="user", relation="supports"),
        ),
        propositions_by_id={"external": external, "user": user},
    )

    assert derived.trust_level == "external_untrusted"
    assert derived.sensitivity == "secret"


def test_corroboration_does_not_contaminate_independent_user_proposition() -> None:
    external = proposition(
        "screen",
        trust_level="external_untrusted",
        sensitivity="sensitive",
    )
    confirmed = proposition(
        "confirmed",
        trust_level="user_explicit",
        source_kind="user",
        links=(EvidenceLink(ref="screen", relation="corroborates"),),
    )

    policy = inherit_evidence_policy(
        confirmed,
        {"screen": external},
        semantic_derivation=False,
    )

    assert policy.trust_level == "user_explicit"
    assert policy.sensitivity == "normal"
    assert policy.trust_bearing_refs == ()


def test_support_edge_inherits_restrictive_policy() -> None:
    sensitive_screen = proposition(
        "screen",
        trust_level="external_untrusted",
        sensitivity="sensitive",
    )
    semantic = proposition(
        "semantic",
        trust_level="assistant_inference",
        source_kind="assistant",
        links=(EvidenceLink(ref="screen", relation="supports"),),
    )

    policy = inherit_evidence_policy(
        semantic,
        {"screen": sensitive_screen},
    )

    assert policy.trust_level == "external_untrusted"
    assert policy.sensitivity == "sensitive"
    assert policy.trust_bearing_refs == ("screen",)


def test_derived_semantics_are_capped_at_assistant_inference() -> None:
    explicit = proposition(
        "user",
        trust_level="user_explicit",
        source_kind="user",
    )
    derived = derive_proposition(
        proposition_id="semantic",
        subject="activity:1",
        predicate="strategy",
        value="bleed build",
        confidence=0.9,
        source_kind="assistant",
        observed_at=NOW,
        links=(EvidenceLink(ref="user", relation="derived_from"),),
        propositions_by_id={"user": explicit},
    )

    assert derived.trust_level == "assistant_inference"


def test_missing_trust_bearing_evidence_fails_closed() -> None:
    semantic = proposition(
        "semantic",
        trust_level="assistant_inference",
        source_kind="assistant",
        links=(EvidenceLink(ref="missing", relation="supports"),),
    )
    with pytest.raises(ValueError, match="missing"):
        inherit_evidence_policy(semantic, {})
    with pytest.raises(ValueError, match="missing"):
        derive_proposition(
            proposition_id="derived",
            subject="activity:1",
            predicate="strategy",
            value="bleed build",
            confidence=0.9,
            source_kind="assistant",
            observed_at=NOW,
            links=(EvidenceLink(ref="missing", relation="derived_from"),),
            propositions_by_id={},
        )


def test_semantic_derivation_requires_backing_evidence() -> None:
    with pytest.raises(ValueError, match="requires trust-bearing evidence"):
        derive_proposition(
            proposition_id="unsupported",
            subject="activity:1",
            predicate="current_objective",
            value="beat Malenia",
            confidence=0.8,
            source_kind="assistant",
            observed_at=NOW,
            links=(),
            propositions_by_id={},
        )


def test_invalid_validity_interval_is_rejected() -> None:
    with pytest.raises(ValueError, match="valid_until"):
        EvidenceProposition(
            proposition_id="bad",
            subject="activity:1",
            predicate="current_objective",
            value="beat Malenia",
            source_kind="user",
            trust_level="user_explicit",
            confidence=1.0,
            observed_at=NOW,
            valid_from=NOW,
            valid_until=datetime(2026, 9, 13, tzinfo=timezone.utc),
        )
