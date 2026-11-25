import { unwrapLabelled } from '../../api/http';
import type {
  CopilotRequest,
  CopilotResult,
  FilingList,
  FilingSummaryResult,
  MarketResearchRequest,
  MarketResearchResult,
  NewsDigestRequest,
  NewsDigestResult,
  RangeResearchRequest,
  RangeResearchResult,
} from './researchTypes';
import { api } from './api/gateway';

/** Read-only AI research (TradingView's AI features, 2026-11): none of these reach orders, alerts or positions. */
export const tradingResearchApi = {
  generate: (request: MarketResearchRequest): Promise<MarketResearchResult> =>
    unwrapLabelled(api.POST('/api/trading/research', { body: request }), 'Trading research'),
  /** AI range: research about one span of the chart. */
  range: (request: RangeResearchRequest): Promise<RangeResearchResult> =>
    unwrapLabelled(api.POST('/api/trading/research/range', { body: request }), 'AI range'),
  /** Chart Copilot: an answer about the chart, with chart changes the person may apply. */
  copilot: (request: CopilotRequest): Promise<CopilotResult> =>
    unwrapLabelled(api.POST('/api/trading/research/copilot', { body: request }), 'Copilot'),
  /** AI news digest: the symbol's recent headlines by theme. */
  newsDigest: (request: NewsDigestRequest): Promise<NewsDigestResult> =>
    unwrapLabelled(api.POST('/api/trading/research/news-digest', { body: request }), 'News digest'),
  /** A US company's recent SEC reports. */
  filings: (instrumentId: string): Promise<FilingList> =>
    unwrapLabelled(api.GET('/api/trading/research/filings', { params: { query: { instrument_id: instrumentId } } }), 'Filings'),
  /** AI filing summary of one of those reports. */
  filingSummary: (instrumentId: string, accession: string): Promise<FilingSummaryResult> =>
    unwrapLabelled(api.POST('/api/trading/research/filings/summary', { body: { instrument_id: instrumentId, accession } }), 'Filing summary'),
};
