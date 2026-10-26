"""A person's line is shown as the model writes it, and its prompt carries no secret (roadmap §7 Q-12)."""
from __future__ import annotations

from app.apps.rpg.rules.dialogue.plan import DialoguePlan
from app.apps.rpg.session.turn import dialogue


def _plan() -> DialoguePlan:
    return DialoguePlan(speaker_id="npc:liora-fen", speaker_name="Liora Fen", secrets=("the shrine word is Heronglass",))


def test_the_line_streams_to_the_turns_draft_and_its_prompt_has_no_secret(monkeypatch) -> None:
    from app.apps.rpg.foundation import llm_app_gateway

    prompts: list[str] = []
    drafts: list[str] = []

    class _Gateway:
        def generate_stream(self, prompt, **_kwargs):
            prompts.append(prompt)
            yield from ({"text": part} for part in ("Stay ", "close, ", "Earthborn."))

        def generate(self, prompt, **_kwargs):  # pragma: no cover - the streamed path is the one taken
            raise AssertionError("a turn the play screen follows streams its line")

    monkeypatch.setattr(llm_app_gateway, "build_app_llm_gateway", lambda: _Gateway())
    monkeypatch.setattr(dialogue, "narration_draft_active", lambda: True)
    monkeypatch.setattr(dialogue, "publish_narration_draft", drafts.append)

    assert dialogue._write_line(_plan(), [], "Liora, is it safe?") == "Stay close, Earthborn."
    assert drafts[0] == 'Liora Fen: "Stay"' and drafts[-1] == 'Liora Fen: "Stay close, Earthborn."'
    assert "Heronglass" not in prompts[0] and "must_never_reveal" not in prompts[0]


def test_a_turn_no_one_follows_writes_the_line_in_one_call(monkeypatch) -> None:
    from app.apps.rpg.foundation import llm_app_gateway

    class _Gateway:
        def generate(self, prompt, **_kwargs):
            return "Stay close."

    monkeypatch.setattr(llm_app_gateway, "build_app_llm_gateway", lambda: _Gateway())
    monkeypatch.setattr(dialogue, "narration_draft_active", lambda: False)
    assert dialogue._write_line(_plan(), [], "Liora?") == "Stay close."



def test_what_repeats_a_secret_is_left_out_of_what_the_writer_is_told() -> None:
    """Review 4: dropping ``must_never_reveal`` left an author's description or goal that repeats a secret in the
    prompt, now shown as it streams."""
    from app.apps.rpg.rules.dialogue.plan import build_plan

    simulation = {"world_model": {"npcs": {"npc:liora": {
        "name": "Liora Fen", "role": "gatewarden",
        "description": "A foxkin gatewarden of the grove. She knows the shrine word is Heronglass. She laughs easily.",
        "goals": ["keep the shrine word Heronglass from the Synod", "find the lost Earthborn"],
        "secrets": ["the shrine word is Heronglass"]}}},
        "present_npc_state": {"present_npc_ids": ["npc:liora"]}}
    plan = build_plan(simulation, "npc:liora", "Liora, what do you guard?")
    told = str(plan.context())
    assert "Heronglass" not in told
    assert "A foxkin gatewarden of the grove." in plan.background and "She laughs easily." in plan.background
    assert plan.goals == ("find the lost Earthborn",)


def test_the_streamed_line_has_the_lines_own_limits(monkeypatch) -> None:
    from app.apps.rpg.foundation import llm_app_gateway

    asked: list[dict] = []

    class _Gateway:
        def generate_stream(self, prompt, **kwargs):
            asked.append(kwargs)
            yield {"text": "Stay close."}

    monkeypatch.setattr(llm_app_gateway, "build_app_llm_gateway", lambda: _Gateway())
    monkeypatch.setattr(dialogue, "narration_draft_active", lambda: True)
    monkeypatch.setattr(dialogue, "publish_narration_draft", lambda text: None)
    dialogue._write_line(_plan(), [], "Liora?")
    assert asked[0]["timeout_s"] == dialogue.LINE_TIMEOUT_SECONDS
    assert asked[0]["provider_options"]["max_tokens"] == 90
    assert asked[0]["provider_options"]["chat_template_kwargs"] == {"enable_thinking": False}
