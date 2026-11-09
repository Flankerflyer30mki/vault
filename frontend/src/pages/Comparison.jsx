import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { money, num, pct, toPoints, usePoll } from "../api";
import { Disclaimer } from "../components";

const COLORS = ["#4dabf7", "#ff6b6b", "#51cf66", "#ffd43b", "#be4bdb", "#ff922b", "#20c997", "#748ffc", "#f06595"];
const SORTS = ["sharpe_ratio", "cagr", "final_value", "max_drawdown", "win_rate"];
const label = (r) => `#${r.id} SL ${pct(r.stop_loss_pct, 0)} / TP ${pct(r.take_profit_pct, 0)}`;

function mergeCurves(runs) {
  const byDate = new Map();
  runs.forEach((r) =>
    toPoints(r.equity_curve).forEach(({ t, v }) => {
      if (!byDate.has(t)) byDate.set(t, { t });
      byDate.get(t)[`run_${r.id}`] = v;
    }),
  );
  return [...byDate.values()].sort((a, b) => (a.t < b.t ? -1 : 1));
}

function Comparison() {
  const { id } = useParams();
  const { data: job, error } = usePoll(`/optimizations/${id}/`, 2500);
  const [sortField, setSortField] = useState("sharpe_ratio");

  if (!job) return error ? <p className="error">{error}</p> : <p>Loading…</p>;

  const runs = job.runs || [];
  const inSample = runs.filter((r) => r.sample !== "out");
  const oos = runs.find((r) => r.sample === "out");
  const done = inSample.filter((r) => r.status === "completed");
  const failed = inSample.filter((r) => r.status === "failed");
  const sorted = [...done].sort((a, b) => {
    const x = parseFloat(a[sortField] ?? -Infinity), y = parseFloat(b[sortField] ?? -Infinity);
    return sortField === "max_drawdown" ? x - y : y - x;
  });
  const chartData = mergeCurves(done);

  return (
    <div>
      <h1>
        Optimization #{job.id} — {job.strategy_name}
      </h1>
      <p>
        {job.symbol} | {job.start_date} to {job.end_date} | Status: {job.status.replace("_", " ")}
      </p>
      {job.split_date && (
        <p className="hint">
          In-sample: {job.start_date} to day before {job.split_date}. Out-of-sample: {job.split_date} to {job.end_date}.
        </p>
      )}
      {error && <p className="error">Live updates paused: {error}</p>}
      <p>
        {done.length} completed · {failed.length} failed · {inSample.length - done.length - failed.length} pending
      </p>
      {failed.length > 0 && (
        <div className="error-box">
          {failed.map((r) => (
            <p key={r.id}>
              <Link to={`/runs/${r.id}`}>{label(r)}</Link>: {r.error_message}
            </p>
          ))}
        </div>
      )}

      {oos && (
        <div className="sandbox-card">
          <div className="sandbox-header">
            <span className="sandbox-title">Out-of-sample result (best in-sample: {label(oos)})</span>
            <span className={oos.status === "completed" ? "sandbox-badge passed" : "sandbox-badge failed"}>
              {oos.status.replace("_", " ")}
            </span>
          </div>
          {oos.status === "completed" && (
            <div className="sandbox-stats">
              <div><span>Final Value</span><strong>{money(oos.final_value)}</strong></div>
              <div><span>CAGR</span><strong>{pct(oos.cagr)}</strong></div>
              <div><span>Sharpe</span><strong>{num(oos.sharpe_ratio)}</strong></div>
              <div><span>Max DD</span><strong>{pct(oos.max_drawdown)}</strong></div>
              <div><span>Buy & Hold</span><strong>{pct(oos.buy_and_hold_return)}</strong></div>
            </div>
          )}
          <Link to={`/runs/${oos.id}`}>Open run →</Link>
        </div>
      )}

      {done.length > 0 && (
        <>
          <h3>In-sample results (sorted by {sortField.replace("_", " ")}) — optimised, expect optimism</h3>
          <div className="sort-buttons">
            {SORTS.map((f) => (
              <button key={f} type="button" aria-pressed={sortField === f} className={sortField === f ? "active" : ""} onClick={() => setSortField(f)}>
                {f.replace("_", " ")}
              </button>
            ))}
          </div>
          <table className="trade-table">
            <thead>
              <tr>
                <th>Run</th><th>Stop Loss</th><th>Take Profit</th><th>Final Value</th><th>CAGR</th>
                <th>Sharpe</th><th>Max Drawdown</th><th>Win Rate</th><th>Costs</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((r) => (
                <tr key={r.id}>
                  <td><Link to={`/runs/${r.id}`}>#{r.id}</Link></td>
                  <td>{pct(r.stop_loss_pct, 0)}</td>
                  <td>{pct(r.take_profit_pct, 0)}</td>
                  <td>{money(r.final_value)}</td>
                  <td>{pct(r.cagr)}</td>
                  <td>{num(r.sharpe_ratio)}</td>
                  <td>{pct(r.max_drawdown)}</td>
                  <td>{pct(r.win_rate)}</td>
                  <td>{money(parseFloat(r.total_commission || 0) + parseFloat(r.total_slippage || 0))}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <h3>In-sample equity curves</h3>
          <div className="chart-container">
            <ResponsiveContainer width="100%" height={450}>
              <LineChart data={chartData} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#2a2a2a" />
                <XAxis dataKey="t" stroke="#888" tick={{ fontSize: 12 }} minTickGap={40} />
                <YAxis stroke="#888" domain={["auto", "auto"]} tick={{ fontSize: 12 }} />
                <Tooltip
                  contentStyle={{ background: "#1a1a1a", border: "1px solid #444", fontSize: "12px", maxWidth: "240px" }}
                  labelStyle={{ color: "#888" }}
                  formatter={(v, name) => [money(v), name]}
                />
                {done.map((r, idx) => (
                  <Line key={r.id} type="monotone" dataKey={`run_${r.id}`} name={label(r)} stroke={COLORS[idx % COLORS.length]} strokeWidth={1.5} dot={false} connectNulls />
                ))}
              </LineChart>
            </ResponsiveContainer>
            <div className="custom-legend">
              {done.map((r, idx) => (
                <div key={r.id} className="legend-item">
                  <span className="legend-swatch" style={{ background: COLORS[idx % COLORS.length] }} />
                  <span>{label(r)}</span>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
      <Disclaimer />
    </div>
  );
}

export default Comparison;
