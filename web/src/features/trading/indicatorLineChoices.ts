import { indicatorOutputsFor } from './indicatorOutputKeys';
import { externalIndicatorOutputKeys, isExternalIndicatorId } from './indicators/externalIndicatorData';
import type { CoreIndicatorId } from './indicators/coreIndicators';
import { newIndicatorInstance } from './tradingStore';

/**
 * The lines an indicator draws with this period (the server registry computes the same keys); an external-data
 * indicator's lines are its data series (TVP-0.2), the same at any period.
 */
export function indicatorLines(indicatorId: string, period: number): Array<{ key: string; title: string }> {
  if (isExternalIndicatorId(indicatorId)) return externalIndicatorOutputKeys(indicatorId).map((key) => ({ key, title: key.slice(indicatorId.length + 1) }));
  try {
    const instance = { ...newIndicatorInstance(indicatorId as CoreIndicatorId), period };
    return indicatorOutputsFor(instance).map((output) => ({ key: output.key, title: output.title }));
  } catch {
    return [];
  }
}
