import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import api from "./api";
import CommandPalette, { matches, openPalette } from "./CommandPalette";
import { currentTheme } from "./theme";

vi.mock("./api", async (importOriginal) => ({
  ...(await importOriginal()),
  default: { get: vi.fn(), post: vi.fn() },
}));
const logout = vi.fn(() => Promise.resolve());
vi.mock("./auth", () => ({ useAuth: () => ({ logout }) }));

function Where() {
  const loc = useLocation();
  return <p data-testid="where">{loc.pathname + loc.search}</p>;
}

beforeEach(() => {
  api.get.mockResolvedValue({ data: { results: [{ id: 4, name: "RSI Mean Reversion", kind: "builder", is_builtin: true }] } });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  delete document.documentElement.dataset.theme;
});

function setup() {
  render(
    <MemoryRouter initialEntries={["/"]}>
      <CommandPalette />
      <Routes>
        <Route path="*" element={<Where />} />
      </Routes>
    </MemoryRouter>,
  );
  return userEvent.setup();
}

describe("CommandPalette", () => {
  it("opens with Ctrl+K, filters, and navigates with the keyboard", async () => {
    const user = setup();
    expect(screen.queryByRole("dialog")).toBeNull();
    await user.keyboard("{Control>}k{/Control}");
    const input = screen.getByRole("combobox");
    expect(document.activeElement).toBe(input);

    await user.type(input, "comp");
    expect(screen.getByRole("option", { name: "Compare strategies" }).getAttribute("aria-selected")).toBe("true");
    expect(screen.queryByRole("option", { name: "Dashboard" })).toBeNull();
    await user.keyboard("{Enter}");
    expect(screen.getByTestId("where").textContent).toBe("/compare");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("offers a backtest for each strategy and moves with the arrow keys", async () => {
    const user = setup();
    openPalette();
    const input = await screen.findByRole("combobox");
    await user.type(input, "rsi");
    expect(await screen.findByRole("option", { name: "Backtest: RSI Mean Reversion" })).toBeTruthy();
    await user.clear(input);
    await user.type(input, "backtest");
    // "New backtest" (page) first, then the strategy.
    await user.keyboard("{ArrowDown}");
    expect(screen.getByRole("option", { name: "Backtest: RSI Mean Reversion" }).getAttribute("aria-selected")).toBe("true");
    await user.keyboard("{Enter}");
    expect(screen.getByTestId("where").textContent).toBe("/run?strategy=4");
  });

  it("runs actions and closes with Escape", async () => {
    const user = setup();
    openPalette();
    await user.type(await screen.findByRole("combobox"), "theme");
    await user.keyboard("{Enter}");
    expect(currentTheme()).toBe("light");

    openPalette();
    await screen.findByRole("dialog");
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();

    openPalette();
    await user.type(await screen.findByRole("combobox"), "nothing like this");
    expect(screen.getByText(/No results/)).toBeTruthy();
  });

  it("matches every word of the query", () => {
    const item = { label: "Optimize a strategy", keywords: "grid search parameters" };
    expect(matches(item, "grid opt")).toBe(true);
    expect(matches(item, "grid compare")).toBe(false);
  });
});
