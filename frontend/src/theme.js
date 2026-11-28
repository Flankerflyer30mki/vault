import { useSyncExternalStore } from "react";

// Dark by default (the Linear/Raycast look); the choice is a per-browser convenience, so storage failures are fine.
// index.html applies the stored theme before first paint to avoid a flash. The theme lives on <html data-theme>;
// every component reading it (sidebar toggle, command palette, charts) sees the same value.
const KEY = "vault-theme";
const listeners = new Set();

export function currentTheme() {
  return document.documentElement.dataset.theme === "light" ? "light" : "dark";
}

export function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.content = theme === "light" ? "#ffffff" : "#08090a";
  try {
    localStorage.setItem(KEY, theme);
  } catch {
    /* private mode: the toggle still works for this page view */
  }
  listeners.forEach((fn) => fn());
}

export function toggleTheme() {
  applyTheme(currentTheme() === "dark" ? "light" : "dark");
}

const subscribe = (fn) => {
  listeners.add(fn);
  return () => listeners.delete(fn);
};

export function useTheme() {
  const theme = useSyncExternalStore(subscribe, currentTheme, () => "dark");
  return [theme, toggleTheme];
}
