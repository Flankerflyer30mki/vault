import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../api";

function RunTrigger() {
  const navigate = useNavigate();
  const [strategies, setStrategies] = useState([]);
  const [error, setError] = useState("");

  const [form, setForm] = useState({
    strategy: "",
    symbol: "AAPL",
    start_date: "2024-01-01",
    end_date: "2026-07-27",
    starting_cash: 10000,
    max_position_pct: 1.0,
    commission_pct: 0.001,
    slippage_pct: 0.0005,
    stop_loss_pct: 0.08,
    take_profit_pct: 0.15,
  });

  useEffect(() => {
    api.get("/strategies/").then((response) => {
      setStrategies(response.data);
      if (response.data.length > 0) {
        setForm((f) => ({ ...f, strategy: response.data[0].id }));
      }
    });
  }, []);

  const handleChange = (field, value) => {
    setForm({ ...form, [field]: value });
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    setError("");
    api
      .post("/runs/", form)
      .then((response) => {
        navigate(`/runs/${response.data.id}`);
      })
      .catch((err) => {
        const detail =
          err.response?.data?.non_field_errors?.[0] ||
          JSON.stringify(err.response?.data) ||
          "Failed to create run";
        setError(detail);
      });
  };

  return (
    <div>
      <h1>New Backtest</h1>
      <form onSubmit={handleSubmit} className="run-form">
        <label>
          Strategy
          <select
            value={form.strategy}
            onChange={(e) => handleChange("strategy", e.target.value)}
          >
            {strategies.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </label>

        <label>
          Symbol
          <input
            type="text"
            value={form.symbol}
            onChange={(e) =>
              handleChange("symbol", e.target.value.toUpperCase())
            }
          />
        </label>

        <label>
          Start Date
          <input
            type="date"
            value={form.start_date}
            onChange={(e) => handleChange("start_date", e.target.value)}
          />
        </label>

        <label>
          End Date
          <input
            type="date"
            value={form.end_date}
            onChange={(e) => handleChange("end_date", e.target.value)}
          />
        </label>

        <label>
          Starting Cash
          <input
            type="number"
            value={form.starting_cash}
            onChange={(e) => handleChange("starting_cash", e.target.value)}
          />
        </label>

        <label>
          Max Position % (0-1)
          <input
            type="number"
            step="0.1"
            value={form.max_position_pct}
            onChange={(e) => handleChange("max_position_pct", e.target.value)}
          />
        </label>

        <label>
          Commission % (e.g. 0.001 = 0.1%)
          <input
            type="number"
            step="0.001"
            value={form.commission_pct}
            onChange={(e) => handleChange("commission_pct", e.target.value)}
          />
        </label>

        <label>
          Slippage % (e.g. 0.0005 = 0.05%)
          <input
            type="number"
            step="0.0001"
            value={form.slippage_pct}
            onChange={(e) => handleChange("slippage_pct", e.target.value)}
          />
        </label>

        <label>
          Stop Loss % (e.g. 0.08 = 8%)
          <input
            type="number"
            step="0.01"
            value={form.stop_loss_pct}
            onChange={(e) => handleChange("stop_loss_pct", e.target.value)}
          />
        </label>

        <label>
          Take Profit % (e.g. 0.15 = 15%)
          <input
            type="number"
            step="0.01"
            value={form.take_profit_pct}
            onChange={(e) => handleChange("take_profit_pct", e.target.value)}
          />
        </label>

        {error && <p className="error">{error}</p>}
        <button type="submit">Run Backtest</button>
      </form>
    </div>
  );
}

export default RunTrigger;
