import { useEffect, useState, useRef } from "react";
import { useParams } from "react-router-dom";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import api from "../api";

function RunDetail() {
  const { id } = useParams();
  const [run, setRun] = useState(null);
  const [progress, setProgress] = useState(null);
  const [trades, setTrades] = useState([]);
  const [equityCurve, setEquityCurve] = useState([]);
  const intervalRef = useRef(null);

  const fetchRun = () => {
    api.get(`/runs/${id}/`).then((response) => {
      setRun(response.data);
    });
  };

  const fetchProgress = () => {
    api.get(`/runs/${id}/progress/`).then((response) => {
      setProgress(response.data);
      if (response.data.done) {
        clearInterval(intervalRef.current);
        fetchRun();
        fetchTrades();
        fetchEquityCurve();
      }
    });
  };

  const fetchTrades = () => {
    api.get(`/runs/${id}/trades/`).then((response) => {
      setTrades(response.data);
    });
  };

  const fetchEquityCurve = () => {
    api.get(`/runs/${id}/equity-curve/`).then((response) => {
      const formatted = response.data.equity_curve.map((value, index) => ({
        bar: index,
        value: value,
      }));
      setEquityCurve(formatted);
    });
  };

  useEffect(() => {
    fetchRun();
    fetchProgress();
    intervalRef.current = setInterval(fetchProgress, 1000);
    return () => clearInterval(intervalRef.current);
  }, [id]);

  if (!run) return <p>Loading...</p>;

  const isRunning = run.status === "pending" || run.status === "running";

  return (
    <div>
      <h1>
        Run #{run.id} — {run.strategy_name}
      </h1>
      <p>
        {run.symbol} | {run.start_date} to {run.end_date} | Starting cash: $
        {run.starting_cash}
      </p>

      {isRunning && progress && (
        <div className="progress-box">
          <p>Status: {run.status}</p>
          <div className="progress-bar-outer">
            <div
              className="progress-bar-inner"
              style={{
                width: `${progress.total > 0 ? (progress.processed / progress.total) * 100 : 0}%`,
              }}
            />
          </div>
          <p>
            {progress.processed} / {progress.total} bars processed
          </p>
        </div>
      )}

      {run.status === "failed" && (
        <div className="error-box">
          <p>Run failed: {run.error_message}</p>
        </div>
      )}

      {(run.status === "completed" || run.status === "failed") && (
        <div className="sandbox-card">
          <div className="sandbox-header">
            <span className="sandbox-title">Sandbox Execution</span>
            <span
              className={
                run.status === "completed"
                  ? "sandbox-badge passed"
                  : "sandbox-badge failed"
              }
            >
              {run.status === "completed" ? "✓ Passed" : "✗ Failed"}
            </span>
          </div>
          {run.status === "completed" && (
            <div className="sandbox-stats">
              <div>
                <span>Execution Time</span>
                <strong>{run.execution_time_ms}ms</strong>
              </div>
              <div>
                <span>Bars Processed</span>
                <strong>{run.bars_processed}</strong>
              </div>
              <div>
                <span>Isolation</span>
                <strong>Subprocess + AST whitelist</strong>
              </div>
            </div>
          )}
          {run.status === "failed" && (
            <p className="sandbox-error">{run.error_message}</p>
          )}
        </div>
      )}

      {run.status === "completed" && (
        <>
          <div className="metrics-grid">
            <div className="metric-card">
              <span>Final Value</span>
              <strong>${parseFloat(run.final_value).toFixed(2)}</strong>
            </div>
            <div className="metric-card">
              <span>CAGR</span>
              <strong>{(run.cagr * 100).toFixed(2)}%</strong>
            </div>
            <div className="metric-card">
              <span>Sharpe Ratio</span>
              <strong>{run.sharpe_ratio.toFixed(2)}</strong>
            </div>
            <div className="metric-card">
              <span>Max Drawdown</span>
              <strong>{(run.max_drawdown * 100).toFixed(2)}%</strong>
            </div>
            <div className="metric-card">
              <span>Win Rate</span>
              <strong>{(run.win_rate * 100).toFixed(2)}%</strong>
            </div>
            <div className="metric-card">
              <span>Execution Time</span>
              <strong>{run.execution_time_ms}ms</strong>
            </div>
          </div>

          <h3>Equity Curve</h3>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={equityCurve}>
              <CartesianGrid strokeDasharray="3 3" stroke="#333" />
              <XAxis dataKey="bar" stroke="#888" />
              <YAxis stroke="#888" domain={["auto", "auto"]} />
              <Tooltip
                contentStyle={{ background: "#222", border: "1px solid #444" }}
              />
              <Line
                type="monotone"
                dataKey="value"
                stroke="#4dabf7"
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>

          <h3>Trade Log ({trades.length} trades)</h3>
          <table className="trade-table">
            <thead>
              <tr>
                <th>Side</th>
                <th>Date</th>
                <th>Price</th>
                <th>Quantity</th>
              </tr>
            </thead>
            <tbody>
              {trades.map((t) => (
                <tr
                  key={t.id}
                  className={t.side === "BUY" ? "buy-row" : "sell-row"}
                >
                  <td>{t.side}</td>
                  <td>{new Date(t.ts).toLocaleDateString()}</td>
                  <td>${parseFloat(t.price).toFixed(2)}</td>
                  <td>{parseFloat(t.quantity).toFixed(4)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}

export default RunDetail;
