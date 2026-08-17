export interface FrozenReplayBar {
  instrument_id: string;
  interval: string;
  start_time: string;
  end_time: string;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: string;
  is_final: boolean;
  adjustment_mode: string;
  session: string;
  provider: string;
  provider_event_id?: string | null;
  provider_sequence?: number | null;
  ingestion_revision: number;
  received_at: string;
}

export interface FrozenDatasetSnapshot {
  dataset_id: string;
  instrument_id: string;
  requested_binding_id?: string | null;
  resolved_binding_id: string;
  provider: string;
  interval: string;
  adjustment_mode: string;
  session_calendar: string;
  exchange_timezone: string;
  gap_policy: 'fail' | 'skip';
  dataset_fingerprint: string;
  source_as_of: string;
  bars: FrozenReplayBar[];
  created_at: string;
}

export interface BacktestTrade {
  trade_index: number;
  side: 'buy' | 'sell';
  signal_bar_index: number;
  fill_bar_index: number;
  signal_time: string;
  fill_time: string;
  quantity: string;
  fill_price: string;
  commission: string;
  cash_after: string;
  position_after: string;
}

export interface BacktestEquityPoint {
  point_index: number;
  bar_time: string;
  cash: string;
  position: string;
  equity: string;
  drawdown_percent: string;
}

export interface BacktestArtifactReference {
  storage_provider: string;
  storage_key: string;
  checksum_sha256: string;
  byte_size: number;
}

export interface BacktestRunResult {
  run_id: string;
  dataset_id: string;
  dataset_fingerprint: string;
  strategy_id: string;
  strategy_parameters: Record<string, unknown>;
  execution_policy: Record<string, unknown>;
  formula_version: string;
  status: 'completed' | 'failed';
  initial_cash: string;
  final_equity: string;
  total_return_percent: string;
  max_drawdown_percent: string;
  win_rate_percent: string;
  exposure_percent: string;
  trade_count: number;
  started_at: string;
  finished_at: string;
  trades: BacktestTrade[];
  equity_curve: BacktestEquityPoint[];
  logs: Array<{ log_index: number; bar_time?: string | null; level: string; message: string; payload: Record<string, unknown> }>;
  artifact?: BacktestArtifactReference | null;
  error_message?: string | null;
}
