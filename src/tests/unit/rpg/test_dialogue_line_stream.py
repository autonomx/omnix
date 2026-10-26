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


def test_the_plan_tells_where_the_heros_quest_goes_on() -> None:
    """The playtest: asked how to mend the phone, Brindle wanted "aether-coil wire"; the quest goes on at the
    Moonroot Ruins. The plan carries the hero's quests the speaker bears on, and where each goes on."""
    from app.apps.rpg.rules.dialogue.plan import build_plan

    simulation = {
        "world_model": {"npcs": {"npc:brindle": {"name": "Brindle Gearwing", "role": "relic mechanic",
                                                 "location_id": "location:village"},
                                 "npc:rhea": {"name": "Rhea Sunward", "role": "captain", "location_id": "location:pass"}},
                        "locations": {"location:village": {"name": "Starfall Village"},
                                      "location:ruins": {"name": "Moonroot Ruins"}}},
        "present_npc_state": {"present_npc_ids": ["npc:brindle", "npc:rhea"]},
        "quest_state": {"quests": [{"quest_id": "quest:phone", "title": "Voices in the Phone", "status": "active",
                                    "objective": "Repair your phone", "visited_locations": ["location:village"],
                                    "locations": ["location:village", "location:ruins"]}]},
    }
    told = build_plan(simulation, "npc:brindle", "What would you need to fix it?").context()
    assert told["heros_quests"] == [{"title": "Voices in the Phone", "objective": "Repair your phone",
                                     "goes_on_at": ["Moonroot Ruins"]}]
    assert "heros_quests" not in build_plan(simulation, "npc:rhea", "Any news?").context()  # it is not hers


def test_someone_who_hands_out_work_offers_a_quest_no_one_gave() -> None:
    """The playtest: the Wayfarers' Guild's registrar, asked for contracts, had none, though the roads' quest was open."""
    from app.apps.rpg.rules.dialogue.plan import build_plan

    simulation = {
        "world_model": {"npcs": {"npc:miri": {"name": "Miri Kestrel", "role": "guild registrar",
                                              "location_id": "location:guild"},
                                 "npc:orik": {"name": "Orik", "role": "innkeeper", "location_id": "location:guild"}}},
        "present_npc_state": {"present_npc_ids": ["npc:miri", "npc:orik"]},
        "quest_state": {"quests": [
            {"quest_id": "quest:wolves", "title": "Echo beasts on the March roads", "status": "available",
             "objective": "Defeat 3 Echo Wolves", "locations": ["location:pass"]},
            {"quest_id": "quest:first", "title": "First Night", "status": "completed", "locations": ["location:guild"]}]},
    }
    miri = build_plan(simulation, "npc:miri", "What contracts does the guild have for me?")
    assert miri.quest_offer["title"] == "Echo beasts on the March roads"
    assert {"title": "First Night", "done": True} in [dict(quest) for quest in miri.hero_quests]
    assert build_plan(simulation, "npc:orik", "Any work for me?").quest_offer == {}  # an innkeeper hands out none


def test_a_worlds_quest_not_in_the_log_is_offered_and_joins_it_and_a_finale_comes_last() -> None:
    """The playtest: three of Aurelia's six quests could never be offered (only the opening's were in the log), and a
    newcomer asking for work was offered the finale."""
    from app.apps.rpg.foundation.state.reducer import reduce
    from app.apps.rpg.rules.dialogue.plan import build_plan, plan_changes

    engine = {"id": "quest:engine", "quest_id": "quest:engine", "title": "The Princess and the Engine",
              "objective": "Help restore the royal engine", "locations": ["location:guild"], "tier": "political"}
    simulation = {
        "world_model": {"npcs": {"npc:seraphine": {"name": "Seraphine", "role": "princess and engineer",
                                                   "location_id": "location:guild"}},
                        "quests": {"quest:engine": engine}},
        "present_npc_state": {"present_npc_ids": ["npc:seraphine"]},
        "quest_state": {"quests": [{"quest_id": "quest:finale", "title": "The Hollow Meridian", "status": "available",
                                    "tier": "finale", "locations": ["location:guild"]}]},
    }
    plan = build_plan(simulation, "npc:seraphine", "Is there any work I could help you with?")
    assert plan.quest_offer["title"] == "The Princess and the Engine"
    document, _ = reduce({"manifest": {}, "state": {}, "simulation_state": simulation}, plan_changes(plan))
    rows = {row["quest_id"]: row for row in document["simulation_state"]["quest_state"]["quests"]}
    assert rows["quest:engine"]["status"] == "available" and rows["quest:engine"]["offered_by"] == "npc:seraphine"


def test_a_seller_asked_what_is_for_sale_names_their_wares_and_a_hunt_goes_on_in_the_wild() -> None:
    """The playtest: Brindle, asked "what do you have for sale?", had nothing priced; the captain, asked where the
    echo wolves are, could only say "the March roads"."""
    from app.apps.rpg.rules.dialogue.plan import build_plan

    simulation = {
        "world_model": {
            "npcs": {"npc:brindle": {"name": "Brindle", "role": "relic mechanic", "location_id": "location:village"}},
            "locations": {"location:village": {"name": "Starfall Village"}, "location:far": {"name": "Cinderhold"},
                          "location:pass": {"name": "Skybridge Pass"}},
            "routes": [{"from": "location:village", "to": "location:pass"}, {"from": "location:pass", "to": "location:far"}],
            "offers": {"npc:brindle": [{"label": "Healing Potion", "price": {"silver": 3}}]}},
        "present_npc_state": {"present_npc_ids": ["npc:brindle"]},
        "quest_state": {"quests": [{"quest_id": "quest:wolves", "title": "Echo beasts", "status": "active",
                                    "objective": "Defeat 3 Echo Wolves", "offered_by": "npc:brindle"}]},
        "party_state": {},
    }
    simulation["player_state"] = {"location_id": "location:village",
                                  "party_state": {"companions": [{"npc_id": "npc:brindle"}]}}
    plan = build_plan(simulation, "npc:brindle", "What do you have for sale?")
    assert plan.wares == ("Healing Potion for 3 silver",)
    # No one lives there, so creatures are met there; the nearest by road first (not Cinderhold, two roads off).
    assert plan.hero_quests[0]["goes_on_at"] == ["Skybridge Pass", "Cinderhold"]
