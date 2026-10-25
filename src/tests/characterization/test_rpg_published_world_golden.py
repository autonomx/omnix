"""A published-world campaign, 30 turns through the production routes (characterization, RQ-0.2).

Aurelia is imported from its bundle, adopted and launched from its "Gateborn: First Light" opening, then
played through ``POST /api/rpg/sessions/{id}/turn``: looking, talking, asking a price, buying, selling,
dropping and picking up, travelling there and back, fighting (and a tactical grid move mid-fight), taking
a quest and advancing it, resting and waiting. The scripted model answers each call by its semantic role
(``tests.rpg.playthrough.scripted_model``), so a change to a call's wording or answer shape changes no
recording.

``rpg-published-world`` records, per turn: the response's changed domains and source, what the turn
changed (fact by fact, and the document sections its state patch touched), the session summary, the facts
after the turn, the roles of the model calls made, and a hash of the normalized campaign document. Its
prose (visible response, narrative blocks, and what the narrator was told) is in the separate
``rpg-published-world-prose`` snapshot, which may be re-recorded without justification
(``OMNIX_UPDATE_PROSE=1``) when only wording changed.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

import pytest

from tests.characterization.harness import GOLDEN_DIR, capture, normalize

# The catalog modules this scenario characterizes (scripts/test_module.py).
MODULES = ("rpg",)

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        not os.environ.get("OMNIX_TEST_DATABASE_URL"),
        reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
    ),
]

# A step is a turn command, or ("tactical_move", (x, y)) for a grid move through the tactical route.
STEPS: tuple[str | tuple[str, tuple[int, int]], ...] = (
    "look around",
    "I greet Liora Fen and ask her where I am",
    "I ask Liora Fen to join my party as a companion.",
    "I accept the quest Voices in the Phone.",
    "Practice swordsmanship with a careful training drill.",
    "go to Starfall Village",
    "look around",
    "I ask Orik Stonewake what he thinks of the newcomers.",
    "I ask Brindle Gearwing what a Healing Potion costs.",
    "I buy a Healing Potion from Brindle Gearwing.",
    "I sell my Iron Dagger to Brindle Gearwing.",
    "I drop one Lantern Bread on the ground.",
    "go to Wayfarers' Guild",
    "look around",
    "go to Starfall Village",
    "I pick up the Lantern Bread.",
    "I buy a meal from Orik Stonewake.",
    "I rent a room for the night from Orik Stonewake.",
    "I go to my room and sleep for the night.",
    "wait",
    "go to Skybridge Pass",  # where no one lives: a Glass Wight bars the way (encounters.md)
    "I attack the Glass Wight.",
    ("tactical_move", (9, 6)),
    "I attack the Glass Wight.",
    "I attack the Glass Wight.",
    "I flee from the Glass Wight.",
    "I drink the Healing Potion.",
    "Check my quests",
    "go to Starfall Village",
    "go to Starfall Grove",
    "wait",
)
PROSE_SNAPSHOT = GOLDEN_DIR / "rpg-published-world-prose.json"


def _patched_sections(turn_row: dict) -> list[str]:
    """The document sections (two levels deep) a turn's state patch touched."""
    sections = set()
    for operation in turn_row.get("state_delta") or ():
        parts = [part for part in str(operation.get("path") or "").split("/")[1:3] if part]
        sections.add("/".join(parts))
    return sorted(sections)


def _stable_text(text: str, session_id: str, world_id: str) -> str:
    """The run's own ids (campaign, world, submissions and jobs) as fixed placeholders."""
    text = text.replace(session_id, "SESSION").replace(world_id.split("-")[-1], "WORLD")
    return re.sub(r"\b(submit|job|pipeline)[:-][0-9a-f]{32}\b", r"\1:ID", text)


def _document_hash(document: dict, session_id: str, world_id: str) -> str:
    """The campaign document's hash once ids, times and durations are normalized (as the golden is).

    Content hashes of the world's documents (releases, maps, the campaign bible) cover the run's world id, so
    they are placeholders. Two parts of today's document are not reproducible and are left out: the
    wall-clock stage timings a turn stores (``runtime_state.perf_trace``) and the random creator preview id
    (``preview_<hex>``).
    """
    document = {**document, "runtime_state": {key: value for key, value in (document.get("runtime_state") or {}).items()
                                              if key != "perf_trace"}}
    text = _stable_text(json.dumps(document, sort_keys=True, ensure_ascii=False), session_id, world_id)
    text = re.sub(r"\b[0-9a-f]{64}\b", "<sha256>", text)
    text = re.sub(r"\bpreview_[0-9a-f]{12}\b", "preview_ID", text)
    canonical = json.dumps(normalize(json.loads(text)), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    dump = os.environ.get("OMNIX_GOLDEN_DUMP_DIR")
    if dump:  # to find what differs between two runs
        Path(dump).mkdir(parents=True, exist_ok=True)
        index = len(list(Path(dump).glob("*.json")))
        (Path(dump) / f"{index:03d}.json").write_text(json.dumps(json.loads(canonical), indent=1, sort_keys=True), encoding="utf-8")
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _prose(body: dict, told: str) -> dict:
    canonical = body.get("canonical_narrative_response") or {}
    return {
        "visible": (body.get("visible_response") or {}).get("plain_text"),
        "blocks": [f"{block.get('kind')}|{block.get('speaker_id') or ''}|{block.get('text')}"
                   for block in canonical.get("blocks") or ()],
        "told": told,
    }


def _play(tmp_path, monkeypatch) -> tuple[dict, dict]:
    from app.apps.rpg.narration.presentation.turn_response import RpgTurnResponse
    from tests.rpg.playthrough.campaigns import Playthrough, fact_changes, launch_aurelia
    from tests.rpg.playthrough.scripted_model import scripted_model_installed

    with scripted_model_installed(monkeypatch) as model:
        session_id, world_id = launch_aurelia(tmp_path, monkeypatch)
        play = Playthrough(session_id)
        facts = play.facts()
        opening = {"facts": facts, "document_hash": _document_hash(play.stored(), session_id, world_id)}
        turns, prose = [], []
        for step in STEPS:
            calls, writes, rows = len(model.calls), len(model.writer_payloads), len(play.turn_rows())
            if isinstance(step, tuple):
                response = play.tactical_move(step[1], submission_id=f"golden-move-{len(turns)}")
                body = response.json()
                record: dict = {"step": f"{step[0]} {list(step[1])}", "status": response.status_code,
                                "response": {key: body.get(key) for key in ("ok", "kind", "actor_cell", "detail")}}
                prose.append({"step": record["step"]})
            else:
                body = play.turn(step)
                RpgTurnResponse.model_validate(body)  # the published contract (WP-8.6)
                result = body.get("result") or {}
                summary = body.get("session_summary") or {}
                record = {
                    "step": step,
                    "status": 200,
                    "response": {
                        "changed_domains": result.get("changed_domains"),
                        "source": result.get("source"),
                        "state": body.get("state"),
                    },
                    "session_summary": {key: summary.get(key) for key in
                                        ("title", "location", "interaction_seq", "state_revision", "player_level")},
                }
                told = model.told() if len(model.writer_payloads) > writes else ""
                prose.append({"step": step, **_prose(body, told)})
            after = play.facts()
            new_rows = play.turn_rows()[rows:]
            record.update({
                "changes": fact_changes(facts, after),
                "patched_sections": sorted({section for row in new_rows for section in _patched_sections(row)}),
                "turn_rows": len(new_rows),
                "facts": after,
                "model_calls": model.roles(calls),
                "document_hash": _document_hash(play.stored(), session_id, world_id),
            })
            turns.append(record)
            facts = after
        assert model.unclassified == [], model.unclassified

    def stable(value: dict) -> dict:
        return json.loads(_stable_text(json.dumps(value, sort_keys=True, ensure_ascii=False), session_id, world_id))

    return stable({"opening": opening, "turns": turns}), stable({"turns": prose})


_RECORDING: list[tuple[dict, dict]] = []


def _recording(tmp_path, monkeypatch) -> tuple[dict, dict]:
    """One play for both checks: the first test plays, the second reuses its recording."""
    if not _RECORDING:
        _RECORDING.append(_play(tmp_path, monkeypatch))
    return _RECORDING[0]


def test_published_world_turns_match_golden(tmp_path, monkeypatch) -> None:
    state, _ = _recording(tmp_path, monkeypatch)
    capture("rpg-published-world", lambda: state)


def test_published_world_prose_matches_snapshot(tmp_path, monkeypatch) -> None:
    """The wording may be re-recorded freely (OMNIX_UPDATE_PROSE=1); the state golden may not."""
    _, prose = _recording(tmp_path, monkeypatch)
    actual = normalize(prose)
    if os.environ.get("OMNIX_UPDATE_PROSE") == "1" or os.environ.get("OMNIX_UPDATE_GOLDEN") == "1":
        PROSE_SNAPSHOT.write_text(json.dumps(actual, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return
    assert PROSE_SNAPSHOT.is_file(), f"missing prose snapshot {PROSE_SNAPSHOT}; record it with OMNIX_UPDATE_PROSE=1"
    expected = json.loads(Path(PROSE_SNAPSHOT).read_text(encoding="utf-8"))
    changed = [index for index, (left, right) in enumerate(zip(expected["turns"], actual["turns"])) if left != right]
    assert expected == actual, (
        f"the prose of turns {changed} changed; if only wording changed, re-record with OMNIX_UPDATE_PROSE=1"
    )
