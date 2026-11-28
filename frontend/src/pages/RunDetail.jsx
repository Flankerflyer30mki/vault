import { RotateCcw } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Area, AreaChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import api, { errorText, money, num, pct, toPoints, usePoll } from "../api";
import { ChartTooltip, axisProps, compact, useChartTheme } from "../charts";
import { Assumptions, Disclaimer, PageHeader, PageSkeleton, StatusBadge, Tabs } from "../components";

const SAMPLE_LABEL = {
  full: "Full period",
  in: "In-sample (optimised)",
  out: "Out-of-sample (held out)",
  bench: "Benchmark (index buy and hold, no costs)",
};

const signed = (v) => (v === null || v === undefined ? "N/A" : `${v > 0 ? "+" : ""}${pct(v)}`);
// The gap between two returns is in percentage points, not percent.
const points = (v) => (v === null || v === undefined ? "N/A" : `${v > 0 ? "+" : ""}${(v * 100).toFixed(2)} pts`);
const tone = (v) => (v === null || v === undefined ? "" : v >= 0 ? "pos" : "neg");

function EquityChart({ curve, start, format }) {
  const theme = useChartTheme();
  const up = curve.length < 2 || curve[curve.length - 1].v >= curve[0].v;
  const color = up ? theme.pos : theme.neg;
  return (
    <div className="chart-container">
      <ResponsiveContainer width="100%" height={320}>
        <AreaChart data={curve} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="equity-fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.22} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid vertical={false} stroke={theme.grid} />
          <XAxis dataKey="t" {...axisProps(theme)} minTickGap={60} />
          <YAxis {...axisProps(theme)} domain={["auto", "auto"]} tickFormatter={compact} width={48} />
          {start !== null && <ReferenceLine y={start} stroke={theme.faint} strokeDasharray="4 4" />}
          <Tooltip
            content={<ChartTooltip format={format} />}
            cursor={{ stroke: theme.faint, strokeDasharray: "3 3" }}
          />
          {/* Linear, not smoothed: a spline invents wiggles between daily closes. */}
          <Area
            type="linear"
            dataKey="v"
            name="Equity"
            stroke={color}
            strokeWidth={1.5}
            fill="url(#equity-fill)"
            dot={false}
            activeDot={{ r: 3, strokeWidth: 0 }}
            animationDuration={500}
          />
        </AreaChart>
      </ResponsiveContainer>
      <p className="chart-caption">Dashed line: starting cash.</p>
    </div>
  );
}

function TradeTable({ trades, format }) {
  return (
    <div className="table-scroll">
      <table className="trade-table">
        <thead>
          <tr>
            <th>Side</th>
            <th>Date</th>
            <th className="num">Fill price</th>
            <th className="num">Quantity</th>
            <th className="num">Commission</th>
            <th className="num">Cash after</th>
            <th>Reason</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((t) => (
            <tr key={t.id}>
              <td>
                <span className={`side side-${t.side.toLowerCase()}`}>{t.side}</span>
              </td>
              <td>{t.ts.slice(0, 10)}</td>
              <td className="num">{format(t.price)}</td>
              <td className="num">{num(t.quantity, 6)}</td>
              <td className="num">{format(t.commission)}</td>
              <td className="num">{format(t.cash_after)}</td>
              <td className="muted">{t.reason.replace("_", " ")}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Reproducibility({ run }) {
  return (
    <dl className="stat-list">
      <div>
        <dt>Engine</dt>
        <dd className="mono">{run.engine_version || "legacy"}</dd>
      </div>
      <div>
        <dt>Strategy SHA-256</dt>
        <dd className="mono" title={run.strategy_hash}>
          {run.strategy_hash.slice(0, 12) || "n/a"}
        </dd>
      </div>
      <div>
        <dt>Data</dt>
        <dd className="mono" title={run.data_manifest?.data_sha256}>
          {run.data_manifest
            ? `${run.data_manifest.provider} · ${run.data_manifest.bar_count} bars · ${run.data_manifest.data_sha256.slice(0, 12)}`
            : "n/a"}
        </dd>
      </div>
      <div>
        <dt>Attempts</dt>
        <dd>{run.attempts}</dd>
      </div>
      <div>
        <dt>Execution time</dt>
        <dd>{run.execution_time_ms} ms</dd>
      </div>
    </dl>
  );
}

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

  if (!run) return error ? <p className="error">{error}</p> : <PageSkeleton />;

  const active = ["queued", "preparing_data", "running"].includes(run.status);
  const progressKnown = run.bars_total > 0 && run.bars_processed !== null;
  const warnings = run.data_manifest?.warnings || [];
  const curve = toPoints(run.equity_curve);
  const legacy = !run.engine_version;
  const cur = (v) => money(v, run.currency); // INR for NSE/BSE symbols, USD for US tickers
  const start = parseFloat(run.starting_cash);
  const totalReturn = run.final_value ? parseFloat(run.final_value) / start - 1 : null;
  const bh = run.buy_and_hold_return;
  const edge = totalReturn !== null && bh !== null && bh !== undefined ? totalReturn - bh : null;

  return (
    <div>
      <PageHeader
        title={run.strategy_name}
        subtitle={
          <>
            Run #{run.id} · <span className="mono">{run.symbol}</span> · {run.start_date} → {run.end_date} · starting
            cash {cur(run.starting_cash)} · {SAMPLE_LABEL[run.sample]}
          </>
        }
      >
        <StatusBadge status={run.status} />
        <Link className="button secondary" to={`/run?strategy=${run.strategy}&symbol=${encodeURIComponent(run.symbol)}`}>
          <RotateCcw size={14} aria-hidden="true" />
          Run again
        </Link>
      </PageHeader>
      {error && <p className="error">Live updates paused: {error}</p>}
      {legacy && (
        <div className="error-box">
          This run was produced by the pre-2.0 engine, which had known accounting and lookahead defects. Its numbers
          are not reliable; re-run it.
        </div>
      )}

      {active && (
        <div className="progress-box" role="status">
          <p>
            <StatusBadge status={run.status} />
          </p>
          {progressKnown ? (
            <>
              <div className="progress-bar-outer">
                <div
                  className="progress-bar-inner"
                  style={{ width: `${(run.bars_processed / run.bars_total) * 100}%` }}
                />
              </div>
              <p className="hint">
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
          <div className="hero-metrics">
            <div className="hero-metric">
              <span>Total return</span>
              <strong className={tone(totalReturn)}>{signed(totalReturn)}</strong>
              <small>{cur(run.final_value)} final value</small>
            </div>
            <div className="hero-metric">
              <span>vs buy &amp; hold</span>
              <strong className={tone(edge)}>{points(edge)}</strong>
              <small>holding returned {signed(bh)} (gross)</small>
            </div>
            <div className="hero-metric">
              <span>CAGR</span>
              <strong>{pct(run.cagr)}</strong>
              <small>per year</small>
            </div>
            <div className="hero-metric">
              <span>Sharpe ratio</span>
              <strong>{num(run.sharpe_ratio)}</strong>
              <small>Sortino {num(run.sortino_ratio)}</small>
            </div>
            <div className="hero-metric">
              <span>Max drawdown</span>
              <strong className={run.max_drawdown ? "neg" : ""}>{pct(run.max_drawdown)}</strong>
              <small>Calmar {num(run.calmar_ratio)}</small>
            </div>
          </div>

          {trades.length === 0 && !tradeError && (
            <p className="hint">Completed with no trades: the strategy never signalled an entry. Equity stays flat.</p>
          )}

          <h3>Equity curve</h3>
          {curve.length > 0 ? (
            <EquityChart curve={curve} start={Number.isFinite(start) ? start : null} format={cur} />
          ) : (
            <p className="hint">No equity curve recorded for this run.</p>
          )}

          <dl className="stat-list stat-list-wide">
            {[
              ["Win rate (net)", pct(run.win_rate)],
              ["Round trips", run.trade_count ?? "N/A"],
              ["Time in market", pct(run.exposure, 0)],
              ["Commission paid", cur(run.total_commission)],
              ["Slippage cost", cur(run.total_slippage)],
              ["Cost drag", pct(run.cost_drag)],
            ].map(([label, value]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd>{value}</dd>
              </div>
            ))}
          </dl>

          {tradeError && <p className="error">{tradeError}</p>}
          <Tabs
            label="Run details"
            tabs={[
              {
                id: "trades",
                label: `Trades (${trades.length})`,
                content: trades.length ? <TradeTable trades={trades} format={cur} /> : <p className="hint">No fills.</p>,
              },
              { id: "assumptions", label: "Assumptions", content: <Assumptions run={run} /> },
              { id: "repro", label: "Reproducibility", content: <Reproducibility run={run} /> },
            ]}
          />
        </>
      )}

      {run.status === "failed" && (
        <>
          <h3>Reproducibility</h3>
          <Reproducibility run={run} />
        </>
      )}
      <Disclaimer />
    </div>
  );
}

export default RunDetail;
