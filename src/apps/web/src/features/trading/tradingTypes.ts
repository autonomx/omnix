import type { components } from '../../api/generated/types';

type Schemas = components['schemas'];
type RequiredField<T, K extends keyof T> = T & Required<Pick<T, K>>;

export type AssetClass = components['schemas']['AssetClass'];
export type InstrumentType = components['schemas']['InstrumentType'];
export type CanonicalInstrument = components['schemas']['CanonicalInstrument'];
export type ProviderPolicy = components['schemas']['ProviderPolicy'];
export type ProviderBinding = components['schemas']['ProviderBinding'];
export type ProviderDescriptor = components['schemas']['ProviderDescriptor'];
export type MarketBar = RequiredField<Schemas['MarketBar-Output'], 'received_at'>;
export type DatasetProvenance = components['schemas']['DatasetProvenance'];
export type BarsResponse = components['schemas']['BarsResponse'];

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
export type TradingAlertNotificationChannel = 'app' | 'toast' | 'sound';
export type TradingAlertTriggerPolicy = 'once' | 'once_per_bar' | 'every_time';
// What the UI sends; alerts it reads carry every parameter (TradingAlertParameters-Output).
export type TradingAlertParameters = Omit<Schemas['TradingAlertParameters-Input'], 'message' | 'trigger_policy'> & {
  message?: string;
  notification_channels?: TradingAlertNotificationChannel[];
  trigger_policy?: TradingAlertTriggerPolicy;
};
export type TradingAlertIndicatorId = NonNullable<TradingAlertParameters['indicator_id']>;
export type TradingAlertEvaluationPolicy = components['schemas']['TradingAlertEvaluationPolicy'];
export type TradingAlert = components['schemas']['TradingAlert'];
export type TradingAlertTrigger = components['schemas']['TradingAlertTrigger'];
export type TradingAlertCreateInput = Omit<Schemas['TradingAlertCreate'], 'parameters' | 'evaluation_policy'> & {
  parameters: TradingAlertParameters;
  evaluation_policy: Schemas['TradingAlertEvaluationPolicy-Input'];
};
export type TradingAlertUpdateInput = Omit<Schemas['TradingAlertUpdate'], 'parameters' | 'evaluation_policy'> & {
  parameters: TradingAlertParameters;
  evaluation_policy: Schemas['TradingAlertEvaluationPolicy-Input'];
};
