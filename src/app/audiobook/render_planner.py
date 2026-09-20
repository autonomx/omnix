"""Derive render work from the current source, annotation, and casting revisions."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.persistence.tenant import TenantContext

from .render_keys import RenderIdentity
from .hashing import object_hash
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
        plan = build_speech_plan(str(row[2]), overrides=overrides)
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
