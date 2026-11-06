import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DisplayPriceDetails, EstimateCoverage, estimateMoney } from "./components/DisplayPrice";
import { costLabel } from "./pages/UsagePage";
import type { DisplayPrice, UsageSummary } from "./types";

const scoringPrice: DisplayPrice = {
  input: "0.042", model_kind: "scoring", billing_dimensions: ["input"], currency: "USD", status: "public_list",
  source_url: "https://example.com/pricing", checked_at: "2026-10-31", revision: "scoring-v1",
  model_version: "1", sku: "scoring", source_model: "Microsoft-Decision-1",
  assumptions: "Output and cache tokens are N/A, not zero-priced.", basis: "Scoring input tokens only",
  provenance: { pricing_table: { input: "$0.042", output: "N/A" } },
};

describe("sourced display pricing", () => {
  it("shows absent scoring output/cache as N/A only with explicit input-only billing metadata", () => {
    render(<DisplayPriceDetails price={scoringPrice} />);
    expect(screen.getByText(/Estimated USD/)).toHaveTextContent("input 0.042 · output N/A · cached input N/A · cache write N/A");
    expect(screen.getByLabelText("Pricing provenance")).toHaveTextContent("$0.042");
    expect(screen.getByRole("link", { name: "Public pricing source" })).toHaveAttribute("href", scoringPrice.source_url);
    expect(screen.queryByText(/undefined|output 0(?:\s|$)/)).not.toBeInTheDocument();
  });

  it.each(["chat", "scoring"] as const)("does not assume missing %s output is free or N/A without billing metadata", (model_kind) => {
    render(<DisplayPriceDetails price={{ ...scoringPrice, model_kind, billing_dimensions: undefined, provenance: undefined, assumptions: "" }} />);
    expect(screen.getByText(/Estimated USD/)).toHaveTextContent("output Unknown — not free");
    expect(screen.getByText(/Estimated USD/)).not.toHaveTextContent("N/A");
  });

  it("preserves tiny nonzero amounts and distinguishes unknown from zero", () => {
    expect(estimateMoney("0.000001142857")).toBe("USD 0.00000114");
    expect(estimateMoney("0.000000000001")).toBe("USD <0.00000001");
    expect(estimateMoney("0")).toBe("USD 0.00");
    expect(estimateMoney(null)).toBe("Unknown");
    expect(estimateMoney(undefined)).toBe("Unknown");
    expect(estimateMoney("")).toBe("Unknown");
    expect(estimateMoney(" \t\n")).toBe("Unknown");
    expect(estimateMoney("NaN")).toBe("Unknown");
  });
  it("uses the inclusive estimate total instead of recorded unknown", () => {
    const result = costLabel({ pricing_revision: "test", estimated_cost_usd: "0.000194285714",
      estimated_requests: 1, unestimated_requests: 0, requests: 1, known_cost: null } as UsageSummary);
    expect(result.value).toBe("USD 0.00019429");
    expect(result.note).toContain("1 estimated");
  });
  it("limits TBC remark to catalog provenance without extra aggregate subtotal", () => {
    render(<DisplayPriceDetails price={{ input: "1.14285714", output: "4", currency: "USD", status: "tbc",
      source_url: "https://bigmodel.cn/pricing", checked_at: "2026-10-27", revision: "test",
      model_version: "glm-5.3", sku: "publisher-proxy", source_model: "GLM-5.3",
      assumption: "7 CNY per USD planning assumption, not ModelArts contract price", assumptions: "Cache detail may be unavailable", basis: "Display only" }} />);
    expect(screen.getByText(/TBC/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Public pricing source" })).toHaveAttribute("href", "https://bigmodel.cn/pricing");
    expect(screen.getByText(/7 CNY/)).toBeInTheDocument();
  });
  it("discloses missing cache approximations without inventing tokens", () => {
    render(<EstimateCoverage estimate={{ unestimated_requests: 2, approximate_requests: 3 }} />);
    expect(screen.getByText(/2 unestimated request/)).toHaveTextContent("3 standard-input approximation");
    expect(screen.queryByText(/TBC subtotal/)).not.toBeInTheDocument();
  });
});