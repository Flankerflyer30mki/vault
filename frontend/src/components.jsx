export function Disclaimer() {
  return (
    <p className="hint">
      Backtests are historical simulations on adjusted daily data. They are not a guarantee of future returns.
    </p>
  );
}

export function Assumptions({ run }) {
  return (
    <ul className="hint">
      <li>Signals use bar t (close included); orders fill at the next bar&apos;s open.</li>
      <li>Stops/targets use daily high/low; gaps fill at the open; if both are touched in one bar, the stop fills.</li>
      {run.cost_model === "india_delivery" ? (
        <li>
          India delivery costs (brokerage + STT, exchange charge, SEBI fee, GST; stamp duty on buys): buy{" "}
          {(run.commission_pct * 100).toFixed(4)}%, sell {(run.sell_commission_pct * 100).toFixed(4)}% per fill. Slippage{" "}
          {(run.slippage_pct * 100).toFixed(3)}% per fill. Flat per-order charges (DP charges) are not included.
        </li>
      ) : (
        <li>
          Commission {(run.commission_pct * 100).toFixed(3)}% and slippage {(run.slippage_pct * 100).toFixed(3)}% per
          fill, charged once.
        </li>
      )}
      <li>Open positions are marked to market at the last close, not liquidated.</li>
      <li>Sharpe: daily returns, risk-free rate 0, annualised with √252.</li>
    </ul>
  );
}

// Free text (any Yahoo symbol) with suggestions from the catalog, Indian stocks and indices included.
export function SymbolInput({ value, onChange, suggestions = [] }) {
  return (
    <label>
      Symbol (Yahoo ticker, e.g. AAPL, RELIANCE.NS, ^NSEI)
      <input
        type="text"
        list="symbol-suggestions"
        value={value}
        pattern="[A-Za-z0-9.\-^=]{1,20}"
        onChange={(e) => onChange(e.target.value.toUpperCase())}
        required
      />
      <datalist id="symbol-suggestions">
        {suggestions.map((s) => (
          <option key={s.symbol} value={s.symbol}>
            {s.name}
          </option>
        ))}
      </datalist>
    </label>
  );
}

// Cost model select. Switching to India delivery resets the fee field to 0% brokerage (a discount broker's
// delivery trade); the statutory charges are added by the server and shown here for transparency.
export function CostModelFields({ catalog, costModel, commission, onChange, showCommission = true }) {
  const india = costModel === "india_delivery";
  const rates = catalog?.india_rates;
  return (
    <>
      <label>
        Cost model
        <select
          value={costModel}
          onChange={(e) =>
            onChange({ cost_model: e.target.value, commission_pct: e.target.value === "india_delivery" ? "0" : "0.001" })
          }
        >
          {(catalog?.cost_models || [{ id: "flat", label: "Flat % per fill" }]).map((m) => (
            <option key={m.id} value={m.id}>
              {m.label}
            </option>
          ))}
        </select>
      </label>
      {showCommission && (
        <label>
          {india ? "Brokerage per fill (0 = discount broker delivery)" : "Commission per fill (0.001 = 0.1%)"}
          <input
            type="number"
            step="0.0001"
            min={0}
            max={0.05}
            value={commission}
            onChange={(e) => onChange({ commission_pct: e.target.value })}
            required
          />
        </label>
      )}
      {india && rates && (
        <p className="hint">
          Added on top of brokerage: STT {pctText(rates.stt)} each side, exchange charge {pctText(rates.exchange_txn)},
          SEBI fee {pctText(rates.sebi_fee)}, stamp duty {pctText(rates.stamp_duty_buy)} on buys, GST 18% on brokerage +
          exchange + SEBI. With zero brokerage: buy {pctText(rates.buy_total)}, sell {pctText(rates.sell_total)} per fill.
        </p>
      )}
    </>
  );
}

const pctText = (fraction) => `${Number((Number(fraction) * 100).toPrecision(4))}%`;
