import { describe, expect, it } from "vitest";
import { money } from "./api";

describe("money", () => {
  it("formats in the symbol's currency", () => {
    expect(money("10000")).toBe("$10,000.00");
    expect(money(100000, "INR")).toBe("₹1,00,000.00"); // Indian digit grouping
    expect(money("1234.5", null)).toBe("1,234.50"); // unknown exchange: no symbol rather than a wrong one
    expect(money(null, "INR")).toBe("N/A");
  });
});
