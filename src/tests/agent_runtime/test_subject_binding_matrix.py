from __future__ import annotations

from datetime import datetime, timezone

from app.agent_runtime.contracts import (
    EvidencePolicy,
    EvidenceReceipt,
    EvidenceRequirement,
    SubjectRef,
)
from app.agent_runtime.evidence import evaluate_evidence_set, subject_matches


def _receipt(
    *,
    source_class: str,
    subject: SubjectRef | None,
    receipt_id: str,
) -> EvidenceReceipt:
    now = datetime.now(timezone.utc)
    return EvidenceReceipt(
        receipt_id=receipt_id,
        run_id="run-1",
        capability_id="test.capability",
        source_class=source_class,
        subject=subject,
        request_digest=receipt_id,
        result_digest=receipt_id,
        observed_at=now,
        executed_at=now,
        trust_level="authoritative",
    )


def test_market_evidence_for_wrong_ticker_is_rejected() -> None:
    required = SubjectRef(
        type="security",
        canonical_id="NVDA:US",
        display_name="NVDA",
        qualifiers={"ticker": "NVDA"},
    )
    wrong = SubjectRef(
        type="security",
        canonical_id="TSLA:US",
        display_name="TSLA",
        qualifiers={"ticker": "TSLA"},
    )
    policy = EvidencePolicy(
        requirement="required",
        requirements=[
            EvidenceRequirement(
                id="quote",
                source_class="market_quote",
                subject=required,
                freshness="current",
                trust_floor="authoritative",
                max_age_seconds=60,
            )
        ],
    )
    result = evaluate_evidence_set(
        "run-1",
        policy,
        [_receipt(source_class="market_quote", subject=wrong, receipt_id="tsla")],
    )
    assert result.passed is False
    assert result.requirements[0].status == "wrong_subject"


def test_repository_evidence_for_wrong_repository_is_rejected() -> None:
    required = SubjectRef(
        type="repository_ref",
        canonical_id="autonomx/omnix",
        qualifiers={"resolved_commit": "abc123"},
    )
    wrong = SubjectRef(
        type="repository_ref",
        canonical_id="other/repo",
        qualifiers={"resolved_commit": "abc123"},
    )
    policy = EvidencePolicy(
        requirement="required",
        requirements=[
            EvidenceRequirement(
                id="ci",
                source_class="repo_ci_state",
                subject=required,
                freshness="current",
                trust_floor="authoritative",
                max_age_seconds=300,
            )
        ],
    )
    result = evaluate_evidence_set(
        "run-1",
        policy,
        [_receipt(source_class="repo_ci_state", subject=wrong, receipt_id="other")],
    )
    assert result.passed is False
    assert result.requirements[0].status == "wrong_subject"


def test_repository_evidence_for_wrong_commit_is_rejected() -> None:
    required = SubjectRef(
        type="repository_ref",
        canonical_id="autonomx/omnix",
        qualifiers={"resolved_commit": "abc123"},
    )
    stale_ref = SubjectRef(
        type="repository_ref",
        canonical_id="autonomx/omnix",
        qualifiers={"resolved_commit": "def456"},
    )
    assert subject_matches(required, stale_ref) is False


def test_required_subject_qualifiers_cannot_be_omitted() -> None:
    required = SubjectRef(
        type="repository_ref",
        canonical_id="autonomx/omnix",
        qualifiers={"requested_ref": "main", "resolved_commit": "abc123"},
    )
    broad = SubjectRef(
        type="repository_ref",
        canonical_id="autonomx/omnix",
        qualifiers={},
    )
    assert subject_matches(required, broad) is False


def test_extra_observed_qualifiers_do_not_break_valid_subject_match() -> None:
    required = SubjectRef(
        type="security",
        canonical_id="NVDA:US",
        qualifiers={"ticker": "NVDA"},
    )
    observed = SubjectRef(
        type="security",
        canonical_id="NVDA:US",
        qualifiers={"ticker": "NVDA", "exchange": "NASDAQ"},
    )
    assert subject_matches(required, observed) is True


def test_subject_type_mismatch_is_rejected_even_if_id_matches() -> None:
    required = SubjectRef(type="security", canonical_id="NVDA:US")
    observed = SubjectRef(type="repository_ref", canonical_id="NVDA:US")
    assert subject_matches(required, observed) is False


def test_prior_subject_receipt_cannot_satisfy_steered_subject() -> None:
    nvda = SubjectRef(
        type="security",
        canonical_id="NVDA:US",
        qualifiers={"ticker": "NVDA"},
    )
    amd = SubjectRef(
        type="security",
        canonical_id="AMD:US",
        qualifiers={"ticker": "AMD"},
    )
    policy = EvidencePolicy(
        requirement="required",
        requirements=[
            EvidenceRequirement(
                id="news",
                source_class="market_news",
                subject=amd,
                freshness="current",
                trust_floor="authoritative",
                max_age_seconds=3600,
            )
        ],
    )
    prior = _receipt(source_class="market_news", subject=nvda, receipt_id="nvda")
    result = evaluate_evidence_set("run-1", policy, [prior])
    assert result.passed is False
    assert result.requirements[0].status == "wrong_subject"


def test_matching_subject_and_source_satisfy_requirement() -> None:
    subject = SubjectRef(
        type="security",
        canonical_id="NVDA:US",
        qualifiers={"ticker": "NVDA"},
    )
    policy = EvidencePolicy(
        requirement="required",
        requirements=[
            EvidenceRequirement(
                id="quote",
                source_class="market_quote",
                subject=subject,
                freshness="current",
                trust_floor="authoritative",
                max_age_seconds=60,
            )
        ],
    )
    result = evaluate_evidence_set(
        "run-1",
        policy,
        [_receipt(source_class="market_quote", subject=subject, receipt_id="nvda")],
    )
    assert result.passed is True


def test_matching_subject_with_wrong_source_class_does_not_satisfy() -> None:
    subject = SubjectRef(
        type="security",
        canonical_id="NVDA:US",
        qualifiers={"ticker": "NVDA"},
    )
    policy = EvidencePolicy(
        requirement="required",
        requirements=[
            EvidenceRequirement(
                id="quote",
                source_class="market_quote",
                subject=subject,
                freshness="current",
                trust_floor="authoritative",
                max_age_seconds=60,
            )
        ],
    )
    result = evaluate_evidence_set(
        "run-1",
        policy,
        [_receipt(source_class="market_news", subject=subject, receipt_id="news")],
    )
    assert result.passed is False
    assert result.missing_requirements == ["quote"]


def test_email_evidence_wrong_account_context_is_rejected() -> None:
    required = SubjectRef(
        type="email_account",
        canonical_id="primary",
        qualifiers={"account": "primary"},
    )
    observed = SubjectRef(
        type="email_account",
        canonical_id="work",
        qualifiers={"account": "work"},
    )
    assert subject_matches(required, observed) is False


def test_calendar_evidence_wrong_calendar_context_is_rejected() -> None:
    required = SubjectRef(
        type="calendar_account",
        canonical_id="primary",
        qualifiers={"calendar": "primary"},
    )
    observed = SubjectRef(
        type="calendar_account",
        canonical_id="shared",
        qualifiers={"calendar": "shared"},
    )
    assert subject_matches(required, observed) is False
