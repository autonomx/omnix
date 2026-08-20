from __future__ import annotations

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if old not in text:
        if new in text:
            return
        raise RuntimeError(f"anchor not found in {path}: {old[:120]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


# HTR-14: recommendation safety floors are invariant; operator/reporting inputs
# may raise them, never lower them. Per-feature sample sizes count only labeled
# binary observations, so missing/unknown values cannot manufacture power.
replace(
    "src/app/trading/research/validation.py",
    '_EXACT_RESEARCH = {"captured_exact", "exact"}\n',
    '_EXACT_RESEARCH = {"captured_exact", "exact"}\n_MIN_PROMOTION_SAMPLE = 100\n_MIN_PROMOTION_EXACT_SAMPLE = 50\n',
)
replace(
    "src/app/trading/research/validation.py",
    '    chronological = sorted(\n',
    '    minimum_sample = max(_MIN_PROMOTION_SAMPLE, int(minimum_sample))\n'
    '    minimum_exact_sample = max(_MIN_PROMOTION_EXACT_SAMPLE, int(minimum_exact_sample))\n'
    '    chronological = sorted(\n',
)
replace(
    "src/app/trading/research/validation.py",
    '        n = sum(1 for row in outcomes if key in (row.get("features") or {}))\n'
    '        exact_n = sum(1 for row in exact if key in (row.get("features") or {}))\n',
    '        n = sum(\n'
    '            1 for row in outcomes\n'
    '            if isinstance((row.get("features") or {}).get(key), bool) and _r(row) is not None\n'
    '        )\n'
    '        exact_n = sum(\n'
    '            1 for row in exact\n'
    '            if isinstance((row.get("features") or {}).get(key), bool) and _r(row) is not None\n'
    '        )\n',
)
replace(
    "src/app/trading/research/validation.py",
    '            "Recommended authority tiers are statistical candidates only; review may preserve or reduce, never strengthen, those tiers.",\n',
    '            "Recommended authority tiers are statistical candidates only; review may preserve or reduce, never strengthen, those tiers.",\n'
    '            "Promotion recommendation floors are at least 100 labeled observations and 50 exact/captured labeled observations per feature; caller inputs may raise but never lower those floors.",\n'
    '            "Per-feature sample counts exclude missing/unknown feature values and outcomes without an R label.",\n',
)

# Pin HTR-15 authority to the first explicitly reviewed artifact for a policy
# version. Later analysis must use a new research_policy_version rather than
# silently changing an already-authoritative policy.
replace(
    "src/app/trading/research/fact_repository.py",
    '    def latest_validation_report(self, policy_version: str) -> ResearchValidationReport | None:\n',
    '    def promoted_validation_report(self, policy_version: str) -> ResearchValidationReport | None:\n'
    '        with self.uow_factory() as uow:\n'
    '            r=uow.connection.execute("SELECT validation_id,policy_version,generated_at,sample_size,exact_sample_size,feature_results,promotion_allowed,notes,immutable_fingerprint FROM omnix_trading_research_validation_reports WHERE workspace_id=%s AND policy_version=%s AND promotion_allowed=TRUE ORDER BY generated_at ASC LIMIT 1",(self.context.workspace_id,policy_version)).fetchone()\n'
    '        if r is None:return None\n'
    '        return ResearchValidationReport(validation_id=r[0],policy_version=r[1],generated_at=r[2],sample_size=r[3],exact_sample_size=r[4],\n'
    '            feature_results=tuple(ValidationFeatureResult.model_validate(x) for x in r[5]),promotion_allowed=r[6],notes=tuple(r[7]),immutable_fingerprint=r[8])\n\n'
    '    def latest_validation_report(self, policy_version: str) -> ResearchValidationReport | None:\n',
)
replace(
    "src/app/trading/strategy_research_policy.py",
    '    validation = repository.latest_validation_report(policy_version)\n',
    '    validation = repository.promoted_validation_report(policy_version)\n',
)
replace(
    "src/app/trading/hermes_research_api.py",
    '    async def validate(request: ValidationInput):\n'
    '        repo=fact_repository_factory(); values=await asyncio.to_thread(repo.outcomes,request.strategy_id,100000)\n',
    '    async def validate(request: ValidationInput):\n'
    '        repo=fact_repository_factory()\n'
    '        promoted=await asyncio.to_thread(repo.promoted_validation_report,request.policy_version)\n'
    '        if promoted is not None:\n'
    '            raise HTTPException(status_code=409,detail="research_policy_version_already_promoted_use_new_version")\n'
    '        values=await asyncio.to_thread(repo.outcomes,request.strategy_id,100000)\n',
)
replace(
    "src/app/trading/hermes_research_api.py",
    '    async def review_validation(request: ReviewValidationInput):\n'
    '        repo=fact_repository_factory()\n'
    '        source=await asyncio.to_thread(repo.latest_validation_report,request.policy_version)\n',
    '    async def review_validation(request: ReviewValidationInput):\n'
    '        repo=fact_repository_factory()\n'
    '        promoted=await asyncio.to_thread(repo.promoted_validation_report,request.policy_version)\n'
    '        if promoted is not None:\n'
    '            raise HTTPException(status_code=409,detail="research_policy_version_already_promoted_use_new_version")\n'
    '        source=await asyncio.to_thread(repo.latest_validation_report,request.policy_version)\n',
)
replace(
    "src/app/trading/hermes_research_api.py",
    '        validation=await asyncio.to_thread(repo.latest_validation_report,policy_version)\n'
    '        decision=evaluate_research_policy(strategy_version=strategy_version,features=features,validation=validation,policy_version=policy_version)\n',
    '        validation=await asyncio.to_thread(\n'
    '            repo.promoted_validation_report if strategy_version == "1.2.0" else repo.latest_validation_report,\n'
    '            policy_version,\n'
    '        )\n'
    '        decision=evaluate_research_policy(strategy_version=strategy_version,features=features,validation=validation,policy_version=policy_version)\n',
)

# Strategy document/version must be one semantic version, not two independently
# writable strings that different runtime paths can interpret differently.
replace(
    "src/app/trading/strategy_repository.py",
    'from pydantic import BaseModel, ConfigDict, Field\n',
    'from pydantic import BaseModel, ConfigDict, Field, model_validator\n',
)
replace(
    "src/app/trading/strategy_repository.py",
    '    updated_at: datetime | None = None\n\n\nclass StrategyEvent',
    '    updated_at: datetime | None = None\n\n'
    '    @model_validator(mode="after")\n'
    '    def validate_strategy_version_alignment(self):\n'
    '        if self.strategy_version != self.config.strategy_version:\n'
    '            raise ValueError("strategy_version_mismatch_between_document_and_config")\n'
    '        return self\n\n\nclass StrategyEvent',
)

# AUTO PAPER: once HTR-15 adjusts quality, surviving candidates must carry the
# adjusted score into arbitration, not revert to the pre-research score.
replace(
    "src/app/trading/strategy_monitor.py",
    '                    allowed = quality_gate.allowed if research_decision is not None else False\n'
    '                    payload = {\n',
    '                    allowed = quality_gate.allowed if research_decision is not None else False\n'
    '                    if allowed and research_decision is not None and result.signal is not None:\n'
    '                        adjusted_quality = quality_gate.adjusted_quality_score\n'
    '                        result = result.model_copy(update={\n'
    '                            "features": result.features.model_copy(update={"quality_score": adjusted_quality}),\n'
    '                            "signal": result.signal.model_copy(update={"quality_score": adjusted_quality}),\n'
    '                        })\n'
    '                    payload = {\n',
)

# Backtest: apply the same HTR quality adjustment before portfolio arbitration,
# use it for risk signal quality, and persist it on the selected trade.
replace(
    "src/app/trading/strategy_backtest.py",
    '    proposed.sort(\n'
    '        key=lambda item: proposal_priority(\n'
    '            observed_at=item[1].entry_time,\n'
    '            quality_score=item[1].quality_score,\n'
    '            discovery_rank=item[0].discovery_rank,\n'
    '            instrument_id=item[1].instrument_id,\n'
    '        )\n'
    '    )\n\n'
    '    selected: list[GapPullbackBacktestTrade] = []\n'
    '    risk_rejections: dict[str, int] = {}\n'
    '    research_rejections: dict[str, int] = {}\n'
    '    execution_rejections: list[str] = []\n'
    '    for candidate, proposal in proposed:\n'
    '        if active.strategy_version == "1.2.0":\n'
    '            if research_policy_resolver is None:\n'
    '                research_reason = "RESEARCH_POLICY_RESOLVER_UNAVAILABLE"\n'
    '            else:\n'
    '                try:\n'
    '                    research_decision = research_policy_resolver(proposal.instrument_id, proposal.entry_time)\n'
    '                except Exception:\n'
    '                    research_reason = "RESEARCH_POLICY_RESOLUTION_ERROR"\n'
    '                else:\n'
    '                    quality_gate = apply_research_policy_to_quality(\n'
    '                        research_decision,\n'
    '                        base_quality_score=proposal.quality_score,\n'
    '                        minimum_quality_score=active.minimum_quality_score,\n'
    '                    )\n'
    '                    research_reason = None if quality_gate.allowed else quality_gate.reason_code\n'
    '            if research_reason is not None:\n'
    '                research_rejections[research_reason] = research_rejections.get(research_reason, 0) + 1\n'
    '                continue\n'
    '        snapshot, realized, open_risk, active_symbols = _virtual_snapshot(\n',
    '    selected: list[GapPullbackBacktestTrade] = []\n'
    '    risk_rejections: dict[str, int] = {}\n'
    '    research_rejections: dict[str, int] = {}\n'
    '    execution_rejections: list[str] = []\n'
    '    ranked_proposals: list[tuple[object, GapPullbackBacktestTrade, int]] = []\n'
    '    for candidate, proposal in proposed:\n'
    '        adjusted_quality_score = proposal.quality_score\n'
    '        if active.strategy_version == "1.2.0":\n'
    '            if research_policy_resolver is None:\n'
    '                research_reason = "RESEARCH_POLICY_RESOLVER_UNAVAILABLE"\n'
    '            else:\n'
    '                try:\n'
    '                    research_decision = research_policy_resolver(proposal.instrument_id, proposal.entry_time)\n'
    '                except Exception:\n'
    '                    research_reason = "RESEARCH_POLICY_RESOLUTION_ERROR"\n'
    '                else:\n'
    '                    quality_gate = apply_research_policy_to_quality(\n'
    '                        research_decision,\n'
    '                        base_quality_score=proposal.quality_score,\n'
    '                        minimum_quality_score=active.minimum_quality_score,\n'
    '                    )\n'
    '                    research_reason = None if quality_gate.allowed else quality_gate.reason_code\n'
    '                    adjusted_quality_score = quality_gate.adjusted_quality_score\n'
    '            if research_reason is not None:\n'
    '                research_rejections[research_reason] = research_rejections.get(research_reason, 0) + 1\n'
    '                continue\n'
    '        ranked_proposals.append((candidate, proposal, adjusted_quality_score))\n'
    '    ranked_proposals.sort(\n'
    '        key=lambda item: proposal_priority(\n'
    '            observed_at=item[1].entry_time,\n'
    '            quality_score=item[2],\n'
    '            discovery_rank=item[0].discovery_rank,\n'
    '            instrument_id=item[1].instrument_id,\n'
    '        )\n'
    '    )\n\n'
    '    for candidate, proposal, adjusted_quality_score in ranked_proposals:\n'
    '        snapshot, realized, open_risk, active_symbols = _virtual_snapshot(\n',
)
replace(
    "src/app/trading/strategy_backtest.py",
    '            quality_score=proposal.quality_score,\n'
    '        )\n'
    '        decision = size_strategy_entry(',
    '            quality_score=adjusted_quality_score,\n'
    '        )\n'
    '        decision = size_strategy_entry(',
)
replace(
    "src/app/trading/strategy_backtest.py",
    '        selected.append(sized.trade)\n',
    '        selected.append(sized.trade.model_copy(update={"quality_score": adjusted_quality_score}))\n',
)

# Frontend API can inspect the currently pinned validation artifact.
replace(
    "src/apps/web/src/features/trading/tradingHermesResearchApi.ts",
    '  reviewValidation: (\n',
    '  validation: (policyVersion = \'trading-research-1\') => requestJson<HermesResearchValidation | null>(\n'
    '    `/api/trading/hermes-research/validation/${encodeURIComponent(policyVersion)}`,\n'
    '  ),\n'
    '  reviewValidation: (\n',
)

# Operator review must be a real review: each feature can be preserved or demoted,
# and the operator supplies the audit note. It cannot strengthen HTR-14.
replace(
    "src/apps/web/src/features/trading/TradingHermesResearchPanel.tsx",
    "import type { HermesResearchAudit, HermesResearchValidation } from './tradingHermesResearchApi';\n",
    "import type { HermesResearchAudit, HermesResearchValidation, ResearchRecommendation } from './tradingHermesResearchApi';\n",
)
replace(
    "src/apps/web/src/features/trading/TradingHermesResearchPanel.tsx",
    'const COVERAGE_LABELS:',
    "const RECOMMENDATION_LEVELS: ResearchRecommendation[] = ['observe_only', 'score_only', 'soft_gate', 'hard_gate'];\n\nconst COVERAGE_LABELS:",
)
replace(
    "src/apps/web/src/features/trading/TradingHermesResearchPanel.tsx",
    "  const [attribution, setAttribution] = useState<Record<string, unknown> | null>(null);\n",
    "  const [attribution, setAttribution] = useState<Record<string, unknown> | null>(null);\n"
    "  const [reviewSelections, setReviewSelections] = useState<Record<string, ResearchRecommendation>>({});\n"
    "  const [reviewNote, setReviewNote] = useState('');\n",
)
replace(
    "src/apps/web/src/features/trading/TradingHermesResearchPanel.tsx",
    '      setValidation(nextValidation);\n'
    '      setAttribution(nextAttribution);\n',
    '      setValidation(nextValidation);\n'
    '      setReviewSelections(Object.fromEntries(nextValidation.feature_results.map((item) => [item.feature, item.recommendation])));\n'
    '      setReviewNote(\'\');\n'
    '      setAttribution(nextAttribution);\n',
)
start = '''  const reviewValidation = async () => {\n    if (!validation || validation.promotion_allowed) return;\n    const approvedRecommendations = Object.fromEntries(\n      validation.feature_results\n        .filter((item) => item.recommendation !== 'observe_only')\n        .map((item) => [item.feature, item.recommendation]),\n    );\n    if (!Object.keys(approvedRecommendations).length) {\n      setNotice('HTR-14 has not recommended any feature for score/gate authority; there is nothing eligible to promote.');\n      return;\n    }\n    const confirmed = window.confirm(\n      'Approve the validator recommendations as an HTR-15 execution-authority artifact?\\n\\n' +\n      'This does not change gap_pullback_v1 1.0/1.1. Only an explicitly configured 1.2 strategy can consume the reviewed policy. ' +\n      'The review cannot strengthen any HTR-14 recommendation.',\n    );\n    if (!confirmed) return;\n    setStatus('loading');\n    try {\n      const reviewed = await tradingHermesResearchApi.reviewValidation(\n        validation.validation_id,\n        approvedRecommendations,\n        'Operator reviewed the HTR-14 causal outcome evidence in the Trading strategy panel and accepts the validator recommendations without strengthening them.',\n      );\n'''
end = '''  const reviewValidation = async () => {\n    if (!validation || validation.promotion_allowed) return;\n    const approvedRecommendations = Object.fromEntries(\n      validation.feature_results.map((item) => [item.feature, reviewSelections[item.feature] ?? 'observe_only']),\n    ) as Record<string, ResearchRecommendation>;\n    if (!Object.values(approvedRecommendations).some((value) => value !== 'observe_only')) {\n      setNotice('Select at least one HTR-14 recommendation for score/gate authority. All other features may remain observe-only.');\n      return;\n    }\n    const note = reviewNote.trim();\n    if (note.length < 10) {\n      setNotice('Add a review note of at least 10 characters explaining the promotion decision.');\n      return;\n    }\n    const confirmed = window.confirm(\n      'Create this reviewed HTR-15 execution-authority artifact?\\n\\n' +\n      'This pins the selected recommendations to trading-research-1. It does not change gap_pullback_v1 1.0/1.1; only an explicitly configured 1.2 strategy can consume it.',\n    );\n    if (!confirmed) return;\n    setStatus('loading');\n    try {\n      const reviewed = await tradingHermesResearchApi.reviewValidation(\n        validation.validation_id,\n        approvedRecommendations,\n        note,\n      );\n'''
replace("src/apps/web/src/features/trading/TradingHermesResearchPanel.tsx", start, end)
old_render = '''        {validation.feature_results.map((item) => <div key={item.feature}>\n          <strong>{item.feature.replaceAll('_', ' ')}</strong><span>{item.recommendation}</span>\n          <small>in {String(item.in_sample_effect_r ?? 'N/A')}R · out {String(item.out_of_sample_effect_r ?? 'N/A')}R · 2R Δ {String(item.win_probability_delta ?? 'N/A')} · CI [{String(item.confidence_interval_low ?? 'N/A')}, {String(item.confidence_interval_high ?? 'N/A')}] · n={item.sample_size}</small>\n        </div>)}\n        {promotableValidation ? <button type="button" className="primary" onClick={() => void reviewValidation()} disabled={status === 'loading' || status === 'running'}>Review & approve validator recommendations</button> : null}\n'''
new_render = '''        {validation.feature_results.map((item) => {\n          const maximum = RECOMMENDATION_LEVELS.indexOf(item.recommendation);\n          return <div key={item.feature}>\n            <strong>{item.feature.replaceAll('_', ' ')}</strong>\n            {validation.promotion_allowed ? <span>{item.recommendation}</span> : <select\n              aria-label={`Reviewed authority for ${item.feature}`}\n              value={reviewSelections[item.feature] ?? 'observe_only'}\n              onChange={(event) => setReviewSelections((current) => ({ ...current, [item.feature]: event.target.value as ResearchRecommendation }))}\n            >{RECOMMENDATION_LEVELS.slice(0, maximum + 1).map((value) => <option key={value} value={value}>{value}</option>)}</select>}\n            <small>validator ≤ {item.recommendation} · in {String(item.in_sample_effect_r ?? 'N/A')}R · out {String(item.out_of_sample_effect_r ?? 'N/A')}R · 2R Δ {String(item.win_probability_delta ?? 'N/A')} · CI [{String(item.confidence_interval_low ?? 'N/A')}, {String(item.confidence_interval_high ?? 'N/A')}] · n={item.sample_size}</small>\n          </div>;\n        })}\n        {promotableValidation ? <>\n          <label className="htr-review-note"><span>Promotion review note</span><textarea value={reviewNote} onChange={(event) => setReviewNote(event.target.value)} placeholder="Explain why these validated features should become authoritative in strategy 1.2." /></label>\n          <button type="button" className="primary" onClick={() => void reviewValidation()} disabled={status === 'loading' || status === 'running'}>Create reviewed HTR-15 policy</button>\n        </> : null}\n'''
replace("src/apps/web/src/features/trading/TradingHermesResearchPanel.tsx", old_render, new_render)

# Strategy UI: 1.2 stays unavailable until a reviewed artifact exists; once it
# exists the operator can explicitly load the same strict 1.1 market structure
# with version 1.2 research authority. New strategies still default to 1.1.
replace(
    "src/apps/web/src/features/trading/TradingStrategiesPanel.tsx",
    "import { tradingPaperApi } from './tradingPaperApi';\n",
    "import { tradingPaperApi } from './tradingPaperApi';\nimport { tradingHermesResearchApi } from './tradingHermesResearchApi';\n",
)
replace(
    "src/apps/web/src/features/trading/TradingStrategiesPanel.tsx",
    "  const [reviewing, setReviewing] = useState(false);\n",
    "  const [reviewing, setReviewing] = useState(false);\n  const [htrPromotionAllowed, setHtrPromotionAllowed] = useState(false);\n",
)
replace(
    "src/apps/web/src/features/trading/TradingStrategiesPanel.tsx",
    "  useEffect(() => { void refresh(); }, []);\n",
    "  useEffect(() => { void refresh(); }, []);\n\n"
    "  useEffect(() => {\n"
    "    let alive = true;\n"
    "    void tradingHermesResearchApi.validation().then((report) => {\n"
    "      if (alive) setHtrPromotionAllowed(Boolean(report?.promotion_allowed));\n"
    "    }).catch(() => { if (alive) setHtrPromotionAllowed(false); });\n"
    "    return () => { alive = false; };\n"
    "  }, [selected?.strategy_id, selected?.revision]);\n",
)
replace(
    "src/apps/web/src/features/trading/TradingStrategiesPanel.tsx",
    "  const save = async () => {\n    if (!draft) return;\n",
    "  const loadReviewedV12 = () => {\n"
    "    if (!draft || !htrPromotionAllowed) return;\n"
    "    const config = { ...strictV11Config(), strategy_version: '1.2.0' as const };\n"
    "    setDraft({ ...draft, strategy_version: '1.2.0', config });\n"
    "    setNotice('Loaded gap_pullback_v1 1.2.0. Market-structure defaults remain the strict v1.1 baseline; only the reviewed trading-research-1 policy becomes authoritative. Review and save explicitly.');\n"
    "  };\n\n"
    "  const save = async () => {\n    if (!draft) return;\n"
    "    if (draft.config.strategy_version === '1.2.0' && !htrPromotionAllowed) {\n"
    "      setNotice('Strategy 1.2 requires an active reviewed HTR-15 validation artifact. Run HTR-14 validation and explicit promotion review first.');\n"
    "      return;\n"
    "    }\n",
)
replace(
    "src/apps/web/src/features/trading/TradingStrategiesPanel.tsx",
    "                {draft.config.strategy_version === '1.0.0' ? <button type=\"button\" onClick={upgradeToStrictV11}>Load v1.1 baseline</button> : null}\n",
    "                {draft.config.strategy_version === '1.0.0' ? <button type=\"button\" onClick={upgradeToStrictV11}>Load v1.1 baseline</button> : null}\n"
    "                {draft.config.strategy_version === '1.1.0' && htrPromotionAllowed ? <button type=\"button\" onClick={loadReviewedV12}>Load reviewed HTR v1.2</button> : null}\n",
)

# ADR: promotion is immutable for a policy version.
replace(
    "docs/architecture/ADR-0005-trading-hermes-research-causality.md",
    "A reviewed artifact may preserve or reduce the authority recommended by HTR-14; it may never strengthen an automatic recommendation. The deterministic recommendation semantics are:\n",
    "A reviewed artifact may preserve or reduce the authority recommended by HTR-14; it may never strengthen an automatic recommendation. The **first reviewed promotion artifact is permanently pinned to its `research_policy_version`**. Further outcome analysis may continue, but changing authoritative recommendations requires a new research-policy version (and a new strategy version whenever authorization semantics differ); the existing policy is never silently redefined. The deterministic recommendation semantics are:\n",
)

print("HTR roadmap completion review patch applied.")
