"""Evaluate RPG narration over published worlds (RQ-0.6).

Generalizes ``edge/dialogue_quality_benchmark.py`` (one starter-town innkeeper, fixed cases) to campaigns played in
Aurelia, Vesper-9 and the starter town through the real turn route and narration path. Each world is one campaign of
``--turns-per-world`` narrated turns (default 300), drawn from the intent corpus's *development* set (never the
held-out set): mostly questions and remarks to someone present (an expected speaker), with looks, inspections,
purchases and travel between the world's scenes in between.

Per narrated turn:

(a) **Deterministic checks**
   - *State contradiction*: the narration claims a change the turn did not apply, or a different one. Claims are read
     from the narration and the dialogue with fixed patterns: arriving somewhere (and where), paying or buying,
     receiving a named item, landing a blow. They are compared with the material changes of the saved game (place,
     purse, pack, fight, NPC health; ``scripts/rpg_intent_eval.py``).
   - *Engine claim validation*: the canonical narrative response's own validation, which runs the claim inference and
     support validation of ``narration/narrative_engine/claims.py`` inside the turn; a failed validation counts.
   - *Correct speaker* (turns with an expected speaker): some dialogue block is spoken by the person addressed, and no
     dialogue block by someone who is not present.
   - *Private canon not leaked*: no word 6-gram of the world's private canon (``secret``, ``secrets``,
     ``hidden_truth``, ``private``, ``gm_notes`` and ``must_not_reveal`` fields of the bundle; for the starter town the
     innkeeper's private profile) appears in what the player sees.
(b) **Model-judged rubric**: grounded, continuous, varied, judged by the same provider (``--judge``). The judge is
   calibrated against 150 human-labelled items (``resources/benchmarks/rpg/narration_calibration/labels.jsonl``);
   until those are labelled the rubric is reported as ``uncalibrated`` and does not gate. With labels, agreement and
   Cohen's kappa are reported per criterion, and the rubric gates only at agreement >= 0.90 and kappa >= 0.70.
(c) **Near duplicate**: a narration whose word 5-gram Jaccard similarity with any of the previous 10 narrations of the
   same campaign is >= 0.6.

Each metric is reported with its n and Wilson 95% bounds.

    OMNIX_DATABASE_URL=... python scripts/rpg_narration_eval.py --provider route --turns-per-world 300 --judge
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
import io
import json
import os
from pathlib import Path
import random
import re
import subprocess
import sys
import time
from typing import Any
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import rpg_intent_eval as intent  # noqa: E402
from tests.rehearsal.rpg.stats import proportion  # noqa: E402

CALIBRATION = ROOT / "resources/benchmarks/rpg/narration_calibration"
WORLDS = ("aurelia", "vesper-9", "starter")
SEED = 20261023
# Travel between a world's scenes, in the order a campaign visits them.
ROTATION = {
    "aurelia": [("grove", None), ("village", "go to Starfall Village"), ("guild", "go to the Wayfarers' Guild"),
                ("village", "go to Starfall Village"), ("grove", "go to Starfall Grove")],
    "vesper-9": [("docks", None)],
    "starter": [("tavern", None), ("market", "go outside"), ("tavern", "go back into the tavern")],
}
SPEAKER_FAMILIES = {"talk", "ask"}
OTHER_FAMILIES = {"look", "inspect", "buy", "status", "decline", "wait"}
PRIVATE_KEYS = {"secret", "secrets", "hidden_truth", "private", "gm_notes", "must_not_reveal"}
NEAR_DUPLICATE_JACCARD = 0.6
NEAR_DUPLICATE_WINDOW = 10
LEAK_NGRAM = 6
CRITERIA = ("grounded", "continuous", "varied")


# --- text helpers ---------------------------------------------------------------------------------------------

def words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", str(text or "").lower())


def ngrams(text: str, size: int) -> set[tuple[str, ...]]:
    tokens = words(text)
    return {tuple(tokens[index:index + size]) for index in range(len(tokens) - size + 1)}


def jaccard(left: set, right: set) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def near_duplicate(text: str, previous: list[str]) -> bool:
    grams = ngrams(text, 5)
    return any(jaccard(grams, ngrams(other, 5)) >= NEAR_DUPLICATE_JACCARD for other in previous[-NEAR_DUPLICATE_WINDOW:])


def private_canon(world: str) -> list[str]:
    """The private canon a player must not see: the bundle's secret fields (and the starter innkeeper's)."""
    if world == "starter":
        from app.apps.rpg.edge.dialogue_quality_benchmark import BRAN_PROFILE

        return [BRAN_PROFILE["biography"]["private"], *BRAN_PROFILE["inventory"]["private"],
                *BRAN_PROFILE["knowledge_boundaries"]["must_not_reveal"]]
    from tests.rehearsal.rpg.worlds import world_bundle

    with zipfile.ZipFile(io.BytesIO(world_bundle(world))) as archive:
        data = json.loads(archive.read("world.json"))
    found: list[str] = []

    def walk(value: Any, key: str = "") -> None:
        if isinstance(value, dict):
            for child_key, child in value.items():
                walk(child, child_key)
        elif isinstance(value, list):
            for child in value:
                walk(child, key)
        elif isinstance(value, str) and key in PRIVATE_KEYS and len(words(value)) >= LEAK_NGRAM:
            found.append(value)

    walk(data)
    return sorted(set(found))


def leaked(text: str, private: list[set[tuple[str, ...]]]) -> bool:
    grams = ngrams(text, LEAK_NGRAM)
    return any(grams & secret for secret in private)


# --- claims against applied changes -----------------------------------------------------------------------------

_ARRIVE = re.compile(r"\byou (?:arrive|reach|step into|step inside|enter|walk into|set foot in|make your way (?:in)?to)\b(.{0,80})")
_PAY = re.compile(r"\byou (?:pay|hand over|count out|part with|buy|purchase)\b")
_RECEIVE = re.compile(r"\b(?:hands you|gives you|you receive|you pocket|you pick up|you accept)\b(.{0,60})")
_BLOW = re.compile(r"\byou (?:strike|hit|slash|stab|wound|kill|slay|cut down)\b")


def contradictions(text: str, found: list[dict[str, Any]], catalog: intent.Catalog) -> list[str]:
    """The narration's claims that the turn's applied changes do not support."""
    lowered = str(text or "").lower()
    kinds = {change["kind"]: change for change in found}
    reasons: list[str] = []
    for match in _ARRIVE.finditer(lowered):
        place = catalog.resolve(match.group(1))
        if place and catalog.entities.get(place, {}).get("kind") == "place":
            moved_to = catalog.resolve(kinds.get("location", {}).get("to"))
            if moved_to != place:
                reasons.append(f"arrival at {place} not applied")
    if _PAY.search(lowered) and "purse" not in kinds:
        reasons.append("payment not applied")
    for match in _RECEIVE.finditer(lowered):
        item = catalog.resolve(match.group(1))
        if item and catalog.entities.get(item, {}).get("kind") in {"item", "offer"} and "items_gained" not in kinds:
            reasons.append(f"{item} received but not gained")
    if _BLOW.search(lowered) and not ({"combat_started", "npc_hurt", "player_hurt"} & set(kinds)):
        reasons.append("blow landed outside a fight")
    return reasons


# --- the campaign script ----------------------------------------------------------------------------------------

def campaign_script(world: str, turns: int, catalog: dict[str, Any], rng: random.Random) -> list[dict[str, Any]]:
    """The inputs of one campaign: per scene visit, travel there, then speaker turns and other turns."""
    dev = [item for item in intent.load_items("dev") if item["world"] == world]
    scenes = catalog["worlds"][world]["scenes"]
    script: list[dict[str, Any]] = []
    visit = 0
    while len(script) < turns:
        scene, travel = ROTATION[world][visit % len(ROTATION[world])]
        visit += 1
        if travel and script:
            script.append({"scene": scene, "input": travel, "family": "move", "expected_speaker": None})
        present = set(scenes[scene]["present"])
        speak = [item for item in dev if item["scene"] == scene and item["action_family"] in SPEAKER_FAMILIES
                 and item["target_entity"] in present]
        other = [item for item in dev if item["scene"] == scene and item["action_family"] in OTHER_FAMILIES]
        block = [("speak", rng.choice(speak)) for _ in range(11) if speak] + [("other", rng.choice(other)) for _ in range(3) if other]
        rng.shuffle(block)
        for kind, item in block:
            script.append({"scene": scene, "input": item["input"], "family": item["action_family"],
                           "expected_speaker": item["target_entity"] if kind == "speak" else None,
                           "corpus_id": item["id"]})
    return script[:turns]


# --- the judge --------------------------------------------------------------------------------------------------

JUDGE_SYSTEM = (
    "You grade one turn of a text role-playing game. Answer with JSON only: "
    '{"grounded": true|false, "continuous": true|false, "varied": true|false, "note": "<one short sentence>"}. '
    "grounded: the narration is consistent with the scene facts and the applied changes given, and invents no fact "
    "that contradicts them. continuous: it follows from the player's input and the previous narration. varied: it is "
    "not a near-repeat, in wording or structure, of the previous narrations."
)


def judge_prompt(turn: dict[str, Any]) -> str:
    context = {
        "world": turn["world"], "scene": turn["scene"], "present": turn["present"], "player_input": turn["input"],
        "applied_changes": turn["changes"], "previous_narrations": turn["previous"][-3:], "narration": turn["text"],
    }
    return "Grade this turn.\nCONTEXT: " + json.dumps(context, ensure_ascii=False)


def parse_judgement(text: str) -> dict[str, Any] | None:
    match = re.search(r"\{.*\}", str(text or ""), re.DOTALL)
    if not match:
        return None
    try:
        value = json.loads(match.group(0))
    except ValueError:
        return None
    if not all(isinstance(value.get(criterion), bool) for criterion in CRITERIA):
        return None
    return {criterion: value[criterion] for criterion in CRITERIA} | {"note": str(value.get("note") or "")[:200]}


def cohen_kappa(pairs: list[tuple[bool, bool]]) -> float | None:
    if not pairs:
        return None
    n = len(pairs)
    observed = sum(a == b for a, b in pairs) / n
    p_human = sum(a for a, _ in pairs) / n
    p_judge = sum(b for _, b in pairs) / n
    expected = p_human * p_judge + (1 - p_human) * (1 - p_judge)
    return round((observed - expected) / (1 - expected), 4) if expected < 1 else None


def calibration(records: list[dict[str, Any]], rejudge: Any = None) -> dict[str, Any]:
    """Agreement and kappa per criterion against the human labels, or uncalibrated.

    With ``rejudge`` (the run's judge), every labelled item is judged again, so the agreement is the current judge's;
    otherwise the judgement stored with the item is used.
    """
    path = CALIBRATION / "labels.jsonl"
    labels = []
    if path.exists():
        labels = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    labelled = [row for row in labels if all(isinstance((row.get("human") or {}).get(c), bool) for c in CRITERIA)
                and isinstance(row.get("judge"), dict)]
    if len(labelled) < 150:
        return {"status": "uncalibrated", "labelled_items": len(labelled), "required": 150,
                "gates": False, "reason": "the human labels are not complete; the rubric does not gate"}
    if rejudge is not None:
        for row in labelled:
            fresh = rejudge({"world": row.get("world"), "scene": row.get("scene"), "present": row.get("present"),
                             "input": row.get("input"), "changes": row.get("applied_changes"),
                             "previous": row.get("previous_narrations") or [], "text": row.get("narration")})
            if isinstance(fresh, dict) and "error" not in fresh:
                row["judge"] = fresh
    result: dict[str, Any] = {"status": "calibrated", "labelled_items": len(labelled),
                              "judge": "current run" if rejudge is not None else "stored with the labels"}
    gates = True
    for criterion in CRITERIA:
        pairs = [(row["human"][criterion], bool(row["judge"].get(criterion))) for row in labelled]
        agreement = sum(a == b for a, b in pairs) / len(pairs)
        kappa = cohen_kappa(pairs)
        result[criterion] = {"agreement": round(agreement, 4), "kappa": kappa}
        gates = gates and agreement >= 0.90 and (kappa or 0) >= 0.70
    result["gates"] = gates
    return result


# --- the run ----------------------------------------------------------------------------------------------------

class Runner:
    def __init__(self, provider: str, judge: bool) -> None:
        from tests.rehearsal.rpg import worlds

        self.worlds = worlds
        self.client = worlds.turn_client()
        if provider == "scripted":
            self.model = worlds.install_scripted_model()
            self.calls = lambda: [{"role": role} for role in self.model.calls]
        else:
            self.model = worlds.install_counting_provider()
            self.calls = lambda: list(self.model.calls)
        self.provider = provider
        self.judge = judge and provider == "route"
        self.catalog = json.loads((intent.CORPUS / "catalog.json").read_text(encoding="utf-8"))

    def play_world(self, world: str, turns: int, rng: random.Random) -> list[dict[str, Any]]:
        catalog = intent.Catalog(self.catalog["worlds"][world])
        private = [ngrams(text, LEAK_NGRAM) for text in private_canon(world)]
        session_id = self.worlds.launch(world)
        records: list[dict[str, Any]] = []
        previous: list[str] = []
        script = campaign_script(world, turns, self.catalog, rng)
        before = intent.material_state(self.worlds.load(session_id))
        for index, step in enumerate(script, 1):
            calls_before = len(self.calls())
            started = time.perf_counter()
            response = self.client.post(f"/api/rpg/sessions/{session_id}/turn", json={"command": step["input"]},
                                        headers={"x-omnix-rpg-submission-id": f"submit:narration:{uuid.uuid4().hex}"})
            elapsed = (time.perf_counter() - started) * 1000
            body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
            session = self.worlds.load(session_id)
            after = intent.material_state(session)
            found = intent.changes(before, after)
            before = after
            canonical = body.get("canonical_narrative_response") or {}
            blocks = canonical.get("blocks") or []
            visible = (body.get("visible_response") or {}).get("plain_text") or "\n".join(
                str(block.get("text") or "") for block in blocks)
            present = list(self.catalog["worlds"][world]["scenes"][step["scene"]]["present"])
            speakers = [catalog.resolve(block.get("speaker_id")) or str(block.get("speaker_id"))
                        for block in blocks if block.get("kind") == "dialogue" and block.get("speaker_id")]
            expected = step["expected_speaker"]
            record = {
                "world": world, "turn": index, "scene": step["scene"], "input": step["input"],
                "family": step["family"], "corpus_id": step.get("corpus_id"), "http": response.status_code,
                "turn_ms": round(elapsed, 1), "text": visible, "speakers": speakers, "expected_speaker": expected,
                "present": present, "changes": found,
                "validation": (canonical.get("validation") or {}),
                "model_calls": [call.get("role") for call in self.calls()[calls_before:]],
                "previous": list(previous[-NEAR_DUPLICATE_WINDOW:]),
            }
            record["checks"] = {
                "state_contradictions": contradictions(visible, found, catalog),
                "engine_validation_failed": (canonical.get("validation") or {}).get("passed") is False,
                "correct_speaker": (expected in speakers and all(speaker in present for speaker in speakers))
                if expected else None,
                "private_leak": leaked(visible, private),
                "near_duplicate": near_duplicate(visible, previous),
                "empty": not visible.strip(),
            }
            if self.judge:
                record["judge"] = self.judge_turn(record)
            previous.append(visible)
            records.append(record)
            print(f"{world} {index}/{len(script)}: {response.status_code} {round(elapsed)} ms", file=sys.stderr)
        return records

    def judge_turn(self, record: dict[str, Any]) -> dict[str, Any] | None:
        from app.providers.base import ChatMessage

        inner = getattr(self.model, "inner", None)
        if inner is None:
            return None
        try:
            response = inner.chat_completion([ChatMessage(role="system", content=JUDGE_SYSTEM),
                                              ChatMessage(role="user", content=judge_prompt(record))])
        except Exception as exc:  # a failed judgement is recorded, not fatal
            return {"error": type(exc).__name__}
        return parse_judgement(getattr(response, "content", "")) or {"error": "unparsable"}


def report_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    narrated = [record for record in records if record["http"] == 200]
    with_speaker = [record for record in narrated if record["expected_speaker"]]
    metrics = {
        "state_contradictions": proportion(sum(bool(r["checks"]["state_contradictions"]) for r in narrated), len(narrated)),
        "engine_claim_validation_failed": proportion(sum(r["checks"]["engine_validation_failed"] for r in narrated), len(narrated)),
        "correct_speaker": proportion(sum(bool(r["checks"]["correct_speaker"]) for r in with_speaker), len(with_speaker)),
        "private_canon_leak": proportion(sum(r["checks"]["private_leak"] for r in narrated), len(narrated)),
        "near_duplicate": proportion(sum(r["checks"]["near_duplicate"] for r in narrated), len(narrated)),
        "empty_narration": proportion(sum(r["checks"]["empty"] for r in narrated), len(narrated)),
        "turn_failures": proportion(len(records) - len(narrated), len(records)),
    }
    judged = [r for r in narrated if isinstance(r.get("judge"), dict) and "error" not in r["judge"]]
    for criterion in CRITERIA:
        metrics[f"judge_{criterion}"] = proportion(sum(r["judge"][criterion] for r in judged), len(judged))
    return metrics


def write_calibration_template(records: list[dict[str, Any]], rng: random.Random) -> int:
    """150 narrated turns, spread over the worlds, for the owner to label (labels null until then)."""
    path = CALIBRATION / "labels.jsonl"
    if path.exists() and path.read_text(encoding="utf-8").strip():
        return 0
    narrated = [record for record in records if record["http"] == 200 and record["text"].strip()]
    rng.shuffle(narrated)
    chosen = narrated[:150]
    rows = [{"id": f"cal-{index:03d}", "world": r["world"], "scene": r["scene"], "input": r["input"],
             "present": r["present"], "applied_changes": r["changes"], "previous_narrations": r["previous"][-3:],
             "narration": r["text"], "judge": r.get("judge"),
             "human": {"grounded": None, "continuous": None, "varied": None, "labeller": None, "note": None}}
            for index, r in enumerate(chosen, 1)]
    CALIBRATION.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
                    encoding="utf-8", newline="\n")
    return len(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--provider", choices=("route", "scripted"), default="scripted")
    parser.add_argument("--turns-per-world", type=int, default=300)
    parser.add_argument("--worlds", nargs="+", choices=WORLDS, default=list(WORLDS))
    parser.add_argument("--judge", action="store_true", help="grade each turn with the provider (route only)")
    parser.add_argument("--calibration-template", action="store_true",
                        help="write the 150-item labelling file from this run when it does not exist yet")
    parser.add_argument("--allow-database", default="")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--records", type=Path)
    args = parser.parse_args(argv)
    os.environ.setdefault("OMNIX_RPG_TURNS_PER_HOUR", "0")
    if args.provider == "route":
        os.environ["OMNIX_RPG_NARRATIVE_WRITER_MODE"] = "auto"
    from tests.rehearsal.rpg import worlds

    database = worlds.require_disposable_database(args.allow_database)
    worlds.bootstrap()
    runner = Runner(args.provider, args.judge)
    identity = worlds.provider_identity() if args.provider == "route" else {"provider": "scripted", "model": "scripted"}
    rng = random.Random(SEED)
    started = time.perf_counter()
    records = [record for world in args.worlds for record in runner.play_world(world, args.turns_per_world, rng)]
    template_rows = write_calibration_template(records, rng) if args.calibration_template else 0
    report = {
        "schema_version": 1,
        "measurement": "RPG narration over published worlds (RQ-0.6)",
        "measured_on": date.today().isoformat(),
        "revision": subprocess.run(["git", "rev-parse", "--short=10", "HEAD"], cwd=ROOT, capture_output=True,
                                   text=True).stdout.strip(),
        "database": database,
        "provider": {**identity, "resolved_models": sorted(getattr(runner.model, "resolved_models", ()))}, "turns_per_world": args.turns_per_world,
        "worlds": args.worlds, "turns": len(records),
        "turns_with_expected_speaker": sum(bool(r["expected_speaker"]) for r in records),
        "metrics": report_metrics(records),
        "by_world": {world: report_metrics([r for r in records if r["world"] == world]) for world in args.worlds},
        "judge_calibration": calibration(records, runner.judge_turn if runner.judge else None),
        "judged": args.judge and args.provider == "route",
        "calibration_template_rows_written": template_rows,
        "contradiction_reasons": dict(Counter(reason.split(" ")[0] for r in records
                                              for reason in r["checks"]["state_contradictions"]).most_common()),
        "model_calls_per_turn": round(sum(len(r["model_calls"]) for r in records) / len(records), 2) if records else None,
        "gates": {"N1 (from RQ-3)": "contradictions upper <= 0.020; correct speaker lower >= 0.985; grounded lower >= 0.93 "
                                    "(calibrated judge only); near-duplicate <= 0.05"},
        "elapsed_s": round(time.perf_counter() - started, 1),
    }
    output = args.output or ROOT / "docs/measurements" / f"rpg-narration-baseline-{date.today().isoformat()}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    if args.records:
        args.records.write_text("".join(json.dumps(r, ensure_ascii=False, default=str) + "\n" for r in records),
                                encoding="utf-8")
    print(json.dumps(report["metrics"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
