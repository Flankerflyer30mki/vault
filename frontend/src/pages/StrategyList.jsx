import { ChevronRight, Copy, Pencil, Play, Plus, Search, Trash2, Workflow } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api, { errorText, list } from "../api";
import { EmptyState, PageHeader, PageSkeleton } from "../components";

const TEMPLATE = `def on_bar(bar, indicators, state):
    fast, slow = indicators.get('sma_10'), indicators.get('sma_50')
    if fast is None or slow is None:
        return "HOLD"
    return "BUY" if fast > slow else "SELL"
`;

// One strategy: a row that expands to show its rules (builder, as read-only Python) or its code.
function StrategyCard({ strategy, onDelete }) {
  const [expanded, setExpanded] = useState(false);
  const builder = strategy.kind === "builder";
  return (
    <li className={expanded ? "expanded" : undefined}>
      <div className="strategy-row">
        <button
          type="button"
          className="strategy-card-header"
          aria-expanded={expanded}
          onClick={() => setExpanded(!expanded)}
          title={expanded ? "Hide" : builder ? "Show rules" : "Show code"}
        >
          <ChevronRight className="expand-chevron" size={15} aria-hidden="true" />
          <span className="strategy-name">{strategy.name}</span>
          <span className="badge badge-kind">{builder ? "builder" : "code"}</span>
          <span className="sr-only">{expanded ? "Hide" : builder ? "Show rules" : "Show code"}</span>
        </button>
        <div className="strategy-actions">
          <Link className="button ghost small" to={`/run?strategy=${strategy.id}`}>
            <Play size={13} aria-hidden="true" />
            Backtest
          </Link>
          {builder && (
            <Link className="button ghost small" to={`/strategies/new?from=${strategy.id}`}>
              <Copy size={13} aria-hidden="true" />
              Use as template
            </Link>
          )}
          {builder && !strategy.is_builtin && (
            <Link className="button ghost small" to={`/strategies/${strategy.id}/edit`}>
              <Pencil size={13} aria-hidden="true" />
              Edit
            </Link>
          )}
          {!strategy.is_builtin && (
            <button
              type="button"
              className="ghost small icon-only danger-hover"
              onClick={() => onDelete(strategy)}
              aria-label={`Delete ${strategy.name}`}
              title="Delete"
            >
              <Trash2 size={13} aria-hidden="true" />
            </button>
          )}
        </div>
      </div>
      {expanded && <pre>{builder ? strategy.python : strategy.code}</pre>}
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
  const [strategies, setStrategies] = useState(null); // null = still loading
  const [codeEnabled, setCodeEnabled] = useState(false);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");

  const fetchStrategies = () =>
    api
      .get("/strategies/")
      .then((res) => setStrategies(list(res.data)))
      .catch((err) => {
        setStrategies((s) => s || []);
        setError(errorText(err));
      });

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

  if (strategies === null) return <PageSkeleton cards={0} rows={8} />;

  const q = query.trim().toLowerCase();
  const shown = q ? strategies.filter((s) => s.name.toLowerCase().includes(q)) : strategies;
  const mine = shown.filter((s) => !s.is_builtin);
  const builtins = shown.filter((s) => s.is_builtin);
  const ownCount = strategies.filter((s) => !s.is_builtin).length;

  return (
    <div>
      <PageHeader title="Strategies" subtitle="Rules that decide when to buy and sell. Start from a template or build your own.">
        <Link className="button" to="/strategies/new">
          <Plus size={14} aria-hidden="true" />
          New strategy
        </Link>
      </PageHeader>
      {error && <p className="error pre">{error}</p>}

      <label className="search-field">
        <Search size={14} aria-hidden="true" />
        <input
          type="search"
          placeholder="Filter strategies…"
          aria-label="Filter strategies"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </label>

      <h3>
        Your strategies <span className="count">{mine.length}</span>
      </h3>
      {ownCount === 0 ? (
        <EmptyState
          icon={Workflow}
          title="No strategies of your own yet"
          action={
            <Link className="button small" to="/strategies/new">
              Build one
            </Link>
          }
        >
          Build one from scratch, or use a built-in template below as a starting point.
        </EmptyState>
      ) : mine.length === 0 ? (
        <p className="hint">No match.</p>
      ) : (
        <ul className="strategy-list">
          {mine.map((s) => (
            <StrategyCard key={s.id} strategy={s} onDelete={handleDelete} />
          ))}
        </ul>
      )}

      <h3>
        Built-in strategies and templates <span className="count">{builtins.length}</span>
      </h3>
      {builtins.length === 0 ? (
        <p className="hint">No match.</p>
      ) : (
        <ul className="strategy-list">
          {builtins.map((s) => (
            <StrategyCard key={s.id} strategy={s} onDelete={handleDelete} />
          ))}
        </ul>
      )}
      {!codeEnabled && (
        <p className="hint">Custom Python strategies are turned off on this deployment; the builder is always available.</p>
      )}

      {codeEnabled && <CodeStrategyForm onCreated={fetchStrategies} />}
    </div>
  );
}

export default StrategyList;
