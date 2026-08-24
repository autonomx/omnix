export type PaperSide = 'buy' | 'sell';
export type PaperOrderType = 'market' | 'limit' | 'stop';
export type PaperOrderStatus = 'open' | 'filled' | 'cancelled' | 'rejected';
export type PaperProtectionStatus = 'pending_entry' | 'active' | 'exit_submitted' | 'closed' | 'cancelled';

export interface PaperAccount {
  account_id: string;
  name: string;
  base_currency: string;
  commission_bps: string;
  enabled: boolean;
  revision: number;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface PaperBalance {
  currency: string;
  available: string;
  reserved: string;
}

export interface PaperPosition {
  instrument_id: string;
  quantity: string;
  average_cost: string;
  realized_pnl: string;
  last_price?: string | null;
  unrealized_pnl: string;
}

export interface PaperOrder {
  account_id: string;
  order_id: string;
  instrument_id: string;
  binding_id?: string | null;
  side: PaperSide;
  order_type: PaperOrderType;
  quantity: string;
  limit_price?: string | null;
  stop_price?: string | null;
  reference_price?: string | null;
  status: PaperOrderStatus;
  filled_quantity: string;
  average_fill_price?: string | null;
  idempotency_key: string;
  rejection_reason?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface PaperFill {
  fill_id: string;
  order_id: string;
  instrument_id: string;
  side: PaperSide;
  quantity: string;
  price: string;
  commission: string;
  source_time: string;
  evaluated_at: string;
  idempotency_key: string;
}

export interface PaperLedgerEntry {
  ledger_id: string;
  entry_type: 'deposit' | 'withdrawal' | 'trade_cash' | 'commission' | 'realized_pnl';
  currency: string;
  amount: string;
  order_id?: string | null;
  fill_id?: string | null;
  idempotency_key: string;
  payload: Record<string, unknown>;
  created_at?: string | null;
}

export interface PaperPositionProtection {
  account_id: string;
  instrument_id: string;
  binding_id?: string | null;
  entry_order_id?: string | null;
  exit_order_id?: string | null;
  take_profit?: string | null;
  stop_loss?: string | null;
  status: PaperProtectionStatus;
  trigger_reason?: string | null;
  revision: number;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface PaperAccountSnapshot {
  account: PaperAccount;
  balances: PaperBalance[];
  positions: PaperPosition[];
  open_orders: PaperOrder[];
  order_history?: PaperOrder[];
  recent_fills: PaperFill[];
  recent_ledger: PaperLedgerEntry[];
}

export interface PaperAccountCreateInput {
  account_id: string;
  name: string;
  base_currency: string;
  initial_cash: string;
  commission_bps: string;
}

export interface PaperOrderInput {
  order_id: string;
  instrument_id: string;
  binding_id?: string | null;
  side: PaperSide;
  order_type: PaperOrderType;
  quantity: string;
  limit_price?: string | null;
  stop_price?: string | null;
  reference_price?: string | null;
  idempotency_key: string;
}

export interface PaperProtectionInput {
  instrument_id: string;
  binding_id?: string | null;
  entry_order_id?: string | null;
  take_profit?: string | null;
  stop_loss?: string | null;
}

export interface PaperRiskPreviewInput {
  instrument_id: string;
  binding_id?: string | null;
  entry_price: string;
  stop_price: string;
  desired_risk_pct: string;
}

export interface PaperRiskPreview {
  allowed: boolean;
  policy_version: string;
  reason_codes: string[];
  limiting_reason_code?: string | null;
  recommended_quantity: string;
  account_equity: string;
  desired_risk_pct: string;
  actual_risk_dollars: string;
  actual_risk_pct: string;
  estimated_notional: string;
  buying_power_before: string;
  buying_power_after: string;
  aggregate_open_risk_dollars: string;
  aggregate_open_risk_pct: string;
  daily_realized_pnl: string;
  daily_loss_remaining: string;
  spread_bps?: string | null;
  observation_age_seconds?: string | null;
  freshness_mode: string;
  execution_eligible: boolean;
  unprotected_exposure_count: number;
}

export interface PaperRiskOrderInput {
  order_id: string;
  instrument_id: string;
  binding_id?: string | null;
  order_type: PaperOrderType;
  trigger_price?: string | null;
  stop_loss: string;
  take_profit?: string | null;
  desired_risk_pct: string;
  idempotency_key: string;
}

export interface PaperRiskOrderResult {
  preview: PaperRiskPreview;
  order: PaperOrder;
  protection: PaperPositionProtection;
}
