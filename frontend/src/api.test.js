import { describe, expect, it } from "vitest";
import { errorText, money } from "./api";

describe("errorText", () => {
  it("adds the request ID to server errors so they can be found in the logs", () => {
    const err = (status, data, headers = {}) => ({ response: { status, data, headers } });
    expect(errorText(err(500, {}, { "x-request-id": "abc123def456" }))).toBe(
      "The server is unavailable. Try again shortly. (request ID: abc123def456)",
    );
    expect(errorText(err(503, { detail: "The backtest queue is full." }, { "x-request-id": "r-1" }))).toBe(
      "The backtest queue is full. (request ID: r-1)",
    );
    expect(errorText(err(500, {}))).toBe("The server is unavailable. Try again shortly.");
    expect(errorText(err(400, { symbol: ["Invalid ticker format"] }, { "x-request-id": "r-2" }))).toBe(
      "symbol: Invalid ticker format",
    ); // the user's own mistake: no ID needed
  });
});

describe("money", () => {
  it("formats in the symbol's currency", () => {
    expect(money("10000")).toBe("$10,000.00");
    expect(money(100000, "INR")).toBe("₹1,00,000.00"); // Indian digit grouping
    expect(money("1234.5", null)).toBe("1,234.50"); // unknown exchange: no symbol rather than a wrong one
    expect(money(null, "INR")).toBe("N/A");
  });
});
