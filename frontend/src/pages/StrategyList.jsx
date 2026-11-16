import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api, { errorText, list } from "../api";

const TEMPLATE = `def on_bar(bar, indicators, state):
    fast, slow = indicators.get('sma_10'), indicators.get('sma_50')
    if fast is None or slow is None:
        return "HOLD"
    return "BUY" if fast > slow else "SELL"
`;

function StrategyCard({ strategy, onDelete }) {
  const [expanded, setExpanded] = useState(false);
  const builder = strategy.kind === "builder";
  return (
    <li>
      <button
        type="button"
        className="strategy-card-header"
        aria-expanded={expanded}
        onClick={() => setExpanded(!expanded)}
      >
        <strong>{strategy.name}</strong>
        {strategy.is_builtin && <span className="badge">built-in</span>}
        <span className="badge badge-kind">{builder ? "builder" : "code"}</span>
        <span className="strategy-meta">
          id: {strategy.id} · {expanded ? "Hide ▲" : builder ? "Show rules ▼" : "Show code ▼"}
        </span>
      </button>
      {expanded && <pre>{builder ? strategy.python : strategy.code}</pre>}
      <div className="strategy-actions">
        {builder && (
          <Link className="button secondary small" to={`/strategies/new?from=${strategy.id}`}>
            Use as template
          </Link>
        )}
        {builder && !strategy.is_builtin && (
          <Link className="button secondary small" to={`/strategies/${strategy.id}/edit`}>
            Edit
          </Link>
        )}
        {!strategy.is_builtin && (
          <button type="button" className="secondary small" onClick={() => onDelete(strategy)}>
            Delete
          </button>
        )}
      </div>
    </li>
  );
}

function CodeStrategyForm({ onCreated }) {
  const [name, setName] = useState("");
  const [code, setCode] = useState(TEMPLATE);
  const [error, setError] = useState("");

  const handleSubmit = (e) => {
    e.preventDefault();
    setError("");
    api
      .post("/strategies/", { name, kind: "code", code })
      .then(() => {
        setName("");
        setCode(TEMPLATE);
        onCreated();
      })
      .catch((err) => setError(errorText(err)));
  };

  return (
    <form onSubmit={handleSubmit} className="strategy-form">
      <h3>New code strategy</h3>
      <p className="hint">
        Custom code is enabled on this deployment. Allowed: plain Python and <code>import math</code>. Return
        &quot;BUY&quot;, &quot;SELL&quot; or &quot;HOLD&quot;.
      </p>
      <input
        type="text"
        placeholder="Strategy name"
        value={name}
        maxLength={100}
        onChange={(e) => setName(e.target.value)}
        required
      />
      <textarea
        aria-label="Strategy code"
        value={code}
        onChange={(e) => setCode(e.target.value)}
        rows={10}
        maxLength={10000}
        required
      />
      {error && <p className="error pre">{error}</p>}
      <button type="submit">Create code strategy</button>
    </form>
  );
}

function StrategyList() {
  const [strategies, setStrategies] = useState([]);
  const [codeEnabled, setCodeEnabled] = useState(false);
  const [error, setError] = useState("");

  const fetchStrategies = () =>
    api
      .get("/strategies/")
      .then((res) => setStrategies(list(res.data)))
      .catch((err) => setError(errorText(err)));

  useEffect(() => {
    fetchStrategies();
    api
      .get("/strategies/catalog/")
      .then((res) => setCodeEnabled(res.data.custom_code_enabled))
      .catch(() => setCodeEnabled(false));
  }, []);

  const handleDelete = (s) => {
    if (!window.confirm(`Delete "${s.name}"? This can't be undone.`)) return;
    setError("");
    api
      .delete(`/strategies/${s.id}/`)
      .then(fetchStrategies)
      .catch((err) => setError(errorText(err)));
  };

  const mine = strategies.filter((s) => !s.is_builtin);
  const builtins = strategies.filter((s) => s.is_builtin);

  return (
    <div>
      <div className="page-head">
        <h1>Strategies</h1>
        <Link className="button" to="/strategies/new">
          New strategy
        </Link>
      </div>
      {error && <p className="error pre">{error}</p>}

      <h3>Your strategies</h3>
      {mine.length === 0 ? (
        <p className="hint">None yet. Build one from scratch, or start from a built-in template below.</p>
      ) : (
        <ul className="strategy-list">
          {mine.map((s) => (
            <StrategyCard key={s.id} strategy={s} onDelete={handleDelete} />
          ))}
        </ul>
      )}

      <h3>Built-in strategies and templates</h3>
      <ul className="strategy-list">
        {builtins.map((s) => (
          <StrategyCard key={s.id} strategy={s} onDelete={handleDelete} />
        ))}
      </ul>

      {codeEnabled && <CodeStrategyForm onCreated={fetchStrategies} />}
    </div>
  );
}

export default StrategyList;
