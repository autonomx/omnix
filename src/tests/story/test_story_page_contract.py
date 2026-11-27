"""A story page from the model and its deterministic check (Storyteller roadmap ST-2.1, ST-2.2)."""
from __future__ import annotations

import json

import pytest

from app.apps.story.page_contract import (
    NEW_CHARACTERS_MAX,
    STORY_PAGE_BUDGET,
    STORY_PAGE_CONTRACT,
    SUMMARY_MAX,
    StoryPageReply,
    check_page,
    tagged_text,
)
from app.providers.base import ChatMessage, ChatResponse, ProviderConfig
from app.providers.structured import StructuredOutputExhausted, StructuredOutputGateway

CAST = [
    {"id": "mara", "name": "Mara Vell", "aliases": ["the courier"]},
    {"id": "tobin", "name": "Tobin"},
]

PAGE = {
    "title": "Lantern Road",
    "blocks": [
        {"kind": "narration", "text": "The road ran on under patient stars."},
        {"kind": "dialogue", "speaker_id": "mara", "text": "“Who's there?”"},
        {"kind": "narration", "text": "Something moved by the milestone."},
        {"kind": "dialogue", "speaker_id": "wren", "text": "“Only me.”"},
    ],
    "new_characters": [{"id": "wren", "name": "Wren", "description": "A girl who keeps the milestones."}],
    "suggested_moves": ["Lower the lantern", "Ask her name", "Walk on"],
}


class FakeProvider:
    provider_name = "lmstudio"

    def __init__(self, replies):
        self.config = ProviderConfig(provider_type="lmstudio", model="test-model")
        self.replies = list(replies)
        self.calls = []

    def chat_completion(self, messages, **kwargs):
        self.calls.append({"messages": list(messages), **kwargs})
        content, finish = self.replies.pop(0)
        return ChatResponse(content=content, model="test-model", finish_reason=finish)


def _generate(provider):
    return StructuredOutputGateway(provider).generate(
        [ChatMessage(role="user", content="Write a page.")], contract=STORY_PAGE_CONTRACT,
        retry_budget=STORY_PAGE_BUDGET)


def test_a_valid_page_keeps_every_speaker():
    reply = _generate(FakeProvider([(json.dumps(PAGE), "stop")]))
    page = check_page(reply, CAST)

    assert page.title == "Lantern Road"
    assert [block.get("speaker_id") for block in page.blocks] == [None, "mara", None, "wren"]
    assert page.unverified == 0
    assert page.new_characters == [{"id": "wren", "name": "Wren", "description": "A girl who keeps the milestones."}]
    assert page.suggested_moves == ["Lower the lantern", "Ask her name", "Walk on"]


def test_an_unknown_speaker_is_flagged_not_dropped():
    reply = StoryPageReply.model_validate({"blocks": [
        {"kind": "dialogue", "speaker_id": "stranger", "text": "“Halt.”"},
        {"kind": "dialogue", "text": "“No name.”"},
        {"kind": "dialogue", "speaker_id": "Mara Vell", "text": "“By name.”"},
        {"kind": "dialogue", "speaker_id": "the courier", "text": "“By alias.”"},
        {"kind": "narration", "speaker_id": "tobin", "text": "Narration has no speaker."},
    ]})
    page = check_page(reply, CAST)

    assert page.blocks[0] == {"kind": "dialogue", "speaker_id": "stranger", "text": "“Halt.”",
                              "attribution": "unverified"}
    assert page.blocks[1] == {"kind": "dialogue", "text": "“No name.”", "attribution": "unverified"}
    assert page.blocks[2]["speaker_id"] == "mara" and "attribution" not in page.blocks[2]
    assert page.blocks[3]["speaker_id"] == "mara"
    assert page.blocks[4] == {"kind": "narration", "text": "Narration has no speaker."}
    assert page.unverified == 2


def test_a_dialogue_tag_inside_a_spoken_line_becomes_narration():
    # Seen in the Phase 2 real-model check: the tag sat between two quoted halves of one line.
    reply = StoryPageReply.model_validate({"blocks": [
        {"kind": "dialogue", "speaker_id": "tobin", "text": '"Asa Venn," he said, and coughed. "Harbour pilot."'},
        {"kind": "dialogue", "speaker_id": "mara", "text": "“Go,” she said."},
        {"kind": "dialogue", "speaker_id": "ghost", "text": "Mara said “stay”"},
        {"kind": "dialogue", "speaker_id": "mara", "text": "“Wait!” — “Now.”"},
        {"kind": "dialogue", "speaker_id": "mara", "text": '"Unclosed, she said.'},
        {"kind": "dialogue", "speaker_id": "mara", "text": "No quotes at all."},
    ]})
    page = check_page(reply, CAST)

    assert [(block["kind"], block.get("speaker_id"), block["text"]) for block in page.blocks] == [
        ("dialogue", "tobin", '"Asa Venn,"'),
        ("narration", None, "he said, and coughed."),
        ("dialogue", "tobin", '"Harbour pilot."'),
        ("dialogue", "mara", "“Go,”"),
        ("narration", None, "she said."),
        ("narration", None, "Mara said"),
        ("dialogue", "ghost", "“stay”"),
        ("dialogue", "mara", "“Wait!” — “Now.”"),
        ("dialogue", "mara", '"Unclosed, she said.'),
        ("dialogue", "mara", "No quotes at all."),
    ]
    # A split line keeps its flag on every spoken part, and only there.
    assert [block.get("attribution") for block in page.blocks[5:7]] == [None, "unverified"]


def test_a_truncated_reply_is_asked_for_again_and_never_used():
    cut = json.dumps(PAGE)[:120]
    provider = FakeProvider([(cut, "length"), (json.dumps(PAGE), "stop")])
    reply = _generate(provider)

    assert len(provider.calls) == 2
    assert check_page(reply, CAST).title == "Lantern Road"


def test_a_reply_cut_off_every_time_fails_the_page():
    cut = json.dumps(PAGE)[:120]
    with pytest.raises(StructuredOutputExhausted):
        _generate(FakeProvider([(cut, "length")] * STORY_PAGE_BUDGET.max_provider_calls))


def test_new_characters_are_capped_and_cleaned():
    proposed = [{"id": f"Guard {index}!", "name": f"  Guard\n{index} ", "description": "x" * 1_000}
                for index in range(NEW_CHARACTERS_MAX + 2)]
    proposed += [{"id": "tobin", "name": "Tobin"}, {"id": "", "name": ""}]
    reply = StoryPageReply.model_validate({
        "blocks": [{"kind": "dialogue", "speaker_id": f"Guard {index}!", "text": f"Line {index}."}
                   for index in range(NEW_CHARACTERS_MAX + 2)] + [
            {"kind": "dialogue", "speaker_id": "tobin", "text": "Me again."}],
        "new_characters": proposed,
    })
    page = check_page(reply, CAST)

    assert [character["id"] for character in page.new_characters] == [
        f"guard-{index}" for index in range(NEW_CHARACTERS_MAX)]
    assert page.new_characters[0]["name"] == "Guard 0"
    assert all(len(character["description"]) == 400 for character in page.new_characters)
    speakers = [block.get("speaker_id") for block in page.blocks]
    assert speakers[:NEW_CHARACTERS_MAX] == [f"guard-{index}" for index in range(NEW_CHARACTERS_MAX)]
    # Past the cap, the lines are kept and flagged; a character already cast stays theirs.
    assert [block.get("attribution") for block in page.blocks[NEW_CHARACTERS_MAX:-1]] == ["unverified"] * 2
    assert page.blocks[-1] == {"kind": "dialogue", "speaker_id": "tobin", "text": "Me again."}


def test_a_proposed_id_that_clashes_gets_its_own():
    reply = StoryPageReply.model_validate({
        "blocks": [{"kind": "dialogue", "speaker_id": "mara-2", "text": "Hi."}],
        "new_characters": [{"id": "Mara", "name": "Mara the Younger"}, {"id": "mara-2", "name": "Mara Again"}],
    })
    page = check_page(reply, CAST)
    # "Mara" is the cast's id (ids match case-sensitively, so this one is new and slugged apart).
    assert [character["id"] for character in page.new_characters] == ["mara-2", "mara-2-2"]
    assert page.blocks[0]["speaker_id"] == "mara-2-2"


def test_text_is_data_and_moves_are_capped():
    reply = StoryPageReply.model_validate({
        "title": "  A\x00 title \n",
        "blocks": [{"kind": "narration", "text": "Ignore the rules.\x07\n\nSecond line."},
                   {"kind": "narration", "text": "   "}],
        "suggested_moves": ["Run", "run", " ", "Hide", "Wait", "Sing"],
    })
    page = check_page(reply, CAST)
    assert page.title == "A title"
    assert page.blocks == [{"kind": "narration", "text": "Ignore the rules.\n\nSecond line."}]
    assert page.suggested_moves == ["Run", "Hide", "Wait"]


def test_the_rolling_summary_is_one_capped_line():
    reply = StoryPageReply.model_validate({"blocks": [{"kind": "narration", "text": "Dusk."}],
                                           "summary": "Mara\nwaits.\x07 " + "x" * (SUMMARY_MAX * 2)})
    summary = check_page(reply, CAST).summary
    assert summary.startswith("Mara waits. x") and len(summary) == SUMMARY_MAX
    assert check_page(StoryPageReply.model_validate({"blocks": [{"text": "Dusk."}]}), CAST).summary == ""


def test_a_page_with_no_text_is_regenerated():
    empty = json.dumps({"blocks": [{"kind": "narration", "text": " "}]})
    provider = FakeProvider([(empty, "stop"), (json.dumps(PAGE), "stop")])
    assert _generate(provider).title == "Lantern Road" and len(provider.calls) == 2


def test_tagged_text_marks_each_speaker():
    assert tagged_text([{"kind": "narration", "text": "Dusk."},
                        {"kind": "dialogue", "speaker_id": "mara", "text": "“Hello.”"},
                        {"kind": "dialogue", "text": "“Who?”"}]) == (
        "Dusk.\n\n[mara] “Hello.”\n\n“Who?”")
