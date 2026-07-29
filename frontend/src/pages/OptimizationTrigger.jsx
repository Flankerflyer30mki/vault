import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../api";

function OptimizationTrigger() {
  const navigate = useNavigate();
  const [strategies, setStrategies] = useState([]);
  const [error, setError] = useState("");

  const [form, setForm] = useState({
    strategy: "",
    symbol: "AAPL",
    start_date: "2024-01-01",
    end_date: "2026-07-27",
    starting_cash: 10000,
  });

  const [stopLossText, setStopLossText] = useState("0.05, 0.08, 0.12");
  const [takeProfitText, setTakeProfitText] = useState("0.10, 0.15, 0.20");

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

  const parseNumberList = (text) => {
    return text
      .split(",")
      .map((s) => parseFloat(s.trim()))
      .filter((n) => !isNaN(n));
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    setError("");

    const stop_loss_options = parseNumberList(stopLossText);
    const take_profit_options = parseNumberList(takeProfitText);

    if (stop_loss_options.length === 0 || take_profit_options.length === 0) {
      setError(
        "Please provide at least one valid number in each parameter list.",
      );
      return;
    }

    const payload = {
      ...form,
      stop_loss_options,
      take_profit_options,
    };

    api
      .post("/optimizations/", payload)
      .then((response) => {
        navigate(`/optimize/${response.data.id}`);
      })
      .catch((err) => {
        const detail =
          JSON.stringify(err.response?.data) ||
          "Failed to create optimization job";
        setError(detail);
      });
  };

  const totalCombinations =
    parseNumberList(stopLossText).length *
    parseNumberList(takeProfitText).length;

  return (
    <div>
      <h1>Parameter Optimization</h1>
      <p className="hint">
        Runs the same strategy across every combination of stop-loss and
        take-profit values, so you can compare which setup performs best.
      </p>

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
          Stop Loss Options (comma-separated, e.g. 0.05, 0.08, 0.12)
          <input
            type="text"
            value={stopLossText}
            onChange={(e) => setStopLossText(e.target.value)}
          />
        </label>

        <label>
          Take Profit Options (comma-separated, e.g. 0.10, 0.15, 0.20)
          <input
            type="text"
            value={takeProfitText}
            onChange={(e) => setTakeProfitText(e.target.value)}
          />
        </label>

        <p className="hint">
          This will run {totalCombinations} backtests concurrently.
        </p>

        {error && <p className="error">{error}</p>}
        <button type="submit">Run Optimization</button>
      </form>
    </div>
  );
}

export default OptimizationTrigger;
