export type WebResearchMode = 'automatic' | 'manual' | 'disabled';
export type RetrievalProfileId = 'fast' | 'balanced' | 'research';

export type RetrievalProfile = {
  id: RetrievalProfileId;
  maxQueries: number;
  maxSources: number;
  maxFetchedPages: number;
  contradictionAnalysis: boolean;
  crossSourceValidation: boolean;
  synthesisDepth: number;
};

export type SourcePreferences = {
  preferOfficialDocs: boolean;
  preferAcademicSources: boolean;
  preferGovernmentSources: boolean;
  preferPrimarySources: boolean;
  allowForums: boolean;
  allowReddit: boolean;
  avoidSocialMedia: boolean;
  avoidGeneratedContent: boolean;
};

export type WebResearchConfig = {
  enabled: boolean;
  mode: WebResearchMode;
  profile: RetrievalProfileId;
  sourcePreferences: SourcePreferences;
  requireCitations: boolean;
};

export type WebResearchDecisionReason = 'explicit_request' | 'freshness_required' | 'verification_required' | 'recommendation' | 'uncertain_fact' | 'manual_only' | 'disabled';

export type WebResearchDecision = {
  shouldRetrieve: boolean;
  reason: WebResearchDecisionReason;
  profile: RetrievalProfile;
};

export const RETRIEVAL_PROFILES: Record<RetrievalProfileId, RetrievalProfile> = {
  fast: { id: 'fast', maxQueries: 2, maxSources: 5, maxFetchedPages: 3, contradictionAnalysis: false, crossSourceValidation: false, synthesisDepth: 1 },
  balanced: { id: 'balanced', maxQueries: 4, maxSources: 12, maxFetchedPages: 8, contradictionAnalysis: true, crossSourceValidation: true, synthesisDepth: 2 },
  research: { id: 'research', maxQueries: 8, maxSources: 30, maxFetchedPages: 20, contradictionAnalysis: true, crossSourceValidation: true, synthesisDepth: 3 },
};

export const DEFAULT_SOURCE_PREFERENCES: SourcePreferences = {
  preferOfficialDocs: true,
  preferAcademicSources: false,
  preferGovernmentSources: true,
  preferPrimarySources: true,
  allowForums: false,
  allowReddit: false,
  avoidSocialMedia: true,
  avoidGeneratedContent: true,
};

export const DEFAULT_WEB_RESEARCH_CONFIG: WebResearchConfig = {
  enabled: false,
  mode: 'manual',
  profile: 'balanced',
  sourcePreferences: DEFAULT_SOURCE_PREFERENCES,
  requireCitations: true,
};

export function decideWebResearch(config: WebResearchConfig, input: { explicitRequest?: boolean; freshnessRequired?: boolean; verificationRequired?: boolean; recommendation?: boolean; uncertainFact?: boolean }): WebResearchDecision {
  const profile = RETRIEVAL_PROFILES[config.profile];
  if (!config.enabled || config.mode === 'disabled') return { shouldRetrieve: false, reason: 'disabled', profile };
  if (config.mode === 'manual' && !input.explicitRequest) return { shouldRetrieve: false, reason: 'manual_only', profile };
  if (input.explicitRequest) return { shouldRetrieve: true, reason: 'explicit_request', profile };
  if (input.freshnessRequired) return { shouldRetrieve: true, reason: 'freshness_required', profile };
  if (input.verificationRequired) return { shouldRetrieve: true, reason: 'verification_required', profile };
  if (input.recommendation) return { shouldRetrieve: true, reason: 'recommendation', profile };
  if (input.uncertainFact) return { shouldRetrieve: true, reason: 'uncertain_fact', profile };
  return { shouldRetrieve: false, reason: 'manual_only', profile };
}

export function createQueryPlan(query: string, profile: RetrievalProfile): string[] {
  const normalized = query.trim();
  if (!normalized) return [];
  const planned = [normalized, `${normalized} official`, `${normalized} latest`, `${normalized} documentation`, `${normalized} comparison`, `${normalized} source`];
  return Array.from(new Set(planned)).slice(0, profile.maxQueries);
}
