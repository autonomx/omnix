from __future__ import annotations

import json
from decimal import Decimal

from app.persistence.tenant import TenantContext, local_tenant_context
from app.persistence.unit_of_work import unit_of_work

from .bounce_model import BounceModelScore
from .catalyst_evidence import CatalystEvidence


class TradingCatalystRepository:
    def __init__(self, *, context: TenantContext | None = None, uow_factory=unit_of_work) -> None:
        self.context = context or local_tenant_context()
        self.uow_factory = uow_factory

    def save_evidence(self, evidence: CatalystEvidence) -> bool:
        with self.uow_factory() as uow:
            inserted = uow.connection.execute(
                """
                INSERT INTO omnix_trading_catalyst_evidence (
                    workspace_id, evidence_id, instrument_id, source_type,
                    source_locator, published_at, captured_at, headline, content,
                    text_hash, facts, dilution_flags, immutable_fingerprint
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s)
                ON CONFLICT (workspace_id, immutable_fingerprint) DO NOTHING
                RETURNING evidence_id
                """,
                (
                    self.context.workspace_id,
                    evidence.evidence_id,
                    evidence.instrument_id,
                    evidence.source_type,
                    evidence.source_locator,
                    evidence.published_at,
                    evidence.captured_at,
                    evidence.headline,
                    evidence.content,
                    evidence.text_hash,
                    json.dumps(evidence.facts, default=str),
                    json.dumps(list(evidence.dilution_flags)),
                    evidence.immutable_fingerprint,
                ),
            ).fetchone()
            uow.commit()
        return inserted is not None

    def list_evidence(self, instrument_id: str, limit: int = 100) -> list[CatalystEvidence]:
        with self.uow_factory() as uow:
            rows = uow.connection.execute(
                """
                SELECT evidence_id, instrument_id, source_type, source_locator,
                       published_at, captured_at, headline, content, text_hash,
                       facts, dilution_flags, immutable_fingerprint
                  FROM omnix_trading_catalyst_evidence
                 WHERE workspace_id = %s AND instrument_id = %s
                 ORDER BY published_at DESC, captured_at DESC LIMIT %s
                """,
                (self.context.workspace_id, instrument_id, limit),
            ).fetchall()
        return [
            CatalystEvidence(
                evidence_id=row[0], instrument_id=row[1], source_type=row[2], source_locator=row[3],
                published_at=row[4], captured_at=row[5], headline=row[6], content=row[7],
                text_hash=row[8], facts=row[9], dilution_flags=tuple(row[10]),
                immutable_fingerprint=row[11],
            )
            for row in rows
        ]

    def save_model_score(
        self,
        *,
        score_id: str,
        strategy_id: str | None,
        instrument_id: str,
        score: BounceModelScore,
    ) -> bool:
        with self.uow_factory() as uow:
            inserted = uow.connection.execute(
                """
                INSERT INTO omnix_trading_model_scores (
                    workspace_id, score_id, strategy_id, instrument_id, model_id,
                    model_version, observed_at, probability, features,
                    label_definition, shadow_only, fingerprint
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, TRUE, %s)
                ON CONFLICT (workspace_id, fingerprint) DO NOTHING
                RETURNING score_id
                """,
                (
                    self.context.workspace_id,
                    score_id,
                    strategy_id,
                    instrument_id,
                    score.model_id,
                    score.model_version,
                    score.observed_at,
                    Decimal(score.probability),
                    json.dumps(score.features.model_dump(mode="json")),
                    score.label_definition,
                    score.fingerprint,
                ),
            ).fetchone()
            uow.commit()
        return inserted is not None


def default_catalyst_repository() -> TradingCatalystRepository:
    return TradingCatalystRepository()
