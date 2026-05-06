from tests.rpg.autoplay.parallel_pipeline import _extract_json_object_from_text


def test_extract_json_object_from_plain_json():
    parsed = _extract_json_object_from_text('{"semantic_intent_candidates": [{"intent": "inspect"}]}')
    assert parsed["semantic_intent_candidates"][0]["intent"] == "inspect"


def test_extract_json_object_from_fenced_json():
    parsed = _extract_json_object_from_text(
        '```json\n{"future_hook_candidates": [{"summary": "Bran reacts later."}]}\n```'
    )
    assert parsed["future_hook_candidates"][0]["summary"] == "Bran reacts later."


def test_extract_json_object_from_preamble_text():
    parsed = _extract_json_object_from_text(
        'Here is the JSON:\n{"memory_candidates": [{"owner": "bran", "summary": "Asked about witness."}]}'
    )
    assert parsed["memory_candidates"][0]["owner"] == "bran"


def test_extract_json_object_respects_nested_braces_in_strings():
    parsed = _extract_json_object_from_text(
        'prefix {"future_hook_candidates": [{"summary": "A note says {sealed}."}]} suffix'
    )
    assert parsed["future_hook_candidates"][0]["summary"] == "A note says {sealed}."