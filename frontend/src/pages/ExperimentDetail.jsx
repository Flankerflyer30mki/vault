import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { money, num, pct, usePoll } from "../api";
import { Disclaimer } from "../components";
import { METRICS, buildMatrix, heatLevel, mergeCurves, metricValue, paramLabel } from "../experiments";

const COLORS = ["#4dabf7", "#ff6b6b", "#51cf66", "#ffd43b", "#be4bdb", "#ff922b", "#20c997", "#748ffc", "#f06595"];
const BENCH_COLOR = "#aaaaaa";

function CurveChart({ runs, name, currency, benchmark }) {
  const all = benchmark ? [...runs, benchmark] : runs;
  const data = mergeCurves(all);
  const cur = (v) => money(v, currency);
  return (
    <div className="chart-container">
      <ResponsiveContainer width="100%" height={400}>
        <LineChart data={data} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#2a2a2a" />
          <XAxis dataKey="t" stroke="#888" tick={{ fontSize: 12 }} minTickGap={40} />
          <YAxis stroke="#888" domain={["auto", "auto"]} tick={{ fontSize: 12 }} />
          <Tooltip
            contentStyle={{ background: "#1a1a1a", border: "1px solid #444", fontSize: "12px", maxWidth: "260px" }}
            labelStyle={{ color: "#888" }}
            formatter={(v, n) => [cur(v), n]}
          />
          {runs.map((r, i) => (
            <Line key={r.id} type="monotone" dataKey={`run_${r.id}`} name={name(r)} stroke={COLORS[i % COLORS.length]} strokeWidth={1.5} dot={false} connectNulls />
          ))}
          {benchmark && (
            <Line type="monotone" dataKey={`run_${benchmark.id}`} name={`Benchmark: ${benchmark.symbol}`} stroke={BENCH_COLOR} strokeDasharray="5 4" strokeWidth={1.5} dot={false} connectNulls />
          )}
        </LineChart>
      </ResponsiveContainer>
      <div className="custom-legend">
        {runs.map((r, i) => (
          <div key={r.id} className="legend-item">
            <span className="legend-swatch" style={{ background: COLORS[i % COLORS.length] }} />
            <span>{name(r)}</span>
          </div>
        ))}
        {benchmark && (
          <div className="legend-item">
            <span className="legend-swatch" style={{ background: BENCH_COLOR }} />
            <span>Benchmark: {benchmark.symbol} (buy and hold, no costs)</span>
          </div>
        )}
      </div>
      <p className="hint">Curves are downsampled for the chart; each run&apos;s page has the full curve.</p>
    </div>
  );
}

function Failures({ runs, name }) {
  const failed = runs.filter((r) => r.status === "failed");
  if (!failed.length) return null;
  return (
    <div className="error-box">
      {failed.map((r) => (
        <p key={r.id}>
          <Link to={`/runs/${r.id}`}>{name(r)}</Link>: {r.error_message}
        </p>
      ))}
    </div>
  );
}

function ComparisonView({ job }) {
  const [metric, setMetric] = useState("total_return");
  const { symbols, rows, benchmarks } = buildMatrix(job);
  const [symbol, setSymbol] = useState(symbols[0]);
  const m = METRICS.find((x) => x.id === metric);
  const cells = rows.flatMap((row) => Object.values(row.cells));
  const benchFor = (sym) => {
    const cur = job.runs.find((r) => r.sample === "full" && r.symbol === sym)?.currency;
    return benchmarks.find((b) => b.currency === cur);
  };
  const cellText = (r) => (r.status === "completed" ? m.fmt(metricValue(r, metric)) : r.status.replace("_", " "));

  return (
    <>
      <h3>Results by strategy and symbol</h3>
      <div className="sort-buttons" role="group" aria-label="Metric">
        {METRICS.map((x) => (
          <button key={x.id} type="button" aria-pressed={metric === x.id} className={metric === x.id ? "active" : ""} onClick={() => setMetric(x.id)}>
            {x.label}
          </button>
        ))}
      </div>
      <div className="table-scroll">
        <table className="trade-table heatmap">
          <thead>
            <tr>
              <th>Strategy</th>
              {symbols.map((s) => (
                <th key={s}>{s}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <th scope="row">{row.name}</th>
                {symbols.map((s) => {
                  const r = row.cells[s];
                  if (!r) return <td key={s}>—</td>;
                  // Colour within each symbol's column: strategies compete on the same stock, not across stocks.
                  const column = rows.map((x) => x.cells[s]).filter((c) => c?.status === "completed").map((c) => metricValue(c, metric));
                  const level = r.status === "completed" ? heatLevel(metricValue(r, metric), column, m.higherIsBetter) : null;
                  return (
                    <td key={s} className="heat-cell" data-level={level === null ? "" : Math.round(level * 4)}>
                      <Link to={`/runs/${r.id}`}>{cellText(r)}</Link>
                    </td>
                  );
                })}
              </tr>
            ))}
            {benchmarks.length > 0 && (
              <tr className="bench-row">
                <th scope="row">Benchmark (buy and hold the index)</th>
                {symbols.map((s) => {
                  const b = benchFor(s);
                  return (
                    <td key={s}>
                      {b ? (
                        <Link to={`/runs/${b.id}`} title={b.symbol}>
                          {b.symbol}: {b.status === "completed" ? m.fmt(metricValue(b, metric)) : b.status}
                        </Link>
                      ) : (
                        "—"
                      )}
                    </td>
                  );
                })}
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <p className="hint">
        Greener is better for the chosen metric, compared within each column. Exposure is shown uncoloured: being in the
        market more is neither good nor bad by itself.
      </p>
      <Failures runs={[...cells, ...benchmarks]} name={(r) => `${r.strategy_name} on ${r.symbol}`} />

      <h3>Equity curves</h3>
      <label className="inline-label">
        Symbol{" "}
        <select value={symbol} onChange={(e) => setSymbol(e.target.value)}>
          {symbols.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </label>
      <CurveChart
        runs={rows.map((row) => row.cells[symbol]).filter((r) => r?.status === "completed")}
        name={(r) => r.strategy_name}
        currency={job.runs.find((r) => r.symbol === symbol)?.currency}
        benchmark={benchFor(symbol)?.status === "completed" ? benchFor(symbol) : null}
      />
    </>
  );
}

const SORTS = ["sharpe_ratio", "sortino_ratio", "cagr", "final_value", "max_drawdown", "win_rate"];

function OptimizationView({ job }) {
  const [sortField, setSortField] = useState("sharpe_ratio");
  const runs = job.runs || [];
  const cur = (v) => money(v, job.currency);
  const inSample = runs.filter((r) => r.sample !== "out");
  const oos = runs.find((r) => r.sample === "out");
  const done = inSample.filter((r) => r.status === "completed");
  const sorted = [...done].sort((a, b) => {
    const x = parseFloat(a[sortField] ?? -Infinity), y = parseFloat(b[sortField] ?? -Infinity);
    return sortField === "max_drawdown" ? x - y : y - x;
  });
  const skipped = job.config?.skipped || [];
  const searched = (job.config?.param_grid || []).map((g) => g.label);

  return (
    <>
      {job.split_date && (
        <p className="hint">
          In-sample: {job.start_date} to day before {job.split_date}. Out-of-sample: {job.split_date} to {job.end_date}.
        </p>
      )}
      <Failures runs={inSample} name={paramLabel} />
      {skipped.length > 0 && (
        <div className="error-box">
          <p className="error-title">{skipped.length} combination{skipped.length > 1 ? "s" : ""} skipped as invalid</p>
          <ul>
            {skipped.map((s, i) => (
              <li key={i}>
                {Object.entries(s.params).map(([k, v]) => `${k} ${v}`).join(" · ")}: {s.reason}
              </li>
            ))}
          </ul>
        </div>
      )}

      {oos && (
        <div className="sandbox-card">
          <div className="sandbox-header">
            <span className="sandbox-title">Out-of-sample result (best in-sample: {paramLabel(oos)})</span>
            <span className={oos.status === "completed" ? "sandbox-badge passed" : "sandbox-badge failed"}>{oos.status.replace("_", " ")}</span>
          </div>
          {oos.status === "completed" && (
            <div className="sandbox-stats">
              <div><span>Final Value</span><strong>{cur(oos.final_value)}</strong></div>
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
          <h3>In-sample results (sorted by {sortField.replace("_", " ")}): optimised, expect optimism</h3>
          <div className="sort-buttons">
            {SORTS.map((f) => (
              <button key={f} type="button" aria-pressed={sortField === f} className={sortField === f ? "active" : ""} onClick={() => setSortField(f)}>
                {f.replace("_", " ")}
              </button>
            ))}
          </div>
          <div className="table-scroll">
            <table className="trade-table">
              <thead>
                <tr>
                  <th>Run</th>
                  {searched.map((l) => (
                    <th key={l}>{l}</th>
                  ))}
                  <th>Stop</th><th>Target</th><th>Final Value</th><th>CAGR</th><th>Sharpe</th><th>Sortino</th>
                  <th>Max DD</th><th>Exposure</th><th>Trades</th><th>Cost drag</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((r) => (
                  <tr key={r.id}>
                    <td><Link to={`/runs/${r.id}`}>#{r.id}</Link></td>
                    {searched.map((l) => (
                      <td key={l}>{r.grid_params?.[l]}</td>
                    ))}
                    <td>{pct(r.stop_loss_pct, 0)}</td>
                    <td>{pct(r.take_profit_pct, 0)}</td>
                    <td>{cur(r.final_value)}</td>
                    <td>{pct(r.cagr)}</td>
                    <td>{num(r.sharpe_ratio)}</td>
                    <td>{num(r.sortino_ratio)}</td>
                    <td>{pct(r.max_drawdown)}</td>
                    <td>{pct(r.exposure, 0)}</td>
                    <td>{r.trade_count ?? "N/A"}</td>
                    <td>{pct(r.cost_drag)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <h3>In-sample equity curves</h3>
          <CurveChart runs={sorted.slice(0, COLORS.length)} name={paramLabel} currency={job.currency} />
          {sorted.length > COLORS.length && <p className="hint">Showing the top {COLORS.length} by the chosen sort.</p>}
        </>
      )}
    </>
  );
}

function ExperimentDetail() {
  const { id } = useParams();
  const { data: job, error } = usePoll(`/experiments/${id}/`, 2500);
  if (!job) return error ? <p className="error">{error}</p> : <p>Loading…</p>;

  const runs = job.runs || [];
  const children = runs.filter((r) => r.sample === "in" || r.sample === "full");
  const finished = children.filter((r) => !["queued", "preparing_data", "running"].includes(r.status)).length;
  const comparison = job.kind === "comparison";

  return (
    <div>
      <h1>
        {comparison ? "Comparison" : "Optimization"} #{job.id}
        {!comparison && ` — ${job.strategy_name}`}
      </h1>
      <p>
        {comparison ? (job.config?.symbols || []).join(", ") : job.symbol} | {job.start_date} to {job.end_date} | Status:{" "}
        {job.status.replace("_", " ")} ({finished}/{children.length} {comparison ? "cells" : "in-sample runs"} finished)
      </p>
      {error && <p className="error">Live updates paused: {error}</p>}
      {comparison ? <ComparisonView job={job} /> : <OptimizationView job={job} />}
      <Disclaimer />
    </div>
  );
}

export default ExperimentDetail;
