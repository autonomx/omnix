"""EV-12's link samples and EV-13's quote sample: names that open their lore, and quotes in their speaker's voice.

Aurelia is played through the turn route by a seeded policy player (``rpg_autoplay.PolicyPlayer``: talking to people,
trading, travelling, fighting in the wild), every model call on RPG's route (``--model``, ``--effort``): the
narration is the model's, with its marks. Each turn's visible response is kept: its narration, its links
(``visible_response.links.narration``: a span and the entry it opens) and its quotes in a speaker's voice
(``visible_response.voices.narration``). Then a judge (the route's model) labels samples:

- **Right target** (EV-12): up to ``--links`` linked mentions; does the linked span refer to the entry it opens?
  Target: point estimate ≥ 0.98, lower bound reported.
- **Coverage** (EV-12): up to ``--responses`` responses; every mention, by the judge, of an entry the hero knows and
  the response could link; the share of those mentions linked. Target: ≥ 0.90.
- **Right speaker** (EV-13): up to ``--quotes`` quotes; who says it, among the people present? Target: point
  estimate ≥ 0.98, lower bound reported.

    OMNIX_DATABASE_URL=postgresql://...@127.0.0.1:16432/<disposable db> \\
        python scripts/rpg_lore_voice_eval.py --model haiku --effort low --allow-database <db> \\
        --output docs/measurements/rpg-lore-voice-<date>.json
"""
from __future__ import annotations

import argparse
from datetime import date
import json
import math
import os
from pathlib import Path
import random
import re
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from tests.rehearsal.rpg import worlds  # noqa: E402

LINK_JUDGE = """In this passage of a role-playing game's narration, the words "{words}" are linked to a lore entry.
PASSAGE: {passage}
ENTRY: {entry}
Do the linked words refer to this entry (the same person, place, thing, group, creature or quest)? Reply with JSON
only: {{"refers": true or false}}"""
COVERAGE_JUDGE = """List every mention, in this passage of a role-playing game's narration, of one of the CANDIDATES
(by name, a short form of it, or a clear title such as "the guide" for the one it means). Count each candidate once.
PASSAGE: {passage}
CANDIDATES: {candidates}
Reply with JSON only: {{"mentioned": ["candidate id", ...]}}"""
QUOTE_JUDGE = """In this passage of a role-playing game's narration, who says the quoted words "{quote}"?
PASSAGE: {passage}
PEOPLE: {people}
Reply with JSON only: {{"speaker_id": "the id of the one who says it, or empty if none of them"}}"""


def _d(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def wilson(successes: int, n: int, z: float = 1.96) -> dict[str, Any]:
    if not n:
        return {"successes": 0, "n": 0, "rate": None, "lower": None}
    p = successes / n
    centre, spread = p + z * z / (2 * n), z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return {"successes": successes, "n": n, "rate": round(p, 4), "lower": round((centre - spread) / (1 + z * z / n), 4)}


def ask(provider: Any, prompt: str) -> dict[str, Any]:
    from app.providers.base import ChatMessage

    try:
        raw = str(getattr(provider.chat_completion([ChatMessage(role="user", content=prompt)], stream=False),
                          "content", "") or "")
        match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        return json.loads(match.group(0)) if match else {}
    except Exception as exc:
        return {"failed": type(exc).__name__}


def play(turns: int, seed: int) -> list[dict[str, Any]]:
    from rpg_autoplay import PolicyPlayer, view

    from app.apps.rpg.foundation.state import access as sections
    from app.apps.rpg.narration.lore_links import linkable
    from app.apps.rpg.rules.hero_knowledge import known_entries

    session_id = worlds.launch("aurelia")
    client = worlds.turn_client()
    player = PolicyPlayer(seed)
    seen = view(worlds.load(session_id))
    refused: set[str] = set()
    kept = []
    for index in range(1, turns + 1):
        command = player.next(seen, refused)
        before = _d(sections.simulation_state_of(worlds.load(session_id)))
        response = client.post(f"/api/rpg/sessions/{session_id}/turn", json={"command": command})
        body = response.json() if response.status_code == 200 else {}
        visible = _d(body.get("visible_response"))
        after = worlds.load(session_id)
        simulation = _d(sections.simulation_state_of(after))
        world = _d(sections.world_model_of(simulation))
        present = list(_d(sections.present_npc_state_of(simulation)).get("present_npc_ids") or [])
        kept.append({"turn": index, "command": command, "narration": str(visible.get("narration") or ""),
                     "links": list(_d(visible.get("links")).get("narration") or []),
                     "voices": list(_d(visible.get("voices")).get("narration") or []),
                     "candidates": {entry_id: {"family": row.get("family"), "names": row.get("names")}
                                    for entry_id, row in linkable(before).items()},
                     "known": sorted(known_entries(before)),
                     "people": {npc_id: str(_d(_d(world.get("npcs")).get(npc_id)).get("name") or npc_id)
                                for npc_id in present}})
        (refused.discard if response.status_code == 200 else refused.add)(command)
        seen = view(after)
        if index % 25 == 0:
            print(f"{index}/{turns}: links {sum(len(row['links']) for row in kept)}, "
                  f"quotes {sum(len(row['voices']) for row in kept)}", flush=True)
    return kept


def judge(provider: Any, kept: list[dict[str, Any]], *, links: int, responses: int, quotes: int, seed: int) -> dict:
    rng = random.Random(seed)
    every_link = [(row, link) for row in kept for link in row["links"]]
    every_quote = [(row, voice) for row in kept for voice in row["voices"]]
    for row in kept:  # coverage counts mentions of entries the hero knows (roadmap §6)
        row["known_candidates"] = {entry_id: row["candidates"][entry_id]["names"] for entry_id in row["known"]
                                   if entry_id in row["candidates"]}
    with_text = [row for row in kept if row["narration"] and row["known_candidates"]]
    link_rows = []
    for row, link in rng.sample(every_link, min(links, len(every_link))):
        words = row["narration"][link["start"]:link["end"]]
        entry = row["candidates"].get(link["entry_id"]) or {"names": [link["entry_id"]]}
        verdict = ask(provider, LINK_JUDGE.format(words=words, passage=row["narration"],
                                                  entry=json.dumps({"id": link["entry_id"], **entry})))
        link_rows.append({"turn": row["turn"], "words": words, "entry_id": link["entry_id"],
                          "refers": verdict.get("refers"), "failed": verdict.get("failed")})
    coverage_rows = []
    for row in rng.sample(with_text, min(responses, len(with_text))):
        verdict = ask(provider, COVERAGE_JUDGE.format(passage=row["narration"], candidates=json.dumps(
            row["known_candidates"], ensure_ascii=False)))
        mentioned = [str(item) for item in verdict.get("mentioned") or [] if str(item) in row["known_candidates"]]
        linked = {link["entry_id"] for link in row["links"]}
        coverage_rows.append({"turn": row["turn"], "mentioned": mentioned, "linked": sorted(linked),
                              "covered": [entry_id for entry_id in mentioned if entry_id in linked],
                              "failed": verdict.get("failed")})
    quote_rows = []
    for row, voice in rng.sample(every_quote, min(quotes, len(every_quote))):
        quote = row["narration"][voice["start"]:voice["end"]]
        verdict = ask(provider, QUOTE_JUDGE.format(quote=quote, passage=row["narration"],
                                                   people=json.dumps(row["people"], ensure_ascii=False)))
        quote_rows.append({"turn": row["turn"], "quote": quote, "speaker_id": voice["speaker_id"],
                           "judged": verdict.get("speaker_id"), "failed": verdict.get("failed")})
    mentions = sum(len(row["mentioned"]) for row in coverage_rows)
    covered = sum(len(row["covered"]) for row in coverage_rows)
    target = wilson(sum(row["refers"] is True for row in link_rows), len(link_rows))
    speaker = wilson(sum(row["judged"] == row["speaker_id"] for row in quote_rows), len(quote_rows))
    return {
        "right_target": target, "coverage": {"mentions": mentions, "linked": covered,
                                              "rate": round(covered / mentions, 4) if mentions else None},
        "right_speaker": speaker,
        "available": {"links": len(every_link), "quotes": len(every_quote), "responses": len(with_text)},
        "judge_failed": sum(1 for row in [*link_rows, *coverage_rows, *quote_rows] if row.get("failed")),
        "passed": {"right_target": target["rate"] is not None and target["rate"] >= 0.98 and len(link_rows) >= links,
                   "coverage": bool(mentions) and covered / mentions >= 0.90 and len(coverage_rows) >= responses,
                   "right_speaker": speaker["rate"] is not None and speaker["rate"] >= 0.98 and len(quote_rows) >= quotes},
        "link_rows": link_rows, "coverage_rows": coverage_rows, "quote_rows": quote_rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--model", default="haiku")
    parser.add_argument("--effort", default="low", choices=("", "low", "medium", "high", "xhigh", "max"))
    parser.add_argument("--turns", type=int, default=200)
    parser.add_argument("--links", type=int, default=300)
    parser.add_argument("--responses", type=int, default=100)
    parser.add_argument("--quotes", type=int, default=200)
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument("--allow-database", default="")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    os.environ["OMNIX_RPG_TURNS_PER_HOUR"] = "0"
    worlds.require_disposable_database(args.allow_database)
    worlds.bootstrap()
    counter = worlds.install_counting_provider(model=args.model, effort=args.effort)
    started = time.perf_counter()
    kept = play(args.turns, args.seed)
    judged = judge(counter.inner, kept, links=args.links, responses=args.responses, quotes=args.quotes, seed=args.seed)
    result = {"schema_version": 1, "measurement": "RPG lore links and quote voices (EV-12, EV-13)",
              "measured_on": date.today().isoformat(), "world": "aurelia", "provider": worlds.provider_identity(counter),
              "turns": len(kept), "elapsed_s": round(time.perf_counter() - started, 1), **judged, "responses": kept}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8",
                               newline="\n")
    print(json.dumps({key: judged[key] for key in ("right_target", "coverage", "right_speaker", "available",
                                                    "judge_failed", "passed")}, indent=2))


if __name__ == "__main__":
    main()
