"""RQ-0.6: the narration evaluation's deterministic checks and its judge calibration (no database, no model)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("omnix_rpg_narration_eval_tests_target", ROOT / "scripts/rpg_narration_eval.py")
narration = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(narration)
CATALOG = json.loads((narration.intent.CORPUS / "catalog.json").read_text(encoding="utf-8"))
AURELIA = narration.intent.Catalog(CATALOG["worlds"]["aurelia"])


def test_near_duplicate_is_five_gram_jaccard_over_the_last_ten():
    line = "The innkeeper wipes the counter and says the road north has been quiet all week."
    assert narration.near_duplicate(line, [line])
    assert narration.near_duplicate(line, [line] + ["Something else entirely happens here today."] * 9)
    assert not narration.near_duplicate(line, [line] + ["Something else entirely happens here today."] * 10)
    assert not narration.near_duplicate("Liora points west toward the village gate.", [line])
    assert narration.jaccard(set(), {("a",)}) == 0.0


def test_claims_are_checked_against_applied_changes():
    arrive = "You arrive at Starfall Village as the lamps are lit."
    assert narration.contradictions(arrive, [], AURELIA) == ["arrival at location:aurelia:starfall-village not applied"]
    moved = [{"kind": "location", "to": "location:aurelia:starfall-village"}]
    assert narration.contradictions(arrive, moved, AURELIA) == []
    assert narration.contradictions("You pay three silver.", [], AURELIA) == ["payment not applied"]
    assert narration.contradictions("You pay three silver.", [{"kind": "purse", "delta": -30}], AURELIA) == []
    assert narration.contradictions("Brindle hands you a healing potion.", [{"kind": "purse", "delta": -30}], AURELIA) == [
        "npc:brindle-gearwing:healing-potion received but not gained"]
    assert narration.contradictions("You strike the wolf.", [], AURELIA) == ["blow landed outside a fight"]
    assert narration.contradictions("You take in your surroundings.", [], AURELIA) == []


def test_private_canon_leak_is_a_shared_six_gram():
    secret = narration.ngrams("He once served Kestrel intelligence and still receives a pension", 6)
    assert narration.leaked("Rumour says he once served Kestrel intelligence and still drinks.", [secret])
    assert not narration.leaked("He served drinks to the crew.", [secret])


def test_private_canon_comes_from_the_bundle_secret_fields():
    texts = narration.private_canon("vesper-9")
    assert any("Kestrel intelligence" in text for text in texts)
    assert narration.private_canon("starter")


def test_judgement_parsing_and_kappa():
    assert narration.parse_judgement('ok {"grounded": true, "continuous": false, "varied": true, "note": "x"}') == {
        "grounded": True, "continuous": False, "varied": True, "note": "x"}
    assert narration.parse_judgement('{"grounded": "yes"}') is None
    assert narration.parse_judgement("no json") is None
    assert narration.cohen_kappa([(True, True), (False, False)] * 5) == 1.0
    assert narration.cohen_kappa([(True, False), (False, True)] * 5) == -1.0


def test_rubric_is_uncalibrated_until_150_items_are_labelled(tmp_path, monkeypatch):
    monkeypatch.setattr(narration, "CALIBRATION", tmp_path)
    assert narration.calibration([])["status"] == "uncalibrated"
    rows = [{"human": {"grounded": True, "continuous": True, "varied": index % 2 == 0},
             "judge": {"grounded": True, "continuous": True, "varied": index % 2 == 0}} for index in range(150)]
    (tmp_path / "labels.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    result = narration.calibration([])
    assert result["status"] == "calibrated" and result["varied"] == {"agreement": 1.0, "kappa": 1.0}
    # A criterion every label agrees on has no chance-corrected kappa: it cannot gate.
    assert result["grounded"]["kappa"] is None and result["gates"] is False


def test_campaign_script_draws_from_the_development_set_with_two_thirds_speakers():
    held = {item["input"] for item in narration.intent.load_items("held_out") if item["world"] == "aurelia"}
    script = narration.campaign_script("aurelia", 60, CATALOG, random.Random(1))
    assert len(script) == 60
    assert all(step.get("corpus_id", "dev").startswith("dev") for step in script)
    assert sum(bool(step["expected_speaker"]) for step in script) >= 36
    assert any(step["family"] == "move" for step in script)
    assert not {step["input"] for step in script if step.get("corpus_id")} - {
        item["input"] for item in narration.intent.load_items("dev")}
    assert held  # the held-out inputs exist and are never drawn


def test_metrics_report_each_denominator():
    def record(**checks):
        base = {"state_contradictions": [], "engine_validation_failed": False, "correct_speaker": None,
                "private_leak": False, "near_duplicate": False, "empty": False}
        return {"http": 200, "expected_speaker": "npc:x" if checks.get("correct_speaker") is not None else None,
                "checks": base | checks}

    records = [record(correct_speaker=True), record(correct_speaker=False), record(near_duplicate=True),
               {"http": 500, "expected_speaker": None, "checks": {}}]
    metrics = narration.report_metrics(records)
    assert metrics["correct_speaker"]["n"] == 2 and metrics["correct_speaker"]["successes"] == 1
    assert metrics["near_duplicate"]["n"] == 3 and metrics["near_duplicate"]["successes"] == 1
    assert metrics["turn_failures"]["successes"] == 1 and metrics["judge_grounded"]["n"] == 0
