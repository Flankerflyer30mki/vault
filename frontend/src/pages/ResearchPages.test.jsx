import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import api, { usePoll } from "../api";
import { CATALOG } from "../test/fixtures";
import Research from "./Research";
import ResearchDetail from "./ResearchDetail";

vi.mock("../api", async (importOriginal) => ({
  ...(await importOriginal()),
  default: { get: vi.fn(), post: vi.fn() },
  usePoll: vi.fn(() => ({ data: null, error: "" })),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const SPEC = {
  version: 1,
  entry: { all: [{ left: { ind: "sma", params: { period: 5 }, output: "value" }, op: "crosses_above", right: { ind: "sma", params: { period: 20 }, output: "value" } }] },
  exit: { any: [{ left: { ind: "sma", params: { period: 5 }, output: "value" }, op: "crosses_below", right: { ind: "sma", params: { period: 20 }, output: "value" } }] },
};
const BASE = {
  id: 3, goal: "A trend strategy that beats buy and hold.", symbol: "AAPL", start_date: "2018-01-01", end_date: "2024-12-31",
  split_date: "2022-11-25", research_end: "2022-11-24", objective: "sharpe_ratio", max_drawdown: 0.25, status: "waiting",
  stage: "explore", error_message: "", steps_used: 1, backtests_used: 2, tokens_in: 2000, tokens_out: 300,
  budgets: { steps: 8, backtests: 40, tokens: 40000, model_calls: 14 }, report: null,
};
const CANDIDATE = {
  id: "c1", name: "SMA 5/20 cross", spec: SPEC, rules: "BUY when all: crosses_above(ind.sma(5), ind.sma(20))", run_id: 41,
  round: 1, stage: "explore", status: "completed", eligible: true, error: "",
  metrics: { sharpe_ratio: 0.91, total_return: 0.42, max_drawdown: 0.18, trade_count: 14 },
};
const STEP = {
  index: 0, stage: "explore", actor: "agent", action: "test", args: { candidates: [{ id: "c1" }, { id: "c2" }] },
  note: "Two families to start: trend and mean reversion.", result: null, ok: true,
};

function renderAt(path) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/research" element={<Research />} />
        <Route path="/research/:id" element={<ResearchDetail />} />
      </Routes>
    </MemoryRouter>,
  );
  return userEvent.setup();
}

describe("Research", () => {
  it("says so when the deployment has no AI", async () => {
    api.get.mockImplementation((url) => Promise.resolve({ data: url === "/research/" ? [] : CATALOG }));
    renderAt("/research");
    expect(await screen.findByText(/AI research isn't configured/)).toBeTruthy();
  });

  it("starts a research run and opens it", async () => {
    api.get.mockImplementation((url) => Promise.resolve({ data: url === "/research/" ? [] : { ...CATALOG, ai_enabled: true } }));
    api.post.mockResolvedValue({ data: { id: 3 } });
    usePoll.mockReturnValue({ data: BASE, error: "" });
    const user = renderAt("/research");
    await user.type(await screen.findByLabelText("Goal"), "A trend strategy that beats buy and hold.");
    await user.click(screen.getByRole("button", { name: "Start research" }));
    expect(await screen.findByText("Research: AAPL")).toBeTruthy();
    const [url, body] = api.post.mock.calls[0];
    expect(url).toBe("/research/");
    expect(body.goal).toBe("A trend strategy that beats buy and hold.");
    expect(body.max_drawdown_pct).toBeNull();
  });
});

describe("ResearchDetail", () => {
  it("shows progress, budgets, candidates and the agent's reasons", () => {
    usePoll.mockReturnValue({ data: { ...BASE, steps: [STEP], candidates: [CANDIDATE] }, error: "" });
    renderAt("/research/3");
    expect(screen.getByText("Running backtests…")).toBeTruthy();
    expect(screen.getByText(/1\/8 decisions · 2\/40 backtests/)).toBeTruthy();
    expect(screen.getByText("tested c1, c2")).toBeTruthy();
    expect(screen.getByText("Two families to start: trend and mean reversion.")).toBeTruthy();
    expect(screen.getByText("SMA 5/20 cross").getAttribute("href")).toBe("/runs/41");
    expect(screen.getByText("Explore").className).toBe("current");
    expect(usePoll).toHaveBeenCalledWith("/research/3/", 2000);
  });

  it("reports the held-out result honestly and lets the user save a candidate", async () => {
    const report = {
      chosen: { id: "c1", name: "SMA 5/20 cross", rules: CANDIDATE.rules, chosen_by: "agent" }, candidates_tested: 5,
      research_period: "2018-01-01 to 2022-11-24", held_out_period: "2022-11-25 to 2024-12-31",
      research_result: { total_return: 0.42, buy_and_hold_return: 0.3, sharpe_ratio: 0.91, max_drawdown: 0.18, trade_count: 14 },
      held_out_result: { total_return: 0.05, buy_and_hold_return: 0.21, sharpe_ratio: 0.4, max_drawdown: 0.12, trade_count: 6 },
      beat_buy_and_hold_held_out: false,
      text: { summary: "It was chosen from 5 candidates.", why: "", caveats: ["One symbol only."] },
      checks: { held_out_tested_once: true, agent_never_saw_held_out_period: true, budgets_respected: true,
        summary_numbers_grounded: true, drawdown_constraint_met_held_out: true },
    };
    usePoll.mockReturnValue({
      data: { ...BASE, status: "completed", stage: "done", report, steps: [STEP], candidates: [CANDIDATE] }, error: "",
    });
    api.post.mockResolvedValue({ data: { id: 77 } });
    const user = renderAt("/research/3");
    expect(screen.getByText("On the held-out period it did not beat buy & hold.")).toBeTruthy();
    expect(screen.getByText("5.00%")).toBeTruthy(); // held-out return
    expect(screen.getByText("21.00%")).toBeTruthy(); // buy & hold over the same held-out period
    expect(screen.getByText(/✓ Held-out period tested exactly once/)).toBeTruthy();
    expect(screen.getByText(/✓ The agent never saw the held-out period/)).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Save as strategy" }));
    expect(api.post).toHaveBeenCalledWith("/strategies/", { name: "SMA 5/20 cross", kind: "builder", spec: SPEC });
    expect((await screen.findByText("Saved: open")).getAttribute("href")).toBe("/strategies/77/edit");
  });

  it("shows a replaced summary as a warning, not a broken rule, and flags twin candidates", () => {
    const report = {
      chosen: { id: "c1", name: "SMA 5/20 cross", rules: CANDIDATE.rules, chosen_by: "code" }, candidates_tested: 2,
      research_period: "a", held_out_period: "b",
      research_result: { total_return: 0.42, buy_and_hold_return: 0.3, sharpe_ratio: 0.91, max_drawdown: 0.18, trade_count: 14 },
      held_out_result: null, beat_buy_and_hold_held_out: null,
      text: { summary: "Plain summary.", why: "", caveats: [] },
      checks: { held_out_tested_once: true, summary_numbers_grounded: false },
    };
    const twin = { ...CANDIDATE, id: "c2", name: "MACD twin", run_id: 42, same_as: "c1" };
    usePoll.mockReturnValue({
      data: { ...BASE, status: "completed", stage: "done", report, steps: [], candidates: [CANDIDATE, twin] }, error: "",
    });
    renderAt("/research/3");
    expect(screen.getByText(/⚠ The agent's summary didn't pass the number check/)).toBeTruthy();
    expect(screen.queryByText(/✗ Every number/)).toBeNull();
    expect(screen.getByText("(same results as c1)")).toBeTruthy();
  });

  it("shows why a run failed", () => {
    usePoll.mockReturnValue({
      data: { ...BASE, status: "failed", error_message: "Stopped: step budget used up, and no candidate met the requirements.", steps: [], candidates: [] },
      error: "",
    });
    renderAt("/research/3");
    expect(screen.getByText(/no candidate met the requirements/)).toBeTruthy();
  });
});
