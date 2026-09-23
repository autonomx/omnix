from __future__ import annotations

from app.audiobook.hashing import text_hash
from app.audiobook.render_planner import load_chapter_units
from app.persistence.tenant import local_tenant_context


class _Connection:
    def __init__(self, source: str) -> None:
        self.source = source
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
        if "omnix_audiobook_document_overrides" in self.query:
            return []
        if "start_offset, end_offset, structural_kind" in self.query:
            return [("span-one", 0, len(self.source), "narration", "test-detector")]
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
