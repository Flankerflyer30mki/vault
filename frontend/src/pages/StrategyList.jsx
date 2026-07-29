import { useEffect, useState } from "react";
import api from "../api";

const TEMPLATES = {
  "SMA Crossover": `def on_bar(bar, indicators, state):
    sma_10 = indicators.get('sma_10')
    sma_50 = indicators.get('sma_50')

    if sma_10 is None or sma_50 is None:
        return "HOLD"

    if sma_10 > sma_50:
        return "BUY"
    elif sma_10 < sma_50:
        return "SELL"
    else:
        return "HOLD"
`,
  "Momentum Threshold": `def on_bar(bar, indicators, state):
    sma_10 = indicators.get('sma_10')
    sma_50 = indicators.get('sma_50')

    if sma_10 is None or sma_50 is None:
        return "HOLD"

    diff_pct = (sma_10 - sma_50) / sma_50

    if diff_pct > 0.02:
        return "BUY"
    elif diff_pct < -0.02:
        return "SELL"
    else:
        return "HOLD"
`,
  "Always Hold (do nothing)": `def on_bar(bar, indicators, state):
    return "HOLD"
`,
};
function StrategyCard({ strategy }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <li>
      <div
        className="strategy-card-header"
        onClick={() => setExpanded(!expanded)}
      >
        <strong>{strategy.name}</strong>
        <span className="strategy-meta">
          id: {strategy.id} · {expanded ? "Hide code ▲" : "Show code ▼"}
        </span>
      </div>
      {expanded && <pre>{strategy.code}</pre>}
    </li>
  );
}
function StrategyList() {
  const [strategies, setStrategies] = useState([]);
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState("");

  const fetchStrategies = () => {
    api.get("/strategies/").then((response) => {
      setStrategies(response.data);
    });
  };

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
        setCode("");
        fetchStrategies();
      })
      .catch((err) => {
        setError("Failed to create strategy. Check your code syntax.");
      });
  };

  return (
    <div>
      <h1>Strategies</h1>

      <form onSubmit={handleSubmit} className="strategy-form">
        <h3>New Strategy</h3>
        <input
          type="text"
          placeholder="Strategy name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />

        <label>
          Start from a template (optional)
          <select
            onChange={(e) =>
              e.target.value && setCode(TEMPLATES[e.target.value])
            }
            defaultValue=""
          >
            <option value="">-- Select a template --</option>
            {Object.keys(TEMPLATES).map((key) => (
              <option key={key} value={key}>
                {key}
              </option>
            ))}
          </select>
        </label>

        <textarea
          placeholder={`def on_bar(bar, indicators, state):\n    sma_10 = indicators.get('sma_10')\n    sma_50 = indicators.get('sma_50')\n    ...\n    return "BUY" or "SELL" or "HOLD"`}
          value={code}
          onChange={(e) => setCode(e.target.value)}
          rows={10}
          required
        />
        {error && <p className="error">{error}</p>}
        <button type="submit">Create Strategy</button>
      </form>

      <h3>Existing Strategies</h3>
      <ul className="strategy-list">
        {strategies.map((s) => (
          <StrategyCard key={s.id} strategy={s} />
        ))}
      </ul>
    </div>
  );
}

export default StrategyList;
