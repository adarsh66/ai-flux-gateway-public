import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { OrganizationCostComparison } from "./components/OrganizationCostCharts";
import type { OrganizationCosts } from "./types";

const estimate = (amount: string | null) => ({ estimated_cost_usd: amount, estimated_requests: amount === null ? 0 : 1, unestimated_requests: amount === null ? 1 : 0, approximate_requests: 0, pricing_revision: "test" });
const data: OrganizationCosts = { total: 3, currency: "USD", start: "2026-11-01T00:00:00Z", end: "2026-11-02T00:00:00Z", order: "measured_tokens_desc_id_asc", items: [
  { id: "a", name: "Alpha", requests: 1, total_tokens: 100, external: estimate("10"), internal: estimate("1") },
  { id: "b", name: "Beta", requests: 1, total_tokens: 50, external: estimate("0"), internal: estimate("8") },
  { id: "c", name: "Gamma", requests: 1, total_tokens: 1, external: estimate(null), internal: { ...estimate("0.000000001"), unestimated_requests: 1, approximate_requests: 1 } },
] };
describe("paired organization cost charts", () => {
  it("keeps common order and numerical scale despite reversed price rankings", () => {
    render(<OrganizationCostComparison data={data} onSelect={() => undefined} />);
    const external = screen.getByRole("region", { name: "external organization cost chart" });
    const internal = screen.getByRole("region", { name: "internal organization cost chart" });
    for (const chart of [external, internal]) expect(within(chart).getAllByRole("button").map(b => b.textContent)).toEqual(["Alpha", "Beta", "Gamma"]);
    expect(external.querySelector(".organization-cost-fill")).toHaveStyle({ width: "100%" });
    expect(internal.querySelector(".organization-cost-fill")).toHaveStyle({ width: "10%" });
    expect(screen.getByText(/Shared USD page scale/)).toHaveTextContent("USD 10.00");
    expect(screen.getByRole("table")).toHaveAccessibleName(/accessible chart data/);
  });
  it("distinguishes zero, unknown, tiny and partial estimates with coverage", () => {
    render(<OrganizationCostComparison data={data} onSelect={() => undefined} />);
    expect(screen.getAllByText("USD 0.00")).toHaveLength(2);
    expect(screen.getAllByText("Unknown")).toHaveLength(2);
    expect(screen.getAllByText("USD <0.00000001")).toHaveLength(2);
    expect(screen.getAllByText(/Partial estimate/)).toHaveLength(2);
    const chart = screen.getByRole("region", { name: "external organization cost chart" });
    expect(chart.querySelectorAll(".organization-cost-fill")).toHaveLength(2);
  });
  it("supports keyboard organization drilldown without changing comparison data", async () => {
    const select = vi.fn();
    render(<OrganizationCostComparison data={data} onSelect={select} />);
    screen.getAllByRole("button", { name: "Alpha" })[0]!.focus();
    await userEvent.keyboard("{Enter}");
    expect(select).toHaveBeenCalledWith("a");
    expect(screen.getAllByRole("button", { name: "Beta" })).toHaveLength(3);
  });
});