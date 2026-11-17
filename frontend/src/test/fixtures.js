// A copy of the shape GET /api/strategies/catalog/ returns (backend: spec.catalog()). max_conditions is lowered
// to 3 here so the limit is quick to reach in tests.
export const CATALOG = {
  version: 1,
  max_conditions: 3,
  operators: [
    { id: ">", label: "is above" },
    { id: "<", label: "is below" },
    { id: ">=", label: "is at or above" },
    { id: "<=", label: "is at or below" },
    { id: "crosses_above", label: "crosses above" },
    { id: "crosses_below", label: "crosses below" },
  ],
  price_fields: ["open", "high", "low", "close", "volume"],
  indicators: [
    { id: "sma", label: "Simple moving average", outputs: ["value"], params: [{ name: "period", type: "int", min: 2, max: 200, default: 20 }] },
    { id: "rsi", label: "Relative strength index (Wilder)", outputs: ["value"], params: [{ name: "period", type: "int", min: 2, max: 200, default: 14 }] },
    {
      id: "macd",
      label: "MACD",
      outputs: ["line", "signal", "hist"],
      params: [
        { name: "fast", type: "int", min: 2, max: 100, default: 12 },
        { name: "slow", type: "int", min: 3, max: 200, default: 26 },
        { name: "signal", type: "int", min: 2, max: 50, default: 9 },
      ],
    },
    {
      id: "bbands",
      label: "Bollinger Bands",
      outputs: ["upper", "middle", "lower"],
      params: [
        { name: "period", type: "int", min: 2, max: 200, default: 20 },
        { name: "std", type: "float", min: 0.5, max: 5, default: 2 },
      ],
    },
  ],
  cost_models: [
    { id: "flat", label: "Flat % per fill" },
    { id: "india_delivery", label: "India delivery (NSE/BSE): brokerage + statutory charges" },
  ],
  india_rates: { stt: "0.001", exchange_txn: "0.0000297", sebi_fee: "0.000001", stamp_duty_buy: "0.00015", buy_total: "0.001186226", sell_total: "0.001036226" },
  suggested_symbols: [{ symbol: "^NSEI", name: "NIFTY 50" }],
  custom_code_enabled: false,
  limits: { max_grid: 25, max_grid_params: 4, max_compare_strategies: 10, max_compare_symbols: 10 },
  benchmarks: { INR: "^NSEI", USD: "^GSPC" },
};

const run = (id, extra) => ({
  id,
  status: "completed",
  starting_cash: "10000.00",
  final_value: "10000.00",
  sharpe_ratio: 0,
  sortino_ratio: 0,
  max_drawdown: 0.1,
  exposure: 0.5,
  cost_drag: 0.002,
  trade_count: 3,
  curve: [["2024-01-02", 10000], ["2024-12-31", 10000]],
  ...extra,
});

// The shape GET /api/experiments/<id>/ returns for a comparison of 2 strategies × 2 symbols (+ 2 benchmarks).
export const COMPARISON = {
  id: 9,
  kind: "comparison",
  status: "partially_completed",
  start_date: "2024-01-01",
  end_date: "2024-12-31",
  currency: null,
  config: { strategies: [3, 4], symbols: ["AAPL", "RELIANCE.NS"], benchmarks: { USD: "^GSPC", INR: "^NSEI" } },
  runs: [
    run(11, { strategy: 3, strategy_name: "EMA Crossover", symbol: "AAPL", currency: "USD", sample: "full", final_value: "11200.00", sharpe_ratio: 1.2 }),
    run(12, { strategy: 3, strategy_name: "EMA Crossover", symbol: "RELIANCE.NS", currency: "INR", sample: "full", final_value: "9500.00", sharpe_ratio: -0.4 }),
    run(13, { strategy: 4, strategy_name: "RSI Mean Reversion", symbol: "AAPL", currency: "USD", sample: "full", final_value: "10400.00", sharpe_ratio: 0.6 }),
    run(14, { strategy: 4, strategy_name: "RSI Mean Reversion", symbol: "RELIANCE.NS", currency: "INR", sample: "full", status: "failed", final_value: null, error_message: "No market data" }),
    run(15, { strategy: 5, strategy_name: "Buy and Hold", symbol: "^GSPC", currency: "USD", sample: "bench", final_value: "12500.00" }),
    run(16, { strategy: 5, strategy_name: "Buy and Hold", symbol: "^NSEI", currency: "INR", sample: "bench", final_value: "10800.00" }),
  ],
};

// An optimization over ema(12).period with one combination skipped.
export const OPTIMIZATION = {
  id: 7,
  kind: "optimization",
  status: "completed",
  strategy_name: "EMA Crossover",
  symbol: "AAPL",
  currency: "USD",
  start_date: "2022-01-01",
  end_date: "2024-12-31",
  split_date: "2024-02-01",
  config: {
    param_grid: [{ label: "ema(12).period", paths: ["entry.all[0].left.params.period"], values: [8, 12] }],
    skipped: [{ params: { "macd(12, 26, 9).fast": 30 }, reason: "must be greater than fast" }],
  },
  runs: [
    run(21, { sample: "in", stop_loss_pct: "0.050000", take_profit_pct: "0.200000", grid_params: { "ema(12).period": 8 }, sharpe_ratio: 0.9, final_value: "10900.00" }),
    run(22, { sample: "in", stop_loss_pct: "0.050000", take_profit_pct: "0.200000", grid_params: { "ema(12).period": 12 }, sharpe_ratio: 1.4, final_value: "11400.00" }),
    run(23, { sample: "out", stop_loss_pct: "0.050000", take_profit_pct: "0.200000", grid_params: { "ema(12).period": 12 }, sharpe_ratio: 0.3, final_value: "10100.00", cagr: 0.01, buy_and_hold_return: 0.05 }),
  ],
};
