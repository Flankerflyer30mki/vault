import { useEffect, useState } from "react";
import api, { errorText, list } from "../api";

const TEMPLATE = `def on_bar(bar, indicators, state):
    fast, slow = indicators.get('sma_10'), indicators.get('sma_50')
    if fast is None or slow is None:
        return "HOLD"
    return "BUY" if fast > slow else "SELL"
`;

function StrategyCard({ strategy }) {
  const [expanded, setExpanded] = useState(false);
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
        <span className="strategy-meta">
          id: {strategy.id} · {expanded ? "Hide code ▲" : "Show code ▼"}
        </span>
      </button>
      {expanded && <pre>{strategy.code}</pre>}
    </li>
  );
}

function StrategyList() {
  const [strategies, setStrategies] = useState([]);
  const [name, setName] = useState("");
  const [code, setCode] = useState(TEMPLATE);
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");

  const fetchStrategies = () =>
    api
      .get("/strategies/")
      .then((res) => setStrategies(list(res.data)))
      .catch((err) => setLoadError(errorText(err)));

  useEffect(() => {
    fetchStrategies();
  }, []);

  const handleSubmit = (e) => {
    e.preventDefault();
    setError("");
    api
      .post("/strategies/", { name, code })
      .then(() => {
        setName("");
        setCode(TEMPLATE);
        fetchStrategies();
      })
      .catch((err) => setError(errorText(err)));
  };

  return (
    <div>
      <h1>Strategies</h1>
      {loadError && <p className="error">{loadError}</p>}

      <h3>Available Strategies</h3>
      <ul className="strategy-list">
        {strategies.map((s) => (
          <StrategyCard key={s.id} strategy={s} />
        ))}
      </ul>

      <form onSubmit={handleSubmit} className="strategy-form">
        <h3>New Strategy</h3>
        <p className="hint">
          Custom code runs only where the operator has enabled it. The public demo runs built-in strategies only.
          Allowed: plain Python and <code>import math</code>. Return &quot;BUY&quot;, &quot;SELL&quot; or
          &quot;HOLD&quot;.
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
        <button type="submit">Create Strategy</button>
      </form>
    </div>
  );
}

export default StrategyList;
