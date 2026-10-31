"""Names that open their lore (evolution roadmap EV-12).

Every mention of an entry with lore (a person, a place, a group, a creature, a thing, a quest) in a response can be
opened. The narrator and the dialogue call mark what they name, ``[[words|entry id]]``; the marks never reach the
text: each is taken out as it is written (``note``: drafts and the final text alike are plain), and kept only to say
which entry a name means where two share it. The links are worked out on the final, checked text (``spans``): every
name of an entry the hero may be shown, written as it is (a proper name: "Starfall Village", not "the village"), or as
a model's mark of one of that entry's names. An entry kept from the hero (a hidden place, a secret thing) is never
linked, nor an id the world does not have. Deterministic prose (the fallback, the journal, the quest log) is linked
the same way, from the names alone.

A link of an entry the hero did not know yet means they have heard of it now: a narration proposal (EV-11) the next
turn folds in (``rules/hero_knowledge.heard_of``). A click opens ``entry_view``: the entry's public lore, what the hero
has learned of it, and links onward; it is no turn, makes no model call, takes no lock and writes nothing.
"""
from __future__ import annotations

import re
from contextvars import ContextVar
from typing import Any, Iterable, Mapping

from app.apps.rpg.foundation.safe_values import safe_dict as _d, safe_list as _l, safe_str as _s
from app.apps.rpg.foundation.state import access as _sections

MARK = re.compile(r"\[\[([^\[\]|]{1,120})\|([^\[\]|]{1,200})\]\]")
_OPEN = re.compile(r"\[\[[^\]]*$")  # a mark the writer has begun and not closed yet (a draft)
_BROKEN = re.compile(r"\[\[([^\[\]|]{1,120})\|[^\s\]]*\]?\]?")  # a final text's mark never closed: its words kept
_NAME_KEYS = ("name", "title", "display_name")
_ALIAS_KEYS = ("aliases", "callings", "titles", "other_names")
_MIN_NAME = 3
_TITLES = frozenset({"captain", "lady", "lord", "master", "mistress", "sister", "brother", "father", "mother", "elder",
                     "king", "queen", "prince", "princess", "doctor", "sergeant", "commander", "archon", "warden",
                     "the", "of"})
_MARKS: ContextVar[tuple[tuple[str, str], ...]] = ContextVar("RPG_LORE_MARKS", default=())
# A quote inside narration, marked with its speaker (EV-13): ``<<speaker id|the quote>>``, spoken in their voice.
QUOTE = re.compile(r"<<([^<>|]{1,200})\|([^<>]{1,600})>>")
_OPEN_QUOTE = re.compile(r"<<[^>]*$")
_QUOTES: ContextVar[tuple[tuple[str, str], ...]] = ContextVar("RPG_QUOTE_MARKS", default=())


def strip_marks(text: str, *, draft: bool = False) -> str:
    """``text`` as it is shown: each mark's words, without the mark. In a ``draft``, a mark still being written is
    left out; in a final text, a mark never closed keeps its words, and a stray bracket is dropped."""
    plain = QUOTE.sub(lambda match: match.group(2), MARK.sub(lambda match: match.group(1), _s(text)))
    if draft:
        return _OPEN_QUOTE.sub("", _OPEN.sub("", plain))
    plain = _BROKEN.sub(lambda match: match.group(1), plain).replace("[[", "").replace("]]", "")
    return re.sub(r"<<[^<>|]{1,200}\|", "", plain).replace("<<", "").replace(">>", "")


def note(text: str) -> str:
    """Keep the marks a model wrote in ``text`` for this response's links, and return it without them."""
    found = tuple((match.group(1).strip(), match.group(2).strip()) for match in MARK.finditer(_s(text)))
    if found:
        _MARKS.set((*_MARKS.get(), *found))
    quotes = tuple((match.group(1).strip(), strip_marks(match.group(2)).strip()) for match in QUOTE.finditer(_s(text)))
    if quotes:
        _QUOTES.set((*_QUOTES.get(), *quotes))
    return strip_marks(text)


def noted() -> tuple[tuple[str, str], ...]:
    """The marks noted in this context: (words, entry id)."""
    return _MARKS.get()


def taken() -> tuple[tuple[str, str], ...]:
    """The marks noted in this context, which are then forgotten: one response's marks never link the next's."""
    marks = _MARKS.get()
    _MARKS.set(())
    return marks


def taken_quotes() -> tuple[tuple[str, str], ...]:
    """The quote marks noted in this context, which are then forgotten: (speaker id, the quote)."""
    quotes = _QUOTES.get()
    _QUOTES.set(())
    return quotes


def voices(text: str, simulation: Mapping[str, Any], quotes: Iterable[tuple[str, str]]) -> list[dict[str, Any]]:
    """Where a quote inside ``text`` is spoken in its speaker's voice (EV-13): ``{"speaker_id", "start", "end"}``,
    kept only for someone who is in the scene or has spoken before; the rest is the narrator's."""
    present = set(_l(_d(_sections.present_npc_state_of(simulation)).get("present_npc_ids")))
    spoken = set(_d(_d(simulation.get("dialogue")).get("exchanges")))
    found: list[dict[str, Any]] = []
    at = 0
    for speaker, quote in quotes:
        if speaker not in present | spoken or not quote:
            continue
        start = text.find(quote, at)
        if start < 0:
            continue
        found.append({"speaker_id": speaker, "start": start, "end": start + len(quote)})
        at = start + len(quote)
    return found


def _names(row: Mapping[str, Any], family: str = "") -> list[str]:
    """An entry's names: its name, title and aliases; and a person's own names in it ("Rhea" of "Captain Rhea
    Sunward"), which link only where no other entry shares them."""
    names = [_s(row.get(key)) for key in _NAME_KEYS]
    for key in _ALIAS_KEYS:
        names += [_s(alias) for alias in _l(row.get(key))]
    if family == "person":
        names += [word for word in _s(row.get("name")).split()[:3]
                  if len(word) >= 4 and word[:1].isupper() and word.casefold() not in _TITLES]
    return [name.strip() for name in dict.fromkeys(names) if len(name.strip()) >= _MIN_NAME]


def linkable(simulation: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """The entries a response may link, by id: their family and names. None kept from the hero."""
    from app.apps.rpg.rules.hero_knowledge import world_entries

    rows = world_entries(simulation)
    holders: dict[str, set[str]] = {}  # each word of every entry's name, and the entries whose name holds it
    for entry_id, row in rows.items():
        for word in _s(row.get("name")).split():
            holders.setdefault(word, set()).add(entry_id)
    found: dict[str, dict[str, Any]] = {}
    for entry_id, row in rows.items():
        whole = _names(row)
        if row.get("hidden") is True or row.get("secret") is True or not whole:
            continue
        # A person's own name ("Elyra" of "Elyra Moonroot") links them only when no other entry's name holds it,
        # one kept from the hero included ("Moonroot" of the Moonroot Ruins).
        parts = [name for name in _names(row, row["family"]) if name not in whole
                 and holders.get(name, set()) <= {entry_id}]
        found[entry_id] = {"family": row["family"], "names": [*whole, *parts]}
    return found


def spans(text: str, simulation: Mapping[str, Any], *, marks: Iterable[tuple[str, str]] = (),
          entries: Mapping[str, Mapping[str, Any]] | None = None) -> list[dict[str, Any]]:
    """The links of ``text`` (final and plain): ``{"entry_id", "start", "end"}``, in order, none overlapping. A name
    as it is written links its entry; one two entries share links the one a mark names, else neither; a mark links
    its words as the writer wrote them (in whatever case), when they are one of its entry's names."""
    entries = linkable(simulation) if entries is None else entries
    marked: dict[str, set[str]] = {}
    for words, entry_id in marks:
        if entry_id in entries and words.casefold() in {name.casefold() for name in entries[entry_id]["names"]}:
            marked.setdefault(words, set()).add(entry_id)
    by_name: dict[str, set[str]] = {}
    for entry_id, row in entries.items():
        for name in row["names"]:
            if name[:1].isupper():
                by_name.setdefault(name, set()).add(entry_id)
    found: list[tuple[int, int, str]] = []
    taken: list[tuple[int, int]] = []

    def free(start: int, end: int) -> bool:
        return all(end <= left or start >= right for left, right in taken)

    for name in sorted({*by_name, *marked}, key=len, reverse=True):
        ids = marked.get(name) or by_name.get(name, set())  # the writer's mark settles a name two entries share
        for match in re.finditer(rf"(?<![\w']){re.escape(name)}(?![\w'])", text):
            if len(ids) != 1 or not free(match.start(), match.end()):
                continue
            taken.append((match.start(), match.end()))
            found.append((match.start(), match.end(), next(iter(ids))))
    return [{"entry_id": entry_id, "start": start, "end": end} for start, end, entry_id in sorted(found)]


def visible_links(visible: Mapping[str, Any], simulation: Mapping[str, Any],
                  marks: Iterable[tuple[str, str]] = ()) -> dict[str, Any]:
    """The links of a turn's visible response: its narration's, and each message's."""
    entries = linkable(simulation)
    marks = tuple(marks)
    return {"narration": spans(_s(visible.get("narration")), simulation, marks=marks, entries=entries),
            "messages": [spans(_s(_d(message).get("text")), simulation, marks=marks, entries=entries)
                         for message in _l(visible.get("messages"))]}


def with_links(visible: Mapping[str, Any], document: Mapping[str, Any] | None) -> dict[str, Any]:
    """``visible`` with its links (``links``), worked out on its final text against the campaign ``document``."""
    if not isinstance(document, Mapping):
        return dict(visible)
    simulation = _d(_sections.simulation_state_of(document))
    return {**dict(visible), "links": visible_links(visible, simulation, taken()),
            "voices": {"narration": voices(_s(visible.get("narration")), simulation, taken_quotes())}}


def heard_of_now(links: Mapping[str, Any], simulation: Mapping[str, Any]) -> list[str]:
    """The entries the links name that the hero did not know: they have heard of them now."""
    from app.apps.rpg.rules.hero_knowledge import known_entries

    known = known_entries(simulation)
    named = [_s(_d(span).get("entry_id")) for span in _l(links.get("narration"))]
    named += [_s(_d(span).get("entry_id")) for row in _l(links.get("messages")) for span in _l(row)]
    return [entry_id for entry_id in dict.fromkeys(named) if entry_id and entry_id not in known]


def propose_heard_of(session_id: str, document: Mapping[str, Any] | None, links: Mapping[str, Any], *,
                     revision: int) -> int:
    """The hero's having heard of what the response named, as narration proposals for the next turn (EV-11)."""
    from app.apps.rpg.foundation.state.proposals import Proposal
    from app.apps.rpg.session.turn.proposals import record_proposals

    if not isinstance(document, Mapping):
        return 0
    heard = heard_of_now(links, _d(_sections.simulation_state_of(document)))
    proposals = [Proposal(proposal_id=f"heard:{session_id}:{revision}:{entry_id}", kind="heard_of", source="narration",
                          after_revision=revision, reason="the response named it", payload={"entry_id": entry_id})
                 for entry_id in heard]
    return record_proposals(session_id, proposals) if proposals else 0


_LORE_KEYS = {"person": ("role", "description", "appearance", "background"),
              "place": ("description", "region_name", "kind"), "group": ("description", "kind"),
              "quest": ("objective", "description"), "item": ("description", "type", "rarity"),
              "creature": ("description", "threat", "habitat")}


def entry_view(document: Mapping[str, Any], entry_id: str) -> dict[str, Any] | None:
    """What a click on a link opens: the entry's public lore (no secret field, no sentence telling a secret), what
    the hero has learned of it (how they know it, what people told them, the facts they learned that name it), and
    links onward from its lore. ``None`` for an entry the hero may not be shown. Reads only."""
    from app.apps.rpg.rules.contracts import secrets_held
    from app.apps.rpg.rules.hero_knowledge import known_entries, world_entries
    from app.apps.rpg.rules.secrets import for_the_model

    simulation = _d(_sections.simulation_state_of(document))
    entries = linkable(simulation)
    if entry_id not in entries:
        return None
    row = world_entries(simulation)[entry_id]
    family = entries[entry_id]["family"]
    secrets = list(secrets_held(_d(_sections.world_model_of(simulation)).get("npcs")))
    lore = for_the_model({key: row.get(key) for key in _LORE_KEYS.get(family, ("description",))
                          if isinstance(row.get(key), str) and _s(row.get(key))}, secrets)
    told = [_s(fact.get("text")) for npc_id, fact_ids in _d(_d(simulation.get("dialogue")).get("known_facts")).items()
            for fact in _knowledge_rows(simulation, str(npc_id)) if _s(fact.get("fact_id")) in set(_l(fact_ids))
            and _mentions(_s(fact.get("text")), entries[entry_id]["names"])]
    facts = [_s(_d(fact).get("told")) for _, fact in sorted(_d(_sections.world_facts_of(simulation)).items())
             if _d(fact).get("known") is True and _mentions(_s(_d(fact).get("told")), entries[entry_id]["names"])]
    learned = {"known_as": known_entries(simulation).get(entry_id, ""),
               "told": for_the_model(told, secrets), "facts": for_the_model(facts, secrets)}
    text = " ".join(_s(value) for value in lore.values())
    onward = [span for span in spans(text, simulation, entries=entries) if span["entry_id"] != entry_id]
    return {"entry_id": entry_id, "family": family, "name": entries[entry_id]["names"][0], "lore": lore,
            "learned": learned, "links": {"lore": onward, "text": text}}


def _knowledge_rows(simulation: Mapping[str, Any], npc_id: str) -> list[dict[str, Any]]:
    for entry in _l(_d(_sections.world_model_of(simulation)).get("knowledge")):
        if _s(_d(entry).get("npc_id")) == npc_id:
            return [_d(fact) for fact in _l(_d(entry).get("facts"))]
    return []


def _mentions(text: str, names: Iterable[str]) -> bool:
    return any(re.search(rf"(?<![\w']){re.escape(name)}(?![\w'])", text, re.IGNORECASE) for name in names)


__all__ = ["MARK", "QUOTE", "taken_quotes", "voices", "entry_view", "heard_of_now", "linkable", "note", "noted", "propose_heard_of", "spans",
           "strip_marks", "taken", "visible_links", "with_links"]
