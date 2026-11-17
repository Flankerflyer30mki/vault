import { describe, expect, it } from "vitest";
import { buildMatrix, heatLevel, mergeCurves, metricValue, paramLabel, parseNumberList, product, symbolList } from "./experiments";
import { COMPARISON } from "./test/fixtures";

describe("parseNumberList", () => {
  it("parses, and names the first bad entry", () => {
    expect(parseNumberList("5, 8,12", { label: "p", min: 2, max: 200, integer: true })).toEqual({ values: [5, 8, 12] });
    expect(parseNumberList("5, 8.5", { label: "p", min: 2, max: 200, integer: true }).error).toBe('p: "8.5" must be a whole number');
    expect(parseNumberList("1, 5", { label: "p", min: 2, max: 200 }).error).toBe('p: "1" must be a number from 2 to 200');
    expect(parseNumberList("0, 0.1", { label: "SL", min: 0, max: 0.99, exclusiveMin: true }).error).toBe('SL: "0" must be a number in (0, 0.99]');
    expect(parseNumberList("5, 5", { label: "p" }).error).toBe("p: values must be unique");
    expect(parseNumberList(" ", { label: "p" }).error).toBe("p: enter at least one value");
    expect(parseNumberList("1,2,3", { label: "p", maxCount: 2 }).error).toBe("p: at most 2 values");
  });

  it("splits symbols on commas or spaces and upper-cases them", () => {
    expect(symbolList("aapl, reliance.ns  ^nsei")).toEqual(["AAPL", "RELIANCE.NS", "^NSEI"]);
    expect(product([2, 3, 4])).toBe(24);
  });
});

describe("comparison helpers", () => {
  it("builds the strategies × symbols matrix in the order chosen", () => {
    const { symbols, rows, benchmarks } = buildMatrix(COMPARISON);
    expect(symbols).toEqual(["AAPL", "RELIANCE.NS"]);
    expect(rows.map((r) => r.name)).toEqual(["EMA Crossover", "RSI Mean Reversion"]);
    expect(rows[0].cells["RELIANCE.NS"].id).toBe(12);
    expect(benchmarks.map((b) => b.symbol)).toEqual(["^GSPC", "^NSEI"]);
  });

  it("computes total return and colours within a column, flipping when lower is better", () => {
    expect(metricValue({ final_value: "11000.00", starting_cash: "10000.00" }, "total_return")).toBeCloseTo(0.1);
    expect(metricValue({ final_value: null, starting_cash: "10000" }, "total_return")).toBeNull();
    expect(heatLevel(0.3, [0.1, 0.3], true)).toBe(1);
    expect(heatLevel(0.3, [0.1, 0.3], false)).toBe(0);
    expect(heatLevel(0.2, [0.2, 0.2], true)).toBe(0.5); // a single value: neutral
    expect(heatLevel(0.2, [0.1, 0.3], null)).toBeNull(); // exposure: never coloured
  });

  it("labels optimization children and merges downsampled curves by date", () => {
    const run = { grid_params: { "ema(12).period": 8, stop_loss_pct: "0.05", take_profit_pct: "0.2" }, stop_loss_pct: "0.050000", take_profit_pct: "0.200000" };
    expect(paramLabel(run)).toBe("ema(12).period 8 · SL 5% · TP 20%");
    const merged = mergeCurves([
      { id: 1, curve: [["2024-01-02", 100], ["2024-01-03", 101]] },
      { id: 2, curve: [["2024-01-03", 99], ["2024-01-04", 98]] },
    ]);
    expect(merged).toEqual([
      { t: "2024-01-02", run_1: 100 },
      { t: "2024-01-03", run_1: 101, run_2: 99 },
      { t: "2024-01-04", run_2: 98 },
    ]);
  });
});
