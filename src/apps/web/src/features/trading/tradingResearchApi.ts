import { api, unwrapLabelled } from '../../api/http';
import type { MarketResearchRequest, MarketResearchResult } from './researchTypes';

export const tradingResearchApi = {
  generate: (request: MarketResearchRequest): Promise<MarketResearchResult> =>
    unwrapLabelled(api.POST('/api/trading/research', { body: request }), 'Trading research'),
};
