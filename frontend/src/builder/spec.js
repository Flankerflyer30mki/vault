// Builder form helpers. The form state IS the spec (same shape the API stores), except that numbers are kept as
// the strings the inputs hold, so a half-typed "1." isn't destroyed on every keystroke. toSpec() converts back.
// The allowlist (indicators, params, limits) always comes from GET /api/strategies/catalog/, never from here.

export const operandKind = (o) => ("ind" in o ? "ind" : "price" in o ? "price" : "const");
export const groupMode = (g) => Object.keys(g)[0];
export const conditionsOf = (g) => g[groupMode(g)];

export function indicatorMeta(catalog, id) {
  return catalog.indicators.find((i) => i.id === id);
}

export function makeOperand(catalog, kind, ind = "sma") {
  if (kind === "price") return { price: "close" };
  if (kind === "const") return { const: "0" };
  const meta = indicatorMeta(catalog, ind);
  return {
    ind,
    params: Object.fromEntries(meta.params.map((p) => [p.name, String(p.default)])),
    output: meta.outputs[0],
  };
}

export function makeCondition(catalog, op = ">") {
  return { left: makeOperand(catalog, "ind", "sma"), op, right: makeOperand(catalog, "price") };
}

export function blankSpec(catalog) {
  return { version: 1, entry: { all: [makeCondition(catalog, ">")] }, exit: { any: [makeCondition(catalog, "<")] } };
}

const mapOperand = (o, f) => {
  if ("const" in o) return { const: f(o.const) };
  if ("ind" in o) return { ...o, params: Object.fromEntries(Object.entries(o.params).map(([k, v]) => [k, f(v)])) };
  return { ...o };
};

const mapSpec = (spec, f) => {
  const side = (g) => ({ [groupMode(g)]: conditionsOf(g).map((c) => ({ ...c, left: mapOperand(c.left, f), right: mapOperand(c.right, f) })) });
  return { ...spec, entry: side(spec.entry), exit: side(spec.exit) };
};

export const toFormState = (spec) => mapSpec(spec, (v) => String(v));

// "14" -> 14. Anything that isn't a number is sent as typed, so the server's error points at that exact field.
export const toSpec = (state) =>
  mapSpec(state, (v) => {
    const t = String(v).trim();
    return t !== "" && Number.isFinite(Number(t)) ? Number(t) : v;
  });

// Server errors are keyed by path ("entry.all[0].left.params.period"); a row shows the ones at or under its path.
export function errorsUnder(errors, prefix) {
  return Object.entries(errors || {})
    .filter(([k]) => k === prefix || k.startsWith(`${prefix}.`) || k.startsWith(`${prefix}[`))
    .map(([, v]) => v);
}

// Plain-English sentence for a condition, used as the row's summary and in tests.
export function describe(catalog, c) {
  const op = catalog.operators.find((o) => o.id === c.op)?.label || c.op;
  const side = (o) => {
    if ("const" in o) return String(o.const);
    if ("price" in o) return o.price;
    const meta = indicatorMeta(catalog, o.ind);
    const args = meta ? meta.params.map((p) => o.params[p.name]).join(", ") : "";
    return `${o.ind.toUpperCase()}(${args})${meta && meta.outputs.length > 1 ? ` ${o.output}` : ""}`;
  };
  return `${side(c.left)} ${op} ${side(c.right)}`;
}
