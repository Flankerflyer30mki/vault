import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api, { errorText, list } from "../api";
import { CostModelFields, FormSection, PageHeader, SymbolInput } from "../components";
import { parseNumberList, product } from "../experiments";

const today = new Date().toISOString().slice(0, 10);

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
    cost_model: "flat",
  });
  const [stopLossText, setStopLossText] = useState("0.05, 0.08, 0.12");
  const [takeProfitText, setTakeProfitText] = useState("0.10, 0.20");
  const [paramText, setParamText] = useState({}); // label -> "8, 12, 16" for the parameters being searched
  const [catalog, setCatalog] = useState(null);

  useEffect(() => {
    api
      .get("/strategies/")
      .then((res) => {
        const s = list(res.data);
        setStrategies(s);
        if (s.length) setForm((f) => ({ ...f, strategy: s[0].id }));
      })
      .catch((err) => setError(errorText(err)));
    api
      .get("/strategies/catalog/")
      .then((res) => setCatalog(res.data))
      .catch(() => setCatalog(null));
  }, []);

  const set = (field, value) => setForm({ ...form, [field]: value });
  const strategy = strategies.find((s) => String(s.id) === String(form.strategy));
  const tunable = strategy?.tunable_params || [];
  const maxGrid = catalog?.limits?.max_grid || 25;
  const maxParams = catalog?.limits?.max_grid_params || 4;

  const sl = parseNumberList(stopLossText, { label: "Stop loss", min: 0, max: 0.99, exclusiveMin: true });
  const tp = parseNumberList(takeProfitText, { label: "Take profit", min: 0, max: 10, exclusiveMin: true });
  const searched = tunable.filter((g) => g.label in paramText);
  const parsed = searched.map((g) => ({
    g,
    ...parseNumberList(paramText[g.label], { label: g.label, min: g.min, max: g.max, integer: g.type === "int" }),
  }));
  const counts = [sl.values?.length || 0, tp.values?.length || 0, ...parsed.map((p) => p.values?.length || 0)];
  const grid = product(counts);
  const inputError =
    sl.error || tp.error || parsed.find((p) => p.error)?.error
    || (searched.length > maxParams ? `At most ${maxParams} parameters at once` : "")
    || (grid > maxGrid ? `${grid} combinations; the limit is ${maxGrid}` : "");

  const toggleParam = (g) =>
    setParamText((t) => {
      const next = { ...t };
      if (g.label in next) delete next[g.label];
      else next[g.label] = String(g.value);
      return next;
    });

  const pickStrategy = (id) => {
    set("strategy", id);
    setParamText({}); // parameters belong to the strategy they came from
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (inputError) return setError(inputError);
    setError("");
    setSubmitting(true);
    const body = {
      kind: "optimization",
      ...form,
      stop_loss_options: sl.values.map(String),
      take_profit_options: tp.values.map(String),
      param_grid: parsed.map((p) => ({ paths: p.g.paths, values: p.values })),
    };
    api
      .post("/experiments/", body)
      .then((res) => navigate(`/experiments/${res.data.id}`))
      .catch((err) => setError(errorText(err)))
      .finally(() => setSubmitting(false));
  };

  return (
    <div>
      <PageHeader
        title="Optimize a strategy"
        subtitle="Every combination runs on the first 70% of the period (in-sample). The best by Sharpe then runs once on the untouched last 30% (out-of-sample). Judge it by the out-of-sample result, not the in-sample ranking."
      />

      <form onSubmit={handleSubmit} className="run-form wide-form form-card">
        <FormSection title="Strategy and market">
          <label>
            Strategy
            <select value={form.strategy} onChange={(e) => pickStrategy(e.target.value)} required>
              {strategies.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                  {s.is_builtin ? " (built-in)" : ""}
                  {s.kind === "builder" ? " · builder" : ""}
                </option>
              ))}
            </select>
          </label>

          {tunable.length > 0 ? (
            <fieldset className="pick-list">
              <legend>Strategy parameters to search</legend>
              <p className="hint">
                A parameter used in several rules (for example the same EMA in the buy and sell rules) changes everywhere
                together.
              </p>
              {tunable.map((g) => (
                <div key={g.label} className="param-row">
                  <label className="check">
                    <input type="checkbox" checked={g.label in paramText} onChange={() => toggleParam(g)} />
                    {g.label} <span className="hint">(now {g.value}, {g.min}–{g.max})</span>
                  </label>
                  {g.label in paramText && (
                    <input
                      type="text"
                      aria-label={`${g.label} values`}
                      value={paramText[g.label]}
                      onChange={(e) => setParamText({ ...paramText, [g.label]: e.target.value })}
                    />
                  )}
                </div>
              ))}
            </fieldset>
          ) : (
            strategy && <p className="hint">Code strategies search stop-loss and take-profit only.</p>
          )}

          <SymbolInput value={form.symbol} onChange={(v) => set("symbol", v)} suggestions={catalog?.suggested_symbols} />
          <CostModelFields
            catalog={catalog}
            costModel={form.cost_model}
            showCommission={false}
            onChange={({ cost_model }) => set("cost_model", cost_model)}
          />
          <p className="hint">
            {form.cost_model === "india_delivery"
              ? "Each run uses zero brokerage plus India's statutory charges."
              : "Each run uses a 0.1% commission per fill."}
          </p>
        </FormSection>
        <FormSection title="Period and money" grid>
          <label>
            Start date
            <input type="date" value={form.start_date} max={today} onChange={(e) => set("start_date", e.target.value)} required />
          </label>
          <label>
            End date
            <input type="date" value={form.end_date} max={today} onChange={(e) => set("end_date", e.target.value)} required />
          </label>
          <label>
            Starting cash (in the symbol&apos;s currency)
            <input type="number" min={100} max={10000000} value={form.starting_cash} onChange={(e) => set("starting_cash", e.target.value)} required />
          </label>
        </FormSection>
        <FormSection title="Risk settings to search" grid>
          <label>
            Stop-loss options (comma-separated fractions, e.g. 0.05, 0.08)
            <input type="text" value={stopLossText} aria-invalid={!!sl.error} onChange={(e) => setStopLossText(e.target.value)} />
          </label>
          <label>
            Take-profit options (comma-separated fractions, e.g. 0.10, 0.15)
            <input type="text" value={takeProfitText} aria-invalid={!!tp.error} onChange={(e) => setTakeProfitText(e.target.value)} />
          </label>
        </FormSection>
        {error && error !== inputError && <p className="error pre">{error}</p>}
        <div className="form-footer">
          <button type="submit" disabled={submitting || !!inputError}>
            {submitting ? "Queueing…" : "Run optimization"}
          </button>
          <p className={inputError ? "error" : "hint"} aria-live="polite">
            {inputError || `${grid} in-sample backtests + 1 out-of-sample run.`}
          </p>
        </div>
      </form>
    </div>
  );
}

export default OptimizationTrigger;
