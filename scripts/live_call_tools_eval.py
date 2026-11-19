"""Does a call's model ask for research and actions when it should, and only then? (companion roadmap 1.6)

Each labelled remark is sent the way a live turn is: the abilities' instructions in the system prompt, the actions
catalog and the call's task list in the per-turn part (``live_voice.pipeline``), ``live_turn`` set, and the real
provider. The reply goes through the call's own ``RequestGate``; an action's input is checked by
``check_voice_action``. Every ability is granted, so a wrong start is the model's choice, not a missing grant.

The character prompt is a short stand-in: a real call also carries its persona, memories and spoken style.

    python scripts/live_call_tools_eval.py --provider claude-cli --model haiku --effort low
    python scripts/live_call_tools_eval.py --provider lmstudio --base-url http://127.0.0.1:1234
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

PERSONA = ("You are Omnix, the person's assistant, talking with them on a voice call. Speak naturally and briefly, "
           "in one or two short sentences, as speech: no lists, no markdown.")
CONTEXT = {
    "current_datetime": "2026-11-15T14:00:00+00:00",
    "user_timezone": "Europe/London",
    "calendar_rule": ("Never infer a missing date, AM/PM choice, duration, or attendee. Return no action when "
                      "clarification is required."),
}
STORY = [
    ("user", "Let's play a story. You're the captain of a pirate ship and I'm your first mate."),
    ("assistant", "Aye, first mate! The fog's rolling in thick tonight and the lanterns are swinging."),
]
TASKS = "tasks"  # the call already has research running and a proposal waiting


@dataclass(frozen=True)
class Item:
    remark: str
    expect: str  # "none", "lookup", "research" or "do:<capability>"
    history: list[tuple[str, str]] = field(default_factory=list)
    setup: str = ""


ITEMS: list[Item] = [
    # Real asks for an action.
    Item("Turn off the desk lamp.", "do:home.set_state"),
    Item("Can you switch the fan on for me?", "do:home.set_state"),
    Item("Is the bedroom light still on?", "do:home.get_state"),
    Item("What devices do you control in my house?", "do:home.list_devices"),
    Item("Put the hallway light on, please.", "do:home.set_state"),
    Item("Am I free tomorrow between nine and eleven in the morning?", "do:calendar.read_availability"),
    Item("Add dentist to my calendar on Tuesday the 17th from 3 to 4 pm.", "do:calendar.create_event"),
    Item("What's on my calendar this afternoon, from two to six?", "do:calendar.read_availability"),
    Item("Book lunch with Sam on Friday the 20th, 12:30 to 1:30.", "do:calendar.create_event"),
    Item("Turn the kitchen plug off.", "do:home.set_state"),
    # Real asks for research.
    Item("Can you research the best electric kettles under fifty pounds for me?", "research"),
    Item("Dig into whether heat pumps are worth it for an old house in the UK.", "research"),
    Item("Please do a proper deep dive on the history of the Suez Canal crisis.", "research"),
    Item("Research which e-bikes have the longest range this year, properly.", "research"),
    Item("I want you to look into the evidence on intermittent fasting, in depth.", "research"),
    # Real asks for a quick look.
    Item("What's the weather in London today?", "lookup"),
    Item("Who won the football last night, Arsenal against Chelsea?", "lookup"),
    Item("What time does the Tesco on the high street close on Sundays?", "lookup"),
    # Small talk and what the model knows.
    Item("Hi, how are you doing?", "none"),
    Item("I'm so tired today.", "none"),
    Item("Tell me a joke.", "none"),
    Item("What's the capital of France?", "none"),
    Item("I turned the lights off before I came to bed.", "none"),
    Item("My calendar is a mess this week.", "none"),
    Item("I was reading about kettles earlier, they're so expensive.", "none"),
    Item("Thanks, that's all for now.", "none"),
    Item("Do you think research is overrated?", "none"),
    # A missing detail: ask first.
    Item("Add a meeting to my calendar.", "none"),
    Item("Put the gym in my diary on Thursday.", "none"),
    Item("Turn it off.", "none"),
    # Role-play lines that mention lights, calendars or research.
    Item("Captain, should we turn off the lanterns so they can't see us?", "none", STORY),
    Item("Douse the lights, men! Every one of them!", "none", STORY),
    Item("Mark the day we reach the island in the ship's log.", "none", STORY),
    Item("Let's research the old treasure map in your cabin.", "none", STORY),
    Item("Switch on the beacon at the bow, captain?", "none", STORY),
    # Running tasks in the per-turn prompt: a question about one starts nothing new.
    Item("How's that kettle research going?", "none", setup=TASKS),
    Item("Did the lamp go off?", "none", setup=TASKS),
    Item("Is the research done yet?", "none", setup=TASKS),
    Item("Okay, while that runs, what's a good film to watch tonight?", "none", setup=TASKS),
    Item("And can you also check if the fan is on?", "do:home.get_state", setup=TASKS),
]


def _task_state() -> str:
    from app.platform.chat.live_call_tasks import call_tasks_prompt

    def message(message_id: str, at: str, **metadata: Any) -> SimpleNamespace:
        return SimpleNamespace(id=message_id, role="assistant", content="Turn off Desk lamp? Say confirm or cancel.",
                               created_at=at, metadata=metadata)

    session = SimpleNamespace(messages=[
        message("reply", "2026-11-15T13:55:00+00:00", reply_to_message_id="u1", call_tasks=[
            {"index": 0, "ability": "deep_research", "query": "best electric kettles under fifty pounds",
             "allowed": True, "start": "started", "job_id": "j0"},
            {"index": 1, "ability": "smart_home", "capability": "home.set_state", "query": "turn off Desk lamp",
             "allowed": True, "start": "started", "job_id": "j1"}]),
        message("proposal", "2026-11-15T13:56:00+00:00", call_task_id="call-task:u1:1",
                governed_proposal_origin="live_call", governed_tool_execution_status="pending",
                report_started_at="2026-11-15T13:59:30+00:00"),
    ])
    jobs = SimpleNamespace(get_job=lambda job_id: SimpleNamespace(
        status="running" if job_id == "j0" else "completed", completed_at="2026-11-15T13:56:00+00:00",
        updated_at=None))
    text = call_tasks_prompt(session, jobs, now=datetime(2026, 11, 15, 14, 0, tzinfo=timezone.utc))
    assert text, "the task list must render"
    return text


def _messages(item: Item, tasks_text: str) -> list[Any]:
    from app.platform.assistant_tools.voice_actions import voice_action_catalog
    from app.platform.live_voice.llm.call_tools import abilities_prompt
    from app.providers import ChatMessage

    grants = {"web_search": True, "deep_research": True, "smart_home": True, "calendar": True}
    messages = [ChatMessage(role="system", content=PERSONA),
                ChatMessage(role="system", content=abilities_prompt(grants) or ""),
                ChatMessage(role="system", content=voice_action_catalog(grants, CONTEXT) or "", per_turn=True)]
    if item.setup == TASKS:
        messages.append(ChatMessage(role="system", content=tasks_text, per_turn=True))
        messages += [ChatMessage(role="user", content="Research the best electric kettles, and turn off the desk lamp."),
                     ChatMessage(role="assistant", content="On it, I'll dig into kettles.")]
    messages += [ChatMessage(role=role, content=content) for role, content in item.history]
    messages.append(ChatMessage(role="user", content=item.remark))
    return messages


def _provider(args: argparse.Namespace) -> tuple[Any, dict[str, Any]]:
    from app.providers.base import ProviderConfig

    if args.provider == "claude-cli":
        from app.providers.claude_cli_provider import ClaudeCliProvider

        extra = {"effort": args.effort} if args.effort else {}
        return ClaudeCliProvider(ProviderConfig(provider_type="claude-cli", model=args.model,
                                                extra_params=extra)), {"live_turn": True}
    from app.providers.lmstudio_provider import LMStudioProvider

    # What a spoken turn sends LM Studio (``live_voice.llm.policy``).
    return LMStudioProvider(ProviderConfig(provider_type="lmstudio", base_url=args.base_url, model=args.model)), {
        "chat_template_kwargs": {"enable_thinking": False}}


def _kind(request: Any) -> str:
    if request is None:
        return "none"
    if request.capability:
        return f"do:{request.capability}"
    return {"web_search": "lookup", "deep_research": "research"}.get(request.ability, request.ability)


def _run_one(provider: Any, options: dict[str, Any], item: Item, tasks_text: str, model: str | None,
             timeout: float) -> dict[str, Any]:
    from app.platform.assistant_tools.voice_actions import check_voice_action
    from app.platform.live_voice.llm.call_tools import RequestGate

    gate = RequestGate()
    started = time.perf_counter()
    first: float | None = None
    text = ""
    error = ""
    try:
        for chunk in provider.chat_completion(messages=_messages(item, tasks_text), model=model, stream=True,
                                              request_timeout_seconds=timeout, **options):
            piece = str(getattr(chunk, "content", "") or "")
            if piece and first is None:
                first = time.perf_counter() - started
            text += piece
            gate.push(piece)
        gate.finish()
    except Exception as exc:  # noqa: BLE001 - recorded as a miss, the run goes on
        error = f"{type(exc).__name__}: {exc}"[:300]
    kind = _kind(gate.request)
    valid = None
    if gate.request is not None and gate.request.capability:
        grants = {"smart_home": True, "calendar": True}
        valid = check_voice_action(gate.request.capability, gate.request.input, grants).ok
    return {"remark": item.remark, "expect": item.expect, "got": kind, "input_valid": valid,
            "correct": kind == item.expect and valid is not False and not error, "error": error,
            "first_text_s": round(first, 2) if first is not None else None,
            "seconds": round(time.perf_counter() - started, 2), "reply": text.strip()[:400],
            "setup": item.setup or ("story" if item.history else "")}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--provider", choices=("claude-cli", "lmstudio"), required=True)
    parser.add_argument("--model", default=None)
    parser.add_argument("--effort", default="low")
    parser.add_argument("--base-url", default="http://127.0.0.1:1234")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--limit", type=int, default=0, help="run only the first N remarks")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    provider, options = _provider(args)
    tasks_text = _task_state()
    rows = []
    for item in ITEMS[: args.limit or None]:
        row = _run_one(provider, options, item, tasks_text, args.model, args.timeout)
        rows.append(row)
        mark = "ok " if row["correct"] else "BAD"
        print(f"{mark} {row['expect']:<32} got {row['got']:<32} {row['seconds']:>5}s  {row['remark']}"
              + (f"  [{row['error']}]" if row["error"] else ""), flush=True)

    def share(selected: list[dict[str, Any]]) -> str:
        return f"{sum(r['correct'] for r in selected)}/{len(selected)}"

    asks = [r for r in rows if r["expect"] != "none"]
    quiet = [r for r in rows if r["expect"] == "none"]
    actions = [r for r in rows if r["got"].startswith("do:")]
    firsts = sorted(r["first_text_s"] for r in rows if r["first_text_s"] is not None)
    summary = {
        "provider": args.provider, "model": args.model, "effort": args.effort if args.provider == "claude-cli" else "",
        "correct": share(rows), "asks_started": share(asks),
        "false_starts": sum(r["got"] != "none" for r in quiet), "of_quiet": len(quiet),
        "action_inputs_valid": f"{sum(bool(r['input_valid']) for r in actions)}/{len(actions)}",
        "role_play_false_starts": sum(r["got"] != "none" for r in quiet if r["setup"] == "story"),
        "errors": sum(bool(r["error"]) for r in rows),
        "first_text_median_s": firsts[len(firsts) // 2] if firsts else None,
        "first_text_max_s": firsts[-1] if firsts else None,
    }
    print(json.dumps(summary, indent=2))
    if args.output:
        args.output.write_text(json.dumps({"summary": summary, "rows": rows}, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
