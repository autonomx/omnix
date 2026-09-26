from __future__ import annotations

import pytest

from app.audiobook.hashing import text_hash
from app.audiobook.render_planner import load_chapter_units
from app.persistence.tenant import local_tenant_context


class _Connection:
    def __init__(self, source: str, kind: str = "narration", exclusions=()) -> None:
        self.source = source
        self.kind = kind
        self.exclusions = exclusions
        self.query = ""

    def execute(self, query, _params):
        self.query = query
        return self

    def fetchone(self):
        if "current_source_revision_id" in self.query:
            return ("source-revision", "standard")
        if "omnix_audiobook_structure_runs" in self.query:
            return None
        return None

    def fetchall(self):
        if "omnix_audiobook_speech_exclusions" in self.query:
            return self.exclusions
        if "omnix_audiobook_document_overrides" in self.query:
            return []
        if "start_offset, end_offset, structural_kind" in self.query:
            return [("span-one", 0, len(self.source), self.kind, "test-detector")]
        if "omnix_audiobook_pronunciations" in self.query:
            return []
        return [("span-one", 0, self.source, text_hash(self.source),
                 "annotation", 1, "speaker", "", "casting", 1,
                 "voice", "a" * 64, "en")]


def test_long_narration_keeps_one_review_span_but_many_unique_render_units() -> None:
    source = "The lantern shone across the water. " * 200
    units = load_chapter_units(
        _Connection(source), local_tenant_context(), project_id="project",
        chapter_id="chapter",
    )
    assert len(units) > 1
    assert {unit.span_id for unit in units} == {"span-one"}
    assert "".join(unit.speech_plan.source_text for unit in units) == source
    assert all(len(unit.speech_plan.tts_input_text) <= 450 for unit in units)
    keys = [unit.identity(provider_id="provider", model_id="model",
                          model_revision="revision", generation_parameters={},
                          seed=None).key() for unit in units]
    assert len(set(keys)) == len(keys)


def test_preview_and_render_units_omit_dialogue_speaker_label() -> None:
    source = "Ehsan: It’s working again."
    for span_id in (None, "span-one"):
        units = load_chapter_units(
            _Connection(source, "dialogue"), local_tenant_context(),
            project_id="project", chapter_id="chapter", span_id=span_id,
        )
        assert len(units) == 1
        assert units[0].speech_plan.source_text == source
        assert units[0].speech_plan.tts_input_text == "It’s working again."


def test_preview_and_render_units_respect_local_text_removal() -> None:
    source = "Testing\nThe morning began."
    for span_id in (None, "span-one"):
        units = load_chapter_units(
            _Connection(source, exclusions=(("excluded", 0, 7, "Testing"),)),
            local_tenant_context(), project_id="project", chapter_id="chapter", span_id=span_id,
        )
        assert units[0].speech_plan.tts_input_text == "\nThe morning began."
        assert units[0].speech_plan.source_text == source


@pytest.mark.parametrize("missing_index,message", [
    (4, 'Go to "Cast and direct" and click "Classify text"'), (6, "Assign a speaker"), (8, "Assign a voice"),
])
def test_preview_and_render_explain_missing_speaker_setup(missing_index, message):
    class Connection(_Connection):
        def fetchall(self):
            rows = super().fetchall()
            if "AS a ON TRUE" in self.query:
                assert "LEFT JOIN LATERAL" in self.query
                row = list(rows[0])
                row[missing_index] = None
                return [tuple(row)]
            return rows

    for span_id in (None, "span-one"):
        with pytest.raises(ValueError, match=message):
            load_chapter_units(
                Connection("Hello."), local_tenant_context(),
                project_id="project", chapter_id="chapter", span_id=span_id,
            )
