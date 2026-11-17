import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api, { errorText, list } from "../api";
import { SymbolInput } from "../components";
import { OBJECTIVES, STATUS_LABEL } from "../research";

const today = new Date().toISOString().slice(0, 10);

// AI research (Phase 5): describe a goal; the agent proposes, backtests and refines strategies on the first 70% of the
// period, and our code tests its pick once on the last 30%.
function Research() {
  const navigate = useNavigate();
  const [catalog, setCatalog] = useState(null);
  const [runs, setRuns] = useState([]);
  const [form, setForm] = useState({
    goal: "",
    symbol: "AAPL",
    start_date: "2015-01-01",
    end_date: today,
    objective: "sharpe_ratio",
    max_drawdown_pct: "",
  });
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    api.get("/strategies/catalog/").then((res) => setCatalog(res.data)).catch(() => setCatalog({}));
    api.get("/research/").then((res) => setRuns(list(res.data))).catch(() => setRuns([]));
  }, []);

  const set = (changes) => setForm({ ...form, ...changes });
  const submit = (e) => {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    const body = { ...form, max_drawdown_pct: form.max_drawdown_pct === "" ? null : Number(form.max_drawdown_pct) };
    api
      .post("/research/", body)
      .then((res) => navigate(`/research/${res.data.id}`))
      .catch((err) => {
        setError(errorText(err));
        setSubmitting(false);
      });
  };

  if (!catalog) return <p>Loading…</p>;
  if (!catalog.ai_enabled) return <p className="hint">AI research isn&apos;t configured on this deployment.</p>;

  return (
    <div className="research">
      <h1>AI research</h1>
      <p className="hint">
        Describe what you&apos;re looking for. The agent proposes strategies, backtests and refines them on the first
        70% of the period. Then Vault tests its pick <strong>once</strong> on the last 30%, which the agent never sees,
        and reports that result next to buy &amp; hold. You decide what to save.
      </p>
      <form onSubmit={submit} className="research-form">
        <label>
          Goal
          <textarea
            rows={3}
            maxLength={1000}
            required
            value={form.goal}
            placeholder="e.g. A trend-following strategy that beats buy and hold with a smaller drawdown."
            onChange={(e) => set({ goal: e.target.value })}
          />
        </label>
        <SymbolInput value={form.symbol} onChange={(symbol) => set({ symbol })} suggestions={catalog.suggested_symbols || []} />
        <div className="row">
          <label>
            Start
            <input type="date" value={form.start_date} onChange={(e) => set({ start_date: e.target.value })} required />
          </label>
          <label>
            End
            <input type="date" value={form.end_date} max={today} onChange={(e) => set({ end_date: e.target.value })} required />
          </label>
          <label>
            Optimise for
            <select value={form.objective} onChange={(e) => set({ objective: e.target.value })}>
              {Object.entries(OBJECTIVES).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          </label>
          <label>
            Max drawdown % (optional)
            <input
              type="number"
              min="1"
              max="100"
              step="any"
              value={form.max_drawdown_pct}
              onChange={(e) => set({ max_drawdown_pct: e.target.value })}
            />
          </label>
        </div>
        {error && <p className="error pre">{error}</p>}
        <button type="submit" disabled={submitting || form.goal.trim().length < 10}>
          {submitting ? "Starting…" : "Start research"}
        </button>
        <p className="hint">Your goal is sent to an AI service (Groq). A run uses at most 8 decisions and 40 backtests.</p>
      </form>

      {runs.length > 0 && (
        <section>
          <h2>Your research</h2>
          <table>
            <thead>
              <tr>
                <th>Goal</th>
                <th>Symbol</th>
                <th>Status</th>
                <th>Started</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id}>
                  <td>
                    <Link to={`/research/${r.id}`}>{r.goal.length > 70 ? `${r.goal.slice(0, 70)}…` : r.goal}</Link>
                  </td>
                  <td>{r.symbol}</td>
                  <td>{STATUS_LABEL[r.status] || r.status}</td>
                  <td>{new Date(r.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
}

export default Research;
