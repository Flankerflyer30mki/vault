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
};
