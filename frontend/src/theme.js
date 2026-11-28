import { useState } from "react";

// Dark by default (the Linear/Raycast look); the choice is a per-browser convenience, so storage failures are fine.
// index.html applies the stored theme before first paint to avoid a flash.
const KEY = "vault-theme";

export function storedTheme() {
  try {
    return localStorage.getItem(KEY) === "light" ? "light" : "dark";
  } catch {
    return "dark";
  }
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
}

export function useTheme() {
  const [theme, setTheme] = useState(storedTheme);
  const toggle = () => {
    const next = theme === "dark" ? "light" : "dark";
    applyTheme(next);
    setTheme(next);
  };
  return [theme, toggle];
}
