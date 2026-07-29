import { useEffect, useState } from "react";
import api from "../api";

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
          <li key={s.id}>
            <strong>{s.name}</strong> (id: {s.id})<pre>{s.code}</pre>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default StrategyList;
