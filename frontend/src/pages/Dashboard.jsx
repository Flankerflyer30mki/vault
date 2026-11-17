import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api, { errorText, pct } from "../api";
import { useAuth } from "../auth";
import { Disclaimer } from "../components";

const QUOTA_LABELS = {
  active_jobs: "Jobs running",
  runs_per_day: "Backtests (last 24 h)",
  experiments_per_day: "Comparisons + optimizations (last 24 h)",
  strategies: "Saved strategies",
  ai_requests_per_day: "AI requests (last 24 h)",
};

function QuotaBar({ label, used, limit }) {
  const share = limit ? Math.min(used / limit, 1) : 0;
  return (
    <div className="quota">
      <span>{label}</span>
      <strong>
        {used} / {limit}
      </strong>
      <div className="progress-bar-outer" aria-hidden="true">
        <div className={`progress-bar-inner${share >= 1 ? " full" : ""}`} style={{ width: `${share * 100}%` }} />
      </div>
    </div>
  );
}

function Progress({ run }) {
  if (run.status === "queued") return <span className="hint">Waiting for a worker…</span>;
  if (!run.bars_total) return <span className="hint">{run.status.replace("_", " ")}</span>;
  const share = Math.min((run.bars_processed || 0) / run.bars_total, 1);
  return (
    <div className="progress-bar-outer" title={`${run.bars_processed} / ${run.bars_total} bars`}>
      <div className="progress-bar-inner" style={{ width: `${share * 100}%` }} />
    </div>
  );
}

// Return vs buy & hold over the same bars: the honest context for any single number.
function Versus({ ret, bh }) {
  if (ret === null || ret === undefined) return <span>N/A</span>;
  const beat = bh !== null && bh !== undefined ? ret > bh : null;
  return (
    <span>
      <strong className={ret >= 0 ? "pos" : "neg"}>{pct(ret)}</strong>
      <span className="hint"> vs {pct(bh)} B&amp;H</span>
      {beat !== null && <span className={`badge ${beat ? "badge-pos" : "badge-neg"}`}>{beat ? "beat" : "lagged"}</span>}
    </span>
  );
}

function Dashboard() {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let timer;
    let cancelled = false;
    const load = () =>
      api
        .get("/dashboard/")
        .then((res) => {
          if (cancelled) return;
          setData(res.data);
          setError("");
          const busy = res.data.active_runs.length || res.data.experiments.some((o) => o.status === "running");
          if (busy) timer = setTimeout(load, 3000); // refresh only while something is running
        })
        .catch((err) => !cancelled && setError(errorText(err)));
    load();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, []);

  if (!data) return error ? <p className="error">{error}</p> : <p>Loading…</p>;
  const { quota } = data;

  return (
    <div className="dashboard">
      <h1>{user.display_name && !user.is_guest ? `Hi, ${user.display_name}` : "Dashboard"}</h1>

      <div className="quick-actions">
        <Link className="button" to="/run">
          New backtest
        </Link>
        <Link className="button" to="/compare">
          Compare strategies
        </Link>
        <Link className="button" to="/optimize">
          New optimization
        </Link>
        <Link className="button secondary" to="/strategies">
          Strategies
        </Link>
      </div>

      <section className="dash-section">
        <h3>
          Usage <span className={`tier tier-${quota.tier}`}>{quota.tier}</span>
        </h3>
        <div className="quota-grid">
          {Object.entries(QUOTA_LABELS).map(([k, label]) => (
            <QuotaBar key={k} label={label} used={quota.usage[k]} limit={quota.limits[k]} />
          ))}
        </div>
        {quota.tier !== "verified" && (
          <p className="hint">
            {quota.tier === "guest" ? (
              <>
                <Link to="/account">Save this workspace as an account</Link> to keep it and raise your limits.
              </>
            ) : (
              <>Verify your email to raise your limits.</>
            )}
          </p>
        )}
      </section>

      <section className="dash-section">
        <h3>Running now</h3>
        {data.active_runs.length === 0 ? (
          <p className="hint">Nothing running.</p>
        ) : (
          <table className="trade-table">
            <tbody>
              {data.active_runs.map((r) => (
                <tr key={r.id}>
                  <td>
                    <Link to={`/runs/${r.id}`}>#{r.id}</Link>
                  </td>
                  <td>{r.strategy_name}</td>
                  <td>{r.symbol}</td>
                  <td className="progress-cell">
                    <Progress run={r} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="dash-section">
        <h3>Recent backtests</h3>
        {data.recent_runs.length === 0 ? (
          <p className="hint">
            No backtests yet. <Link to="/run">Run your first one</Link>.
          </p>
        ) : (
          <table className="trade-table">
            <thead>
              <tr>
                <th>Run</th>
                <th>Strategy</th>
                <th>Symbol</th>
                <th>Period</th>
                <th>Return</th>
              </tr>
            </thead>
            <tbody>
              {data.recent_runs.map((r) => (
                <tr key={r.id}>
                  <td>
                    <Link to={`/runs/${r.id}`}>#{r.id}</Link>
                  </td>
                  <td>{r.strategy_name}</td>
                  <td>{r.symbol}</td>
                  <td>
                    {r.start_date} → {r.end_date}
                  </td>
                  <td>
                    {r.status === "failed" ? (
                      <span className="error">failed ({r.failure_category})</span>
                    ) : (
                      <Versus ret={r.total_return} bh={r.buy_and_hold_return} />
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="dash-section">
        <h3>Recent comparisons and optimizations</h3>
        {data.experiments.length === 0 ? (
          <p className="hint">
            None yet. <Link to="/compare">Compare strategies</Link> side by side, or{" "}
            <Link to="/optimize">optimize one</Link>: the best in-sample settings are re-tested once on held-out data.
          </p>
        ) : (
          <table className="trade-table">
            <thead>
              <tr>
                <th>Job</th>
                <th>What</th>
                <th>Symbols</th>
                <th>Status</th>
                <th>Out-of-sample result</th>
              </tr>
            </thead>
            <tbody>
              {data.experiments.map((o) => (
                <tr key={o.id}>
                  <td>
                    <Link to={`/experiments/${o.id}`}>#{o.id}</Link>
                  </td>
                  <td>
                    {o.kind === "comparison" ? "Comparison" : "Optimization"}: {o.title}
                  </td>
                  <td>{o.kind === "comparison" ? o.symbols.join(", ") : o.symbol}</td>
                  <td>
                    {o.status.replace("_", " ")}
                    {o.status === "running" && (
                      <span className="hint">
                        {" "}
                        ({o.runs_done}/{o.runs_total})
                      </span>
                    )}
                  </td>
                  <td>
                    {o.kind === "comparison" ? (
                      <span className="hint">—</span>
                    ) : o.out_of_sample?.status === "completed" ? (
                      <Versus ret={o.out_of_sample.total_return} bh={o.out_of_sample.buy_and_hold_return} />
                    ) : (
                      <span className="hint">{o.out_of_sample ? o.out_of_sample.status : "not yet"}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="dash-section">
        <h3>Strategies</h3>
        <ul className="chip-list">
          {data.strategies.map((s) => (
            <li key={s.id}>
              {s.name}
              {s.is_builtin && <span className="badge">built-in</span>}
            </li>
          ))}
        </ul>
        <p className="hint">
          <Link to="/strategies">Manage strategies</Link>
          {!data.custom_code_enabled && " · Custom code is disabled on this deployment; built-in strategies are available."}
        </p>
      </section>

      <Disclaimer />
    </div>
  );
}

export default Dashboard;
