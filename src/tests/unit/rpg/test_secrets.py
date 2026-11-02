"""What may be said (rules/secrets.py): a world's secrets stay in their own fields, out of everything shown or sent."""
from __future__ import annotations

from app.apps.rpg.rules.secrets import public_canon, sayable
from app.apps.rpg.session.upgrades.hidden_truths import keep_secrets_to_themselves

TRUTH = "Her childhood was assembled from incompatible donors, making her living proof of an illegal experiment."
CANON = {
    "entities": {"ent:mara": {"name": "Mara Vey", "hidden_truth": TRUTH,
                              "description": f"A memory courier.\n\nShe drinks station coffee. {TRUTH} She wants proof."}},
    "facts": [{"id": "fact:mara", "content": f"A memory courier. {TRUTH}", "entity_refs": ["ent:mara"]}],
    "documents": [{"id": "doc:actors", "full_text": f"Mara Vey carries memories.\n\n{TRUTH}"}],
}


def test_a_canons_secrets_leave_everything_but_their_own_fields() -> None:
    """The tenth review: a lore world's every fact and page carried its hidden truth to the lore panel and the
    narrator's evidence."""
    public = public_canon(CANON)
    mara = public["entities"]["ent:mara"]
    assert mara["hidden_truth"] == TRUTH  # kept where the rules that guard it read it
    assert mara["description"] == "A memory courier.\n\nShe drinks station coffee. She wants proof."  # as written else
    assert public["facts"][0]["content"] == "A memory courier."
    assert public["documents"][0]["full_text"] == "Mara Vey carries memories."
    assert public_canon({"facts": [{"content": "Nothing hidden here."}]}) == {"facts": [{"content": "Nothing hidden here."}]}


def test_a_sentence_sharing_only_small_words_with_a_secret_is_kept() -> None:
    """The tenth review: "the", "is" and "a" made "The mayor is a kind old man" a secret's."""
    assert sayable("The mayor is a kind old man who feeds the stray cats.", ("The mayor is a Helix agent.",)) == (
        "The mayor is a kind old man who feeds the stray cats.")
    assert sayable("The mayor smiles. The mayor is a Helix agent.", ("The mayor is a Helix agent.",)) == "The mayor smiles."


def test_version_11_takes_the_secrets_out_of_a_campaigns_world_model() -> None:
    """A campaign begun before: its world model's people and places kept their hidden truths in their descriptions."""
    place = "An interchange of dark water. Platform Zero receives a driverless wartime train on irregular nights."
    document = {
        "campaign_bible_projection": {"entities": {"p:station": {
            "id": "p:station", "name": "Black Rain Station",
            "hidden_truth": "Platform Zero receives a driverless wartime train on irregular nights."}}},
        "simulation_state": {"world_model": {
            "locations": {"p:station": {"name": "Black Rain Station", "description": place}},
            "npcs": {"npc:mara": {"name": "Mara Vey", "secrets": [TRUTH], "description": f"A courier. {TRUTH}"}},
        }},
    }
    world = keep_secrets_to_themselves(document)["simulation_state"]["world_model"]
    assert world["locations"]["p:station"]["description"] == "An interchange of dark water."
    assert world["npcs"]["npc:mara"]["description"] == "A courier." and world["npcs"]["npc:mara"]["secrets"] == [TRUTH]


def test_an_authors_sentence_that_shares_nouns_with_a_secret_tells_none_of_it() -> None:
    """The eleventh review: the starter town's quest objective and a public patrol fact share nouns with the
    innkeeper's secrets, and the filter blanked them."""
    canon = {
        "characters": [{"id": "npc:bran", "name": "Bran", "secrets": [
            "The sealed crates come from the old quarry, and Bran is paid to keep them out of the ledger.",
            "He abandoned his post at the Northern Watch the night the beacon went dark."]}],
        "quests": [{"id": "quest:quarry", "objective":
                    "Find the source of the pale light in the old quarry, and what the sealed crates carry."}],
        "knowledge": [{"text": "A patrol went up to the Northern Watch ten days ago."}],
        "documents": [{"id": "doc:bran", "full_text":
                       "Bran keeps the inn.\nHe abandoned his post at the Northern Watch the night the beacon went dark."}],
        # A search index's "secrets" entry is a list of card ids, no secret.
        "indexes": {"lexical": {"secrets": ["card:fact:roles:004"], "name": ["card:fact:roles:004"]}},
        "retrieval_cards": [{"id": "card:fact:roles:004", "title": "fact:roles archetypes:004"}],
    }
    public = public_canon(canon)
    assert public["quests"] == canon["quests"] and public["knowledge"] == canon["knowledge"]
    assert public["documents"][0]["full_text"] == "Bran keeps the inn."  # a line break ends a sentence
    assert public["retrieval_cards"] == canon["retrieval_cards"]


def test_what_a_model_reads_of_the_world_has_no_secret_field_or_sentence() -> None:
    """The twelfth review: scene lore sent a place's whole entity, its hidden truth with it."""
    from app.apps.rpg.rules.secrets import for_the_model

    truth = "Platform Zero receives a driverless wartime train on irregular nights."
    place = {"id": "p:station", "name": "Black Rain Station", "hidden_truth": truth,
             "description": f"An interchange of dark water. {truth}"}
    assert for_the_model({"location": place}, [truth]) == {"location": {
        "id": "p:station", "name": "Black Rain Station", "description": "An interchange of dark water."}}
