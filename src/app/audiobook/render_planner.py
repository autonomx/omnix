"""Derive render work from the current source, annotation, and casting revisions."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.persistence.tenant import TenantContext

from .render_keys import RenderIdentity
from .hashing import object_hash
from .models import SourceSpan
from .document_structure import (
    READ_ONCE, effective_render_action, effective_role, mask_span_for_render,
)
from .document_structure_repository import PostgresAudiobookDocumentStructureRepository
from .speech_plan import SpeechPlan, build_speech_plan, split_speech_plan


@dataclass(frozen=True, slots=True)
class RenderUnit:
    span_id: str
    ordinal: int
    source_hash: str
    annotation_id: str
    annotation_revision: int
    speaker_id: str
    casting_id: str
    casting_revision: int
    voice_profile_id: str
    voice_revision_hash: str
    delivery: str
    language: str
    speech_plan: SpeechPlan
    segment_index: int = 0
    segment_start: int = 0
    segment_end: int = 0
    segment_count: int = 1

    def identity(
        self, *, provider_id: str, model_id: str, model_revision: str,
        generation_parameters: dict[str, Any], seed: int | None,
    ) -> RenderIdentity:
        return RenderIdentity(
            source_span_hash=(self.source_hash if self.segment_count == 1 else
                              object_hash({"source_hash": self.source_hash,
                                           "segment_index": self.segment_index,
                                           "segment_start": self.segment_start,
                                           "segment_end": self.segment_end})),
            annotation_revision=f"{self.annotation_id}:{self.annotation_revision}",
            speaker_id=self.speaker_id,
            casting_revision=f"{self.casting_id}:{self.casting_revision}",
            voice_revision=self.voice_revision_hash,
            reference_audio_hash=self.voice_revision_hash,
            provider_id=provider_id, model_id=model_id, model_revision=model_revision,
            language=self.language, delivery_instruction=self.delivery,
            speech_plan_hash=self.speech_plan.hash,
            generation_parameters=generation_parameters, seed=seed,
        )


def load_chapter_units(
    connection: Any, context: TenantContext, *, project_id: str, chapter_id: str,
    span_id: str | None = None,
) -> list[RenderUnit]:
    project_row = connection.execute(
        """SELECT current_source_revision_id,
                  COALESCE(settings->>'audiobook_mode', 'standard')
             FROM omnix_audiobook_projects
            WHERE workspace_id = %s AND id = %s AND deleted_at IS NULL""",
        (context.workspace_id, project_id),
    ).fetchone()
    if project_row is None or not project_row[0]:
        raise ValueError("project has no canonical source")
    source_revision_id = str(project_row[0])
    audiobook_mode = str(project_row[1] or "standard")
    structure_repository = PostgresAudiobookDocumentStructureRepository(connection)
    all_blocks = structure_repository.list_blocks(
        context, source_revision_id=source_revision_id,
    )
    chapter_blocks = [
        block for block in all_blocks if block.chapter_id == chapter_id
    ]
    structure_overrides = structure_repository.list_overrides(
        context, project_id=project_id, source_revision_id=source_revision_id,
    )
    read_once_block_ids: set[str] = set()
    seen_read_once: set[str] = set()
    for block in all_blocks:
        if effective_render_action(
            block, mode=audiobook_mode, overrides=structure_overrides,
        ) != READ_ONCE:
            continue
        key = block.recurrence_group or (
            f"role:{effective_role(block, structure_overrides)}"
        )
        if key not in seen_read_once:
            seen_read_once.add(key)
            read_once_block_ids.add(block.id)

    span_meta_rows = connection.execute(
        """SELECT id, start_offset, end_offset, structural_kind, detector_version
             FROM omnix_audiobook_spans
            WHERE workspace_id = %s AND chapter_id = %s""",
        (context.workspace_id, chapter_id),
    ).fetchall()
    span_meta = {
        str(row[0]): (int(row[1]), int(row[2]), str(row[3]), str(row[4]))
        for row in span_meta_rows
    }

    pronunciation_rows = connection.execute(
        """SELECT DISTINCT ON (source_term) source_term, spoken_term
             FROM omnix_audiobook_pronunciations
            WHERE workspace_id = %s AND project_id = %s
            ORDER BY source_term, revision DESC""",
        (context.workspace_id, project_id),
    ).fetchall()
    overrides = {str(term): str(spoken) for term, spoken in pronunciation_rows}
    rows = connection.execute(
        """
        SELECT s.id, s.ordinal, s.source_text, s.source_hash,
               a.id, a.revision, a.speaker_id, a.delivery,
               c.id, c.revision, c.voice_profile_id, c.voice_revision_hash,
               p.language
          FROM omnix_audiobook_spans AS s
          JOIN omnix_audiobook_chapters AS ch
            ON ch.workspace_id = s.workspace_id AND ch.id = s.chapter_id
          JOIN omnix_audiobook_source_revisions AS sr
            ON sr.workspace_id = ch.workspace_id AND sr.id = ch.source_revision_id
          JOIN omnix_audiobook_projects AS p
            ON p.workspace_id = sr.workspace_id AND p.id = sr.project_id
           AND p.current_source_revision_id = sr.id
          JOIN LATERAL (
              SELECT id, revision, speaker_id, delivery
                FROM omnix_audiobook_annotations
               WHERE workspace_id = s.workspace_id AND span_id = s.id
               ORDER BY revision DESC LIMIT 1
          ) AS a ON TRUE
          LEFT JOIN LATERAL (
              SELECT id, revision, voice_profile_id, voice_revision_hash
                FROM omnix_audiobook_castings
               WHERE workspace_id = s.workspace_id AND speaker_id = a.speaker_id
               ORDER BY revision DESC LIMIT 1
          ) AS c ON TRUE
         WHERE s.workspace_id = %s AND sr.project_id = %s AND ch.id = %s
           AND (%s::text IS NULL OR s.id = %s)
         ORDER BY s.ordinal
        """, (context.workspace_id, project_id, chapter_id, span_id, span_id),
    ).fetchall()
    units: list[RenderUnit] = []
    for row in rows:
        source_text = str(row[2])
        if chapter_blocks:
            meta = span_meta.get(str(row[0]))
            if meta is None:
                raise ValueError(f"source span metadata missing for {row[0]}")
            start_offset, end_offset, structural_kind, detector_version = meta
            source_span = SourceSpan(
                id=str(row[0]), chapter_id=chapter_id, ordinal=int(row[1]),
                start_offset=start_offset, end_offset=end_offset,
                source_text=source_text, source_hash=str(row[3]),
                structural_kind=structural_kind, detector_version=detector_version,
            )
            source_text = mask_span_for_render(
                source_span, chapter_blocks, mode=audiobook_mode,
                overrides=structure_overrides,
                read_once_block_ids=read_once_block_ids,
            )
        plan = build_speech_plan(source_text, overrides=overrides)
        if not plan.tts_input_text.strip():
            continue
        if row[8] is None:
            raise ValueError(f"speaker {row[6]} has no voice casting")
        segments = split_speech_plan(plan)
        for segment_index, (start, end, segment_plan) in enumerate(segments):
            if not segment_plan.tts_input_text.strip():
                continue
            units.append(RenderUnit(
                span_id=str(row[0]), ordinal=int(row[1]), source_hash=str(row[3]),
                annotation_id=str(row[4]), annotation_revision=int(row[5]),
                speaker_id=str(row[6]), delivery=str(row[7]),
                casting_id=str(row[8]), casting_revision=int(row[9]),
                voice_profile_id=str(row[10]), voice_revision_hash=str(row[11]),
                language=str(row[12]), speech_plan=segment_plan,
                segment_index=segment_index, segment_start=start,
                segment_end=end, segment_count=len(segments),
            ))
    return units
