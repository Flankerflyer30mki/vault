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
      <li>
        Commission {(run.commission_pct * 100).toFixed(3)}% and slippage {(run.slippage_pct * 100).toFixed(3)}% per
        fill, charged once. Open positions are marked to market at the last close, not liquidated.
      </li>
      <li>Sharpe: daily returns, risk-free rate 0, annualised with √252.</li>
    </ul>
  );
}
