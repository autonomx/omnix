"""Build the RPG intent corpus v1 (RQ-0.4): 2,000 labelled player inputs over three worlds.

This wrote ``resources/benchmarks/rpg/intent_corpus/`` once, on 2026-10-23. The JSONL files it wrote are the
corpus; this script is kept as the record of how the inputs and their labels were made. It does not overwrite a
frozen held-out file: ``--force`` is required, and the evaluation harness (``scripts/rpg_intent_eval.py``) fails
when the held-out file's SHA-256 changes, so a rebuild is an explicit, reviewed re-freeze.

Labels are produced by construction: every template states the action family, which slot is the target entity,
and whether the correct handling changes campaign state. The label policy is in the corpus README. Inputs mix
plain commands, questions, hypotheticals, negations, multi-step commands, typos and the substring traps the
evaluation found ("useful", "forest", "white", "current", "rest" inside words). Labels are model-made and pending
the owner's spot check.

    python scripts/rpg_intent_corpus_build.py [--force]
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import random
import re
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "resources/benchmarks/rpg/intent_corpus"
SEED = 20261023
SIZES = {"aurelia": 667, "vesper-9": 667, "starter": 666}
DEV_SIZE = 800
HELD_OUT_SIZE = 1200
FAMILIES = (
    "look", "inspect", "move", "talk", "ask", "decline", "buy", "sell", "attack", "flee", "defend", "take", "drop",
    "give", "use_item", "equip", "unequip", "manipulate", "rest", "wait", "quest", "practice", "party", "status",
    "clarify",
)

# --- the worlds -----------------------------------------------------------------------------------------------------
# Each entity: id -> (kind, names the player may use, ids the engine may report for it).
ENTITIES: dict[str, dict[str, tuple[str, list[str], list[str]]]] = {
    "aurelia": {
        "npc:liora-fen": ("person", ["Liora", "Liora Fen", "the guide", "my guide"], []),
        "npc:orik-stonewake": ("person", ["Orik", "Orik Stonewake", "the innkeeper", "Master Stonewake"], []),
        "npc:brindle-gearwing": ("person", ["Brindle", "Brindle Gearwing", "the mechanic", "the relic merchant"], []),
        "npc:captain-rhea-sunward": ("person", ["Captain Rhea", "Rhea", "Captain Sunward", "the guard captain"], []),
        "npc:miri-kestrel": ("person", ["Miri", "Miri Kestrel", "the registrar"], []),
        "npc:seraphine-valecourt": ("person", ["Seraphine", "Princess Seraphine", "the princess"], []),
        "npc:elyra-moonroot": ("person", ["Elyra", "Elyra Moonroot", "the archivist"], []),
        "npc:vael-ardyn": ("person", ["Vael", "Vael Ardyn", "the demon general"], []),
        "npc:archon-malrec": ("person", ["Malrec", "Archon Malrec", "the Archon"], []),
        "npc:naia-of-the-open-hand": ("person", ["Naia", "Naia of the Open Hand", "the saint of the Road Between"], []),
        "location:aurelia:arrival-grove": ("place", ["Starfall Grove", "the grove", "the arrival grove"], []),
        "location:aurelia:starfall-village": ("place", ["Starfall Village", "the village"], []),
        "location:aurelia:wayfarer-guild": ("place", ["the Wayfarers' Guild", "the guild", "the guild hall"], []),
        "location:aurelia:skybridge-pass": ("place", ["Skybridge Pass", "the pass", "the mountain pass"], []),
        "location:aurelia:moonroot-ruins": ("place", ["Moonroot Ruins", "the ruins"], []),
        "location:aurelia:hollow-meridian": ("place", ["the Hollow Meridian"], []),
        "location:aurelia:valecourt": ("place", ["Valecourt", "the capital"], []),
        "location:aurelia:cinderhold": ("place", ["Cinderhold"], []),
        "iron_dagger": ("item", ["iron dagger", "dagger", "knife"], []),
        "travel_cloak": ("item", ["travel cloak", "cloak"], []),
        "item:gateborn-compass": ("item", ["Gateborn Compass", "compass"], []),
        "item:lantern-bread": ("item", ["lantern bread", "bread"], ["lantern_bread"]),
        "item:wayfarer-sigil": ("item", ["Wayfarer Sigil", "sigil"], []),
        "item:moonroot-key": ("item", ["Moonroot Key"], []),
        "item:ashen-oathblade": ("item", ["Ashen Oathblade", "oathblade"], []),
        "npc:orik-stonewake:night": ("offer", ["a room", "a room for the night", "a bed for the night", "lodging", "a night's lodging"], []),
        "npc:orik-stonewake:meal": ("offer", ["a hot meal", "a meal", "supper"], []),
        "npc:orik-stonewake:drink": ("offer", ["a drink", "something to drink"], []),
        "npc:brindle-gearwing:lantern-bread": ("offer", ["a loaf of lantern bread", "some lantern bread"], []),
        "npc:brindle-gearwing:healing-potion": ("offer", ["a healing potion", "a potion", "the healing potion"], ["healing_potion"]),
        "npc:brindle-gearwing:repair": ("offer", ["a gear repair", "repairs for my gear"], []),
        "npc:miri-kestrel:information": ("offer", ["the local news", "news"], []),
        "creature:echo-wolf": ("creature", ["echo wolf", "the echo wolf", "the wolf"], []),
        "creature:sky-manta": ("creature", ["sky manta", "the sky manta"], []),
        "creature:glass-wight": ("creature", ["glass wight", "the glass wight"], []),
        "creature:rootbound-knight": ("creature", ["rootbound knight", "the rootbound knight"], []),
        "quest:first-night-in-aurelia": ("quest", ["First Night in Aurelia"], []),
        "quest:voices-in-the-phone": ("quest", ["Voices in the Phone"], []),
        "quest:hollow-meridian": ("quest", ["The Hollow Meridian quest"], []),
    },
    "vesper-9": {
        "ent:actors:juno-rask": ("person", ["Juno", "Juno Rask", "the union leader"], []),
        "ent:actors:nadi-vale": ("person", ["Inspector Vale", "Nadi Vale", "Inspector Nadi Vale", "the inspector"], []),
        "ent:actors:selene-kade": ("person", ["Dr. Kade", "Selene Kade", "Dr. Selene Kade", "the doctor"], []),
        "ent:actors:mara-vey": ("person", ["Mara", "Mara Vey", "the courier"], []),
        "ent:actors:ilya-sorn": ("person", ["Ilya", "Ilya Sorn"], []),
        "ent:actors:brother-static": ("person", ["Brother Static"], []),
        "ent:actors:oren-pike": ("person", ["Oren", "Oren Pike", "the fixer"], []),
        "ent:actors:tamsin-rho": ("person", ["Tamsin", "Tamsin Rho"], []),
        "ent:places:tidebreak-docks": ("place", ["Tidebreak Docks", "the docks"], []),
        "ent:places:saint-voltage-market": ("place", ["Saint Voltage Night Market", "the night market", "Saint Voltage"], []),
        "ent:places:halcyon-memory-clinic": ("place", ["Halcyon Memory Clinic", "the memory clinic", "the clinic"], []),
        "ent:places:black-rain-station": ("place", ["Black Rain Station", "the station"], []),
        "ent:places:undertone": ("place", ["the Undertone", "the club"], []),
        "ent:places:meridian-stack-77": ("place", ["Meridian Stack 77", "Stack 77"], []),
        "ent:places:null-chapel": ("place", ["the Null Chapel", "the chapel"], []),
        "iron_dagger": ("item", ["iron dagger", "dagger", "knife"], []),
        "travel_cloak": ("item", ["travel cloak", "cloak"], []),
        "ent:equipment_vehicles:kestrel-m12": ("item", ["Kestrel M-12", "smartpistol", "Kestrel M-12 Smartpistol"], []),
        "ent:equipment_vehicles:coilwire-blade": ("item", ["coilwire monoblade", "monoblade"], []),
        "ent:equipment_vehicles:veiljack-deck": ("item", ["Veiljack deck", "field deck", "Veiljack Field Deck"], []),
        "ent:equipment_vehicles:rainrunner-bike": ("item", ["Rainrunner bike", "courier bike"], []),
        "ent:equipment_vehicles:hush-drone": ("item", ["Hush drone", "recon drone"], []),
        "ent:equipment_vehicles:identity-wafer": ("item", ["ghost identity wafer", "identity wafer"], []),
        "ent:equipment_vehicles:memory-coldcase": ("item", ["mnemonic coldcase", "coldcase"], []),
        "ent:equipment_vehicles:tidebreaker-exosuit": ("item", ["Tidebreaker exosuit", "exosuit"], []),
        "ent:threats:cerberus-squad": ("creature", ["Cerberus squad", "the Kestrel Cerberus Squad"], []),
        "ent:threats:debt-collectors": ("creature", ["debt collectors", "the licensed debt collectors"], []),
        "ent:threats:glass-wasps": ("creature", ["glass wasps"], []),
        "ent:groups:red-knives-union": ("group", ["the Red Knives", "the Red Knives Union", "the union"], []),
        "ent:groups:kestrel-dynamics": ("group", ["Kestrel Dynamics", "Kestrel"], []),
        "ent:groups:helix-meridian": ("group", ["Helix Meridian", "Helix"], []),
        "ent:networks:the-veil": ("group", ["the Veil"], []),
        "quest:opening:black-rain-rising": ("quest", ["Black Rain Rising"], []),
        "ent:quests:strikebreaker-protocol": ("quest", ["Strikebreaker Protocol"], []),
        "ent:quests:borrowed-face": ("quest", ["Borrowed Face"], []),
        "ent:quests:city-beneath-tide": ("quest", ["The City Beneath the Tide"], []),
    },
    "starter": {
        "npc:Bran": ("person", ["Bran", "the innkeeper", "the barkeep", "the bartender"], ["npc_innkeeper"]),
        "npc:Mira": ("person", ["Mira", "the server", "the serving girl"], []),
        "npc:Elara": ("person", ["Elara", "Elara the Merchant", "the merchant", "the trader"], ["npc_merchant"]),
        "npc:Aldric": ("person", ["Captain Aldric", "Aldric", "the guard captain"], ["npc_guard_captain", "npc:GuardCaptain"]),
        "location:rusty_flagon": ("place", ["the Rusty Flagon", "the tavern", "the inn"], ["loc_tavern", "rusty_flagon_tavern"]),
        "location:market": ("place", ["the market", "Market Square", "the market square"], ["loc_market"]),
        "location:old_road": ("place", ["the Old Road", "the old road"], []),
        "location:old_mill": ("place", ["the Old Mill", "the old mill"], []),
        "location:nearby_wilderness": ("place", ["the wilderness", "the wilds"], ["loc_forest"]),
        "iron_dagger": ("item", ["iron dagger", "dagger", "knife"], []),
        "travel_cloak": ("item", ["travel cloak", "cloak"], []),
        "trail_rations": ("item", ["trail rations", "rations", "a ration"], []),
        "torch": ("item", ["torch"], []),
        "bran_lodging_common_cot": ("offer", ["a cot in the common room", "the common room cot", "a cot"], []),
        "bran_lodging_private_room": ("offer", ["a private room", "the private room"], []),
        "bran_meal_stew": ("offer", ["a bowl of stew", "the hot stew", "some stew"], []),
        "bran_drink_ale": ("offer", ["a mug of ale", "an ale", "a pint of ale"], []),
        "bran_paid_rumor": ("offer", ["a rumor", "the local rumor"], []),
        "elara_torch": ("offer", ["a torch", "a new torch"], []),
        "elara_rope": ("offer", ["some rope", "a coil of rope", "rope"], []),
        "elara_basic_repair": ("offer", ["a gear repair", "a basic repair"], []),
        "creature:bandit": ("creature", ["bandit", "the bandit"], []),
        "creature:wolf": ("creature", ["wolf", "the wolf"], []),
        "tavern_rumor": ("quest", ["the rumor at the Rusty Flagon", "Rumor at the Rusty Flagon"], []),
    },
}
for world_entities in ENTITIES.values():
    for skill in ("swordsmanship", "archery", "magic", "stealth", "persuasion", "investigation", "defense",
                  "intimidation", "hacking", "firearms"):
        world_entities[f"skill:{skill}"] = ("skill", [skill], [skill])

# Scenes: where the player stands for an input, who is present, where they can go, what they can buy there.
SCENES: dict[str, dict[str, dict[str, Any]]] = {
    "aurelia": {
        "grove": {"location_id": "location:aurelia:arrival-grove", "setup": [],
                  "present": ["npc:liora-fen"], "exits": ["location:aurelia:starfall-village"],
                  "offers": [], "buyer": "", "outdoor": True,
                  "creatures": ["creature:echo-wolf", "creature:rootbound-knight"]},
        "village": {"location_id": "location:aurelia:starfall-village", "setup": ["go to Starfall Village"],
                    "present": ["npc:orik-stonewake", "npc:brindle-gearwing", "npc:captain-rhea-sunward"],
                    "exits": ["location:aurelia:arrival-grove", "location:aurelia:wayfarer-guild",
                              "location:aurelia:skybridge-pass"],
                    "offers": ["npc:orik-stonewake:night", "npc:orik-stonewake:meal", "npc:orik-stonewake:drink",
                               "npc:brindle-gearwing:lantern-bread", "npc:brindle-gearwing:healing-potion",
                               "npc:brindle-gearwing:repair"],
                    "buyer": "npc:brindle-gearwing", "outdoor": False, "creatures": []},
        "guild": {"location_id": "location:aurelia:wayfarer-guild",
                  "setup": ["go to Starfall Village", "go to the Wayfarers' Guild"],
                  "present": ["npc:miri-kestrel", "npc:seraphine-valecourt"],
                  "exits": ["location:aurelia:starfall-village"], "offers": ["npc:miri-kestrel:information"],
                  "buyer": "", "outdoor": False, "creatures": []},
    },
    "vesper-9": {
        "docks": {"location_id": "ent:places:tidebreak-docks", "setup": [],
                  "present": ["ent:actors:juno-rask", "ent:actors:nadi-vale", "ent:actors:selene-kade"],
                  "exits": ["ent:places:saint-voltage-market", "ent:places:black-rain-station",
                            "ent:places:halcyon-memory-clinic", "ent:places:undertone"],
                  "offers": [], "buyer": "", "outdoor": True, "creatures": []},
    },
    "starter": {
        "tavern": {"location_id": "location:rusty_flagon", "setup": [], "present": ["npc:Bran", "npc:Mira"],
                   "exits": ["location:market", "location:old_road"],
                   "offers": ["bran_lodging_common_cot", "bran_lodging_private_room", "bran_meal_stew",
                              "bran_drink_ale", "bran_paid_rumor"],
                   "buyer": "", "outdoor": False, "creatures": []},
        "market": {"location_id": "location:market", "setup": ["go outside"], "present": ["npc:Elara"],
                   "exits": ["location:rusty_flagon", "location:old_road"],
                   "offers": ["elara_torch", "elara_rope", "elara_basic_repair"],
                   "buyer": "npc:Elara", "outdoor": True, "creatures": []},
    },
}
# What the player carries at the opening, and which of it is eaten when used.
CARRIED = {
    "aurelia": ["iron_dagger", "travel_cloak", "item:gateborn-compass", "item:lantern-bread"],
    "vesper-9": ["iron_dagger", "travel_cloak"],
    "starter": ["iron_dagger", "travel_cloak", "trail_rations", "torch"],
}
FOOD = {"aurelia": ["item:lantern-bread"], "vesper-9": [], "starter": ["trail_rations"]}
EQUIPPED = ["iron_dagger", "travel_cloak"]
AVAILABLE_QUESTS = {"aurelia": ["quest:voices-in-the-phone", "quest:hollow-meridian"], "vesper-9": [], "starter": []}
ACTIVE_QUESTS = {"aurelia": ["quest:first-night-in-aurelia"], "vesper-9": ["quest:opening:black-rain-rising"],
                 "starter": ["tavern_rumor"]}
OTHER_QUESTS = {"aurelia": [], "vesper-9": ["ent:quests:strikebreaker-protocol", "ent:quests:borrowed-face",
                                             "ent:quests:city-beneath-tide"], "starter": []}
SKILLS = {"aurelia": ["swordsmanship", "archery", "magic", "stealth", "persuasion", "investigation"],
          "vesper-9": ["hacking", "firearms", "stealth", "persuasion", "intimidation", "investigation"],
          "starter": ["swordsmanship", "archery", "stealth", "persuasion", "defense", "investigation"]}
# Who can join the party when asked (the guide is the world's "first companion").
RECRUITS = {"aurelia": ["npc:liora-fen"], "vesper-9": [], "starter": []}
# Topics to ask about that are not entities of the catalog.
TOPICS = {
    "aurelia": ["the Meridian Gate", "Resonance magic", "Earthborn arrivals", "the blackout", "the way home",
                "the guild contracts", "the moonwell", "the quest board", "Echo Arts", "the cloud sea"],
    "vesper-9": ["the strike", "the seawall alarm", "the contraband container", "the missing pump controllers",
                 "the Civic Mesh", "memory theft", "the flood surge", "identity credit", "the Veil Collapse",
                 "the Choir of Moth"],
    "starter": ["the rumor", "the notice board", "the road north", "work around here", "the old mill",
                "bandits on the road", "the weather", "the town gate", "the hearth-side talk", "the king's guard"],
}
MONEY_OK = {"aurelia": True, "vesper-9": False, "starter": True}


def name(world: str, entity: str, rng: random.Random) -> str:
    return rng.choice(ENTITIES[world][entity][1])


def first_name(world: str, entity: str) -> str:
    return ENTITIES[world][entity][1][0]


def cap(text: str) -> str:
    return text[:1].upper() + text[1:]


# --- templates ----------------------------------------------------------------------------------------------------
# A template: (family, stateful, target slot or None, text with {slots}, tags). Slots: p (present person),
# a (absent person), l (exit place), f (far place), i (carried item), e (food), o (offer here), c (creature),
# q (available quest), Q (active quest), k (skill), t (topic), r (recruit), w (any world item), g (group).

T = list[tuple[str, Any, str | None, str, tuple[str, ...]]]

LOOK: T = [
    ("look", False, None, "look around", ()), ("look", False, None, "Look around.", ()),
    ("look", False, None, "I look around", ()), ("look", False, None, "survey the area", ()),
    ("look", False, None, "What do I see?", ("question",)), ("look", False, None, "describe the place", ()),
    ("look", False, None, "take a look around", ()), ("look", False, None, "I glance around the room", ()),
    ("look", False, None, "what's here?", ("question",)), ("look", False, None, "look", ()),
    ("look", False, None, "I scan my surroundings", ()), ("look", False, None, "where am I?", ("question",)),
    ("look", False, None, "who's around?", ("question",)), ("look", False, None, "observe", ()),
    ("look", False, None, "I listen for a moment", ()), ("look", False, None, "lok around", ("typo",)),
    ("look", False, None, "look arround", ("typo",)), ("look", False, None, "lookaround", ("typo",)),
    ("look", False, None, "I take in the scene", ()), ("look", False, None, "what is going on here?", ("question",)),
    ("look", False, None, "Is anyone else here?", ("question",)),
    ("look", False, None, "I look around and then wait", ("multi_step",)),
    ("look", False, None, "check out the surroundings", ()),
    ("look", False, None, "I peer through the crowd", ()),
    ("look", False, None, "describe who is present", ()),
]
INSPECT: T = [
    ("inspect", False, "i", "examine my {i}", ()), ("inspect", False, "i", "inspect the {i}", ()),
    ("inspect", False, "i", "look at my {i}", ()), ("inspect", False, "i", "I study the {i} closely", ()),
    ("inspect", False, "p", "look at {p}", ()), ("inspect", False, "p", "I study {p}'s face", ()),
    ("inspect", False, "p", "examine {p}", ()), ("inspect", False, "p", "what does {p} look like?", ("question",)),
    ("inspect", False, "i", "what is this {i} for?", ("question",)), ("inspect", False, "i", "exmaine the {i}", ("typo",)),
    ("inspect", False, "i", "turn the {i} over in my hands", ()), ("inspect", False, "p", "I watch {p} carefully", ()),
    ("inspect", False, "i", "check the {i} for damage", ()),
    ("inspect", False, "p", "I size up {p}", ()),
    ("inspect", False, "i", "describe my {i}", ()),
]
TALK: T = [
    ("talk", False, "p", "talk to {p}", ()), ("talk", False, "p", "I greet {p}", ()),
    ("talk", False, "p", "say hello to {p}", ()), ("talk", False, "p", "Hello, {P}!", ()),
    ("talk", False, "p", "speak with {p}", ()), ("talk", False, "p", "chat with {p}", ()),
    ("talk", False, "p", "I nod to {p}", ()), ("talk", False, "p", "tell {p} my name is Wren", ()),
    ("talk", False, "p", "{P}, thank you for your help.", ()), ("talk", False, "p", "I wave at {p}", ()),
    ("talk", False, "p", "tak to {p}", ("typo",)), ("talk", False, "p", "talk too {p}", ("typo",)),
    ("talk", False, "p", "I introduce myself to {p}", ()), ("talk", False, "p", "{P}, I'm new here.", ()),
    ("talk", False, "p", "I apologize to {p}", ()), ("talk", False, "p", "I compliment {p}", ()),
    ("talk", False, "p", "tell {p} a joke", ()), ("talk", False, "p", "I thank {p}", ()),
    ("talk", False, "p", "Good evening, {P}.", ()), ("talk", False, "p", "I sit down next to {p} and chat", ()),
    ("talk", False, "p", "{P}, that sounds useful.", ("trap:use",)),
    ("talk", False, "p", "{P}, how interesting.", ("trap:rest",)),
    ("talk", False, "p", "I tell {p} that the forest looked dark", ("trap:rest",)),
    ("talk", False, "p", "{P}, it is a great day.", ("trap:eat",)),
    ("talk", False, "p", "I tell {p} about the white light I saw", ("trap:hit",)),
    ("talk", False, "p", "{P}, my mistake, sorry.", ("trap:take",)),
    ("talk", False, "p", "{P}, because I said so.", ("trap:use",)),
    ("talk", False, "p", "{P}, I am restless tonight.", ("trap:rest",)),
    ("talk", False, "p", "I tell {p} I found a useful shortcut", ("trap:use",)),
    ("talk", False, "p", "{P}, the current is strong here.", ("trap:rent",)),
]
REMARK: T = [
    ("talk", False, None, "That sounds useful.", ("trap:use",)), ("talk", False, None, "Interesting.", ("trap:rest",)),
    ("talk", False, None, "The forest looks dark tonight.", ("trap:rest",)),
    ("talk", False, None, "What a great view.", ("trap:eat",)), ("talk", False, None, "I hum a tune", ()),
    ("talk", False, None, "This is a mistake.", ("trap:take",)), ("talk", False, None, "I laugh", ()),
    ("talk", False, None, "Hello?", ()), ("talk", False, None, "I sing a song", ()),
    ("talk", False, None, "Such white walls.", ("trap:hit",)), ("talk", False, None, "The current runs fast.", ("trap:rent",)),
    ("talk", False, None, "I smile", ()), ("talk", False, None, "I sigh and think about home", ()),
    ("talk", False, None, "Because of the rain, everything smells like a forest.", ("trap:use", "trap:rest")),
    ("talk", False, None, "That would be useful later.", ("trap:use",)),
    ("talk", False, None, "I shout a greeting to everyone", ()),
    ("talk", False, None, "nice place", ()),
    ("talk", False, None, "I hate this weather.", ("trap:eat",)),
]
ASK: T = [
    ("ask", False, "p", "ask {p} about {t}", ()), ("ask", False, "p", "{P}, what do you know about {t}?", ("question",)),
    ("ask", False, "p", "{P}, where am I?", ("question",)), ("ask", False, "p", "ask {p} what happened here", ()),
    ("ask", False, "p", "{P}, can you tell me about {t}?", ("question",)),
    ("ask", False, "p", "I ask {p} for advice", ()), ("ask", False, "p", "{P}, who are you?", ("question",)),
    ("ask", False, "p", "{P}, what should I do next?", ("question",)), ("ask", False, "p", "ask {p} about {a}", ()),
    ("ask", False, "p", "{P}, have you heard of {a}?", ("question",)),
    ("ask", False, "p", "{P}, how do I get to {f}?", ("question",)),
    ("ask", False, "p", "aks {p} about {t}", ("typo",)), ("ask", False, "p", "ask {p} abuot {t}", ("typo",)),
    ("ask", False, "p", "{P}, what's the current news?", ("question", "trap:rent")),
    ("ask", False, "p", "{P}, is this house yours?", ("question", "trap:use")),
    ("ask", False, "p", "{P}, what is the most useful thing to know here?", ("question", "trap:use")),
    ("ask", False, "p", "{P}, is the forest safe?", ("question", "trap:rest")),
    ("ask", False, "p", "{P}, what's that white tower?", ("question", "trap:hit")),
    ("ask", False, "p", "{P}, do you know any good stories?", ("question",)),
    ("ask", False, "p", "I ask {p} where {a} is", ()),
    ("ask", False, "p", "{P}, why are you here?", ("question",)),
    ("ask", False, "p", "{P}, what do you think of {g}?", ("question",)),
    ("ask", False, "a", "who is {a}?", ("question",)), ("ask", False, "a", "where can I find {a}?", ("question",)),
    ("ask", False, "a", "what do people say about {a}?", ("question",)),
    ("ask", False, "f", "where is {f}?", ("question",)), ("ask", False, "f", "what is {f} like?", ("question",)),
    ("ask", False, "f", "how far is {f}?", ("question",)),
    ("ask", False, "Q", "what do I need to do for {Q}?", ("question",)),
    ("ask", False, "Q", "remind me what {Q} is about", ()),
    ("ask", False, "g", "what is {g}?", ("question",)),
    ("ask", False, "w", "what is the {w}?", ("question",)),
]
PRICE: T = [
    ("ask", False, "o", "how much is {o}?", ("question", "price")), ("ask", False, "o", "what does {o} cost?", ("question", "price")),
    ("ask", False, "o", "how much for {o}?", ("question", "price")), ("ask", False, "o", "is {o} expensive?", ("question", "price")),
    ("ask", False, "o", "what's the price of {o}?", ("question", "price")),
    ("ask", False, "o", "could I get {o} here?", ("question", "hypothetical")),
    ("ask", False, "o", "would {o} be worth it?", ("question", "hypothetical")),
    ("ask", False, "o", "if I bought {o}, how much would I have left?", ("question", "hypothetical")),
    ("ask", False, None, "what do you sell?", ("question",)), ("ask", False, None, "what's on the menu?", ("question",)),
    ("ask", False, None, "what can I buy here?", ("question",)),
    ("ask", False, None, "what's for dinner?", ("question", "trap:inn")),
    ("ask", False, None, "how much money do these things cost?", ("question",)),
]
HYPOTHETICAL: T = [
    ("ask", False, "p", "what would happen if I attacked {p}?", ("question", "hypothetical")),
    ("ask", False, "p", "what if I punched {p}?", ("question", "hypothetical")),
    ("ask", False, "l", "if I went to {l}, what would I find?", ("question", "hypothetical")),
    ("ask", False, "l", "how long would it take to walk to {l}?", ("question", "hypothetical")),
    ("ask", False, "i", "what would happen if I dropped my {i}?", ("question", "hypothetical")),
    ("ask", False, "p", "should I trust {p}?", ("question",)),
    ("ask", False, "i", "could I sell my {i} somewhere?", ("question", "hypothetical")),
    ("ask", False, "k", "would practicing {k} help me?", ("question", "hypothetical")),
    ("ask", False, "p", "is it a good idea to ask {p} for help?", ("question", "hypothetical")),
    ("ask", False, "l", "is {l} dangerous?", ("question",)),
    ("ask", False, "i", "can I use the {i} to fight?", ("question", "hypothetical")),
    ("ask", False, "p", "what would {p} think if I left?", ("question", "hypothetical")),
]
DECLINE: T = [
    ("decline", False, None, "no thanks", ("negation",)), ("decline", False, None, "never mind", ("negation",)),
    ("decline", False, None, "I don't want to fight", ("negation",)), ("decline", False, None, "I won't buy anything yet", ("negation",)),
    ("decline", False, None, "not now", ("negation",)), ("decline", False, None, "I decide not to go anywhere", ("negation",)),
    ("decline", False, "p", "{P}, no, I don't need anything.", ("negation",)),
    ("decline", False, "p", "I tell {p} I'm not interested", ("negation",)),
    ("decline", False, "p", "{P}, I won't attack you.", ("negation",)),
    ("decline", False, None, "I put my dagger away and don't attack", ("negation",)),
    ("decline", False, None, "I don't want to drop anything", ("negation",)),
    ("decline", False, None, "forget it", ("negation",)),
    ("decline", False, "p", "I refuse {p}'s offer", ("negation",)),
    ("decline", False, None, "Don't buy the potion.", ("negation",)),
    ("decline", False, None, "I'd rather not rest here", ("negation", "trap:rest")),
]
STATUS: T = [
    ("status", False, None, "check my inventory", ()), ("status", False, None, "what's in my pack?", ("question",)),
    ("status", False, None, "show my quests", ()), ("status", False, None, "what level am I?", ("question",)),
    ("status", False, None, "how much money do I have?", ("question",)), ("status", False, None, "check my purse", ()),
    ("status", False, None, "inventory", ()), ("status", False, None, "show me my skills", ()),
    ("status", False, None, "what am I carrying?", ("question",)), ("status", False, None, "check my health", ()),
    ("status", False, None, "review my journal", ()), ("status", False, None, "what are my objectives?", ("question",)),
    ("status", False, None, "chek my inventroy", ("typo",)), ("status", False, None, "status", ()),
    ("status", False, None, "show my character sheet", ()), ("status", False, None, "how hurt am I?", ("question",)),
    ("status", False, None, "what quests do I have?", ("question",)), ("status", False, None, "check my xp", ()),
]
CLARIFY: T = [
    ("clarify", False, None, "do it", ()), ("clarify", False, None, "the thing", ()), ("clarify", False, None, "go there", ()),
    ("clarify", False, None, "use it", ()), ("clarify", False, None, "hmm", ()), ("clarify", False, None, "asdf", ()),
    ("clarify", False, None, "yes", ()), ("clarify", False, None, "buy", ()), ("clarify", False, None, "attack", ()),
    ("clarify", False, None, "give it to them", ()), ("clarify", False, None, "?", ()), ("clarify", False, None, "ok", ()),
    ("clarify", False, None, "that one", ()), ("clarify", False, None, "again", ()), ("clarify", False, None, "the other one", ()),
    ("clarify", False, None, "talk", ()), ("clarify", False, None, "go", ()), ("clarify", False, None, "take", ()),
    ("clarify", False, None, "do the usual", ("trap:use",)), ("clarify", False, None, "same as before", ()),
]
WAIT: T = [
    ("wait", False, None, "wait", ()), ("wait", False, None, "I wait a while", ()), ("wait", False, None, "wait for an hour", ()),
    ("wait", False, None, "keep watch", ()), ("wait", False, None, "I bide my time", ()), ("wait", False, None, "let some time pass", ()),
    ("wait", False, None, "wiat", ("typo",)), ("wait", False, None, "I wait until evening", ()),
    ("wait", False, None, "wait and see what happens", ()), ("wait", False, None, "do nothing for a bit", ()),
]
REST: T = [
    ("rest", True, None, "rest for a while", ()), ("rest", True, None, "I sit down and rest", ()),
    ("rest", True, None, "take a short rest", ()), ("rest", True, None, "I sleep until morning", ()),
    ("rest", True, None, "make camp and sleep", ()), ("rest", True, None, "I catch my breath", ()),
    ("rest", True, None, "rest", ()), ("rest", True, None, "I lie down for a nap", ()),
]
MOVE: T = [
    ("move", True, "l", "go to {l}", ()), ("move", True, "l", "travel to {l}", ()), ("move", True, "l", "I walk to {l}", ()),
    ("move", True, "l", "head to {l}", ()), ("move", True, "l", "let's go to {l}", ()), ("move", True, "l", "I set off for {l}", ()),
    ("move", True, "l", "take me to {l}", ()), ("move", True, "l", "I leave for {l}", ()), ("move", True, "l", "go to {l} now", ()),
    ("move", True, "l", "I make my way to {l}", ()), ("move", True, "l", "goto {l}", ("typo",)),
    ("move", True, "l", "go too {l}", ("typo",)), ("move", True, "l", "travle to {l}", ("typo",)),
    ("move", True, "l", "go to {l} and look around", ("multi_step",)),
    ("move", True, "l", "I head to {l}, then wait", ("multi_step",)),
    ("move", True, "l", "walk over to {l}", ()), ("move", True, "l", "Could you take me to {l}? I go.", ()),
    ("move", True, "l", "I go to {l} because it seems useful", ("trap:use",)),
    ("move", True, "l", "I head toward {l} through the forest", ("trap:rest",)),
]
BUY: T = [
    ("buy", "pay", "o", "buy {o}", ()), ("buy", "pay", "o", "I buy {o}", ()), ("buy", "pay", "o", "I'd like {o}, please", ()),
    ("buy", "pay", "o", "purchase {o}", ()), ("buy", "pay", "o", "I'll take {o}", ()), ("buy", "pay", "o", "give me {o}, here's the coin", ()),
    ("buy", "pay", "o", "I pay for {o}", ()), ("buy", "pay", "o", "one {o_bare}, please", ()), ("buy", "pay", "o", "buy {o} for me", ()),
    ("buy", "pay", "o", "by {o}", ("typo",)), ("buy", "pay", "o", "buy {o} pls", ()), ("buy", "pay", "o", "I want to buy {o}", ()),
    ("buy", "pay", "o", "buy {o} and then look around", ("multi_step",)),
    ("buy", "pay", "o", "I order {o}", ()), ("buy", "pay", "o", "sell me {o}", ()),
]
# Buying where nobody sells it, or with an empty purse: the player means to buy, and nothing changes.
BUY_NOWHERE: T = [
    ("buy", False, "w", "buy a {w}", ()), ("buy", False, "w", "I want to buy the {w}", ()),
    ("buy", False, "w", "where can I buy a {w}? I'll buy one.", ()), ("buy", False, "w", "purchase a {w}", ()),
    ("buy", False, "w", "I buy a {w}", ()),
]
SELL: T = [
    ("sell", "sale", "i", "sell my {i}", ()), ("sell", "sale", "i", "I sell the {i}", ()),
    ("sell", "sale", "i", "I want to sell my {i}", ()), ("sell", "sale", "i", "sell the {i} for coin", ()),
    ("sell", "sale", "i", "sel my {i}", ("typo",)),
]
ATTACK: T = [
    ("attack", True, "c", "attack the {c_bare}", ()), ("attack", True, "c", "I attack the {c_bare}", ()),
    ("attack", True, "c", "fight the {c_bare}", ()), ("attack", True, "c", "strike the {c_bare} with my dagger", ()),
    ("attack", True, "c", "atack the {c_bare}", ("typo",)), ("attack", True, "c", "I charge at the {c_bare}", ()),
    ("attack", True, "p", "punch {p}", ()), ("attack", True, "p", "I attack {p}", ()), ("attack", True, "p", "stab {p}", ()),
    ("attack", True, "p", "I kick {p}", ()), ("attack", True, "p", "hit {p} with my dagger", ()),
    ("attack", True, "p", "I shove {p} hard", ()),
]
GIVE: T = [
    ("give", True, "i", "give my {i} to {p}", ()), ("give", True, "i", "I hand {p} my {i}", ()),
    ("give", True, "i", "offer the {i} to {p} as a gift", ()), ("give", True, "i", "giv my {i} to {p}", ("typo",)),
]
DROP: T = [
    ("drop", True, "i", "drop my {i}", ()), ("drop", True, "i", "I drop the {i}", ()), ("drop", True, "i", "discard the {i}", ()),
    ("drop", True, "i", "throw away my {i}", ()), ("drop", True, "i", "I put the {i} down and leave it", ()),
    ("drop", True, "i", "drp the {i}", ("typo",)),
]
USE_FOOD: T = [
    ("use_item", True, "e", "eat the {e}", ()), ("use_item", True, "e", "I eat some {e}", ()),
    ("use_item", True, "e", "have a bite of {e}", ()), ("use_item", True, "e", "consume the {e}", ()),
    ("use_item", True, "e", "eat {e}", ()), ("use_item", True, "e", "I snack on the {e}", ()),
]
USE_TOOL: T = [
    ("use_item", False, "i", "use my {i}", ()), ("use_item", False, "i", "I hold up the {i}", ()),
    ("use_item", False, "i", "use the {i}", ()),
]
EQUIP: T = [
    ("unequip", True, "i", "unequip my {i}", ()), ("unequip", True, "i", "take off my {i}", ()),
    ("unequip", True, "i", "I put away my {i}", ()), ("unequip", True, "i", "remove the {i}", ()),
    ("equip", False, "i", "equip my {i}", ()), ("equip", False, "i", "I ready my {i}", ()),
    ("equip", False, "i", "wield the {i}", ()),
]
QUEST: T = [
    ("quest", True, "q", "accept the quest {q}", ()), ("quest", True, "q", "I'll take on {q}", ()),
    ("quest", True, "q", "start the quest {q}", ()), ("quest", True, "q", "I accept {q}", ()),
    ("quest", True, "q", "sign me up for {q}", ()),
]
PRACTICE: T = [
    ("practice", True, "k", "practice {k}", ()), ("practice", True, "k", "I train my {k}", ()),
    ("practice", True, "k", "spend an hour practicing {k}", ()), ("practice", True, "k", "drill {k}", ()),
    ("practice", True, "k", "practise {k}", ()), ("practice", True, "k", "pratice {k}", ("typo",)),
    ("practice", True, "k", "I train {k} for a while", ()),
]
PARTY: T = [
    ("party", True, "r", "ask {r} to join my party", ()), ("party", True, "r", "{R}, will you travel with me? Join me.", ()),
    ("party", True, "r", "I invite {r} to join me", ()), ("party", True, "r", "recruit {r}", ()),
]
FLEE_DEFEND: T = [
    ("flee", False, None, "run away", ()), ("flee", False, None, "flee", ()),
    ("defend", False, None, "raise my guard", ()), ("defend", False, None, "I take a defensive stance", ()),
]
MANIPULATE: T = [
    ("manipulate", False, None, "open the door", ()), ("manipulate", False, None, "close the door behind me", ()),
    ("manipulate", False, None, "search the area for anything hidden", ()),
]


def slot_values(world: str, scene: dict[str, Any]) -> dict[str, list[str]]:
    entities = ENTITIES[world]
    people = [key for key, value in entities.items() if value[0] == "person"]
    places = [key for key, value in entities.items() if value[0] == "place"]
    absent = [key for key in people if key not in scene["present"]]
    far = [key for key in places if key not in scene["exits"] and key != scene["location_id"]]
    return {
        "p": list(scene["present"]), "a": absent, "l": list(scene["exits"]), "f": far, "i": CARRIED[world],
        "e": FOOD[world], "o": list(scene["offers"]), "c": list(scene["creatures"]), "q": AVAILABLE_QUESTS[world],
        "Q": ACTIVE_QUESTS[world] + OTHER_QUESTS[world], "k": [f"skill:{skill}" for skill in SKILLS[world]],
        "r": [key for key in RECRUITS[world] if key in scene["present"]],
        "w": [key for key, value in entities.items() if value[0] == "item" and key not in CARRIED[world]],
        "g": [key for key, value in entities.items() if value[0] == "group"],
    }


def render(world: str, scene_name: str, template: tuple, rng: random.Random) -> dict[str, Any] | None:
    family, stateful, target_slot, text, tags = template
    scene = SCENES[world][scene_name]
    values = slot_values(world, scene)
    chosen: dict[str, str] = {}
    needed = {slot for slot in "palfieocqQkrwg" if "{" + slot in text or "{" + slot.upper() in text}
    needed |= {target_slot} if target_slot else set()
    if "{t}" in text:
        chosen_topic = rng.choice(TOPICS[world])
    else:
        chosen_topic = ""
    for slot in needed:
        options = values.get(slot) or []
        if not options:
            return None
        chosen[slot] = rng.choice(options)
    if "{P}" in text and "p" not in chosen:
        if not values["p"]:
            return None
        chosen["p"] = rng.choice(values["p"])
    if "{R}" in text and "r" not in chosen:
        if not values["r"]:
            return None
        chosen["r"] = rng.choice(values["r"])
    words: dict[str, str] = {"t": chosen_topic}
    for slot, entity in chosen.items():
        label = name(world, entity, rng)
        words[slot] = label
        # Someone addressed by name at the start of a line is named, not described ("Orik, ...", not "The innkeeper, ...").
        address = label if not label.startswith(("the ", "my ")) else first_name(world, entity)
        words[slot.upper()] = cap(address)
    if "o" in chosen:
        words["o_bare"] = words["o"].removeprefix("a ").removeprefix("an ").removeprefix("the ").removeprefix("some ")
    if "c" in chosen:
        words["c_bare"] = words["c"].removeprefix("the ")
    if "{i}" in text and "i" in chosen:
        words["i"] = words["i"].removeprefix("a ")
    rendered = text
    for slot, value in words.items():
        rendered = rendered.replace("{" + slot + "}", value)
    if "{" in rendered:
        return None
    rendered = re.sub(r"\ba ([aeioAEIO])", r"an \1", rendered)
    # Whether the correct handling changes state, where it depends on the scene.
    if stateful == "pay":
        stateful = MONEY_OK[world] and bool(scene["offers"])
    elif stateful == "sale":
        stateful = bool(scene["buyer"])
    target = chosen.get(target_slot) if target_slot else None
    if family == "buy" and target_slot == "o" and not scene["offers"]:
        return None
    return {"world": world, "scene": scene_name, "input": rendered, "action_family": family,
            "target_entity": target, "stateful": bool(stateful), "tags": list(tags)}


# Per world, how many of each template group (scaled to the world's size).
MIX = [
    (LOOK, 30), (INSPECT, 50), (TALK, 75), (REMARK, 25), (ASK, 130), (PRICE, 30), (HYPOTHETICAL, 35), (DECLINE, 25),
    (STATUS, 35), (CLARIFY, 30), (WAIT, 18), (REST, 12), (MOVE, 45), (BUY, 40), (BUY_NOWHERE, 10), (SELL, 10), (ATTACK, 25), (GIVE, 12),
    (DROP, 14), (USE_FOOD, 10), (USE_TOOL, 8), (EQUIP, 14), (QUEST, 8), (PRACTICE, 24), (PARTY, 6), (FLEE_DEFEND, 4),
    (MANIPULATE, 4),
]


def scene_for(world: str, group: T, rng: random.Random) -> str:
    scenes = list(SCENES[world])
    if group is BUY or group is PRICE:
        scenes = [scene for scene in scenes if SCENES[world][scene]["offers"]] or scenes
    if group is SELL:
        with_buyer = [scene for scene in scenes if SCENES[world][scene]["buyer"]]
        scenes = with_buyer + scenes if with_buyer else scenes
    if group is BUY_NOWHERE:
        scenes = [scene for scene in scenes if not SCENES[world][scene]["offers"]] or scenes
    return rng.choice(scenes)


def build_world(world: str, rng: random.Random) -> list[dict[str, Any]]:
    total_weight = sum(weight for _, weight in MIX)
    items: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for group, weight in MIX:
        want = round(SIZES[world] * weight / total_weight)
        attempts = 0
        made = 0
        while made < want and attempts < want * 60:
            attempts += 1
            scene = scene_for(world, group, rng)
            item = render(world, scene, rng.choice(group), rng)
            if item is None or (scene, item["input"].lower()) in seen:
                continue
            seen.add((scene, item["input"].lower()))
            items.append(item)
            made += 1
    # Top up or trim to the exact size with talk and ask items, which every scene supports.
    while len(items) < SIZES[world]:
        scene = rng.choice(list(SCENES[world]))
        item = render(world, scene, rng.choice(ASK + TALK + INSPECT), rng)
        if item and (scene, item["input"].lower()) not in seen:
            seen.add((scene, item["input"].lower()))
            items.append(item)
    rng.shuffle(items)
    return items[: SIZES[world]]


def split(items: list[dict[str, Any]], rng: random.Random) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Stratified by world and family: 40% development, 60% held out."""
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in items:
        groups.setdefault((item["world"], item["action_family"]), []).append(item)
    dev: list[dict[str, Any]] = []
    held: list[dict[str, Any]] = []
    for key in sorted(groups):
        members = groups[key]
        rng.shuffle(members)
        cut = round(len(members) * DEV_SIZE / len(items))
        dev.extend(members[:cut])
        held.extend(members[cut:])
    while len(dev) > DEV_SIZE:
        held.append(dev.pop(rng.randrange(len(dev))))
    while len(dev) < DEV_SIZE:
        dev.append(held.pop(rng.randrange(len(held))))
    return dev, held


def number(items: list[dict[str, Any]], prefix: str) -> list[dict[str, Any]]:
    ordered = sorted(items, key=lambda item: (item["world"], item["scene"], item["action_family"], item["input"]))
    return [{"id": f"{prefix}-{index:04d}", **item, "labelled_by": "model", "review": "pending_owner_spot_check"}
            for index, item in enumerate(ordered, 1)]


def catalog() -> dict[str, Any]:
    return {
        "format_version": "rpg-intent-catalog-v1",
        "families": list(FAMILIES),
        "worlds": {
            world: {
                "scenes": SCENES[world],
                "entities": {key: {"kind": kind, "names": names, "alias_ids": aliases}
                             for key, (kind, names, aliases) in sorted(ENTITIES[world].items())},
            }
            for world in ENTITIES
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--force", action="store_true", help="overwrite an existing corpus (a re-freeze)")
    args = parser.parse_args(argv)
    held_path = CORPUS / "held_out.jsonl"
    if held_path.exists() and not args.force:
        raise SystemExit("the corpus exists and its held-out set is frozen; pass --force to rebuild and re-freeze")
    rng = random.Random(SEED)
    items = [item for world in ("aurelia", "vesper-9", "starter") for item in build_world(world, rng)]
    dev, held = split(items, rng)
    dev, held = number(dev, "dev"), number(held, "held")
    CORPUS.mkdir(parents=True, exist_ok=True)
    for path, rows in ((CORPUS / "dev.jsonl", dev), (held_path, held)):
        path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
                        encoding="utf-8", newline="\n")
    (CORPUS / "catalog.json").write_text(json.dumps(catalog(), indent=1, ensure_ascii=False, sort_keys=True) + "\n",
                                         encoding="utf-8", newline="\n")
    not_stateful = sum(not row["stateful"] for row in held)
    with_target = sum(row["target_entity"] is not None for row in held)
    print(json.dumps({"dev": len(dev), "held_out": len(held), "held_out_not_stateful": not_stateful,
                      "held_out_with_target": with_target,
                      "held_out_sha256": hashlib.sha256(held_path.read_bytes()).hexdigest()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
