import { useEffect, useRef, useState } from "react";
import api, { errorText } from "../api";

const DONE = ["completed", "failed"];
const POLL_MS = 1000;
const MAX_POLLS = 120; // two minutes; the worker fails a request it can't finish well before that

// "Describe your strategy" (Phase 4). The server queues the request; a worker asks the AI for a builder spec, which the
// server validates. On success the spec is handed to the builder form for the user to review: nothing is saved here.
function AssistPanel({ maxChars = 1000, onSpec }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [answer, setAnswer] = useState(null);
  const [error, setError] = useState("");
  const timer = useRef(null);

  useEffect(() => () => clearTimeout(timer.current), []);

  const finish = (data) => {
    setBusy(false);
    setAnswer(data);
    if (data.outcome === "spec") onSpec(data.result.spec, data.result.name);
  };

  const poll = (id, n = 0) => {
    api
      .get(`/assist/${id}/`)
      .then((res) => {
        if (DONE.includes(res.data.status)) return finish(res.data);
        if (n >= MAX_POLLS) {
          setBusy(false);
          return setError("The AI is taking too long. Try again in a minute.");
        }
        timer.current = setTimeout(() => poll(id, n + 1), POLL_MS);
        return undefined;
      })
      .catch((err) => {
        setBusy(false);
        setError(errorText(err));
      });
  };

  const submit = (e) => {
    e.preventDefault();
    setError("");
    setAnswer(null);
    setBusy(true);
    api
      .post("/assist/strategy/", { prompt: text })
      .then((res) => (DONE.includes(res.data.status) ? finish(res.data) : poll(res.data.id)))
      .catch((err) => {
        setBusy(false);
        setError(errorText(err));
      });
  };

  return (
    <section className="assist" aria-label="Describe your strategy">
      <form onSubmit={submit}>
        <label htmlFor="assist-text">Describe your strategy in words</label>
        <textarea
          id="assist-text"
          rows={3}
          maxLength={maxChars}
          value={text}
          placeholder="e.g. Buy when the 20-day EMA crosses above the 50-day EMA and RSI 14 is below 70; sell when the EMAs cross back."
          onChange={(e) => setText(e.target.value)}
        />
        <div className="assist-actions">
          <button type="submit" disabled={busy || text.trim().length < 10}>
            {busy ? "Asking the AI…" : "Fill in the rules"}
          </button>
          <span className="hint">
            {text.length}/{maxChars}. Your description is sent to an AI service (Groq). It fills in the form below; nothing
            is saved until you click Save.
          </span>
        </div>
      </form>
      <div aria-live="polite">
        {error && <p className="error">{error}</p>}
        {answer?.outcome === "spec" && (
          <div className="assist-result">
            <p>
              Filled in from your description{answer.cached ? " (an earlier answer to the same description)" : ""}.
              Check the rules below before saving.
            </p>
            {answer.result.notes?.length > 0 && (
              <ul>
                {answer.result.notes.map((n) => (
                  <li key={n}>{n}</li>
                ))}
              </ul>
            )}
          </div>
        )}
        {answer?.outcome === "unsupported" && (
          <p className="error">The AI can&apos;t build that here: {answer.result.reason}</p>
        )}
        {answer?.status === "failed" && <p className="error">{answer.error_message}</p>}
      </div>
    </section>
  );
}

export default AssistPanel;
