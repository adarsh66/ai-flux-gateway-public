import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DisplayPriceDetails, EstimateCoverage, estimateMoney } from "./components/DisplayPrice";
import { costLabel } from "./pages/UsagePage";
import type { UsageSummary } from "./types";

describe("sourced display pricing", () => {
  it("preserves tiny nonzero amounts and distinguishes unknown from zero", () => {
    expect(estimateMoney("0.000001142857")).toBe("USD 0.00000114");
    expect(estimateMoney("0.000000000001")).toBe("USD <0.00000001");
    expect(estimateMoney("0")).toBe("USD 0.00");
    expect(estimateMoney(null)).toBe("Unknown");
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