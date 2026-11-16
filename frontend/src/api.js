import axios from "axios";
import { useEffect, useState } from "react";

// Same-origin API: Vite (dev), nginx (compose) and Vercel (prod) forward /api to Django, so the session
// cookie is first-party and there is no CORS. axios echoes the csrftoken cookie in X-CSRFToken on every
// unsafe request, reading it fresh each time (Django rotates it on login).
const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "/api",
  timeout: 15000,
  xsrfCookieName: "csrftoken",
  xsrfHeaderName: "X-CSRFToken",
});

// Any "not signed in" answer (session expired, signed out in another tab, password changed elsewhere)
// tells the auth context, which sends the user to the login page.
export const UNAUTHENTICATED = "vault:unauthenticated";
api.interceptors.response.use(
  (res) => res,
  (err) => {
    const detail = err?.response?.data?.detail;
    if (err?.response?.status === 403 && typeof detail === "string" && detail.startsWith("Authentication credentials")) {
      window.dispatchEvent(new Event(UNAUTHENTICATED));
    }
    return Promise.reject(err);
  },
);

export default api;

export const TERMINAL = ["completed", "failed", "partially_completed"];

// DRF errors -> "field: message" lines. Never dumps raw JSON or HTML at the user.
export function errorText(err, fallback = "Request failed") {
  const res = err?.response;
  if (!res) return "Cannot reach the API. Check your connection and try again.";
  if (res.status === 429) return res.data?.detail && !/throttled/i.test(res.data.detail)
    ? res.data.detail // a quota message says which limit was hit
    : "Too many requests. Wait a moment and try again.";
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
// Money in the symbol's currency (the API sends "INR", "USD", or null when the exchange is unknown).
// INR uses Indian digit grouping: ₹1,00,000.00.
export const money = (v, currency = "USD") => {
  if (v === null || v === undefined || v === "") return "N/A";
  const n = parseFloat(v);
  if (!currency) return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return new Intl.NumberFormat(currency === "INR" ? "en-IN" : "en-US", { style: "currency", currency }).format(n);
};
export const num = (v, dp = 2) => (v === null || v === undefined ? "N/A" : Number(v).toFixed(dp));
export const list = (data) => (Array.isArray(data) ? data : data?.results || []);
// Legacy runs stored a bare list of floats; v2 stores [date, value].
export const toPoints = (curve) => (curve || []).map((p, i) => (Array.isArray(p) ? { t: p[0], v: p[1] } : { t: i, v: p }));
