"""Rich-reply evaluation harness (chat generative UI, GUI-3.3). Opt-in: calls live providers.

Run one or more models, each at the level to test, for example:

    OMNIX_GUI_EVAL_MODELS="claude_cli:haiku=full,lmstudio:qwen3-8b=basic" \\
    python -m pytest src/tests/evaluation/test_generative_ui_eval.py -m gui_eval -n 0 -s

Each prompt in ``resources/chat/generative_ui/evaluation/prompts.json`` is sampled
``OMNIX_GUI_EVAL_SAMPLES`` times (default 5) through the real prompt assembly with
rich replies enabled; replies are compiled as the save paths compile them. A
dated report per model is written to ``docs/roadmap/evaluations/`` (or
``OMNIX_GUI_EVAL_OUTPUT``). A model's ``rich_ui`` level is set in
``app/providers/model_catalog.py`` only from a report that passed the gate.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.platform.chat import ChatMessage, ChatSession
from app.platform.chat.generative_ui import finalize_reply_ui
from app.platform.chat.generative_ui.evaluation import EvalSample, load_prompts, report_markdown, score_samples
from app.platform.chat.generative_ui.prompting import RichReplyDecision, catalog_instruction_tokens
from app.platform.chat.prompt_assembly import build_prompt_assembly
from app.platform.chat.prompt_rendering import render_prompt_assembly

pytestmark = [
    pytest.mark.gui_eval,
    pytest.mark.live_provider,
    pytest.mark.skipif(not os.environ.get("OMNIX_GUI_EVAL_MODELS"), reason="set OMNIX_GUI_EVAL_MODELS to run the rich-reply evaluation"),
]

ROOT = Path(__file__).resolve().parents[3]
PROMPTS = ROOT / "resources" / "chat" / "generative_ui" / "evaluation" / "prompts.json"
SYSTEM_PROMPT = "You are Omnix, a helpful assistant. Answer clearly and concisely."


class AnySymbol:
    """Every well-formed symbol is known: the evaluation measures how the model writes blocks,
    not catalog coverage, and makes no market-data calls."""

    def instrument_id(self, symbol: str) -> str | None:
        return f"equity:EVAL:{symbol}"


def _models() -> list[tuple[str, str, str]]:
    models = []
    for entry in os.environ.get("OMNIX_GUI_EVAL_MODELS", "").split(","):
        if not entry.strip():
            continue
        target, _, level = entry.strip().partition("=")
        provider, _, model = target.partition(":")
        models.append((provider.strip(), model.strip(), (level or "full").strip()))
    return models


def _messages(prompt, level: str):
    from app.providers import ChatMessage as ProviderMessage

    now = datetime.now(timezone.utc).isoformat()
    session = ChatSession(id="chat:gui-eval", title="eval", created_at=now, updated_at=now, rich_replies="on")
    user = ChatMessage(id="msg:eval", role="user", content=prompt.prompt, created_at=now)
    assembly = build_prompt_assembly(
        session, user, global_system_prompt=SYSTEM_PROMPT,
        context_items=[dict(item) for item in prompt.context_items],
        rich_replies=RichReplyDecision(True, level, "evaluation"),  # type: ignore[arg-type]
    )
    return [ProviderMessage(role=message.role, content=message.content) for message in render_prompt_assembly(assembly).messages]


def _sample(provider, model: str, prompt, level: str) -> EvalSample:
    started = time.perf_counter()
    try:
        response = provider.chat_completion(messages=_messages(prompt, level), model=model, stream=False)
    except Exception as exc:  # a provider failure is counted, not fatal
        return EvalSample(prompt, "", None, time.perf_counter() - started, error=f"{type(exc).__name__}: {exc}"[:300])
    latency = time.perf_counter() - started
    content = (getattr(response, "content", "") or "").strip()
    usage = getattr(response, "usage", None) or {}
    tokens = usage.get("completion_tokens") or usage.get("output_tokens") if isinstance(usage, dict) else None
    ui = finalize_reply_ui(content, {}, context_items=[dict(item) for item in prompt.context_items], symbol_lookup=AnySymbol()).get("ui")
    resolved = getattr(response, "model", None)
    return EvalSample(
        prompt, content, ui, latency, tokens if isinstance(tokens, int) else None,
        resolved_model=str(resolved) if resolved else None,
    )


@pytest.mark.parametrize(("provider_id", "model", "level"), _models())
def test_rich_reply_evaluation(provider_id: str, model: str, level: str) -> None:
    from app.providers.service import get_routed_provider

    provider = get_routed_provider(provider_id, model)
    assert provider is not None, f"provider {provider_id} is not available"
    prompts = load_prompts(json.loads(PROMPTS.read_text(encoding="utf-8")))
    samples_per_prompt = int(os.environ.get("OMNIX_GUI_EVAL_SAMPLES", "5"))
    samples = [_sample(provider, model, prompt, level) for prompt in prompts for _ in range(samples_per_prompt)]
    metrics = score_samples(samples, instruction_tokens=catalog_instruction_tokens(level), level=level)  # type: ignore[arg-type]

    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    output = Path(os.environ.get("OMNIX_GUI_EVAL_OUTPUT", ROOT / "docs" / "roadmap" / "evaluations"))
    output.mkdir(parents=True, exist_ok=True)
    stem = f"GUI_EVAL_{date}_{provider_id}_{model}_{level}".replace(":", "-").replace("/", "-")
    label = f"{provider_id}:{model}"
    (output / f"{stem}.md").write_text(
        report_markdown(label, level, metrics, date=date, samples_per_prompt=samples_per_prompt, prompts=len(prompts)),
        encoding="utf-8",
    )
    (output / f"{stem}.json").write_text(json.dumps({
        "model": label, "level": level, "date": date, "metrics": metrics.as_dict(),
        "samples": [
            {"prompt": sample.prompt.id, "label": sample.prompt.label, "latency_seconds": round(sample.latency_seconds, 3),
             "error": sample.error, "content": sample.content,
             "diagnostics": (sample.ui or {}).get("diagnostics", []), "blocks": len((sample.ui or {}).get("blocks", {}))}
            for sample in samples
        ],
    }, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\n{label} ({level}): {'PASSED' if metrics.passed else 'FAILED'} {metrics.failures}")
    assert metrics.samples == len(samples)
