import { describe, expect, it } from "vitest";
import { CATALOG } from "../test/fixtures";
import { blankSpec, describe as sentence, errorsUnder, makeOperand, toFormState, toSpec } from "./spec";

// Same shape the server stores (normalised: every param present, numbers as numbers).
const MACD_BOLLINGER = {
  version: 1,
  entry: {
    all: [
      {
        left: { ind: "macd", params: { fast: 12, slow: 26, signal: 9 }, output: "line" },
        op: "crosses_above",
        right: { ind: "macd", params: { fast: 12, slow: 26, signal: 9 }, output: "signal" },
      },
      { left: { price: "close" }, op: ">", right: { ind: "bbands", params: { period: 20, std: 2.5 }, output: "middle" } },
    ],
  },
  exit: { any: [{ left: { ind: "rsi", params: { period: 14 }, output: "value" }, op: ">", right: { const: 70.5 } }] },
};

describe("form state <-> spec", () => {
  it("round-trips a spec without losing or changing anything", () => {
    const state = toFormState(MACD_BOLLINGER);
    expect(state.entry.all[1].right.params.std).toBe("2.5"); // inputs hold strings
    expect(state.exit.any[0].right.const).toBe("70.5");
    expect(toSpec(state)).toEqual(MACD_BOLLINGER);
  });

  it("does not mutate its input", () => {
    const copy = structuredClone(MACD_BOLLINGER);
    toSpec(toFormState(MACD_BOLLINGER));
    expect(MACD_BOLLINGER).toEqual(copy);
  });

  it("sends non-numbers as typed so the server error points at that field", () => {
    const state = toFormState(MACD_BOLLINGER);
    state.exit.any[0].left.params.period = "";
    state.exit.any[0].right.const = "abc";
    const spec = toSpec(state);
    expect(spec.exit.any[0].left.params.period).toBe("");
    expect(spec.exit.any[0].right.const).toBe("abc");
  });

  it("builds a blank spec and operands from the catalog defaults", () => {
    const blank = blankSpec(CATALOG);
    expect(Object.keys(blank.entry)).toEqual(["all"]);
    expect(Object.keys(blank.exit)).toEqual(["any"]);
    expect(toSpec(blank).entry.all[0].left).toEqual({ ind: "sma", params: { period: 20 }, output: "value" });
    expect(makeOperand(CATALOG, "ind", "macd")).toEqual({
      ind: "macd",
      params: { fast: "12", slow: "26", signal: "9" },
      output: "line",
    });
    expect(makeOperand(CATALOG, "const")).toEqual({ const: "0" });
  });
});

describe("helpers", () => {
  it("collects errors at or under a path, and nothing from siblings", () => {
    const errors = {
      "entry.all[1].left.params.period": "bad period",
      "entry.all[1]": "row problem",
      "entry.all[10].op": "not this one",
      "exit.any": "too many",
    };
    expect(errorsUnder(errors, "entry.all[1]")).toEqual(["bad period", "row problem"]);
    expect(errorsUnder(errors, "exit")).toEqual(["too many"]);
  });

  it("describes a condition in plain words", () => {
    expect(sentence(CATALOG, MACD_BOLLINGER.entry.all[0])).toBe("MACD(12, 26, 9) line crosses above MACD(12, 26, 9) signal");
    expect(sentence(CATALOG, MACD_BOLLINGER.exit.any[0])).toBe("RSI(14) is above 70.5");
  });
});
