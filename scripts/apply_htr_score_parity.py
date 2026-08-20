from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise RuntimeError(f"HTR score parity anchor mismatch in {path}: {text.count(old)}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> None:
    replace_once(
        "src/app/trading/strategy_monitor.py",
        "from .strategy_research_policy import resolve_strategy_research_policy\n",
        "from .strategy_research_policy import apply_research_policy_to_quality, resolve_strategy_research_policy\n",
    )
    replace_once(
        "src/app/trading/strategy_monitor.py",
        '''                    else:\n                        reason_code = research_decision.reason_code\n                        detail = None\n                    allowed = research_decision is not None and research_decision.allowed\n                    payload = {\n                        "strategy_version": config.config.strategy_version,\n                        "policy_version": (\n                            research_decision.policy_version if research_decision is not None else "trading-research-1"\n                        ),\n                        "authoritative": True,\n                        "allowed": allowed,\n                        "score_adjustment": (\n                            research_decision.score_adjustment if research_decision is not None else 0\n                        ),\n                        "detail": detail,\n                        "decision_at": observed_at,\n                    }\n''',
        '''                    else:\n                        quality_gate = apply_research_policy_to_quality(\n                            research_decision,\n                            base_quality_score=result.features.quality_score,\n                            minimum_quality_score=config.config.minimum_quality_score,\n                        )\n                        reason_code = quality_gate.reason_code\n                        detail = None\n                    allowed = quality_gate.allowed if research_decision is not None else False\n                    payload = {\n                        "strategy_version": config.config.strategy_version,\n                        "policy_version": (\n                            research_decision.policy_version if research_decision is not None else "trading-research-1"\n                        ),\n                        "authoritative": True,\n                        "allowed": allowed,\n                        "score_adjustment": (\n                            quality_gate.score_adjustment if research_decision is not None else 0\n                        ),\n                        "base_quality_score": (\n                            quality_gate.base_quality_score if research_decision is not None else result.features.quality_score\n                        ),\n                        "adjusted_quality_score": (\n                            quality_gate.adjusted_quality_score if research_decision is not None else result.features.quality_score\n                        ),\n                        "minimum_quality_score": config.config.minimum_quality_score,\n                        "detail": detail,\n                        "decision_at": observed_at,\n                    }\n''',
    )
    replace_once(
        "src/app/trading/strategy_backtest.py",
        "from .research.policy import ResearchPolicyDecision\n",
        "from .research.policy import ResearchPolicyDecision\nfrom .strategy_research_policy import apply_research_policy_to_quality\n",
    )
    replace_once(
        "src/app/trading/strategy_backtest.py",
        '''                else:\n                    research_reason = None if research_decision.allowed else research_decision.reason_code\n            if research_reason is not None:\n                research_rejections[research_reason] = research_rejections.get(research_reason, 0) + 1\n                continue\n''',
        '''                else:\n                    quality_gate = apply_research_policy_to_quality(\n                        research_decision,\n                        base_quality_score=proposal.quality_score,\n                        minimum_quality_score=active.minimum_quality_score,\n                    )\n                    research_reason = None if quality_gate.allowed else quality_gate.reason_code\n            if research_reason is not None:\n                research_rejections[research_reason] = research_rejections.get(research_reason, 0) + 1\n                continue\n''',
    )
    Path(__file__).unlink()


if __name__ == "__main__":
    main()
