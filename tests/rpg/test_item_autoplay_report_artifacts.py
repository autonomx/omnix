import json
import zipfile
from pathlib import Path

from app.rpg.survival_report_artifacts import (
    ITEM_AUTOPLAY_COVERAGE_JSON_NAME,
    append_survival_report_artifacts_to_zip,
    attach_survival_artifact_manifest,
    write_survival_report_artifacts,
)


def _item_state() -> dict:
    targets = [
        "diagnostics",
        "pickup",
        "use_effect",
        "recipe_discovery",
        "crafting",
        "merchant",
        "modification",
        "combat",
        "maintenance",
        "report",
    ]
    traces = [
        {"coverage_target": target, "event": f"item_{target}", "turn": index * 10}
        for index, target in enumerate(targets, start=1)
    ]
    return {
        "current_turn": 100,
        "turn_count": 100,
        "player": {
            "inventory": [
                {
                    "id": "healing_potion",
                    "name": "Healing Potion",
                    "quantity": 1,
                    "type": "consumable",
                    "stackable": True,
                },
                {
                    "id": "iron_ore",
                    "name": "Iron Ore",
                    "quantity": 2,
                    "type": "material",
                    "material_id": "iron_ore",
                    "stackable": True,
                },
            ]
        },
        "crafting": {"known_recipes": ["iron_dagger"]},
        "mechanics": {
            "item_traces": traces,
            "pickup_traces": [traces[1]],
            "item_use_traces": [traces[2]],
            "crafting_traces": [traces[4]],
            "market_traces": [traces[5]],
            "modification_traces": [traces[6]],
            "item_combat_traces": [traces[7]],
            "item_diagnostic_traces": [traces[0]],
        },
    }


def test_survival_artifacts_include_item_autoplay_coverage(tmp_path: Path) -> None:
    rows = [
        {
            "turn_index": 100,
            "turn_result": {"ok": True, "simulation_state": _item_state()},
        }
    ]

    result = write_survival_report_artifacts(tmp_path, rows)

    item_json_path = Path(result["item_coverage_json_path"])
    assert item_json_path.exists()
    item_payload = json.loads(item_json_path.read_text(encoding="utf-8"))
    assert item_payload["state_found"] is True
    assert item_payload["latest_report"]["ok"] is True
    assert item_payload["endurance_plan"]["summary"]["final_turn"] == 100
    assert item_payload["endurance_progress"]["ok"] is True
    assert {row["label"] for row in item_payload["latest_rows"]} >= {"Coverage score", "Scenario steps"}

    manifest = attach_survival_artifact_manifest({}, result)
    assert manifest["item_autoplay_coverage_json"].endswith(ITEM_AUTOPLAY_COVERAGE_JSON_NAME)
    assert manifest["item_endurance_progress"]["ok"] is True


def test_item_autoplay_coverage_is_appended_to_zip(tmp_path: Path) -> None:
    rows = [
        {
            "turn_index": 100,
            "turn_result": {"ok": True, "simulation_state": _item_state()},
        }
    ]
    zip_path = tmp_path / "autoplay-campaign-results.zip"

    result = append_survival_report_artifacts_to_zip(zip_path, rows, prefix="survival")

    assert "survival/item-autoplay-coverage.json" in result["zip_members"]
    assert "survival/item-autoplay-coverage.html" in result["zip_members"]
    with zipfile.ZipFile(zip_path, "r") as zf:
        item_payload = json.loads(zf.read("survival/item-autoplay-coverage.json").decode("utf-8"))
    assert item_payload["latest_report"]["ok"] is True
    assert item_payload["endurance_progress"]["ok"] is True
