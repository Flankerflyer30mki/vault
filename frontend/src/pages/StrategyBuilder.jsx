import { useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import api, { errorText } from "../api";
import AssistPanel from "../builder/AssistPanel";
import { PageSkeleton } from "../components";
import {
  blankSpec,
  conditionsOf,
  describe,
  errorsUnder,
  groupMode,
  indicatorMeta,
  makeCondition,
  makeOperand,
  operandKind,
  toFormState,
  toSpec,
} from "../builder/spec";

const KIND_LABEL = { ind: "Indicator", price: "Price", const: "Number" };
const SIDE = {
  entry: { title: "Buy when", help: "Checked on every bar while in cash." },
  exit: { title: "Sell when", help: "Checked on every bar while holding. If both groups are true, the sell wins." },
};

function FieldError({ errors, path }) {
  const msg = errors[path];
  return msg ? <span className="field-error">{msg}</span> : null;
}

function OperandEditor({ operand, path, label, catalog, errors, onChange }) {
  const kind = operandKind(operand);
  const meta = kind === "ind" ? indicatorMeta(catalog, operand.ind) : null;
  return (
    <div className="operand">
      <select aria-label={`${label} type`} value={kind} onChange={(e) => onChange(makeOperand(catalog, e.target.value))}>
        {Object.entries(KIND_LABEL).map(([k, v]) => (
          <option key={k} value={k}>
            {v}
          </option>
        ))}
      </select>

      {kind === "ind" && (
        <>
          <select
            aria-label={`${label} indicator`}
            value={operand.ind}
            onChange={(e) => onChange(makeOperand(catalog, "ind", e.target.value))}
          >
            {catalog.indicators.map((i) => (
              <option key={i.id} value={i.id}>
                {i.label}
              </option>
            ))}
          </select>
          {meta.params.map((p) => (
            <label key={p.name} className="param">
              {p.name}
              <input
                type="number"
                aria-label={`${label} ${p.name}`}
                min={p.min}
                max={p.max}
                step={p.type === "int" ? 1 : 0.1}
                value={operand.params[p.name]}
                aria-invalid={!!errors[`${path}.params.${p.name}`]}
                onChange={(e) => onChange({ ...operand, params: { ...operand.params, [p.name]: e.target.value } })}
              />
              <FieldError errors={errors} path={`${path}.params.${p.name}`} />
            </label>
          ))}
          {meta.outputs.length > 1 && (
            <select
              aria-label={`${label} output`}
              value={operand.output}
              onChange={(e) => onChange({ ...operand, output: e.target.value })}
            >
              {meta.outputs.map((o) => (
                <option key={o} value={o}>
                  {o}
                </option>
              ))}
            </select>
          )}
          <FieldError errors={errors} path={`${path}.ind`} />
          <FieldError errors={errors} path={`${path}.output`} />
        </>
      )}

      {kind === "price" && (
        <select aria-label={`${label} price`} value={operand.price} onChange={(e) => onChange({ price: e.target.value })}>
          {catalog.price_fields.map((f) => (
            <option key={f} value={f}>
              {f}
            </option>
          ))}
        </select>
      )}

      {kind === "const" && (
        <>
          <input
            type="number"
            step="any"
            aria-label={`${label} number`}
            value={operand.const}
            aria-invalid={!!errors[`${path}.const`]}
            onChange={(e) => onChange({ const: e.target.value })}
          />
          <FieldError errors={errors} path={`${path}.const`} />
        </>
      )}
      <FieldError errors={errors} path={path} />
    </div>
  );
}

function ConditionRow({ cond, path, label, catalog, errors, onChange, onRemove, canRemove }) {
  const rowErrors = errorsUnder(errors, path).length > 0;
  return (
    <li className={`condition${rowErrors ? " has-error" : ""}`}>
      <p className="condition-summary">{describe(catalog, cond)}</p>
      <div className="condition-fields">
        <OperandEditor
          operand={cond.left}
          path={`${path}.left`}
          label={`${label} left`}
          catalog={catalog}
          errors={errors}
          onChange={(left) => onChange({ ...cond, left })}
        />
        <select aria-label={`${label} operator`} value={cond.op} onChange={(e) => onChange({ ...cond, op: e.target.value })}>
          {catalog.operators.map((o) => (
            <option key={o.id} value={o.id}>
              {o.label}
            </option>
          ))}
        </select>
        <OperandEditor
          operand={cond.right}
          path={`${path}.right`}
          label={`${label} right`}
          catalog={catalog}
          errors={errors}
          onChange={(right) => onChange({ ...cond, right })}
        />
        <button type="button" className="secondary small" onClick={onRemove} disabled={!canRemove} aria-label={`Remove ${label}`}>
          Remove
        </button>
      </div>
      <FieldError errors={errors} path={`${path}.op`} />
      <FieldError errors={errors} path={path} />
    </li>
  );
}

function GroupEditor({ side, group, catalog, errors, onChange }) {
  const mode = groupMode(group);
  const conds = conditionsOf(group);
  const setConds = (next) => onChange({ [mode]: next });
  return (
    <fieldset className="group">
      <legend>{SIDE[side].title}</legend>
      <p className="hint">{SIDE[side].help}</p>
      <label>
        Combine
        <select aria-label={`${side} combine`} value={mode} onChange={(e) => onChange({ [e.target.value]: conds })}>
          <option value="all">all of these are true (AND)</option>
          <option value="any">any of these is true (OR)</option>
        </select>
      </label>
      <ol className="conditions">
        {conds.map((c, i) => (
          <ConditionRow
            key={i}
            cond={c}
            path={`${side}.${mode}[${i}]`}
            label={`${side} condition ${i + 1}`}
            catalog={catalog}
            errors={errors}
            canRemove={conds.length > 1}
            onChange={(next) => setConds(conds.map((x, j) => (j === i ? next : x)))}
            onRemove={() => setConds(conds.filter((_, j) => j !== i))}
          />
        ))}
      </ol>
      <FieldError errors={errors} path={side} />
      <FieldError errors={errors} path={`${side}.${mode}`} />
      <button
        type="button"
        className="secondary"
        disabled={conds.length >= catalog.max_conditions}
        onClick={() => setConds([...conds, makeCondition(catalog, side === "entry" ? ">" : "<")])}
      >
        Add condition ({conds.length}/{catalog.max_conditions})
      </button>
    </fieldset>
  );
}

function StrategyBuilder() {
  const { id } = useParams(); // editing an existing strategy
  const [search] = useSearchParams();
  const from = search.get("from"); // starting from a template
  const navigate = useNavigate();
  const [catalog, setCatalog] = useState(null);
  const [name, setName] = useState("");
  const [state, setState] = useState(null);
  const [errors, setErrors] = useState({});
  const [formError, setFormError] = useState("");
  const [preview, setPreview] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const source = id || from;
    Promise.all([api.get("/strategies/catalog/"), source ? api.get(`/strategies/${source}/`) : null])
      .then(([c, s]) => {
        setCatalog(c.data);
        if (!s) return setState(blankSpec(c.data));
        if (s.data.kind !== "builder") return setFormError("This strategy is written in code; it can't be opened in the builder.");
        setState(toFormState(s.data.spec));
        setName(id ? s.data.name : `${s.data.name} (copy)`.slice(0, 100));
      })
      .catch((err) => setFormError(errorText(err)));
  }, [id, from]);

  // Live check while editing: the server validates and renders the spec, so the form never re-implements the rules.
  useEffect(() => {
    if (!state) return undefined;
    const timer = setTimeout(() => {
      api
        .post("/strategies/preview/", { spec: toSpec(state) })
        .then((res) => {
          setPreview(res.data);
          setErrors({});
        })
        .catch((err) => {
          const e = err?.response?.data?.spec;
          setPreview(null);
          if (e && typeof e === "object" && !Array.isArray(e)) setErrors(e);
        });
    }, 400);
    return () => clearTimeout(timer);
  }, [state]);

  const save = (e) => {
    e.preventDefault();
    setSaving(true);
    setFormError("");
    const spec = toSpec(state);
    const req = id ? api.patch(`/strategies/${id}/`, { name, spec }) : api.post("/strategies/", { name, kind: "builder", spec });
    req
      .then(() => navigate("/strategies"))
      .catch((err) => {
        const d = err?.response?.data;
        if (d?.spec && typeof d.spec === "object" && !Array.isArray(d.spec)) {
          setErrors(d.spec);
          setFormError("Fix the highlighted fields.");
        } else {
          setFormError(errorText(err));
        }
      })
      .finally(() => setSaving(false));
  };

  if (!catalog || !state) return formError ? <p className="error">{formError}</p> : <PageSkeleton cards={0} rows={4} />;
  const problems = Object.keys(errors).length;

  return (
    <div className="builder">
      <h1>{id ? "Edit strategy" : "New strategy"}</h1>
      <p className="hint">
        On every bar: if the sell group is true, sell; otherwise, if the buy group is true, buy. Orders fill at the next
        bar&apos;s open. Long-only: the strategy is either fully invested or in cash.
      </p>
      {catalog.ai_enabled && (
        <AssistPanel
          onSpec={(spec, suggested) => {
            setState(toFormState(spec));
            setName((current) => current || suggested);
          }}
        />
      )}
      {/* noValidate: the server is the one source of truth, so its message shows on the field (the same wording
          as the live check) instead of the browser's own popup. min/max still drive the number spinners. */}
      <form onSubmit={save} noValidate>
        <label className="builder-name">
          Name
          <input type="text" value={name} maxLength={100} required onChange={(e) => setName(e.target.value)} />
        </label>
        {["entry", "exit"].map((side) => (
          <GroupEditor
            key={side}
            side={side}
            group={state[side]}
            catalog={catalog}
            errors={errors}
            onChange={(group) => setState({ ...state, [side]: group })}
          />
        ))}

        <section className="preview" aria-live="polite">
          {problems > 0 ? (
            <p className="error">
              {problems} problem{problems > 1 ? "s" : ""} to fix.
            </p>
          ) : (
            preview && (
              <>
                <p className="hint">
                  Needs {preview.warmup_bars} warm-up bar{preview.warmup_bars > 1 ? "s" : ""} before the start date.
                </p>
                <details>
                  <summary>View as Python (read-only; Vault runs the spec, never this code)</summary>
                  <pre>{preview.python}</pre>
                </details>
              </>
            )
          )}
        </section>

        {formError && <p className="error pre">{formError}</p>}
        <div className="builder-actions">
          <button type="submit" disabled={saving}>
            {saving ? "Saving…" : id ? "Save changes" : "Save strategy"}
          </button>
          <Link className="button secondary" to="/strategies">
            Cancel
          </Link>
        </div>
      </form>
    </div>
  );
}

export default StrategyBuilder;
