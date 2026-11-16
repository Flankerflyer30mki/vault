// Pure helpers for experiment forms and pages (comparisons and optimizations). Kept free of React so they're
// unit-tested directly. The server re-validates everything; these only give early feedback.
import { num, pct } from "./api";

// "5, 8, 12" -> { values: [5, 8, 12] } or { error } naming the first bad entry. Nothing is silently dropped.
export function parseNumberList(text, { label, min = -Infinity, max = Infinity, integer = false, maxCount = 10, exclusiveMin = false }) {
  const parts = String(text).split(",").map((s) => s.trim()).filter(Boolean);
  if (parts.length === 0) return { error: `${label}: enter at least one value` };
  if (parts.length > maxCount) return { error: `${label}: at most ${maxCount} values` };
  const values = [];
  for (const p of parts) {
    const n = Number(p);
    const low = exclusiveMin ? n > min : n >= min;
    if (p === "" || !Number.isFinite(n) || !low || n > max) {
      return { error: `${label}: "${p}" must be a number ${exclusiveMin ? `in (${min}, ${max}]` : `from ${min} to ${max}`}` };
    }
    if (integer && !Number.isInteger(n)) return { error: `${label}: "${p}" must be a whole number` };
    values.push(n);
  }
  if (new Set(values).size !== values.length) return { error: `${label}: values must be unique` };
  return { values };
}

export const symbolList = (text) =>
  String(text)
    .split(/[\s,]+/)
    .map((s) => s.trim().toUpperCase())
    .filter(Boolean);

export const product = (counts) => counts.reduce((a, b) => a * b, 1);

// The metrics a comparison can be ranked or coloured by. higherIsBetter drives the heatmap colour direction.
export const METRICS = [
  { id: "total_return", label: "Total return", fmt: (v) => pct(v), higherIsBetter: true },
  { id: "sharpe_ratio", label: "Sharpe", fmt: (v) => num(v), higherIsBetter: true },
  { id: "sortino_ratio", label: "Sortino", fmt: (v) => num(v), higherIsBetter: true },
  { id: "calmar_ratio", label: "Calmar", fmt: (v) => num(v), higherIsBetter: true },
  { id: "max_drawdown", label: "Max drawdown", fmt: (v) => pct(v), higherIsBetter: false },
  { id: "exposure", label: "Exposure", fmt: (v) => pct(v, 0), higherIsBetter: null },
  { id: "cost_drag", label: "Cost drag", fmt: (v) => pct(v), higherIsBetter: false },
];

export function metricValue(run, id) {
  if (id === "total_return") {
    if (run.final_value === null || run.final_value === undefined || !Number(run.starting_cash)) return null;
    return Number(run.final_value) / Number(run.starting_cash) - 1;
  }
  const v = run[id];
  return v === null || v === undefined ? null : Number(v);
}

// Comparison runs -> a strategies × symbols grid. Rows and columns keep the order the user chose.
export function buildMatrix(job) {
  const cells = (job.runs || []).filter((r) => r.sample === "full");
  const symbols = job.config?.symbols || [...new Set(cells.map((r) => r.symbol))];
  const order = job.config?.strategies || [];
  const rows = [];
  const byStrategy = new Map();
  for (const r of cells) {
    if (!byStrategy.has(r.strategy)) byStrategy.set(r.strategy, { id: r.strategy, name: r.strategy_name, cells: {} });
    byStrategy.get(r.strategy).cells[r.symbol] = r;
  }
  for (const id of order) if (byStrategy.has(id)) rows.push(byStrategy.get(id));
  for (const [id, row] of byStrategy) if (!order.includes(id)) rows.push(row);
  const benchmarks = (job.runs || []).filter((r) => r.sample === "bench");
  return { symbols, rows, benchmarks };
}

// 0..1 position of a value within the column's range, flipped when lower is better; null when undefined.
export function heatLevel(value, values, higherIsBetter) {
  if (value === null || higherIsBetter === null) return null;
  const finite = values.filter((v) => v !== null && Number.isFinite(v));
  const lo = Math.min(...finite), hi = Math.max(...finite);
  if (!(hi > lo)) return 0.5;
  const t = (value - lo) / (hi - lo);
  return higherIsBetter ? t : 1 - t;
}

// "ema(12).period 8 · SL 5% · TP 20%" for an optimization child.
export function paramLabel(run) {
  const g = run.grid_params || {};
  const parts = Object.entries(g)
    .filter(([k]) => k !== "stop_loss_pct" && k !== "take_profit_pct")
    .map(([k, v]) => `${k} ${v}`);
  parts.push(`SL ${pct(run.stop_loss_pct, 0)}`, `TP ${pct(run.take_profit_pct, 0)}`);
  return parts.join(" · ");
}

// Downsampled curves of several runs merged on date for one chart.
export function mergeCurves(runs, key = (r) => `run_${r.id}`) {
  const byDate = new Map();
  for (const r of runs) {
    for (const p of r.curve || []) {
      const [t, v] = Array.isArray(p) ? p : [null, p];
      if (!byDate.has(t)) byDate.set(t, { t });
      byDate.get(t)[key(r)] = v;
    }
  }
  return [...byDate.values()].sort((a, b) => (a.t < b.t ? -1 : a.t > b.t ? 1 : 0));
}
