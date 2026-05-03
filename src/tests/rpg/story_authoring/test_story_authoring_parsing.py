from app.rpg.story_authoring.parsing import parse_story_authoring_json


def test_parse_story_authoring_json_accepts_object_string():
    result = parse_story_authoring_json('{"proposal_version":"story_proposal_v1"}')

    assert result["ok"] is True
    assert result["proposal"]["proposal_version"] == "story_proposal_v1"


def test_parse_story_authoring_json_strips_code_fence():
    result = parse_story_authoring_json('```json\n{"proposal_type":"story_pack"}\n```')

    assert result["ok"] is True
    assert result["proposal"]["proposal_type"] == "story_pack"


def test_parse_story_authoring_json_rejects_non_object():
    result = parse_story_authoring_json('["bad"]')

    assert result["ok"] is False
    assert result["error"].startswith("json_root_not_object")


def test_parse_story_authoring_json_rejects_invalid_json():
    result = parse_story_authoring_json("{bad json")

    assert result["ok"] is False
    assert result["error"].startswith("invalid_json")