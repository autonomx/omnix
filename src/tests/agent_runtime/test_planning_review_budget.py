from __future__ import annotations

from types import SimpleNamespace

from app.agent_runtime import planning_review


class _Budget:
    def __init__(self) -> None:
        self.authorizations: list[tuple[str, str]] = []
        self.tokens: list[tuple[str, int | None, int | None]] = []

    def authorize_model_call(self, run_id: str, *, provider_id: str):
        self.authorizations.append((run_id, provider_id))
        return {"model_calls": len(self.authorizations)}

    def record_token_usage(
        self,
        run_id: str,
        *,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ):
        self.tokens.append((run_id, input_tokens, output_tokens))
        return {"output_tokens": output_tokens or 0}


class _Provider:
    provider_name = "chatgpt_codex"

    def __init__(self) -> None:
        self.calls = 0
        self.config = SimpleNamespace(model="gpt-5.6-luna")

    def chat_completion(self, *args, **kwargs):
        del args, kwargs
        self.calls += 1
        return SimpleNamespace(
            usage={
                "prompt_tokens": 101 + self.calls,
                "completion_tokens": 20 + self.calls,
            }
        )


def test_budgeted_review_provider_charges_every_provider_attempt(monkeypatch) -> None:
    budget = _Budget()
    provider = _Provider()
    monkeypatch.setattr(planning_review, "default_agent_budget_manager", lambda: budget)
    wrapped = planning_review._BudgetedReviewProvider(
        provider,
        run_id="run-review-budget",
        provider_id="llm:chatgpt_codex",
    )

    wrapped.chat_completion([])
    wrapped.chat_completion([])

    assert provider.calls == 2
    assert budget.authorizations == [
        ("run-review-budget", "llm:chatgpt_codex"),
        ("run-review-budget", "llm:chatgpt_codex"),
    ]
    assert budget.tokens == [
        ("run-review-budget", 102, 21),
        ("run-review-budget", 103, 22),
    ]


def test_budgeted_review_provider_delegates_capability_attributes(monkeypatch) -> None:
    budget = _Budget()
    provider = _Provider()
    provider.structured_capabilities = lambda model=None: {"model": model}
    monkeypatch.setattr(planning_review, "default_agent_budget_manager", lambda: budget)
    wrapped = planning_review._BudgetedReviewProvider(
        provider,
        run_id="run-review-budget",
        provider_id="llm:chatgpt_codex",
    )

    assert wrapped.provider_name == "chatgpt_codex"
    assert wrapped.config.model == "gpt-5.6-luna"
    assert wrapped.structured_capabilities(model="gpt-5.6-luna") == {
        "model": "gpt-5.6-luna"
    }
