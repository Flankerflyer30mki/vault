import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import api, { usePoll } from "../api";
import { CATALOG, COMPARISON, OPTIMIZATION } from "../test/fixtures";
import ComparisonTrigger from "./ComparisonTrigger";
import ExperimentDetail from "./ExperimentDetail";

vi.mock("../api", async (importOriginal) => ({
  ...(await importOriginal()),
  default: { get: vi.fn(), post: vi.fn() },
  usePoll: vi.fn(),
}));

beforeAll(() => {
  // Recharts' ResponsiveContainer measures its box; jsdom has no layout engine.
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
});

const STRATEGIES = [
  { id: 3, name: "EMA Crossover", kind: "builder", is_builtin: false, tunable_params: [] },
  { id: 4, name: "RSI Mean Reversion", kind: "builder", is_builtin: false, tunable_params: [] },
  { id: 5, name: "Python thing", kind: "code", is_builtin: false, tunable_params: [] }, // can't run: custom code off
];

beforeEach(() => {
  api.get.mockImplementation((url) =>
    url === "/strategies/catalog/" ? Promise.resolve({ data: CATALOG })
      : url === "/strategies/" ? Promise.resolve({ data: { results: STRATEGIES } })
        : Promise.reject(new Error(`unexpected GET ${url}`)));
  api.post.mockResolvedValue({ data: { id: 42 } });
  // Default = the real hook's first state (still loading). The comparison form navigates to the results page after
  // submitting; without a default that page could render after the test with an unset mock and crash (seen on CI).
  usePoll.mockReturnValue({ data: null, error: "" });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function renderAt(path) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/compare" element={<ComparisonTrigger />} />
        <Route path="/experiments/:id" element={<ExperimentDetail />} />
      </Routes>
    </MemoryRouter>,
  );
  return userEvent.setup();
}

describe("ComparisonTrigger", () => {
  it("counts cells, enforces the limit and posts the matrix", async () => {
    const user = renderAt("/compare");
    await user.click(await screen.findByLabelText("EMA Crossover"));
    expect(screen.queryByLabelText("Python thing")).toBeNull(); // custom code can't run here, so it isn't offered
    expect(screen.getByText("1 × 2 = 2 backtests, plus benchmarks.")).toBeTruthy();
    await user.click(screen.getByLabelText("RSI Mean Reversion"));
    const symbols = screen.getByLabelText("Symbols (comma-separated Yahoo tickers)");
    await user.clear(symbols);
    await user.type(symbols, "a b c d e f g h i j k l m");
    expect(screen.getByText("At most 10 symbols")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Run comparison" }).disabled).toBe(true);
    await user.clear(symbols);
    await user.type(symbols, "aapl, reliance.ns");
    await user.click(screen.getByRole("button", { name: "+ ^NSEI" }));
    expect(screen.getByText("2 × 3 = 6 backtests, plus benchmarks.")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Run comparison" }));
    const [url, body] = api.post.mock.calls[0];
    expect(url).toBe("/experiments/");
    expect(body).toMatchObject({ kind: "comparison", strategies: [3, 4], symbols: ["AAPL", "RELIANCE.NS", "^NSEI"], stop_loss_pct: null });
    expect(await screen.findByText("Loading…")).toBeTruthy(); // it navigated to the new experiment's page
  });
});

describe("ExperimentDetail", () => {
  it("shows a comparison as a heatmap with benchmarks and failures", async () => {
    usePoll.mockReturnValue({ data: COMPARISON, error: "" });
    const user = renderAt("/experiments/9");
    const table = screen.getByRole("table");
    const ema = within(table).getByRole("row", { name: /EMA Crossover/ });
    expect(within(ema).getByText("12.00%")).toBeTruthy(); // 11200 / 10000 - 1
    expect(within(ema).getByText("-5.00%")).toBeTruthy();
    const rsi = within(table).getByRole("row", { name: /RSI Mean Reversion/ });
    expect(within(rsi).getByText("failed")).toBeTruthy();
    expect(within(table).getByText("^GSPC: 25.00%")).toBeTruthy();
    expect(within(table).getByText("^NSEI: 8.00%")).toBeTruthy();
    // Within the AAPL column the better strategy is the greener cell.
    expect(within(ema).getByText("12.00%").closest("td").dataset.level).toBe("4");
    expect(within(rsi).getByText("4.00%").closest("td").dataset.level).toBe("0");
    expect(screen.getByText(/No market data/)).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Sharpe" }));
    expect(within(ema).getByText("1.20")).toBeTruthy();
  });

  it("shows an optimization with its searched parameters, skipped combinations and out-of-sample run", () => {
    usePoll.mockReturnValue({ data: OPTIMIZATION, error: "" });
    renderAt("/experiments/7");
    expect(screen.getByRole("heading", { name: "Optimization #7 — EMA Crossover" })).toBeTruthy();
    expect(screen.getByRole("columnheader", { name: "ema(12).period" })).toBeTruthy();
    expect(screen.getByText(/1 combination skipped as invalid/)).toBeTruthy();
    expect(screen.getByText(/must be greater than fast/)).toBeTruthy();
    expect(screen.getByText(/best in-sample: ema\(12\).period 12 · SL 5% · TP 20%/)).toBeTruthy();
    const rows = screen.getAllByRole("row").slice(1);
    expect(within(rows[0]).getByText("#22")).toBeTruthy(); // sorted by Sharpe: 1.4 before 0.9
  });
});
