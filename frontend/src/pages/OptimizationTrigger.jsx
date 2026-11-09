import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api, { errorText, list } from "../api";

const MAX_VALUES = 10;
const MAX_GRID = 25; // server enforces its own limit; this is only early feedback
const today = new Date().toISOString().slice(0, 10);

// Returns { values } or { error } naming the first bad entry. Nothing is silently dropped.
function parseList(text, label, max) {
  const parts = text.split(",").map((s) => s.trim()).filter(Boolean);
  if (parts.length === 0) return { error: `${label}: enter at least one value` };
  if (parts.length > MAX_VALUES) return { error: `${label}: at most ${MAX_VALUES} values` };
  for (const p of parts) {
    const n = Number(p);
    if (!/^\d*\.?\d+$/.test(p) || !(n > 0 && n <= max)) return { error: `${label}: "${p}" must be a number in (0, ${max}]` };
  }
  if (new Set(parts.map(Number)).size !== parts.length) return { error: `${label}: values must be unique` };
  return { values: parts };
}

function OptimizationTrigger() {
  const navigate = useNavigate();
  const [strategies, setStrategies] = useState([]);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [form, setForm] = useState({
    strategy: "",
    symbol: "AAPL",
    start_date: "2022-01-01",
    end_date: today,
    starting_cash: "10000",
  });
  const [stopLossText, setStopLossText] = useState("0.05, 0.08, 0.12");
  const [takeProfitText, setTakeProfitText] = useState("0.10, 0.15, 0.20");

  useEffect(() => {
    api
      .get("/strategies/")
      .then((res) => {
        const s = list(res.data);
        setStrategies(s);
        if (s.length) setForm((f) => ({ ...f, strategy: s[0].id }));
      })
      .catch((err) => setError(errorText(err)));
  }, []);

  const set = (field, value) => setForm({ ...form, [field]: value });
  const sl = parseList(stopLossText, "Stop loss", 0.99);
  const tp = parseList(takeProfitText, "Take profit", 10);
  const grid = (sl.values?.length || 0) * (tp.values?.length || 0);
  const inputError = sl.error || tp.error || (grid > MAX_GRID ? `${grid} combinations; the limit is ${MAX_GRID}` : "");

  const handleSubmit = (e) => {
    e.preventDefault();
    if (inputError) return setError(inputError);
    setError("");
    setSubmitting(true);
    api
      .post("/optimizations/", { ...form, stop_loss_options: sl.values, take_profit_options: tp.values })
      .then((res) => navigate(`/optimize/${res.data.id}`))
      .catch((err) => setError(errorText(err)))
      .finally(() => setSubmitting(false));
  };

  return (
    <div>
      <h1>Parameter Optimization</h1>
      <p className="hint">
        Every stop-loss × take-profit combination runs on the first 70% of the period (in-sample). The best
        combination by Sharpe is then run once on the untouched last 30% (out-of-sample). Judge it by the
        out-of-sample result, not the in-sample ranking.
      </p>

      <form onSubmit={handleSubmit} className="run-form">
        <label>
          Strategy
          <select value={form.strategy} onChange={(e) => set("strategy", e.target.value)} required>
            {strategies.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
                {s.is_builtin ? " (built-in)" : ""}
              </option>
            ))}
          </select>
        </label>
        <label>
          Symbol
          <input type="text" value={form.symbol} onChange={(e) => set("symbol", e.target.value.toUpperCase())} required />
        </label>
        <label>
          Start Date
          <input type="date" value={form.start_date} max={today} onChange={(e) => set("start_date", e.target.value)} required />
        </label>
        <label>
          End Date
          <input type="date" value={form.end_date} max={today} onChange={(e) => set("end_date", e.target.value)} required />
        </label>
        <label>
          Starting Cash ($)
          <input type="number" min={100} max={10000000} value={form.starting_cash} onChange={(e) => set("starting_cash", e.target.value)} required />
        </label>
        <label>
          Stop Loss Options (comma-separated fractions, e.g. 0.05, 0.08)
          <input type="text" value={stopLossText} aria-invalid={!!sl.error} onChange={(e) => setStopLossText(e.target.value)} />
        </label>
        <label>
          Take Profit Options (comma-separated fractions, e.g. 0.10, 0.15)
          <input type="text" value={takeProfitText} aria-invalid={!!tp.error} onChange={(e) => setTakeProfitText(e.target.value)} />
        </label>
        <p className={inputError ? "error" : "hint"}>{inputError || `${grid} in-sample backtests + 1 out-of-sample run.`}</p>
        {error && error !== inputError && <p className="error pre">{error}</p>}
        <button type="submit" disabled={submitting || !!inputError}>
          {submitting ? "Queueing…" : "Run Optimization"}
        </button>
      </form>
    </div>
  );
}

export default OptimizationTrigger;
