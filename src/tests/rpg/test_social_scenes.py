from __future__ import annotations

from app.rpg.social_scenes import (
    SocialSpeakRequest,
    SocialThread,
    apply_speak_decision,
    build_memory_hook,
    decide_npc_speaks,
    social_scene_report,
)


def test_directly_addressed_npc_can_speak() -> None:
    thread = SocialThread("thread-1", "directed", ("bran", "player"))
    decision = decide_npc_speaks(thread, SocialSpeakRequest("bran", "thread-1", directly_addressed=True))

    assert decision.allowed is True
    assert decision.reason == "directly_addressed"


def test_ambient_budget_blocks_idle_speech() -> None:
    thread = SocialThread("thread-1", "ambient", ("bran", "elara"), ambient_budget=0)
    decision = decide_npc_speaks(thread, SocialSpeakRequest("bran", "thread-1"))

    assert decision.allowed is False
    assert decision.reason == "ambient_budget_empty"


def test_repeat_speaker_is_blocked_unless_addressed() -> None:
    thread = SocialThread("thread-1", "group", ("bran", "elara"), last_speaker_id="bran")
    blocked = decide_npc_speaks(thread, SocialSpeakRequest("bran", "thread-1"))
    allowed = decide_npc_speaks(thread, SocialSpeakRequest("bran", "thread-1", directly_addressed=True))

    assert blocked.reason == "repeat_speaker_blocked"
    assert allowed.allowed is True


def test_apply_decision_updates_last_speaker_and_ambient_budget() -> None:
    thread = SocialThread("thread-1", "ambient", ("bran",), ambient_budget=2)
    decision = decide_npc_speaks(thread, SocialSpeakRequest("bran", "thread-1"))
    updated = apply_speak_decision(thread, decision)

    assert updated.last_speaker_id == "bran"
    assert updated.ambient_budget == 1


def test_memory_hook_is_deterministic_and_sorted() -> None:
    hook = build_memory_hook("promise", source_event_id="event-7", npc_ids=("elara", "bran", "bran"), fact="Player promised help.")

    assert hook.hook_id == "social:event-7:promise"
    assert hook.npc_ids == ("bran", "elara")
    assert hook.as_dict()["kind"] == "promise"


def test_social_scene_report_is_payload_friendly() -> None:
    thread = SocialThread("thread-1", "negotiation", ("player", "elara"), ambient_budget=1)
    decision = decide_npc_speaks(thread, SocialSpeakRequest("elara", "thread-1", urgent_reaction=True))
    payload = social_scene_report(thread, [decision])

    assert payload["thread_id"] == "thread-1"
    assert payload["kind"] == "negotiation"
    assert payload["decisions"][0]["reason"] == "urgent_reaction"
