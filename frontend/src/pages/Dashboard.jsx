import { ChevronRight, GitCompare, Play, SlidersHorizontal } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api, { errorText, pct } from "../api";
import { useAuth } from "../auth";
import { Disclaimer, EmptyState, PageHeader, PageSkeleton, StatusBadge } from "../components";

const QUOTA_LABELS = {
  active_jobs: "Jobs running",
  runs_per_day: "Backtests (last 24 h)",
  experiments_per_day: "Comparisons + optimizations (last 24 h)",
  strategies: "Saved strategies",
  ai_requests_per_day: "AI requests (last 24 h)",
  research_per_day: "AI research runs (last 24 h)",
};

function QuotaBar({ label, used, limit }) {
  const share = limit ? Math.min(used / limit, 1) : 0;
  return (
    <div className="quota">
      <span>{label}</span>
      <strong>
        {used} <span className="quota-limit">/ {limit}</span>
      </strong>
      <div className="progress-bar-outer" aria-hidden="true">
        <div className={`progress-bar-inner${share >= 1 ? " full" : ""}`} style={{ width: `${share * 100}%` }} />
      </div>
    </div>
  );
}

function Progress({ run }) {
  if (run.status === "queued") return <span className="hint">Waiting for a worker…</span>;
  if (!run.bars_total) return <StatusBadge status={run.status} />;
  const share = Math.min((run.bars_processed || 0) / run.bars_total, 1);
  return (
    <div className="progress-bar-outer" title={`${run.bars_processed} / ${run.bars_total} bars`}>
      <div className="progress-bar-inner" style={{ width: `${share * 100}%` }} />
    </div>
  );
}

// Return vs buy & hold over the same bars: the honest context for any single number.
function Versus({ ret, bh }) {
  if (ret === null || ret === undefined) return <span className="hint">N/A</span>;
  const beat = bh !== null && bh !== undefined ? ret > bh : null;
  return (
    <span className="versus">
      <strong className={ret >= 0 ? "pos" : "neg"}>{pct(ret)}</strong>
      <span className="hint"> vs {pct(bh)} B&amp;H</span>
      {beat !== null && <span className={`badge ${beat ? "badge-pos" : "badge-neg"}`}>{beat ? "beat" : "lagged"}</span>}
    </span>
  );
}

// One clickable row: id, a title with a muted line under it, something on the right, a chevron.
function Row({ to, id, title, meta, children }) {
  return (
    <li>
      <Link className="row" to={to}>
        <span className="row-id">#{id}</span>
        <span className="row-main">
          <span className="row-title">{title}</span>
          <span className="row-meta">{meta}</span>
        </span>
        <span className="row-side">{children}</span>
        <ChevronRight className="row-chevron" size={15} aria-hidden="true" />
      </Link>
    </li>
  );
}

function experimentResult(o) {
  if (o.kind === "comparison" || o.status !== "completed") return <StatusBadge status={o.status} />;
  if (o.out_of_sample?.status === "completed") {
    return <Versus ret={o.out_of_sample.total_return} bh={o.out_of_sample.buy_and_hold_return} />;
  }
  return <span className="hint">held-out test {o.out_of_sample ? o.out_of_sample.status : "not yet run"}</span>;
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

  if (!data) return error ? <p className="error">{error}</p> : <PageSkeleton cards={0} rows={6} />;
  const { quota } = data;

  return (
    <div className="dashboard">
      <PageHeader
        title={user.display_name && !user.is_guest ? `Hi, ${user.display_name}` : "Dashboard"}
        subtitle="Your recent backtests and experiments."
      >
        <Link className="button secondary" to="/compare">
          <GitCompare size={14} aria-hidden="true" />
          Compare
        </Link>
        <Link className="button" to="/run">
          <Play size={14} aria-hidden="true" />
          New backtest
        </Link>
      </PageHeader>

      {data.active_runs.length > 0 && (
        <section className="dash-section">
          <h3>Running now</h3>
          <ul className="rows">
            {data.active_runs.map((r) => (
              <Row key={r.id} to={`/runs/${r.id}`} id={r.id} title={r.strategy_name} meta={r.symbol}>
                <span className="progress-cell">
                  <Progress run={r} />
                </span>
              </Row>
            ))}
          </ul>
        </section>
      )}

      <section className="dash-section">
        <h3>Recent backtests</h3>
        {data.recent_runs.length === 0 ? (
          <EmptyState
            icon={Play}
            title="No backtests yet"
            action={
              <Link className="button small" to="/run">
                Run your first one
              </Link>
            }
          >
            Pick a strategy and a symbol; results are compared with simply holding the stock.
          </EmptyState>
        ) : (
          <ul className="rows">
            {data.recent_runs.map((r) => (
              <Row
                key={r.id}
                to={`/runs/${r.id}`}
                id={r.id}
                title={r.strategy_name}
                meta={
                  <>
                    <span className="mono">{r.symbol}</span> · {r.start_date} → {r.end_date}
                  </>
                }
              >
                {r.status === "failed" ? (
                  <span className="error">failed ({r.failure_category})</span>
                ) : r.status === "completed" ? (
                  <Versus ret={r.total_return} bh={r.buy_and_hold_return} />
                ) : (
                  <StatusBadge status={r.status} />
                )}
              </Row>
            ))}
          </ul>
        )}
      </section>

      <section className="dash-section">
        <h3>Recent comparisons and optimizations</h3>
        {data.experiments.length === 0 ? (
          <EmptyState icon={SlidersHorizontal} title="No experiments yet">
            <Link to="/compare">Compare strategies</Link> side by side, or <Link to="/optimize">optimize one</Link>:
            the best in-sample settings are re-tested once on held-out data.
          </EmptyState>
        ) : (
          <ul className="rows">
            {data.experiments.map((o) => (
              <Row
                key={o.id}
                to={`/experiments/${o.id}`}
                id={o.id}
                title={`${o.kind === "comparison" ? "Comparison" : "Optimization"}: ${o.title}`}
                meta={
                  <>
                    <span className="mono">{o.kind === "comparison" ? o.symbols.join(", ") : o.symbol}</span>
                    {o.status === "running" && ` · ${o.runs_done}/${o.runs_total} runs`}
                  </>
                }
              >
                {experimentResult(o)}
              </Row>
            ))}
          </ul>
        )}
      </section>

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

      <Disclaimer />
    </div>
  );
}

export default Dashboard;
