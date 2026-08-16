export type PaperSide = 'buy' | 'sell';
export type PaperOrderType = 'market' | 'limit' | 'stop';
export type PaperOrderStatus = 'open' | 'filled' | 'cancelled' | 'rejected';

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
