import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import api from "../api";
import { CATALOG } from "../test/fixtures";
import StrategyBuilder from "./StrategyBuilder";

vi.mock("../api", async (importOriginal) => ({
  ...(await importOriginal()),
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn() },
}));

const PERIOD_ERROR = "must be a whole number between 2 and 200";
const TEMPLATE = {
  id: 7,
  name: "EMA Crossover (12/26)",
  kind: "builder",
  spec: {
    version: 1,
    entry: { all: [{ left: { ind: "sma", params: { period: 12 }, output: "value" }, op: "crosses_above", right: { ind: "sma", params: { period: 26 }, output: "value" } }] },
    exit: { any: [{ left: { ind: "sma", params: { period: 12 }, output: "value" }, op: "crosses_below", right: { ind: "sma", params: { period: 26 }, output: "value" } }] },
  },
};

// Mimics the server's period check, so live preview and save agree the way the real API does.
const firstPeriodError = (spec) => {
  const p = spec.entry.all?.[0]?.left?.params?.period;
  return p !== undefined && !(Number.isInteger(p) && p >= 2 && p <= 200)
    ? { response: { status: 400, data: { spec: { "entry.all[0].left.params.period": PERIOD_ERROR } } } }
    : null;
};

beforeEach(() => {
  api.get.mockImplementation((url) =>
    url === "/strategies/catalog/" ? Promise.resolve({ data: CATALOG })
      : url === "/strategies/7/" ? Promise.resolve({ data: TEMPLATE })
        : Promise.reject(new Error(`unexpected GET ${url}`)));
  api.post.mockImplementation((url, body) => {
    const err = firstPeriodError(body.spec);
    if (err) return Promise.reject(err);
    if (url === "/strategies/preview/") return Promise.resolve({ data: { python: "def on_bar(bar, ind):\n", warmup_bars: 26 } });
    return Promise.resolve({ status: 201, data: { id: 1 } });
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function renderAt(path) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/strategies/new" element={<StrategyBuilder />} />
        <Route path="/strategies/:id/edit" element={<StrategyBuilder />} />
        <Route path="/strategies" element={<p>strategy list page</p>} />
      </Routes>
    </MemoryRouter>,
  );
  return userEvent.setup();
}

describe("StrategyBuilder", () => {
  it("starts from a blank spec and shows the live preview", async () => {
    renderAt("/strategies/new");
    expect(await screen.findByText("Buy when")).toBeTruthy();
    expect(screen.getByText("SMA(20) is above close")).toBeTruthy();
    expect(await screen.findByText(/Needs 26 warm-up bars/)).toBeTruthy();
  });

  it("shows an indicator's own parameters and outputs when it is chosen", async () => {
    const user = renderAt("/strategies/new");
    const indicator = await screen.findByLabelText("entry condition 1 left indicator");
    await user.selectOptions(indicator, "macd");
    expect(screen.getByLabelText("entry condition 1 left fast").value).toBe("12");
    expect(screen.getByLabelText("entry condition 1 left slow").value).toBe("26");
    expect(screen.getByLabelText("entry condition 1 left output").value).toBe("line");
    expect(screen.queryByLabelText("entry condition 1 left period")).toBeNull();
    await user.selectOptions(screen.getByLabelText("entry condition 1 right type"), "const");
    expect(screen.getByLabelText("entry condition 1 right number").value).toBe("0");
  });

  it("stops adding conditions at the catalog limit and never removes the last one", async () => {
    const user = renderAt("/strategies/new");
    const [entryAdd] = await screen.findAllByRole("button", { name: "Add condition (1/3)" }); // entry, then exit
    await user.click(entryAdd);
    expect(screen.getByRole("button", { name: "Remove entry condition 1" }).disabled).toBe(false);
    await user.click(screen.getByRole("button", { name: "Add condition (2/3)" }));
    expect(screen.getByRole("button", { name: "Add condition (3/3)" }).disabled).toBe(true);
    expect(screen.getByRole("button", { name: "Remove exit condition 1" }).disabled).toBe(true);
  });

  it("saves the spec with numbers, not the strings the inputs hold", async () => {
    const user = renderAt("/strategies/new");
    await user.type(await screen.findByLabelText("Name"), "My SMA");
    const period = screen.getByLabelText("entry condition 1 left period");
    await user.clear(period);
    await user.type(period, "50");
    await user.click(screen.getByRole("button", { name: "Save strategy" }));
    expect(await screen.findByText("strategy list page")).toBeTruthy();
    const [url, body] = api.post.mock.calls.find(([u]) => u === "/strategies/");
    expect(url).toBe("/strategies/");
    expect(body.name).toBe("My SMA");
    expect(body.kind).toBe("builder");
    expect(body.spec.entry.all[0].left).toEqual({ ind: "sma", params: { period: 50 }, output: "value" });
  });

  it("puts the server's error on the exact field and blocks the save", async () => {
    const user = renderAt("/strategies/new");
    await user.type(await screen.findByLabelText("Name"), "Broken");
    const period = screen.getByLabelText("entry condition 1 left period");
    await user.clear(period);
    await user.type(period, "1");
    expect(await screen.findByText(PERIOD_ERROR)).toBeTruthy(); // from the live preview
    expect(period.getAttribute("aria-invalid")).toBe("true");
    expect(screen.getByText("1 problem to fix.")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Save strategy" }));
    expect(await screen.findByText("Fix the highlighted fields.")).toBeTruthy();
    expect(screen.queryByText("strategy list page")).toBeNull();
  });

  it("opens a template as an editable copy", async () => {
    renderAt("/strategies/new?from=7");
    await waitFor(() => expect(screen.getByLabelText("Name").value).toBe("EMA Crossover (12/26) (copy)"));
    expect(screen.getByLabelText("entry condition 1 operator").value).toBe("crosses_above");
    expect(screen.getByLabelText("entry condition 1 right period").value).toBe("26");
  });
});
