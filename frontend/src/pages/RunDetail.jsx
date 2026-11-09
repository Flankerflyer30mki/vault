import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import api, { errorText, money, num, pct, toPoints, usePoll } from "../api";
import { Assumptions, Disclaimer } from "../components";

const SAMPLE_LABEL = { full: "Full period", in: "In-sample (optimised)", out: "Out-of-sample (held out)" };

function RunDetail() {
  const { id } = useParams();
  const { data: run, error } = usePoll(`/runs/${id}/`, 1500);
  const [trades, setTrades] = useState([]);
  const [tradeError, setTradeError] = useState("");

  const status = run?.status;
  useEffect(() => {
    if (status !== "completed") return;
    api
      .get(`/runs/${id}/trades/`)
      .then((res) => setTrades(res.data))
      .catch((err) => setTradeError(errorText(err)));
  }, [id, status]);

  if (!run) return error ? <p className="error">{error}</p> : <p>Loading…</p>;

  const active = ["queued", "preparing_data", "running"].includes(run.status);
  const progressKnown = run.bars_total > 0 && run.bars_processed !== null;
  const warnings = run.data_manifest?.warnings || [];
  const curve = toPoints(run.equity_curve);
  const legacy = !run.engine_version;

  return (
    <div>
      <h1>
        Run #{run.id} — {run.strategy_name}
      </h1>
      <p>
        {run.symbol} | {run.start_date} to {run.end_date} | Starting cash: {money(run.starting_cash)} |{" "}
        {SAMPLE_LABEL[run.sample]}
      </p>
      {error && <p className="error">Live updates paused: {error}</p>}
      {legacy && (
        <div className="error-box">
          This run was produced by the pre-2.0 engine, which had known accounting and lookahead defects. Its numbers
          are not reliable; re-run it.
        </div>
      )}

      {active && (
        <div className="progress-box" role="status">
          <p>Status: {run.status.replace("_", " ")}</p>
          {progressKnown ? (
            <>
              <div className="progress-bar-outer">
                <div
                  className="progress-bar-inner"
                  style={{ width: `${(run.bars_processed / run.bars_total) * 100}%` }}
                />
              </div>
              <p>
                {run.bars_processed} / {run.bars_total} bars processed
              </p>
            </>
          ) : (
            <p className="hint">{run.status === "queued" ? "Waiting for a worker…" : "Progress not available yet."}</p>
          )}
        </div>
      )}

      {run.status === "failed" && (
        <div className="error-box">
          <p className="error-title">Run failed ({run.failure_category || "unknown"})</p>
          <p>{run.error_message}</p>
        </div>
      )}

      {warnings.length > 0 && (
        <div className="error-box">
          <p className="error-title">Data coverage warnings</p>
          <ul>
            {warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      {run.status === "completed" && (
        <>
          {trades.length === 0 && !tradeError && (
            <p className="hint">Completed with no trades: the strategy never signalled an entry. Equity stays flat.</p>
          )}
          <div className="metrics-grid">
            {[
              ["Final Value", money(run.final_value)],
              ["CAGR", pct(run.cagr)],
              ["Sharpe Ratio", num(run.sharpe_ratio)],
              ["Max Drawdown", pct(run.max_drawdown)],
              ["Win Rate (net)", pct(run.win_rate)],
              ["Buy & Hold (gross)", pct(run.buy_and_hold_return)],
              ["Commission Paid", money(run.total_commission)],
              ["Slippage Cost", money(run.total_slippage)],
              ["Execution Time", `${run.execution_time_ms} ms`],
            ].map(([label, value]) => (
              <div className="metric-card" key={label}>
                <span>{label}</span>
                <strong>{value}</strong>
              </div>
            ))}
          </div>

          <h3>Equity Curve</h3>
          {curve.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={curve}>
                <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                <XAxis dataKey="t" stroke="#888" minTickGap={40} />
                <YAxis stroke="#888" domain={["auto", "auto"]} />
                <Tooltip
                  contentStyle={{ background: "#222", border: "1px solid #444" }}
                  formatter={(v) => money(v)}
                />
                <Line type="monotone" dataKey="v" name="Equity" stroke="#4dabf7" dot={false} />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <p className="hint">No equity curve recorded for this run.</p>
          )}

          <h3>Trade Log ({trades.length} fills)</h3>
          {tradeError && <p className="error">{tradeError}</p>}
          {trades.length > 0 && (
            <table className="trade-table">
              <thead>
                <tr>
                  <th>Side</th>
                  <th>Date</th>
                  <th>Fill Price</th>
                  <th>Quantity</th>
                  <th>Commission</th>
                  <th>Cash After</th>
                  <th>Reason</th>
                </tr>
              </thead>
              <tbody>
                {trades.map((t) => (
                  <tr key={t.id} className={t.side === "BUY" ? "buy-row" : "sell-row"}>
                    <td>{t.side}</td>
                    <td>{t.ts.slice(0, 10)}</td>
                    <td>{money(t.price)}</td>
                    <td>{num(t.quantity, 6)}</td>
                    <td>{money(t.commission)}</td>
                    <td>{money(t.cash_after)}</td>
                    <td>{t.reason.replace("_", " ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <h3>Execution Assumptions</h3>
          <Assumptions run={run} />
        </>
      )}

      {(run.status === "completed" || run.status === "failed") && (
        <div className="sandbox-card">
          <div className="sandbox-header">
            <span className="sandbox-title">Reproducibility</span>
          </div>
          <div className="sandbox-stats">
            <div>
              <span>Engine</span>
              <strong>{run.engine_version || "legacy"}</strong>
            </div>
            <div>
              <span>Strategy SHA-256</span>
              <strong title={run.strategy_hash}>{run.strategy_hash.slice(0, 12) || "n/a"}</strong>
            </div>
            <div>
              <span>Data</span>
              <strong title={run.data_manifest?.data_sha256}>
                {run.data_manifest
                  ? `${run.data_manifest.provider} · ${run.data_manifest.bar_count} bars · ${run.data_manifest.data_sha256.slice(0, 12)}`
                  : "n/a"}
              </strong>
            </div>
            <div>
              <span>Attempts</span>
              <strong>{run.attempts}</strong>
            </div>
          </div>
        </div>
      )}
      <Disclaimer />
    </div>
  );
}

export default RunDetail;
