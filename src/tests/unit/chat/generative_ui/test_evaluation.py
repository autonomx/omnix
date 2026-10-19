"""Scoring for the rich-reply evaluation (GUI-3.3)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.platform.chat.generative_ui import CompileScope, compile_chat_ui
from app.platform.chat.generative_ui.evaluation import (
    EvalPrompt,
    EvalSample,
    load_prompts,
    report_markdown,
    score_samples,
    wilson_interval,
)

PROMPTS = Path(__file__).resolve().parents[5] / "resources" / "chat" / "generative_ui" / "evaluation" / "prompts.json"
FENCE = "```"
GOOD = f'Numbers.\n\n{FENCE}omnix-ui\n{{"type": "stats", "items": [{{"label": "A", "value": "1"}}]}}\n{FENCE}'
BAD = f"Numbers.\n\n{FENCE}omnix-ui\n{{broken\n{FENCE}"


def sample(label: str, content: str, *, blocks: tuple[str, ...] = ("stats",), latency: float = 1.0) -> EvalSample:
    prompt = EvalPrompt(id=f"{label}-x", label=label, style="data", prompt="?", expected_blocks=blocks if label == "block" else ())
    ui = compile_chat_ui(content, CompileScope(clock=lambda: datetime(2026, 10, 11, tzinfo=timezone.utc)))
    return EvalSample(prompt, content, ui, latency, output_tokens=100)


def test_wilson_interval_matches_known_values():
    lower, upper = wilson_interval(93, 100)
    assert round(lower, 3) == 0.863 and round(upper, 3) == 0.966
    assert wilson_interval(0, 0) == (0.0, 0.0)
    assert wilson_interval(200, 200)[0] > 0.98


def test_scores_validity_precision_recall_and_leakage():
    samples = [
        *[sample("block", GOOD) for _ in range(8)],
        sample("block", BAD),
        sample("block", "Just prose."),
        sample("markdown", GOOD),
        *[sample("markdown", "| a | b |\n|---|---|\n| 1 | 2 |") for _ in range(4)],
        sample("plain", GOOD),
        *[sample("plain", "Hello!") for _ in range(9)],
    ]
    metrics = score_samples(samples, instruction_tokens=400)

    assert (metrics.fences, metrics.valid_blocks) == (11, 10)
    assert metrics.precision == pytest.approx(9 / 11)
    assert metrics.recall == pytest.approx(9 / 10)
    assert metrics.leakage == pytest.approx(0.1)
    assert metrics.diagnostics == {"invalid_json": 1}
    assert not metrics.passed
    assert any(failure.startswith("leakage") for failure in metrics.failures)
    assert any(failure.startswith("valid-block lower bound") for failure in metrics.failures)


def test_a_clean_model_passes_and_basic_counts_only_its_subset():
    samples = [
        *[sample("block", GOOD) for _ in range(120)],
        *[sample("block", "Prose only.", blocks=("form",)) for _ in range(10)],
        *[sample("plain", "Hello!") for _ in range(40)],
    ]
    full = score_samples(samples, instruction_tokens=404)
    basic = score_samples(samples, instruction_tokens=228, level="basic")

    assert full.passed and basic.passed
    assert full.samples == 170 and basic.samples == 160
    assert basic.recall == 1.0 and full.recall == pytest.approx(120 / 130)


def test_errors_are_counted_and_left_out_of_rates():
    failed = EvalSample(EvalPrompt("p", "plain", "chit-chat", "hi"), "", None, 0.0, error="Timeout")
    metrics = score_samples([failed, sample("plain", "Hello!")], instruction_tokens=1)

    assert (metrics.samples, metrics.errors) == (2, 1)
    assert metrics.leakage == 0.0


def test_the_checked_in_prompt_set_is_balanced_and_valid():
    prompts = load_prompts(json.loads(PROMPTS.read_text(encoding="utf-8")))
    labels = [prompt.label for prompt in prompts]

    assert len(prompts) == 40
    assert len({prompt.id for prompt in prompts}) == 40
    assert labels.count("block") >= 15 and labels.count("markdown") >= 10 and labels.count("plain") >= 10
    assert {prompt.style for prompt in prompts} == {"data", "comparison", "how-to", "chit-chat", "trading-research"}
    covered = {block for prompt in prompts for block in prompt.expected_blocks}
    assert covered == {"stats", "chart", "price_chart", "sources", "choices", "form"}
    assert all(prompt.context_items for prompt in prompts if "sources" in prompt.expected_blocks)


def test_unknown_block_types_in_the_prompt_set_are_rejected():
    with pytest.raises(ValueError):
        load_prompts({"prompts": [{"id": "x", "label": "block", "style": "data", "prompt": "?", "expected_blocks": ["table"]}]})


def test_the_report_states_the_verdict_and_the_gate():
    metrics = score_samples([sample("block", GOOD)], instruction_tokens=404)
    report = report_markdown("claude_cli:haiku", "full", metrics, date="2026-10-18", samples_per_prompt=5, prompts=40)

    assert report.startswith("# Rich-reply evaluation: claude_cli:haiku (full) — 2026-10-18")
    assert "Gate: FAILED" in report
    assert "lower bound ≥ 0.93" in report


def test_the_report_counts_whole_replies_and_names_resolved_models():
    good = sample("block", GOOD)
    mixed = sample("block", GOOD + "\n\n" + BAD)
    metrics = score_samples([
        EvalSample(good.prompt, good.content, good.ui, 1.0, resolved_model="claude-haiku-x"),
        EvalSample(mixed.prompt, mixed.content, mixed.ui, 1.0, resolved_model="claude-haiku-x"),
    ], instruction_tokens=1)

    assert (metrics.replies_with_blocks, metrics.replies_all_valid) == (2, 1)
    assert metrics.resolved_models == ["claude-haiku-x"]
    report = report_markdown("m", "full", metrics, date="2026-10-19", samples_per_prompt=1, prompts=2)
    assert "| Replies whose blocks all rendered | 1/2 |" in report
    assert "`claude-haiku-x`" in report
