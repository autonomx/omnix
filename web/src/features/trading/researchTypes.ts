import type { components } from './api/generated';
export type MarketResearchRequest = components['schemas']['MarketResearchRequest'];

export type ResearchSource = components['schemas']['ResearchSource'];

export type MarketResearchResult = components['schemas']['MarketResearchResult'];

export type RangeResearchRequest = components['schemas']['RangeResearchRequest'];

export type RangeResearchResult = components['schemas']['RangeResearchResult'];

export type RangeResearchAction = RangeResearchRequest['action'];

export type CopilotRequest = components['schemas']['CopilotRequest'];

export type CopilotResult = components['schemas']['CopilotResult'];

export type CopilotAction = components['schemas']['CopilotAction'];

export type CopilotMessage = components['schemas']['CopilotMessage'];

export type NewsDigestRequest = components['schemas']['NewsDigestRequest'];

export type NewsDigestResult = components['schemas']['NewsDigestResult'];

export type FilingList = components['schemas']['FilingList'];

export type FilingEntry = components['schemas']['FilingEntry'];

export type FilingSummaryResult = components['schemas']['FilingSummaryResult'];

export type RangeHeadline = components['schemas']['RangeHeadline'];
