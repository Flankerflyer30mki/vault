import { useEffect, useState } from "react";

// Chart colours come from the CSS tokens (index.css), so charts follow the light/dark theme. SVG presentation
// attributes can't use var(), so the values are read from the document and re-read when the theme changes.
const TOKENS = {
  accent: "--accent",
  text: "--text",
  muted: "--text-muted",
  faint: "--text-faint",
  grid: "--border",
  surface: "--bg-elev",
  pos: "--pos",
  neg: "--neg",
  bench: "--chart-bench",
};
const SERIES_COUNT = 9;
// Used when the tokens can't be read (tests: jsdom has no stylesheet).
const FALLBACK = { accent: "#8b95f7", text: "#d6d7da", muted: "#8a8f98", faint: "#5f636b", grid: "#212226", surface: "#0e0f11", pos: "#4cc38a", neg: "#f2666a", bench: "#8a8f98" };

function readTheme() {
  const style = getComputedStyle(document.documentElement);
  const get = (name, fallback) => style.getPropertyValue(name).trim() || fallback;
  const theme = Object.fromEntries(Object.entries(TOKENS).map(([k, v]) => [k, get(v, FALLBACK[k])]));
  theme.series = Array.from({ length: SERIES_COUNT }, (_, i) => get(`--series-${i + 1}`, FALLBACK.accent));
  return theme;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useChartTheme() {
  const [theme, setTheme] = useState(readTheme);
  useEffect(() => {
    const observer = new MutationObserver(() => setTheme(readTheme()));
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => observer.disconnect();
  }, []);
  return theme;
}

// Quiet axes: no axis line or tick marks, faint labels.
// eslint-disable-next-line react-refresh/only-export-components
export const axisProps = (theme) => ({
  stroke: theme.grid,
  tick: { fill: theme.faint, fontSize: 11 },
  tickLine: false,
  axisLine: false,
});

// 12345.6 → "12.3k"; keeps the y axis narrow.
// eslint-disable-next-line react-refresh/only-export-components
export const compact = (v) =>
  new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(v);

// Tooltip body styled by CSS (.chart-tooltip) instead of inline colours.
export function ChartTooltip({ active, payload, label, format = (v) => v }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip-label">{label}</div>
      {payload.map((p) => (
        <div key={p.dataKey} className="chart-tooltip-row">
          <span className="legend-swatch" style={{ background: p.color || p.stroke }} />
          <span className="chart-tooltip-name">{p.name}</span>
          <strong>{format(p.value)}</strong>
        </div>
      ))}
    </div>
  );
}
