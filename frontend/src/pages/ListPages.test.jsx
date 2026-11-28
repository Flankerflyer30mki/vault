import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import api from "../api";
import { CATALOG } from "../test/fixtures";
import Dashboard from "./Dashboard";
import RunTrigger from "./RunTrigger";
import StrategyList from "./StrategyList";

vi.mock("../api", async (importOriginal) => ({
  ...(await importOriginal()),
  default: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
}));
vi.mock("../auth", () => ({ useAuth: () => ({ user: { display_name: "Ada", is_guest: false } }) }));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const QUOTA = {
  tier: "verified",
  usage: { active_jobs: 0, runs_per_day: 1, experiments_per_day: 0, strategies: 1, ai_requests_per_day: 0, research_per_day: 0 },
  limits: { active_jobs: 10, runs_per_day: 200, experiments_per_day: 20, strategies: 100, ai_requests_per_day: 50, research_per_day: 3 },
};
const DASHBOARD = {
  quota: QUOTA,
  active_runs: [],
  experiments: [],
  strategies: [],
  custom_code_enabled: false,
  recent_runs: [
    { id: 7, status: "completed", strategy_name: "EMA Crossover", symbol: "AAPL", start_date: "2024-01-01", end_date: "2024-12-31", total_return: 0.12, buy_and_hold_return: 0.3 },
    { id: 8, status: "failed", failure_category: "data", strategy_name: "RSI", symbol: "XYZ", start_date: "2024-01-01", end_date: "2024-12-31" },
  ],
};
const STRATEGIES = [
  { id: 3, name: "EMA Crossover", kind: "builder", is_builtin: true, python: "def on_bar(): ..." },
  { id: 4, name: "RSI Mean Reversion", kind: "builder", is_builtin: true, python: "" },
  { id: 9, name: "My momentum", kind: "builder", is_builtin: false, python: "" },
];

function routeGets(map) {
  api.get.mockImplementation((url) => (url in map ? Promise.resolve({ data: map[url] }) : Promise.reject(new Error(`GET ${url}`))));
}

describe("Dashboard", () => {
  it("lists recent backtests as links with the result against buy and hold", async () => {
    routeGets({ "/dashboard/": DASHBOARD });
    render(<MemoryRouter><Dashboard /></MemoryRouter>);
    const row = (await screen.findByText("EMA Crossover")).closest("a");
    expect(row.getAttribute("href")).toBe("/runs/7");
    expect(within(row).getByText("12.00%")).toBeTruthy();
    expect(within(row).getByText("lagged")).toBeTruthy();
    expect(screen.getByText("failed (data)").closest("a").getAttribute("href")).toBe("/runs/8");
    expect(screen.queryByText("Running now")).toBeNull(); // the section only appears while something runs
  });

  it("shows empty states with a next step", async () => {
    routeGets({ "/dashboard/": { ...DASHBOARD, recent_runs: [] } });
    render(<MemoryRouter><Dashboard /></MemoryRouter>);
    expect(await screen.findByText("No backtests yet")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Run your first one" }).getAttribute("href")).toBe("/run");
    expect(screen.getByText("No experiments yet")).toBeTruthy();
  });
});

describe("StrategyList", () => {
  it("filters by name and offers a backtest for each strategy", async () => {
    routeGets({ "/strategies/": { results: STRATEGIES }, "/strategies/catalog/": CATALOG });
    render(<MemoryRouter><StrategyList /></MemoryRouter>);
    await screen.findByText("My momentum");
    expect(screen.getAllByRole("link", { name: "Backtest" })[0].getAttribute("href")).toBe("/run?strategy=9");

    await userEvent.type(screen.getByLabelText("Filter strategies"), "rsi");
    expect(screen.getByText("RSI Mean Reversion")).toBeTruthy();
    expect(screen.queryByText("EMA Crossover")).toBeNull();
    expect(screen.queryByText("My momentum")).toBeNull();
  });

  it("expands a row to show its rules", async () => {
    routeGets({ "/strategies/": { results: STRATEGIES }, "/strategies/catalog/": CATALOG });
    render(<MemoryRouter><StrategyList /></MemoryRouter>);
    const toggle = (await screen.findByText("EMA Crossover")).closest("button");
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    await userEvent.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByText("def on_bar(): ...")).toBeTruthy();
  });
});

describe("RunTrigger", () => {
  it("preselects the strategy given in ?strategy=", async () => {
    routeGets({ "/strategies/": { results: STRATEGIES }, "/strategies/catalog/": CATALOG });
    render(
      <MemoryRouter initialEntries={["/run?strategy=4"]}>
        <Routes>
          <Route path="/run" element={<RunTrigger />} />
        </Routes>
      </MemoryRouter>,
    );
    await screen.findByRole("option", { name: /RSI Mean Reversion/ });
    expect(screen.getByLabelText("Strategy").value).toBe("4");
  });
});
