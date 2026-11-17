import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api, { errorText, list } from "../api";
import { CostModelFields } from "../components";
import { symbolList } from "../experiments";

const today = new Date().toISOString().slice(0, 10);

function ComparisonTrigger() {
  const navigate = useNavigate();
  const [strategies, setStrategies] = useState([]);
  const [catalog, setCatalog] = useState(null);
  const [picked, setPicked] = useState([]);
  const [symbolsText, setSymbolsText] = useState("AAPL, MSFT");
  const [form, setForm] = useState({
    start_date: "2022-01-01",
    end_date: today,
    starting_cash: "10000",
    cost_model: "flat",
    commission_pct: "0.001",
    stop_loss_pct: "",
    take_profit_pct: "",
  });
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    api
      .get("/strategies/")
      .then((res) => setStrategies(list(res.data)))
      .catch((err) => setError(errorText(err)));
    api
      .get("/strategies/catalog/")
      .then((res) => setCatalog(res.data))
      .catch(() => setCatalog(null));
  }, []);

  const runnable = strategies.filter((s) => s.kind === "builder" || s.is_builtin || catalog?.custom_code_enabled);
  const symbols = symbolList(symbolsText);
  const limits = catalog?.limits || { max_grid: 25, max_compare_strategies: 10, max_compare_symbols: 10 };
  const cells = picked.length * symbols.length;
  const inputError =
    picked.length === 0 ? "Pick at least one strategy"
      : symbols.length === 0 ? "Enter at least one symbol"
        : picked.length > limits.max_compare_strategies ? `At most ${limits.max_compare_strategies} strategies`
          : symbols.length > limits.max_compare_symbols ? `At most ${limits.max_compare_symbols} symbols`
            : new Set(symbols).size !== symbols.length ? "Symbols must be unique"
              : cells > limits.max_grid ? `${cells} cells; the limit is ${limits.max_grid}` : "";

  const toggle = (id) => setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));
  const addSymbol = (s) => !symbols.includes(s) && setSymbolsText(symbols.concat(s).join(", "));
  const set = (changes) => setForm({ ...form, ...changes });

  const handleSubmit = (e) => {
    e.preventDefault();
    if (inputError) return setError(inputError);
    setError("");
    setSubmitting(true);
    const body = { kind: "comparison", strategies: picked, symbols, ...form };
    for (const f of ["stop_loss_pct", "take_profit_pct"]) if (body[f] === "") body[f] = null;
    api
      .post("/experiments/", body)
      .then((res) => navigate(`/experiments/${res.data.id}`))
      .catch((err) => setError(errorText(err)))
      .finally(() => setSubmitting(false));
  };

  return (
    <div>
      <h1>Compare strategies</h1>
      <p className="hint">
        Every chosen strategy runs on every symbol over the same period and costs, next to an index benchmark
        (NIFTY 50 for Indian symbols, S&amp;P 500 for US ones). Each cell is an ordinary backtest you can open.
      </p>
      <form onSubmit={handleSubmit} className="run-form wide-form">
        <fieldset className="pick-list">
          <legend>Strategies ({picked.length} chosen)</legend>
          {runnable.map((s) => (
            <label key={s.id} className="check">
              <input type="checkbox" checked={picked.includes(s.id)} onChange={() => toggle(s.id)} />
              {s.name}
              {s.is_builtin ? <span className="badge">built-in</span> : null}
            </label>
          ))}
        </fieldset>
        <label>
          Symbols (comma-separated Yahoo tickers)
          <input type="text" value={symbolsText} onChange={(e) => setSymbolsText(e.target.value)} />
        </label>
        <div className="chip-row" aria-label="Suggested symbols">
          {(catalog?.suggested_symbols || []).map((s) => (
            <button key={s.symbol} type="button" className="secondary small" title={s.name} onClick={() => addSymbol(s.symbol)}>
              + {s.symbol}
            </button>
          ))}
        </div>
        <CostModelFields catalog={catalog} costModel={form.cost_model} commission={form.commission_pct} onChange={set} />
        <label>
          Start Date
          <input type="date" value={form.start_date} max={today} onChange={(e) => set({ start_date: e.target.value })} required />
        </label>
        <label>
          End Date
          <input type="date" value={form.end_date} max={today} onChange={(e) => set({ end_date: e.target.value })} required />
        </label>
        <label>
          Starting cash (in each symbol&apos;s currency)
          <input type="number" min={100} max={10000000} value={form.starting_cash} onChange={(e) => set({ starting_cash: e.target.value })} required />
        </label>
        <label>
          Stop loss for every cell (0.08 = 8%, blank = none)
          <input type="number" step="0.01" min={0.001} max={0.99} value={form.stop_loss_pct} onChange={(e) => set({ stop_loss_pct: e.target.value })} />
        </label>
        <label>
          Take profit for every cell (0.15 = 15%, blank = none)
          <input type="number" step="0.01" min={0.001} max={10} value={form.take_profit_pct} onChange={(e) => set({ take_profit_pct: e.target.value })} />
        </label>
        <p className={inputError ? "error" : "hint"} aria-live="polite">
          {inputError || `${picked.length} × ${symbols.length} = ${cells} backtests, plus benchmarks.`}
        </p>
        {error && error !== inputError && <p className="error pre">{error}</p>}
        <button type="submit" disabled={submitting || !!inputError}>
          {submitting ? "Queueing…" : "Run comparison"}
        </button>
      </form>
    </div>
  );
}

export default ComparisonTrigger;
