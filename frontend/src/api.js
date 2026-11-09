import axios from "axios";
import { useEffect, useState } from "react";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "http://localhost:8000/api",
  timeout: 15000,
});

export default api;

export const TERMINAL = ["completed", "failed", "partially_completed"];

// DRF errors -> "field: message" lines. Never dumps raw JSON or HTML at the user.
export function errorText(err, fallback = "Request failed") {
  const res = err?.response;
  if (!res) return "Cannot reach the API. Check your connection and try again.";
  if (res.status === 429) return "Too many requests. Wait a moment and try again.";
  if (res.status >= 500) return res.data?.detail || "The server is unavailable. Try again shortly.";
  const d = res.data;
  if (d && typeof d === "object") {
    if (d.detail) return d.detail;
    return Object.entries(d)
      .map(([k, v]) => `${k === "non_field_errors" ? "" : k + ": "}${[].concat(v).join(" ")}`)
      .join("\n");
  }
  return fallback;
}

// Polls `url` every `ms` until the payload's status is terminal, `maxErrors` consecutive
// failures occur, or the component unmounts. Returns { data, error }.
export function usePoll(url, ms = 2000, maxErrors = 5) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let timer;
    let errors = 0;
    const controller = new AbortController();
    const tick = () =>
      api
        .get(url, { signal: controller.signal })
        .then((res) => {
          errors = 0;
          setError("");
          setData(res.data);
          if (!TERMINAL.includes(res.data.status)) timer = setTimeout(tick, ms);
        })
        .catch((err) => {
          if (controller.signal.aborted) return;
          errors += 1;
          setError(errorText(err));
          if (errors < maxErrors && err.response?.status !== 404) timer = setTimeout(tick, ms * errors);
        });
    tick();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [url, ms, maxErrors]);

  return { data, error };
}

export const pct = (v, dp = 2) => (v === null || v === undefined ? "N/A" : `${(v * 100).toFixed(dp)}%`);
export const money = (v) => (v === null || v === undefined ? "N/A" : `$${parseFloat(v).toFixed(2)}`);
export const num = (v, dp = 2) => (v === null || v === undefined ? "N/A" : Number(v).toFixed(dp));
export const list = (data) => (Array.isArray(data) ? data : data?.results || []);
// Legacy runs stored a bare list of floats; v2 stores [date, value].
export const toPoints = (curve) => (curve || []).map((p, i) => (Array.isArray(p) ? { t: p[0], v: p[1] } : { t: i, v: p }));
