from __future__ import annotations

from pathlib import Path


TYPES = Path("src/apps/web/src/features/trading/tradingStrategyTypes.ts")
API = Path("src/apps/web/src/features/trading/tradingStrategyApi.ts")
PANEL = Path("src/apps/web/src/features/trading/TradingStrategiesPanel.tsx")


def replace_exact(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)


def patch_types() -> None:
    text = TYPES.read_text(encoding="utf-8")
    anchor = """export type CatalystShadowClassification = {\n"""
    insertion = """export type V2QualificationThresholds = {\n  prospective_start: string;\n  minimum_matched_trades: number;\n  minimum_distinct_sessions: number;\n  minimum_distinct_symbols: number;\n  minimum_execution_match_rate: string | number;\n  minimum_expectancy_r: string | number;\n  one_sided_confidence_level: string | number;\n  maximum_drawdown_r: string | number;\n  live_match_window_minutes: number;\n};\n\nexport type V2ProspectiveQualification = {\n  strategy_id: string;\n  qualification_version: string;\n  prospective_start: string;\n  expected_profile_fingerprint: string;\n  current_profile_fingerprint: string;\n  profile_match: boolean;\n  replay_trade_count: number;\n  matched_eligible_trade_count: number;\n  distinct_sessions: number;\n  distinct_symbols: number;\n  execution_match_rate?: string | number | null;\n  expectancy_r?: string | number | null;\n  one_sided_90_lcb_r?: string | number | null;\n  max_drawdown_r?: string | number | null;\n  thresholds: V2QualificationThresholds;\n  evidence_fingerprint: string;\n  qualified: boolean;\n  reviewed: boolean;\n  auto_paper_authorized: boolean;\n  reason_codes: string[];\n};\n\nexport type CatalystShadowClassification = {\n"""
    TYPES.write_text(replace_exact(text, anchor, insertion, "V2 qualification types"), encoding="utf-8")


def patch_api() -> None:
    text = API.read_text(encoding="utf-8")
    import_old = """  StrategyResearchReviewResponse,\n  TradingStrategyConfig,\n"""
    import_new = """  StrategyResearchReviewResponse,\n  TradingStrategyConfig,\n  V2ProspectiveQualification,\n"""
    text = replace_exact(text, import_old, import_new, "strategy API type import")
    method_old = """  protections: async (strategyId: string) => {\n    const payload = await requestJson<{ protections?: StrategyProtection[] }>(\n      `/api/trading/strategies/${encodeURIComponent(strategyId)}/protections?active_only=true`,\n    );\n    return Array.isArray(payload.protections) ? payload.protections : [];\n  },\n  discoverYahooUniverse: (input: YahooGapperDiscoveryInput) => requestJson<GapperUniverse>(\n"""
    method_new = """  protections: async (strategyId: string) => {\n    const payload = await requestJson<{ protections?: StrategyProtection[] }>(\n      `/api/trading/strategies/${encodeURIComponent(strategyId)}/protections?active_only=true`,\n    );\n    return Array.isArray(payload.protections) ? payload.protections : [];\n  },\n  v2Qualification: (strategyId: string) =>\n    requestJson<V2ProspectiveQualification>(\n      `/api/trading/strategies/${encodeURIComponent(strategyId)}/v2/qualification`,\n    ),\n  reviewV2Qualification: (strategyId: string, reviewNote: string) =>\n    requestJson<V2ProspectiveQualification>(\n      `/api/trading/strategies/${encodeURIComponent(strategyId)}/v2/qualification/review`,\n      { method: 'POST', body: JSON.stringify({ review_note: reviewNote }) },\n    ),\n  discoverYahooUniverse: (input: YahooGapperDiscoveryInput) => requestJson<GapperUniverse>(\n"""
    API.write_text(replace_exact(text, method_old, method_new, "strategy API qualification methods"), encoding="utf-8")


def patch_panel() -> None:
    text = PANEL.read_text(encoding="utf-8")
    import_old = """  StrategyResearchReview,\n  TradingStrategyConfig,\n} from './tradingStrategyTypes';\n"""
    import_new = """  StrategyResearchReview,\n  TradingStrategyConfig,\n  V2ProspectiveQualification,\n} from './tradingStrategyTypes';\n"""
    text = replace_exact(text, import_old, import_new, "panel V2 type import")

    state_old = """  const [reviewing, setReviewing] = useState(false);\n  const [htrPromotionAllowed, setHtrPromotionAllowed] = useState(false);\n\n  const selected = useMemo(\n"""
    state_new = """  const [reviewing, setReviewing] = useState(false);\n  const [htrPromotionAllowed, setHtrPromotionAllowed] = useState(false);\n  const [v2Qualification, setV2Qualification] = useState<V2ProspectiveQualification | null>(null);\n  const [v2ReviewNote, setV2ReviewNote] = useState('');\n  const [v2Reviewing, setV2Reviewing] = useState(false);\n\n  const selected = useMemo(\n"""
    text = replace_exact(text, state_old, state_new, "panel qualification state")

    effect_old = """  useEffect(() => {\n    if (!selected) return;\n    setDraft(structuredClone(selected));\n"""
    effect_new = """  useEffect(() => {\n    let alive = true;\n    if (!selected || selected.config.strategy_version !== '2.0.0') {\n      setV2Qualification(null);\n      return () => { alive = false; };\n    }\n    void tradingStrategyApi.v2Qualification(selected.strategy_id).then((qualification) => {\n      if (alive) setV2Qualification(qualification);\n    }).catch((error) => {\n      if (alive) {\n        setV2Qualification(null);\n        setNotice(error instanceof Error ? error.message : String(error));\n      }\n    });\n    return () => { alive = false; };\n  }, [selected?.strategy_id, selected?.revision, selected?.config.strategy_version]);\n\n  useEffect(() => {\n    if (!selected) return;\n    setDraft(structuredClone(selected));\n"""
    text = replace_exact(text, effect_old, effect_new, "panel qualification effect")

    start_old = """    setResearchReviews([]);\n    setSelectedCandidates(new Set());\n    setDraft(defaultStrategy(accounts[0].account_id));\n"""
    start_new = """    setResearchReviews([]);\n    setV2Qualification(null);\n    setV2ReviewNote('');\n    setSelectedCandidates(new Set());\n    setDraft(defaultStrategy(accounts[0].account_id));\n"""
    text = replace_exact(text, start_old, start_new, "panel reset qualification")

    action_old = """  const save = async () => {\n    if (!draft) return;\n"""
    action_new = """  const reviewV2Qualification = async () => {\n    if (!selected || selected.config.strategy_version !== '2.0.0') return;\n    const note = v2ReviewNote.trim();\n    if (note.length < 10) {\n      setNotice('V2 prospective promotion review requires an audit note of at least 10 characters.');\n      return;\n    }\n    setV2Reviewing(true);\n    try {\n      const qualification = await tradingStrategyApi.reviewV2Qualification(selected.strategy_id, note);\n      setV2Qualification(qualification);\n      setV2ReviewNote('');\n      setNotice(qualification.auto_paper_authorized\n        ? 'V2 prospective evidence review recorded. AUTO PAPER is now authorized for this exact evidence/profile snapshot; future evidence changes require a new review.'\n        : 'V2 review recorded, but AUTO PAPER remains blocked by the server qualification policy.');\n    } catch (error) {\n      setNotice(error instanceof Error ? error.message : String(error));\n    } finally {\n      setV2Reviewing(false);\n    }\n  };\n\n  const save = async () => {\n    if (!draft) return;\n"""
    text = replace_exact(text, action_old, action_new, "panel review action")

    save_guard_old = """    if (draft.config.strategy_version === '1.2.0' && !htrPromotionAllowed) {\n      setNotice('Strategy 1.2 requires an active reviewed HTR-15 validation artifact. Run HTR-14 validation and explicit promotion review first.');\n      return;\n    }\n    if (!draft.account_id) {\n"""
    save_guard_new = """    if (draft.config.strategy_version === '1.2.0' && !htrPromotionAllowed) {\n      setNotice('Strategy 1.2 requires an active reviewed HTR-15 validation artifact. Run HTR-14 validation and explicit promotion review first.');\n      return;\n    }\n    if (draft.config.strategy_version === '2.0.0' && draft.mode === 'auto_paper' && !v2Qualification?.auto_paper_authorized) {\n      setNotice('Strategy 2.0 AUTO PAPER is fail-closed until the frozen prospective qualification floors pass and the exact evidence snapshot receives an explicit review.');\n      return;\n    }\n    if (!draft.account_id) {\n"""
    text = replace_exact(text, save_guard_old, save_guard_new, "panel V2 save guard")

    mode_old = """                {(['off', 'shadow', 'auto_paper'] as StrategyMode[]).map((mode) => <button type=\"button\" key={mode} className={draft.mode === mode ? 'active' : undefined} aria-pressed={draft.mode === mode} onClick={() => setDraft({ ...draft, mode })}>{mode === 'auto_paper' ? 'Auto paper' : mode[0].toUpperCase() + mode.slice(1)}</button>)}\n"""
    mode_new = """                {(['off', 'shadow', 'auto_paper'] as StrategyMode[]).map((mode) => {\n                  const v2AutoBlocked = mode === 'auto_paper' && draft.config.strategy_version === '2.0.0' && !v2Qualification?.auto_paper_authorized;\n                  return <button type=\"button\" key={mode} className={draft.mode === mode ? 'active' : undefined} aria-pressed={draft.mode === mode} disabled={v2AutoBlocked} title={v2AutoBlocked ? 'Requires reviewed prospective V2 qualification' : undefined} onClick={() => setDraft({ ...draft, mode })}>{mode === 'auto_paper' ? 'Auto paper' : mode[0].toUpperCase() + mode.slice(1)}</button>;\n                })}\n"""
    text = replace_exact(text, mode_old, mode_new, "panel V2 mode guard")

    overview_old = """            </section>\n\n            <section className=\"trading-strategy-pipeline\">\n"""
    overview_new = """            </section>\n\n            {draft.config.strategy_version === '2.0.0' ? (\n              <section className=\"trading-config-block\" aria-label=\"V2 prospective qualification\">\n                <header>\n                  <strong>Prospective AUTO PAPER qualification</strong>\n                  <small>Frozen Aug 24+ policy · raw morning archive + live eligible SHADOW signal + post-session Alpaca IEX replay</small>\n                </header>\n                {v2Qualification ? (\n                  <>\n                    <div className=\"trading-strategy-grid\">\n                      <div><strong>Profile</strong><small>{v2Qualification.profile_match ? 'Exact frozen V2 profile' : 'Mismatch — reload frozen V11 v2'}</small></div>\n                      <div><strong>Matched trades</strong><small>{v2Qualification.matched_eligible_trade_count} / {v2Qualification.thresholds.minimum_matched_trades}</small></div>\n                      <div><strong>Distinct sessions</strong><small>{v2Qualification.distinct_sessions} / {v2Qualification.thresholds.minimum_distinct_sessions}</small></div>\n                      <div><strong>Distinct symbols</strong><small>{v2Qualification.distinct_symbols} / {v2Qualification.thresholds.minimum_distinct_symbols}</small></div>\n                      <div><strong>Execution match</strong><small>{v2Qualification.execution_match_rate == null ? 'N/A' : `${(Number(v2Qualification.execution_match_rate) * 100).toFixed(1)}%`} · min {(Number(v2Qualification.thresholds.minimum_execution_match_rate) * 100).toFixed(0)}%</small></div>\n                      <div><strong>Expectancy</strong><small>{v2Qualification.expectancy_r == null ? 'N/A' : `${Number(v2Qualification.expectancy_r).toFixed(3)}R`} · min +{Number(v2Qualification.thresholds.minimum_expectancy_r).toFixed(2)}R</small></div>\n                      <div><strong>90% lower bound</strong><small>{v2Qualification.one_sided_90_lcb_r == null ? 'N/A' : `${Number(v2Qualification.one_sided_90_lcb_r).toFixed(3)}R`} · must be &gt; 0R</small></div>\n                      <div><strong>Max drawdown</strong><small>{v2Qualification.max_drawdown_r == null ? 'N/A' : `${Number(v2Qualification.max_drawdown_r).toFixed(3)}R`} · max {Number(v2Qualification.thresholds.maximum_drawdown_r).toFixed(1)}R</small></div>\n                    </div>\n                    <p><small>Profile <code>{v2Qualification.current_profile_fingerprint.slice(0, 12)}</code> · evidence <code>{v2Qualification.evidence_fingerprint.slice(0, 12)}</code> · replay trades {v2Qualification.replay_trade_count}. {v2Qualification.reason_codes.length ? `Blocking: ${v2Qualification.reason_codes.join(', ')}` : 'All quantitative floors pass.'}</small></p>\n                    <p><strong>{v2Qualification.auto_paper_authorized ? 'AUTO PAPER authorized' : v2Qualification.qualified ? 'Quantitatively qualified — explicit review required' : 'Prospective qualification in progress'}</strong></p>\n                    {v2Qualification.qualified && !v2Qualification.reviewed ? (\n                      <div className=\"trading-strategy-grid\">\n                        <label className=\"wide-field\"><span>Promotion review note<small>binds approval to this exact evidence fingerprint</small></span><textarea value={v2ReviewNote} onChange={(event) => setV2ReviewNote(event.target.value)} placeholder=\"Review the prospective sample, execution coverage, drawdown and edge before approving AUTO PAPER.\" /></label>\n                        <button type=\"button\" onClick={() => void reviewV2Qualification()} disabled={v2Reviewing || v2ReviewNote.trim().length < 10}>{v2Reviewing ? 'Recording review…' : 'Approve exact V2 evidence snapshot'}</button>\n                      </div>\n                    ) : null}\n                  </>\n                ) : (\n                  <p><small>Save the frozen V2 profile in SHADOW mode first. Qualification begins with the prospective epoch on 2026-08-24; historical reconstruction cannot unlock AUTO PAPER.</small></p>\n                )}\n              </section>\n            ) : null}\n\n            <section className=\"trading-strategy-pipeline\">\n"""
    text = replace_exact(text, overview_old, overview_new, "panel qualification card")
    PANEL.write_text(text, encoding="utf-8")


def main() -> int:
    patch_types()
    patch_api()
    patch_panel()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
