import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api, { errorText, list } from "../api";

const today = new Date().toISOString().slice(0, 10);

// [field, label, step, min, max]
const NUMERIC = [
  ["starting_cash", "Starting Cash ($)", "1", 100, 10000000],
  ["max_position_pct", "Max Position (fraction of cash, 0.01–1)", "0.01", 0.01, 1],
  ["commission_pct", "Commission per fill (0.001 = 0.1%)", "0.0001", 0, 0.05],
  ["slippage_pct", "Slippage per fill (0.0005 = 0.05%)", "0.0001", 0, 0.05],
  ["stop_loss_pct", "Stop Loss (0.08 = 8%, blank = none)", "0.01", 0.001, 0.99],
  ["take_profit_pct", "Take Profit (0.15 = 15%, blank = none)", "0.01", 0.001, 10],
];

function RunTrigger() {
  const navigate = useNavigate();
  const [strategies, setStrategies] = useState([]);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [form, setForm] = useState({
    strategy: "",
    symbol: "AAPL",
    start_date: "2024-01-01",
    end_date: today,
    starting_cash: "10000",
    max_position_pct: "1",
    commission_pct: "0.001",
    slippage_pct: "0.0005",
    stop_loss_pct: "0.08",
    take_profit_pct: "0.15",
  });

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

  // Same form submitted twice (double click, retry) = same key = same run. Any edit = new key.
  const [idemKey, setIdemKey] = useState(() => crypto.randomUUID());
  const set = (field, value) => {
    setForm({ ...form, [field]: value });
    setIdemKey(crypto.randomUUID());
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    const payload = { ...form };
    for (const f of ["stop_loss_pct", "take_profit_pct"]) if (payload[f] === "") payload[f] = null;
    api
      .post("/runs/", payload, { headers: { "Idempotency-Key": idemKey } })
      .then((res) => navigate(`/runs/${res.data.id}`))
      .catch((err) => setError(errorText(err)))
      .finally(() => setSubmitting(false));
  };

  return (
    <div>
      <h1>New Backtest</h1>
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
          Symbol (Yahoo ticker)
          <input
            type="text"
            value={form.symbol}
            pattern="[A-Za-z0-9.\-^=]{1,20}"
            onChange={(e) => set("symbol", e.target.value.toUpperCase())}
            required
          />
        </label>
        <label>
          Start Date
          <input type="date" value={form.start_date} max={today} onChange={(e) => set("start_date", e.target.value)} required />
        </label>
        <label>
          End Date
          <input type="date" value={form.end_date} max={today} onChange={(e) => set("end_date", e.target.value)} required />
        </label>
        {NUMERIC.map(([field, label, step, min, max]) => (
          <label key={field}>
            {label}
            <input
              type="number"
              step={step}
              min={min}
              max={max}
              value={form[field]}
              required={!["stop_loss_pct", "take_profit_pct"].includes(field)}
              onChange={(e) => set(field, e.target.value)}
            />
          </label>
        ))}
        {error && <p className="error pre">{error}</p>}
        <button type="submit" disabled={submitting}>
          {submitting ? "Queueing…" : "Run Backtest"}
        </button>
      </form>
    </div>
  );
}

export default RunTrigger;
