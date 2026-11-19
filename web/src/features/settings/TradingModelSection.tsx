import type { ProviderFacadePayload } from '../../api/client';
import { TaskModelSection } from './TaskModelSection';

/** The routing override trading reads (backend ``trading.model_route.TRADING_ROUTE_KEY``). */
export const TRADING_ROUTE_KEY = 'trading-research';

/** Which provider and model trading's AI research uses. Unset, it follows the default provider. */
export function TradingModelSection({ payload }: { payload?: ProviderFacadePayload }) {
  return (
    <TaskModelSection
      payload={payload}
      routeKey={TRADING_ROUTE_KEY}
      title="Trading model"
      description="Runs trading's AI research during market hours. A local model spends none of your provider's usage limit. This is research only: it never places orders."
      providerLabel="Trading provider"
      modelLabel="Trading model"
      typedModel={(provider) => provider === 'lmstudio'}
      modelHelp={(provider) => (provider === 'lmstudio' ? 'Blank uses whichever model is loaded. Enter a model key to pin it: trading then pauses if another model is loaded.' : undefined)}
    />
  );
}
