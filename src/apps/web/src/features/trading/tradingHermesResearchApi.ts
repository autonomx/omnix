import type { components } from '../../api/generated/types';
import { api, unwrapLabelled } from '../../api/http';

type Schemas = components['schemas'];

// Trading research payloads as the gateway sends them (WP-9.3).
export type HermesResearchCoverage = Schemas['ResearchCoverage'];
export type HermesResearchReport = Schemas['TradingResearchReport'];
export type HermesResearchEvidence = Schemas['TradingEvidence'];
export type HermesMarketBriefItem = Schemas['TradingMarketBriefItem'];
export type HermesMarketBrief = Schemas['TradingMarketBrief'];
export type HermesSupplyFact = Schemas['SupplyFact'];
export type HermesResearchFactSet = Schemas['TradingFactSet'];
export type HermesResearchFeatures = Schemas['StrategyResearchFeatures'];
export type HermesResearchAction = Schemas['ResearchActionRecord'];
export type HermesShadowAnnotation = Schemas['NoveltyShadowAnnotation'];
export type HermesResearchAudit = Schemas['TradingResearchAuditView'];
export type HermesResearchValidation = Schemas['ResearchValidationReport'];
export type HermesResearchStart = Schemas['TradingResearchCoordinatorResult'];
export type ResearchCoverageState = HermesResearchCoverage['atm'];
export type ResearchRecommendation = HermesResearchValidation['feature_results'][number]['recommendation'];

const research = <T>(call: Promise<{ data?: T; error?: unknown; response: Response }>) => unwrapLabelled(call, 'Trading research');

export const tradingHermesResearchApi = {
  start: (instrumentId: string, strategyId?: string | null): Promise<HermesResearchStart> =>
    research(api.POST('/api/trading/hermes-research/start', {
      body: {
        instrument_id: instrumentId,
        strategy_id: strategyId || null,
        deadline_seconds: 45,
        max_steps: 8,
        max_queries: 5,
        max_sources: 20,
        max_extracts: 8,
        run_shadow_ai: true,
      },
    })),
  audit: (instrumentId: string, asOf?: string): Promise<HermesResearchAudit> =>
    research(api.GET('/api/trading/hermes-research/audit', {
      params: { query: { instrument_id: instrumentId, ...(asOf ? { as_of: asOf } : {}) } },
    })),
  attribution: (strategyId: string): Promise<Record<string, unknown>> =>
    research(api.GET('/api/trading/hermes-research/attribution', { params: { query: { strategy_id: strategyId } } })),
  validate: (strategyId: string): Promise<HermesResearchValidation> =>
    research(api.POST('/api/trading/hermes-research/validate', {
      body: { strategy_id: strategyId, policy_version: 'trading-research-1', minimum_sample: 100, minimum_exact_sample: 50 },
    })),
  validation: (policyVersion = 'trading-research-1'): Promise<HermesResearchValidation | null> =>
    research(api.GET('/api/trading/hermes-research/validation/{policy_version}', { params: { path: { policy_version: policyVersion } } })),
  reviewValidation: (
    sourceValidationId: string,
    approvedRecommendations: Record<string, ResearchRecommendation>,
    reviewNote: string,
  ): Promise<HermesResearchValidation> =>
    research(api.POST('/api/trading/hermes-research/validation/review', {
      body: {
        source_validation_id: sourceValidationId,
        policy_version: 'trading-research-1',
        approved_recommendations: approvedRecommendations,
        review_note: reviewNote,
        confirm_execution_authority: true,
      },
    })),
};
