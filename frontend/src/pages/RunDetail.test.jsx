import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import api, { usePoll } from "../api";
import RunDetail from "./RunDetail";

vi.mock("../api", async (importOriginal) => ({
  ...(await importOriginal()),
  default: { get: vi.fn() },
  usePoll: vi.fn(),
}));

beforeAll(() => {
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const RUN = {
  id: 3,
  status: "completed",
  strategy: 9,
  strategy_name: "Trend RSI",
  symbol: "RELIANCE.NS",
  currency: "INR",
  sample: "full",
  start_date: "2024-01-01",
  end_date: "2024-12-31",
  starting_cash: "10000.00",
  final_value: "11200.00",
  buy_and_hold_return: 0.3,
  cagr: 0.12,
  sharpe_ratio: 0.9,
  sortino_ratio: 1.5,
  calmar_ratio: 1.1,
  max_drawdown: 0.07,
  win_rate: 0.8,
  trade_count: 1,
  exposure: 0.1,
  total_commission: "20",
  total_slippage: "5",
  cost_drag: 0.002,
  execution_time_ms: 40,
  engine_version: "2.1.0",
  strategy_hash: "abcdef0123456789",
  attempts: 1,
  cost_model: "flat",
  commission_pct: 0.001,
  slippage_pct: 0.0005,
  data_manifest: { provider: "yahoo", bar_count: 250, data_sha256: "0123456789abcdef", warnings: [] },
  equity_curve: [["2024-01-02", 10000], ["2024-12-31", 11200]],
};
const TRADES = [
  { id: 1, side: "BUY", ts: "2024-01-03T00:00:00Z", price: "100", quantity: "99.5", commission: "10", cash_after: "0", reason: "signal" },
  { id: 2, side: "SELL", ts: "2024-06-03T00:00:00Z", price: "112", quantity: "99.5", commission: "11", cash_after: "11200", reason: "take_profit" },
];

function renderRun() {
  usePoll.mockReturnValue({ data: RUN, error: "" });
  api.get.mockResolvedValue({ data: TRADES });
  render(
    <MemoryRouter initialEntries={["/runs/3"]}>
      <Routes>
        <Route path="/runs/:id" element={<RunDetail />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("RunDetail", () => {
  it("leads with total return and the difference from buy and hold", async () => {
    renderRun();
    expect(screen.getByText("+12.00%")).toBeTruthy(); // 11200 / 10000 - 1
    expect(screen.getByText("-18.00 pts")).toBeTruthy(); // 12% vs 30% holding: percentage points
    expect(screen.getByText(/holding returned \+30\.00%/)).toBeTruthy();
    const again = screen.getByRole("link", { name: /run again/i });
    expect(again.getAttribute("href")).toBe("/run?strategy=9&symbol=RELIANCE.NS");
  });

  it("puts trades, assumptions and reproducibility in tabs", async () => {
    renderRun();
    const tradesTab = await screen.findByRole("tab", { name: "Trades (2)" });
    expect(tradesTab.getAttribute("aria-selected")).toBe("true");
    expect(screen.getByText("take profit")).toBeTruthy();

    tradesTab.focus();
    await userEvent.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: "Assumptions" }).getAttribute("aria-selected")).toBe("true");
    expect(screen.getByText(/orders fill at the next bar/)).toBeTruthy();

    await userEvent.click(screen.getByRole("tab", { name: "Reproducibility" }));
    expect(screen.getByText("abcdef012345")).toBeTruthy();
    expect(screen.queryByText("take profit")).toBeNull();
  });
});
