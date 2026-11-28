import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import api, { errorText, list } from "../api";
import { CostModelFields, FormSection, PageHeader, SymbolInput } from "../components";

const today = new Date().toISOString().slice(0, 10);

// [field, label, step, min, max]
const NUMERIC = [
  ["starting_cash", "Starting cash (in the symbol's currency)", "1", 100, 10000000],
  ["max_position_pct", "Max Position (fraction of cash, 0.01–1)", "0.01", 0.01, 1],
  ["slippage_pct", "Slippage per fill (0.0005 = 0.05%)", "0.0001", 0, 0.05],
  ["stop_loss_pct", "Stop loss (0.08 = 8%, blank = none)", "0.001", 0.001, 0.99],
  ["take_profit_pct", "Take profit (0.15 = 15%, blank = none)", "0.001", 0.001, 10],
];

function RunTrigger() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [wanted] = useState(() => Number(params.get("strategy")) || null); // /run?strategy=<id>&symbol=<s> preselects them
  const [strategies, setStrategies] = useState([]);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [form, setForm] = useState({
    strategy: "",
    symbol: (params.get("symbol") || "AAPL").toUpperCase(), // "Run again" passes the symbol
    start_date: "2024-01-01",
    end_date: today,
    starting_cash: "10000",
    max_position_pct: "1",
    cost_model: "flat",
    commission_pct: "0.001",
    slippage_pct: "0.0005",
    stop_loss_pct: "", // optional: blank = no stop
    take_profit_pct: "", // optional: blank = no target
  });
  const [catalog, setCatalog] = useState(null);

  useEffect(() => {
    api
      .get("/strategies/")
      .then((res) => {
        const s = list(res.data);
        setStrategies(s);
        const pick = s.find((x) => x.id === wanted) || s[0];
        if (pick) setForm((f) => ({ ...f, strategy: pick.id }));
      })
      .catch((err) => setError(errorText(err)));
    api
      .get("/strategies/catalog/")
      .then((res) => setCatalog(res.data))
      .catch(() => setCatalog(null)); // the form still works with the flat model and no suggestions
  }, [wanted]);

  // Same form submitted twice (double click, retry) = same key = same run. Any edit = new key.
  const [idemKey, setIdemKey] = useState(() => crypto.randomUUID());
  const set = (field, value) => patch({ [field]: value });
  const patch = (changes) => {
    setForm({ ...form, ...changes });
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

  // One number field from NUMERIC, by name.
  const numberField = (field) => {
    const [, label, step, min, max] = NUMERIC.find(([f]) => f === field);
    return (
      <label key={field}>
        {label}
        <input
          type="number"
          step={step}
          min={min}
          max={max}
          value={form[field]}
          placeholder={["stop_loss_pct", "take_profit_pct"].includes(field) ? "none" : undefined}
          required={!["stop_loss_pct", "take_profit_pct"].includes(field)}
          onChange={(e) => set(field, e.target.value)}
        />
      </label>
    );
  };

  return (
    <div>
      <PageHeader title="New backtest" subtitle="Run one strategy on one symbol. Signals use each day's close; orders fill at the next open." />
      <form onSubmit={handleSubmit} className="run-form form-card">
        <FormSection title="Strategy and market">
          <label>
            Strategy
            <select value={form.strategy} onChange={(e) => set("strategy", e.target.value)} required>
              {strategies.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                  {s.is_builtin ? " (built-in)" : ""}
                  {s.kind === "builder" ? " · builder" : ""}
                </option>
              ))}
            </select>
          </label>
          <SymbolInput value={form.symbol} onChange={(v) => set("symbol", v)} suggestions={catalog?.suggested_symbols} />
        </FormSection>
        <FormSection title="Period" grid>
          <label>
            Start date
            <input type="date" value={form.start_date} max={today} onChange={(e) => set("start_date", e.target.value)} required />
          </label>
          <label>
            End date
            <input type="date" value={form.end_date} max={today} onChange={(e) => set("end_date", e.target.value)} required />
          </label>
        </FormSection>
        <FormSection title="Money and costs" grid>
          {numberField("starting_cash")}
          {numberField("max_position_pct")}
          <CostModelFields
            catalog={catalog}
            costModel={form.cost_model}
            commission={form.commission_pct}
            onChange={patch}
          />
          {numberField("slippage_pct")}
        </FormSection>
        <FormSection title="Risk (optional)" grid>
          {numberField("stop_loss_pct")}
          {numberField("take_profit_pct")}
        </FormSection>
        {error && <p className="error pre">{error}</p>}
        <div className="form-footer">
          <button type="submit" disabled={submitting}>
            {submitting ? "Queueing…" : "Run backtest"}
          </button>
        </div>
      </form>
    </div>
  );
}

export default RunTrigger;
