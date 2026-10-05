"""Default agent run limits come from the settings (owner decision)."""
from __future__ import annotations

from app.agent_runtime import budget
from app.agent_runtime.contracts import AgentRunSpec, ModelRef, RunLimits
from app.settings.profile_experience import AgentRunSettingsProfile
from app.settings.profile_models import SettingsProfile


def _spec(limits: RunLimits) -> AgentRunSpec:
    return AgentRunSpec(run_id="run-1", task="t", model=ModelRef(provider_id="lmstudio", model_id="m"), limits=limits)


def test_unset_limits_take_the_settings_defaults(monkeypatch) -> None:
    monkeypatch.setattr(budget, "_agent_run_settings", lambda: AgentRunSettingsProfile(
        default_max_output_tokens=50_000, default_max_cost_usd=2.5,
    ))

    filled = budget.apply_default_run_limits(_spec(RunLimits()))
    explicit = budget.apply_default_run_limits(_spec(RunLimits(max_tokens=10, max_cost=0.1)))

    assert (filled.limits.max_tokens, filled.limits.max_cost) == (50_000, 2.5)
    assert (explicit.limits.max_tokens, explicit.limits.max_cost) == (10, 0.1)
    assert filled.limits.max_steps == RunLimits().max_steps


def test_without_defaults_runs_stay_unlimited(monkeypatch) -> None:
    monkeypatch.setattr(budget, "_agent_run_settings", lambda: AgentRunSettingsProfile())
    spec = _spec(RunLimits())

    assert budget.apply_default_run_limits(spec) is spec


def test_unreadable_settings_leave_the_spec_unchanged(monkeypatch) -> None:
    def unavailable():
        raise RuntimeError("settings store unavailable")

    monkeypatch.setattr(budget, "_agent_run_settings", unavailable)
    spec = _spec(RunLimits())

    assert budget.apply_default_run_limits(spec) is spec
    assert budget.provider_price("openrouter") is None


def test_the_settings_document_accepts_the_agent_run_section() -> None:
    profile = SettingsProfile.model_validate({"agentRuns": {
        "defaultMaxOutputTokens": 1000, "defaultMaxCostUsd": 1.5,
        "providerPrices": {"openrouter": {"inputUsdPerMillion": 0.5, "outputUsdPerMillion": 1.5}},
    }})

    assert profile.agent_runs.default_max_output_tokens == 1000
    assert profile.agent_runs.provider_prices["openrouter"].output_usd_per_million == 1.5
    assert SettingsProfile().agent_runs.default_max_cost_usd is None
