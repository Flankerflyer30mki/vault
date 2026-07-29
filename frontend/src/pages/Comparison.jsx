import { useEffect, useState } from "react";
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

const COLORS = [
  "#4dabf7",
  "#ff6b6b",
  "#51cf66",
  "#ffd43b",
  "#be4bdb",
  "#ff922b",
  "#20c997",
  "#748ffc",
  "#f06595",
];

function Comparison() {
  const { id } = useParams();
  const [job, setJob] = useState(null);
  const [runs, setRuns] = useState([]);
  const [chartData, setChartData] = useState([]);
  const [sortField, setSortField] = useState("sharpe_ratio");

  const fetchAllRuns = async (runIds) => {
    const runDetails = await Promise.all(
      runIds.map((rid) => api.get(`/runs/${rid}/`).then((res) => res.data)),
    );
    setRuns(runDetails);

    const curves = await Promise.all(
      runIds.map((rid) =>
        api.get(`/runs/${rid}/equity-curve/`).then((res) => ({
          id: rid,
          curve: res.data.equity_curve,
        })),
      ),
    );

    const maxLength = Math.max(...curves.map((c) => c.curve.length));
    const merged = [];
    for (let i = 0; i < maxLength; i++) {
      const point = { bar: i };
      curves.forEach((c) => {
        point[`run_${c.id}`] = c.curve[i] ?? null;
      });
      merged.push(point);
    }
    setChartData(merged);
  };

  useEffect(() => {
    const interval = setInterval(() => {
      api.get(`/optimizations/${id}/`).then((response) => {
        setJob(response.data);
        if (response.data.status === "completed") {
          clearInterval(interval);
          fetchAllRuns(response.data.run_ids);
        }
      });
    }, 2000);

    api.get(`/optimizations/${id}/`).then((response) => {
      setJob(response.data);
      if (response.data.status === "completed") {
        clearInterval(interval);
        fetchAllRuns(response.data.run_ids);
      }
    });

    return () => clearInterval(interval);
  }, [id]);

  if (!job) return <p>Loading...</p>;

  const sortedRuns = [...runs].sort(
    (a, b) => (b[sortField] ?? -Infinity) - (a[sortField] ?? -Infinity),
  );

  return (
    <div>
      <h1>
        Optimization #{job.id} — {job.strategy_name}
      </h1>
      <p>
        {job.symbol} | {job.start_date} to {job.end_date} | Status: {job.status}
      </p>

      {job.status !== "completed" && (
        <p>
          Running {job.run_ids.length > 0 ? job.run_ids.length : ""} backtests
          concurrently, please wait...
        </p>
      )}

      {job.status === "completed" && runs.length > 0 && (
        <>
          <h3>Results (sorted by {sortField.replace("_", " ")})</h3>
          <div className="sort-buttons">
            {[
              "sharpe_ratio",
              "cagr",
              "final_value",
              "max_drawdown",
              "win_rate",
            ].map((field) => (
              <button
                key={field}
                className={sortField === field ? "active" : ""}
                onClick={() => setSortField(field)}
              >
                {field.replace("_", " ")}
              </button>
            ))}
          </div>

          <table className="trade-table">
            <thead>
              <tr>
                <th>Run</th>
                <th>Stop Loss</th>
                <th>Take Profit</th>
                <th>Final Value</th>
                <th>CAGR</th>
                <th>Sharpe</th>
                <th>Max Drawdown</th>
                <th>Win Rate</th>
              </tr>
            </thead>
            <tbody>
              {sortedRuns.map((r, idx) => (
                <tr
                  key={r.id}
                  style={{ color: idx === 0 ? "#51cf66" : undefined }}
                >
                  <td>
                    #{r.id} {idx === 0 && "★ Best"}
                  </td>
                  <td>{(r.stop_loss_pct * 100).toFixed(0)}%</td>
                  <td>{(r.take_profit_pct * 100).toFixed(0)}%</td>
                  <td>${parseFloat(r.final_value).toFixed(2)}</td>
                  <td>{(r.cagr * 100).toFixed(2)}%</td>
                  <td>{r.sharpe_ratio.toFixed(2)}</td>
                  <td>{(r.max_drawdown * 100).toFixed(2)}%</td>
                  <td>{(r.win_rate * 100).toFixed(2)}%</td>
                </tr>
              ))}
            </tbody>
          </table>

          <h3>Overlaid Equity Curves</h3>
          <div className="chart-container">
            <ResponsiveContainer width="100%" height={450}>
              <LineChart
                data={chartData}
                margin={{ top: 10, right: 30, left: 0, bottom: 0 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#2a2a2a" />
                <XAxis dataKey="bar" stroke="#888" tick={{ fontSize: 12 }} />
                <YAxis
                  stroke="#888"
                  domain={["auto", "auto"]}
                  tick={{ fontSize: 12 }}
                />
                <Tooltip
                  contentStyle={{
                    background: "#1a1a1a",
                    border: "1px solid #444",
                    fontSize: "12px",
                    maxWidth: "220px",
                  }}
                  labelStyle={{ color: "#888" }}
                  formatter={(value, name) => [
                    `$${parseFloat(value).toFixed(2)}`,
                    name,
                  ]}
                />
                {runs.map((r, idx) => (
                  <Line
                    key={r.id}
                    type="monotone"
                    dataKey={`run_${r.id}`}
                    name={`#${r.id} (SL ${(r.stop_loss_pct * 100).toFixed(0)}%/TP ${(r.take_profit_pct * 100).toFixed(0)}%)`}
                    stroke={COLORS[idx % COLORS.length]}
                    strokeWidth={1.5}
                    dot={false}
                    connectNulls
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>

            <div className="custom-legend">
              {runs.map((r, idx) => (
                <div key={r.id} className="legend-item">
                  <span
                    className="legend-swatch"
                    style={{ background: COLORS[idx % COLORS.length] }}
                  />
                  <span>
                    #{r.id} — SL {(r.stop_loss_pct * 100).toFixed(0)}% / TP{" "}
                    {(r.take_profit_pct * 100).toFixed(0)}%
                  </span>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export default Comparison;
