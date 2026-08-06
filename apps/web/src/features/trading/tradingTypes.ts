import type { components } from '../../api/generated/types';

type Schemas = components['schemas'];
type RequiredField<T, K extends keyof T> = T & Required<Pick<T, K>>;

export type AssetClass = Schemas['AssetClass'];
export type InstrumentType = Schemas['InstrumentType'];
export type CanonicalInstrument = Schemas['CanonicalInstrument'];
export type ProviderPolicy = Schemas['ProviderPolicy'];
export type ProviderBinding = Schemas['ProviderBinding'];
export type ProviderDescriptor = Schemas['ProviderDescriptor'];
export type MarketBar = RequiredField<Schemas['MarketBar'], 'received_at'>;
export type DatasetProvenance = Schemas['DatasetProvenance'];
export type BarsResponse = Schemas['BarsResponse'] & { bars: MarketBar[] };

export type TradingStreamMessage =
  | {
      type: 'bar';
      bar: Omit<MarketBar, 'adjustment_mode' | 'session' | 'provider' | 'received_at'> & {
        binding_id: string;
      };
    }
  | { type: 'error'; code: string; message: string };

export type TradingDocument = Schemas['TradingDocumentResponse'];
export type TradingAlertCondition = Schemas['TradingAlert']['condition_type'];
export type TradingAlertParameters = Schemas['TradingAlertParameters'];
export type TradingAlertIndicatorId = NonNullable<TradingAlertParameters['indicator_id']>;
export type TradingAlertEvaluationPolicy = Schemas['TradingAlertEvaluationPolicy'];
export type TradingAlert = Omit<Schemas['TradingAlert'], 'parameters' | 'evaluation_policy'> & {
  parameters: TradingAlertParameters;
  evaluation_policy: TradingAlertEvaluationPolicy;
};
export type TradingAlertTrigger = Omit<Schemas['TradingAlertTrigger'], 'payload'> & {
  payload: Record<string, unknown>;
};
export type TradingAlertCreateInput = Schemas['TradingAlertCreate'];
export type TradingAlertUpdateInput = Omit<Schemas['TradingAlertUpdate'], 'parameters' | 'evaluation_policy'> & {
  parameters: TradingAlertParameters;
  evaluation_policy: TradingAlertEvaluationPolicy;
};
