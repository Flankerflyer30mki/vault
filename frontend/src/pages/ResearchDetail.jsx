import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import api, { errorText, num, pct, usePoll } from "../api";
import { OBJECTIVES, STATUS_LABEL } from "../research";

const STAGES = ["explore", "refine", "validate", "report", "done"];
const STAGE_LABEL = { explore: "Explore", refine: "Refine", validate: "Held-out test", report: "Report", done: "Done" };
const CHECK_LABEL = {
  held_out_tested_once: "Held-out period tested exactly once",
  agent_never_saw_held_out_period: "The agent never saw the held-out period",
  budgets_respected: "Step and backtest budgets respected",
  summary_numbers_grounded: "Every number in the summary comes from the results",
  drawdown_constraint_met_held_out: "Drawdown constraint met on the held-out period",
};

function SaveButton({ candidate }) {
  const [state, setState] = useState("");
  const save = () => {
    setState("saving");
    api
      .post("/strategies/", { name: candidate.name.slice(0, 100), kind: "builder", spec: candidate.spec })
      .then((res) => setState(`saved:${res.data.id}`))
      .catch((err) => setState(`error:${errorText(err)}`));
  };
  if (state.startsWith("saved:")) return <Link to={`/strategies/${state.slice(6)}/edit`}>Saved: open</Link>;
  return (
    <>
      <button type="button" className="secondary small" onClick={save} disabled={state === "saving"}>
        Save as strategy
      </button>
      {state.startsWith("error:") && <span className="error"> {state.slice(6)}</span>}
    </>
  );
}

function Step({ s }) {
  const what = {
    test: `tested ${s.args?.candidates?.map((c) => c.id).join(", ")}`,
    search: `searched ${s.args?.parameter} of ${s.args?.of}: ${s.args?.candidates?.map((c) => c.id).join(", ")}`,
    next_stage: "moved on to refining",
    choose: `chose ${s.args?.candidate}`,
    holdout: "held-out test",
    report: "report",
    rejected: "action rejected",
    failed: "stopped",
  }[s.action] || s.action;
  return (
    <li className={`step step-${s.actor}${s.ok ? "" : " step-bad"}`}>
      <span className="step-who">{s.actor === "agent" ? "Agent" : "Vault"}</span> <strong>{what}</strong>
      {s.note && <p>{s.note}</p>}
      {s.action === "rejected" && s.result?.errors && (
        <ul className="hint">
          {Object.entries(s.result.errors).map(([k, v]) => (
            <li key={k}>
              {k}: {v}
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

function Report({ run }) {
  const r = run.report;
  const h = r.held_out_result;
  const research = r.research_result;
  return (
    <section className="research-report">
      <h2>Result: {r.chosen.name}</h2>
      <p className="hint">
        {r.chosen.rules} · chosen by {r.chosen.chosen_by === "code" ? "Vault (a budget ran out)" : "the agent"} from{" "}
        {r.candidates_tested} candidates
      </p>
      <table>
        <thead>
          <tr>
            <th />
            <th>Research period ({r.research_period})</th>
            <th>Held-out period ({r.held_out_period})</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>Total return</td>
            <td>{pct(research.total_return)}</td>
            <td>{h ? pct(h.total_return) : "n/a"}</td>
          </tr>
          <tr>
            <td>Buy &amp; hold</td>
            <td>{pct(research.buy_and_hold_return)}</td>
            <td>{h ? pct(h.buy_and_hold_return) : "n/a"}</td>
          </tr>
          <tr>
            <td>Sharpe</td>
            <td>{num(research.sharpe_ratio)}</td>
            <td>{h ? num(h.sharpe_ratio) : "n/a"}</td>
          </tr>
          <tr>
            <td>Max drawdown</td>
            <td>{pct(research.max_drawdown)}</td>
            <td>{h ? pct(h.max_drawdown) : "n/a"}</td>
          </tr>
          <tr>
            <td>Round trips</td>
            <td>{research.trade_count}</td>
            <td>{h ? h.trade_count : "n/a"}</td>
          </tr>
        </tbody>
      </table>
      {r.beat_buy_and_hold_held_out !== null && (
        <p className={r.beat_buy_and_hold_held_out ? "" : "error"}>
          On the held-out period it {r.beat_buy_and_hold_held_out ? "beat" : "did not beat"} buy &amp; hold.
        </p>
      )}
      <p>{r.text.summary}</p>
      {r.text.why && <p className="hint">{r.text.why}</p>}
      {r.text.caveats?.length > 0 && (
        <ul>
          {r.text.caveats.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ul>
      )}
      <h3>Checks</h3>
      <ul className="checks">
        {Object.entries(r.checks)
          .filter(([, v]) => v !== null)
          .map(([k, v]) => (
            <li key={k} className={v ? "check-ok" : "check-bad"}>
              {v ? "✓" : "✗"} {CHECK_LABEL[k] || k}
            </li>
          ))}
      </ul>
      <p className="hint">
        The research result is optimistic: it was picked from {r.candidates_tested} candidates on that data. The
        held-out result is the fairer estimate. Past results don&apos;t predict future returns.
      </p>
    </section>
  );
}

function ResearchDetail() {
  const { id } = useParams();
  const { data: run, error } = usePoll(`/research/${id}/`, 2000);
  if (error && !run) return <p className="error">{error}</p>;
  if (!run) return <p>Loading…</p>;
  const stageIndex = STAGES.indexOf(run.stage);
  const candidates = run.candidates || [];
  const steps = run.steps || [];
  return (
    <div className="research">
      <h1>Research: {run.symbol}</h1>
      <p className="research-goal">“{run.goal}”</p>
      <p className="hint">
        Optimising {OBJECTIVES[run.objective]}
        {run.max_drawdown ? `, max drawdown ${pct(run.max_drawdown, 0)}` : ""}. Research {run.start_date} to{" "}
        {run.research_end}; held out {run.split_date} to {run.end_date}.
      </p>
      <ol className="stages">
        {STAGES.map((s, i) => (
          <li key={s} className={i < stageIndex ? "done" : i === stageIndex ? "current" : ""}>
            {STAGE_LABEL[s]}
          </li>
        ))}
      </ol>
      <p>
        <strong>{STATUS_LABEL[run.status] || run.status}</strong> · {run.steps_used}/{run.budgets.steps} decisions ·{" "}
        {run.backtests_used}/{run.budgets.backtests} backtests · {(run.tokens_in + run.tokens_out).toLocaleString()}/
        {run.budgets.tokens.toLocaleString()} tokens
      </p>
      {run.status === "failed" && <p className="error">{run.error_message}</p>}
      {run.report && <Report run={run} />}

      {candidates.length > 0 && (
        <section>
          <h2>Candidates (research period)</h2>
          <table className="candidates">
            <thead>
              <tr>
                <th>ID</th>
                <th>Name</th>
                <th>Sharpe</th>
                <th>Return</th>
                <th>Max DD</th>
                <th>Trades</th>
                <th>Eligible</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {candidates.map((c) => (
                <tr key={c.id} className={run.report?.chosen.id === c.id ? "chosen" : ""} title={c.rules}>
                  <td>{c.id}</td>
                  <td>
                    <Link to={`/runs/${c.run_id}`}>{c.name}</Link>
                  </td>
                  <td>{c.metrics ? num(c.metrics.sharpe_ratio) : c.status}</td>
                  <td>{c.metrics ? pct(c.metrics.total_return) : ""}</td>
                  <td>{c.metrics ? pct(c.metrics.max_drawdown) : ""}</td>
                  <td>{c.metrics ? c.metrics.trade_count : ""}</td>
                  <td>{c.metrics ? (c.eligible ? "yes" : "no") : ""}</td>
                  <td>{c.status === "completed" && <SaveButton candidate={c} />}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      <section>
        <h2>Timeline</h2>
        {steps.length === 0 ? (
          <p className="hint">The agent is starting…</p>
        ) : (
          <ol className="timeline">
            {steps.map((s) => (
              <Step key={s.index} s={s} />
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}

export default ResearchDetail;
