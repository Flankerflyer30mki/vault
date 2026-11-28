import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import api from "../api";
import { CATALOG } from "../test/fixtures";
import RunTrigger from "./RunTrigger";

vi.mock("../api", async (importOriginal) => ({
  ...(await importOriginal()),
  default: { get: vi.fn(), post: vi.fn() },
}));

beforeEach(() => {
  api.get.mockImplementation((url) =>
    url === "/strategies/catalog/" ? Promise.resolve({ data: CATALOG })
      : url === "/strategies/" ? Promise.resolve({ data: { results: [{ id: 3, name: "EMA Crossover", kind: "builder" }] } })
        : Promise.reject(new Error(`unexpected GET ${url}`)));
  api.post.mockResolvedValue({ data: { id: 42 } });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const form = () => screen.getByRole("button", { name: /run backtest/i }).closest("form");

describe("RunTrigger", () => {
  it("starts with no stop or target and sends them as null", async () => {
    render(<MemoryRouter><RunTrigger /></MemoryRouter>);
    await screen.findByRole("option", { name: /EMA Crossover/ });
    expect(screen.getByLabelText(/stop loss/i).value).toBe("");
    expect(screen.getByLabelText(/take profit/i).value).toBe("");
    expect(form().checkValidity()).toBe(true);
    await userEvent.click(screen.getByRole("button", { name: /run backtest/i }));
    expect(api.post.mock.calls[0][1]).toMatchObject({ stop_loss_pct: null, take_profit_pct: null });
  });

  // Regression: step 0.01 counted from min 0.001 made 0.08 and 0.15 (the examples in the labels) invalid, so the
  // browser silently refused to submit the form.
  it("accepts the example values from the labels", async () => {
    render(<MemoryRouter><RunTrigger /></MemoryRouter>);
    await screen.findByRole("option", { name: /EMA Crossover/ });
    await userEvent.type(screen.getByLabelText(/stop loss/i), "0.08");
    await userEvent.type(screen.getByLabelText(/take profit/i), "0.15");
    expect(form().checkValidity()).toBe(true);
  });
});
