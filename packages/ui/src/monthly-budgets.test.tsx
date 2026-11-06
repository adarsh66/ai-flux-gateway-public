import type { ReactNode } from "react";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { ApiError, ControlApi } from "./client";
import { SessionProvider } from "./session";
import { CustomerMonthlyBudgetCard, MonthlyBudgetDetails, MonthlyBudgetGauge } from "./components/MonthlyBudget";
import { AdminBudgetsAndFinOpsPage, CustomerCreditsPage } from "./pages/TokenExchangePages";
import { validMonthlyAllocation } from "./pages/MonthlyBudgetsPage";
import type { AdminMonthlyBudgetDashboard, MonthlyBudgetSummary, Paged, MonthlyBudgetRevision } from "./types";

const config = { clientId: "c", authority: "a", apiScope: "s", controlApiUrl: "/api", gatewayUrl: "https://gateway/v1" };
const me = { organization_id: "org-a", organization_name: "Alpha", object_id: "user-a", tenant_id: "tenant-a", role: "customer" as const };
const budget: MonthlyBudgetSummary = {
  organization_id: "org-a", organization_name: "Alpha", allocated_usd: "100.0000",
  estimated_used_usd: "125.000000000000", estimated_remaining_usd: null, estimated_overrun_usd: "25.000000000000",
  estimated_utilization_pct: 125, advisory_threshold_pct: 80, status: "over_budget",
  period_start: "2026-11-01T00:00:00Z", period_end: "2026-12-01T00:00:00Z", as_of: "2026-11-03T08:00:00Z",
  latest_usage_at: "2026-11-03T07:55:00Z", estimated_requests: 20, unestimated_requests: 0,
  pricing_revision: "external-v2", version: 3, estimate_complete: false, basis: "external_customer_prices", hard_stop_enabled: false,
};
const unconfigured: MonthlyBudgetSummary = { ...budget, allocated_usd: null, estimated_used_usd: null,
  estimated_remaining_usd: null, estimated_overrun_usd: null, estimated_utilization_pct: null, status: "unconfigured", version: 0 };
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
function dashboard(value: MonthlyBudgetSummary): AdminMonthlyBudgetDashboard {
  return { budget: value, internal: { estimated_cost_usd: "7.25", estimated_requests: 18, unestimated_requests: 2,
    approximate_requests: 1, pricing_revision: "internal-v9" }, internal_basis: "internal_price_estimate", internal_scope: "completion_usage",
    archived_at: null, read_only: false, as_of: value.as_of };
}
function apiFor(items = [budget]) {
  const api = new ControlApi("/api", async () => "test", vi.fn());
  vi.spyOn(api, "adminMonthlyBudgets").mockResolvedValue({ items, total: items.length });
  vi.spyOn(api, "adminMonthlyBudgetDashboard").mockImplementation(async (id) => dashboard(items.find((r) => r.organization_id === id) ?? { ...unconfigured, organization_id: id }));
  vi.spyOn(api, "monthlyBudgetHistory").mockResolvedValue({ items: [], total: 0 });
  vi.spyOn(api, "monthlyBudget").mockResolvedValue(budget);
  vi.spyOn(api, "saveMonthlyBudget").mockResolvedValue({ ...budget, version: 4 });
  return api;
}
function view(api: ControlApi, node: ReactNode, principal = me) {
  return <MemoryRouter><SessionProvider api={api} me={principal} config={config} onSignOut={() => undefined}>{node}</SessionProvider></MemoryRouter>;
}
async function selectOrganization(id = "org-a") {
  await waitFor(() => expect(screen.getByLabelText("Organization")).toBeEnabled());
  await userEvent.selectOptions(screen.getByLabelText("Organization"), id);
  await screen.findByLabelText("Monthly allocation (USD)");
}
async function fillDraft(value = "42.1234") {
  await userEvent.clear(screen.getByLabelText("Monthly allocation (USD)"));
  await userEvent.type(screen.getByLabelText("Monthly allocation (USD)"), value);
  await userEvent.type(screen.getByLabelText("Reason for budget change"), "Quarterly review");
}

describe("Monthly advisory budget display", () => {
  it.each([79, 80, 100, 125])("displays %s%% numerically with a capped accessible visual", (pct) => {
    render(<MonthlyBudgetDetails budget={{ ...budget, estimated_utilization_pct: pct,
      status: pct > 100 ? "over_budget" : pct >= 80 ? "threshold_reached" : "below_threshold", estimate_complete: pct < 80 }} />);
    const progress = screen.getByRole("progressbar", { name: "Monthly budget utilization" });
    expect(progress).toHaveAttribute("aria-valuenow", String(Math.min(100, pct)));
    expect(progress).toHaveAttribute("aria-valuetext", `${pct}% estimated utilization; advisory only`);
    expect(screen.getByText(`${pct}%`)).toBeInTheDocument();
    expect(screen.getByText(pct > 100 ? "Over monthly budget — advisory only" : pct >= 80 ? "On-screen advisory threshold reached" : "Below advisory threshold")).toBeInTheDocument();
    expect(screen.getByText(/never blocks traffic/)).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });
  it.each(["unknown", "unconfigured"] as const)("shows %s without inventing zero or an allocation", (status) => {
    render(<MonthlyBudgetDetails budget={{ ...unconfigured, status }} />);
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
    expect(screen.getByText("Not configured")).toBeInTheDocument();
    expect(screen.getAllByText("Unknown").length).toBeGreaterThan(0);
    expect(screen.queryByText("USD 0.00")).not.toBeInTheDocument();
  });
  it("discloses UTC boundaries, as-of, latest usage and incomplete scoring coverage even with zero unestimated rows", () => {
    render(<MonthlyBudgetDetails budget={budget} />);
    expect(screen.getByText(/2026-11-01 00:00:00 UTC.*2026-12-01 00:00:00 UTC/)).toBeInTheDocument();
    expect(screen.getByText("2026-11-03 08:00:00 UTC")).toBeInTheDocument();
    expect(screen.getByText("2026-11-03 07:55:00 UTC")).toBeInTheDocument();
    expect(screen.getByText(/20 estimated request\(s\); 0 unestimated.*Incomplete estimate coverage/)).toBeInTheDocument();
    expect(screen.getByText(/does not prove complete scoring coverage/)).toBeInTheDocument();
    expect(screen.getByText("external-v2")).toBeInTheDocument();
  });
  it("keeps tiny known values and unknown remaining separate without recomputing money", () => {
    render(<MonthlyBudgetDetails budget={{ ...budget, estimated_used_usd: "0.000000000001", estimated_remaining_usd: null }} />);
    expect(screen.getByText("USD <0.00000001")).toBeInTheDocument();
    expect(screen.getByText("Unknown")).toBeInTheDocument();
  });
  it("keeps a configured allocation visible when the usage estimate is unknown", () => {
    render(<MonthlyBudgetDetails budget={{ ...budget, status: "unknown", estimated_used_usd: null,
      estimated_remaining_usd: null, estimated_overrun_usd: null, estimated_utilization_pct: null, latest_usage_at: null }} />);
    expect(screen.queryByText("Budget utilization unknown")).not.toBeInTheDocument();
    expect(screen.getByText("USD 100.00")).toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
    expect(screen.getByText("Not available")).toBeInTheDocument();
    expect(screen.queryByText("USD 0.00")).not.toBeInTheDocument();
  });
});

describe("Admin monthly budget editor", () => {
  it("starts unconfigured allocation blank, 80% on-screen only; GET never writes or seeds", async () => {
    const api = apiFor([unconfigured]);
    render(view(api, <AdminBudgetsAndFinOpsPage />));
    await selectOrganization();
    expect(screen.getByLabelText("Monthly allocation (USD)")).toHaveValue("");
    expect(screen.getByLabelText("On-screen advisory threshold (%)")).toHaveValue(80);
    expect(screen.getByRole("button", { name: "Save monthly budget" })).toBeDisabled();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/allowed models|hard stop|Credit allocation/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Sync|Turnstile|send email/i })).not.toBeInTheDocument();
    expect(api.saveMonthlyBudget).not.toHaveBeenCalled();
    expect(await screen.findByText("No budget changes")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "FinOps usage ledger" })).toHaveAttribute("href", "/usage");
  });
  it("sends decimal/CAS/reason only, disables all controls while saving, then reloads summary and history", async () => {
    const api = apiFor();
    const save = deferred<MonthlyBudgetSummary>();
    vi.mocked(api.saveMonthlyBudget).mockReturnValueOnce(save.promise);
    render(view(api, <AdminBudgetsAndFinOpsPage />));
    await selectOrganization();
    await fillDraft();
    await userEvent.clear(screen.getByLabelText("On-screen advisory threshold (%)"));
    await userEvent.type(screen.getByLabelText("On-screen advisory threshold (%)"), "90");
    await userEvent.click(screen.getByRole("button", { name: "Save monthly budget" }));
    expect(api.saveMonthlyBudget).toHaveBeenCalledTimes(1);
    expect(api.saveMonthlyBudget).toHaveBeenCalledWith("org-a", {
      allocated_usd: "42.1234", advisory_threshold_pct: 90, expected_version: 3, reason: "Quarterly review",
    });
    expect(screen.getByLabelText("Organization")).toBeDisabled();
    expect(screen.getByLabelText("Monthly allocation (USD)")).toBeDisabled();
    expect(screen.getByLabelText("On-screen advisory threshold (%)")).toBeDisabled();
    expect(screen.getByLabelText("Reason for budget change")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Refresh budgets" })).toBeDisabled();
    const updated = { ...budget, allocated_usd: "42.1234", advisory_threshold_pct: 90, version: 4 };
    vi.mocked(api.adminMonthlyBudgets).mockResolvedValue({ items: [updated], total: 1 });
    vi.mocked(api.adminMonthlyBudgetDashboard).mockResolvedValue(dashboard(updated));
    vi.mocked(api.monthlyBudgetHistory).mockResolvedValue({ items: [{ version: 4, allocated_usd: "42.1234", advisory_threshold_pct: 90,
      reason: "Quarterly review", changed_by: "admin-reviewer", changed_at: budget.as_of }], total: 1 });
    await act(async () => { save.resolve(updated); });
    expect(await screen.findByText(/Monthly advisory budget saved/)).toBeInTheDocument();
    expect(await screen.findByText("admin-reviewer")).toBeInTheDocument();
    expect(api.adminMonthlyBudgets).toHaveBeenCalledTimes(2);
    expect(screen.getByText(/Saved version 4/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Reason for budget change"), "Next review");
    await userEvent.click(screen.getByRole("button", { name: "Save monthly budget" }));
    expect(vi.mocked(api.saveMonthlyBudget).mock.calls[1]?.[1].expected_version).toBe(4);
  });
  it("retains conflict draft, prevents blind resave, clears errors and drafts on organization switch", async () => {
    const beta = { ...unconfigured, organization_id: "org-b", organization_name: "Beta" };
    const api = apiFor([budget, beta]);
    vi.mocked(api.saveMonthlyBudget).mockRejectedValue(new ApiError(409, "stale"));
    render(view(api, <AdminBudgetsAndFinOpsPage />));
    await selectOrganization(); await fillDraft();
    await userEvent.click(screen.getByRole("button", { name: "Save monthly budget" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Refresh budgets to load the latest version");
    expect(screen.getByLabelText("Monthly allocation (USD)")).toHaveValue("42.1234");
    expect(screen.getByRole("button", { name: "Save monthly budget" })).toBeDisabled();
    await userEvent.selectOptions(screen.getByLabelText("Organization"), "org-b");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(await screen.findByLabelText("Monthly allocation (USD)")).toHaveValue("");
    expect(screen.getByLabelText("Reason for budget change")).toHaveValue("");
    expect(api.monthlyBudgetHistory).toHaveBeenLastCalledWith("org-b", 0, 20);
  });
  it("recovers a conflict only after explicitly refreshing the current CAS version", async () => {
    const api = apiFor();
    vi.mocked(api.saveMonthlyBudget).mockRejectedValueOnce(new ApiError(409, "stale"));
    render(view(api, <AdminBudgetsAndFinOpsPage />));
    await selectOrganization(); await fillDraft();
    await userEvent.click(screen.getByRole("button", { name: "Save monthly budget" }));
    await screen.findByRole("alert");
    vi.mocked(api.adminMonthlyBudgets).mockResolvedValue({ items: [{ ...budget, version: 8 }], total: 1 });
    vi.mocked(api.adminMonthlyBudgetDashboard).mockResolvedValue(dashboard({ ...budget, version: 8 }));
    await userEvent.click(screen.getByRole("button", { name: "Refresh budgets" }));
    await screen.findByText(/Saved version 8/);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    await fillDraft(); await userEvent.click(screen.getByRole("button", { name: "Save monthly budget" }));
    expect(vi.mocked(api.saveMonthlyBudget).mock.calls[1]?.[1].expected_version).toBe(8);
  });
  it("shows truthful save failure and permits a deliberate retry", async () => {
    const api = apiFor();
    vi.mocked(api.saveMonthlyBudget).mockRejectedValueOnce(new ApiError(503, "Budget storage unavailable"));
    render(view(api, <AdminBudgetsAndFinOpsPage />));
    await selectOrganization(); await fillDraft();
    await userEvent.click(screen.getByRole("button", { name: "Save monthly budget" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Budget storage unavailable");
    expect(screen.queryByText(/Monthly advisory budget saved/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save monthly budget" })).toBeEnabled();
  });
  it("keeps metadata loading and failure distinct from an empty organization list, then retries", async () => {
    const api = apiFor();
    const loading = deferred<Paged<MonthlyBudgetSummary>>();
    vi.mocked(api.adminMonthlyBudgets).mockReturnValueOnce(loading.promise);
    render(view(api, <AdminBudgetsAndFinOpsPage />));
    expect(screen.getByText("Loading…")).toBeInTheDocument();
    expect(screen.queryByText("No organizations")).not.toBeInTheDocument();
    await act(async () => loading.reject(new ApiError(403, "Administrator access required")));
    expect(await screen.findByRole("alert")).toHaveTextContent("Administrator access required");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    await selectOrganization();
    expect(api.saveMonthlyBudget).not.toHaveBeenCalled();
  });
  it("shows a history fetch error without erasing the allocation editor", async () => {
    const api = apiFor();
    vi.mocked(api.monthlyBudgetHistory).mockRejectedValueOnce(new ApiError(503, "History unavailable"));
    render(view(api, <AdminBudgetsAndFinOpsPage />));
    await selectOrganization();
    expect(await screen.findByRole("alert")).toHaveTextContent("History unavailable");
    expect(screen.getByLabelText("Monthly allocation (USD)")).toHaveValue("100.0000");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("No budget changes")).toBeInTheDocument();
  });
  it.each(["0", "101", "80.5", ""])("does not submit invalid on-screen threshold %j", async (threshold) => {
    const api = apiFor();
    render(view(api, <AdminBudgetsAndFinOpsPage />));
    await selectOrganization(); await fillDraft();
    const input = screen.getByLabelText("On-screen advisory threshold (%)");
    await userEvent.clear(input);
    if (threshold) await userEvent.type(input, threshold);
    expect(screen.getByRole("button", { name: "Save monthly budget" })).toBeDisabled();
    expect(api.saveMonthlyBudget).not.toHaveBeenCalled();
  });
  it("fetches all organization pages rather than silently truncating at 100", async () => {
    const api = apiFor();
    const first = Array.from({ length: 100 }, (_, i) => ({ ...budget, organization_id: `org-${i}`, organization_name: `Org ${i}` }));
    vi.mocked(api.adminMonthlyBudgets).mockResolvedValueOnce({ items: first, total: 101 })
      .mockResolvedValueOnce({ items: [{ ...unconfigured, organization_id: "last-org", organization_name: "Last" }], total: 101 });
    render(view(api, <AdminBudgetsAndFinOpsPage />));
    await selectOrganization("last-org");
    expect(api.adminMonthlyBudgets).toHaveBeenNthCalledWith(2, 100, 100, "current");
    expect(screen.getByLabelText("Monthly allocation (USD)")).toHaveValue("");
  });
  it("paginates audit history and discards late previous-organization history", async () => {
    const api = apiFor([budget, { ...budget, organization_id: "org-b", organization_name: "Beta" }]);
    const late = deferred<Paged<MonthlyBudgetRevision>>();
    vi.mocked(api.monthlyBudgetHistory).mockResolvedValueOnce({ items: [{ version: 3, allocated_usd: "100", advisory_threshold_pct: 80, reason: "Alpha revision", changed_by: "a", changed_at: budget.as_of }], total: 21 })
      .mockReturnValueOnce(late.promise)
      .mockResolvedValueOnce({ items: [], total: 0 });
    render(view(api, <AdminBudgetsAndFinOpsPage />));
    await selectOrganization();
    await screen.findByText("Alpha revision");
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(api.monthlyBudgetHistory).toHaveBeenLastCalledWith("org-a", 20, 20);
    await userEvent.selectOptions(screen.getByLabelText("Organization"), "org-b");
    await screen.findByText("No budget changes");
    await act(async () => late.resolve({ items: [{ version: 1, allocated_usd: "2", advisory_threshold_pct: 80, reason: "Stale private revision", changed_by: "a", changed_at: budget.as_of }], total: 1 }));
    expect(screen.queryByText("Stale private revision")).not.toBeInTheDocument();
  });
  it.each(["", "0", "-1", "1e3", "NaN", "Infinity", "01", "1.00001", "1000000000.0001", "9999999999"])("rejects invalid allocation %j without float conversion", (value) => {
    expect(validMonthlyAllocation(value)).toBe(false);
  });
  it.each(["0.0001", "42.1234", "999999999.9999", "1000000000", "1000000000.0000"])("accepts valid exact allocation %s", (value) => {
    expect(validMonthlyAllocation(value)).toBe(true);
  });
});

describe("Admin dashboard and separate archive view", () => {
  it("shows five metrics, separate internal partial basis and a native collapsed disclosure", async () => {
    const api = apiFor();
    const { container } = render(view(api, <AdminBudgetsAndFinOpsPage />));
    await selectOrganization();
    expect(container.querySelectorAll(".overview-budget-metrics > div")).toHaveLength(5);
    expect(screen.getAllByRole("progressbar")).toHaveLength(1);
    expect(screen.getByText("Estimated internal cost (USD)").nextElementSibling).toHaveTextContent("USD 7.25");
    expect(screen.getByText("Partial completion usage estimate")).toBeVisible();
    const disclosure = container.querySelector("details")!;
    expect(disclosure).not.toHaveAttribute("open");
    expect(within(disclosure).getByText("internal-v9")).not.toBeVisible();
    await userEvent.click(screen.getByText("Budget details & calculation basis"));
    expect(within(disclosure).getByText("internal-v9")).toBeVisible();
    expect(within(disclosure).getByText(/18 estimated request.*2 unestimated.*1 approximate/)).toBeVisible();
    expect(within(disclosure).getByText(/excludes Decision-1 scoring and retries/)).toBeVisible();
    expect(api.monthlyBudget).not.toHaveBeenCalled();
    expect(api.saveMonthlyBudget).not.toHaveBeenCalled();
  });
  it("all-unknown internal usage stays Unknown rather than zero", async () => {
    const api = apiFor();
    const unknown = dashboard(budget);
    unknown.internal = { ...unknown.internal, estimated_cost_usd: null, estimated_requests: 0, unestimated_requests: 4, approximate_requests: 0 };
    vi.mocked(api.adminMonthlyBudgetDashboard).mockResolvedValue(unknown);
    render(view(api, <AdminBudgetsAndFinOpsPage />));
    await selectOrganization();
    expect(screen.getByText("Estimated internal cost (USD)").nextElementSibling).toHaveTextContent("Unknown");
    expect(screen.getByText("Unknown — no known priced subtotal")).toBeVisible();
  });
  it("archive view has retained estimates and history but no editor, save or restore", async () => {
    const api = apiFor();
    const archived = { ...dashboard(budget), archived_at: "2026-11-02T10:00:00Z", read_only: true };
    vi.mocked(api.adminMonthlyBudgetDashboard).mockResolvedValue(archived);
    render(view(api, <AdminBudgetsAndFinOpsPage />));
    await userEvent.click(screen.getByRole("button", { name: "Archived organizations" }));
    await waitFor(() => expect(screen.getByLabelText("Organization")).toBeEnabled());
    await userEvent.selectOptions(screen.getByLabelText("Organization"), "org-a");
    await screen.findByText("Estimated internal cost (USD)");
    expect(api.adminMonthlyBudgets).toHaveBeenLastCalledWith(0, 100, "archived");
    expect(screen.getByText(/Archived organization · read-only/)).toHaveTextContent("2026-11-02");
    expect(await screen.findByText("No budget changes")).toBeInTheDocument();
    expect(screen.queryByLabelText("Monthly allocation (USD)")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /save|restore/i })).not.toBeInTheDocument();
    expect(api.saveMonthlyBudget).not.toHaveBeenCalled();
  });
  it("discards a late selected snapshot after switching views, and refresh removes stale selection", async () => {
    const api = apiFor();
    const late = deferred<AdminMonthlyBudgetDashboard>();
    vi.mocked(api.adminMonthlyBudgetDashboard).mockReturnValueOnce(late.promise);
    render(view(api, <AdminBudgetsAndFinOpsPage />));
    await waitFor(() => expect(screen.getByLabelText("Organization")).toBeEnabled());
    await userEvent.selectOptions(screen.getByLabelText("Organization"), "org-a");
    await userEvent.click(screen.getByRole("button", { name: "Archived organizations" }));
    await act(async () => late.resolve(dashboard(budget)));
    expect(screen.queryByText("Estimated internal cost (USD)")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Current organizations" }));
    await selectOrganization();
    vi.mocked(api.adminMonthlyBudgets).mockResolvedValue({ items: [], total: 0 });
    await userEvent.click(screen.getByRole("button", { name: "Refresh budgets" }));
    await screen.findByText("No organizations");
    expect(screen.queryByLabelText("Monthly allocation (USD)")).not.toBeInTheDocument();
    expect(screen.queryByText("Estimated internal cost (USD)")).not.toBeInTheDocument();
  });
});

describe("Customer monthly budget isolation", () => {
  it("renders one dashboard, one vertical gauge and four authoritative metrics with collapsed native disclosure metadata", async () => {
    const api = apiFor();
    const { container } = render(view(api, <CustomerMonthlyBudgetCard overview />));
    const dashboard = await screen.findByRole("region", { name: "Monthly advisory budget" });
    expect(screen.getAllByRole("heading", { name: "Monthly advisory budget" })).toHaveLength(1);
    expect(screen.getAllByRole("progressbar")).toHaveLength(1);
    expect(container.querySelectorAll(".overview-budget-metrics > div")).toHaveLength(4);
    expect(container.querySelector(".monthly-overview-grid")).toBeNull();
    expect(within(dashboard).getByText("November 2026 · UTC", { exact: false })).toBeInTheDocument();
    expect(within(dashboard).getByText("Estimated overrun").nextElementSibling).toHaveTextContent("USD 25.00");
    const disclosure = container.querySelector("details")!;
    expect(disclosure).not.toHaveAttribute("open");
    expect(within(disclosure).getByText("external-v2")).not.toBeVisible();
    const summary = screen.getByText("Budget details & calculation basis");
    await userEvent.click(summary);
    expect(disclosure).toHaveAttribute("open");
    expect(within(disclosure).getByText("external-v2")).toBeVisible();
    expect(within(disclosure).getByText(/2026-11-01 00:00:00 UTC.*2026-12-01 00:00:00 UTC/)).toBeVisible();
    expect(within(disclosure).getByText("2026-11-03 08:00:00 UTC")).toBeVisible();
    expect(within(disclosure).getByText("2026-11-03 07:55:00 UTC")).toBeVisible();
    expect(within(disclosure).getByText(/20 estimated request.*0 unestimated/)).toBeVisible();
    expect(within(disclosure).getByText(/no rollover/)).toBeVisible();
    expect(within(disclosure).getByText(/Email notifications are not enabled/)).toBeVisible();
    expect(within(disclosure).getByText(/Decision-1 scoring telemetry/)).toBeVisible();
    expect(screen.getByText(/Incomplete coverage — known amounts/)).toBeVisible();
    expect(screen.getByText(/Advisory only — never blocks traffic/)).toBeVisible();
    await userEvent.click(summary);
    expect(disclosure).not.toHaveAttribute("open");
    expect(api.monthlyBudget).toHaveBeenCalledTimes(1);
    expect(api.saveMonthlyBudget).not.toHaveBeenCalled();
  });
  it.each([0, 79, 80, 100, 125])("unified overview preserves %s%%, status, exact money and metadata without a second panel", async (pct) => {
    const api = apiFor();
    vi.mocked(api.monthlyBudget).mockResolvedValueOnce({ ...budget, estimate_complete: true, estimated_used_usd: String(pct),
      estimated_utilization_pct: pct, status: pct > 100 ? "over_budget" : pct >= 80 ? "threshold_reached" : "below_threshold" });
    const { container } = render(view(api, <CustomerMonthlyBudgetCard overview />));
    expect(await screen.findByText(`${pct}%`)).toBeVisible();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", String(Math.min(100, pct)));
    expect(container.querySelectorAll(".panel")).toHaveLength(1);
    expect(screen.getByText("Known estimated usage").nextElementSibling).toHaveTextContent(`USD ${pct}.00`);
    expect(container.querySelectorAll(".badge")).toHaveLength(1);
    expect(container.querySelector("details")).not.toHaveAttribute("open");
  });
  it("leaves default customer Usage presentation expanded and unchanged", async () => {
    const api = apiFor();
    const { container } = render(view(api, <CustomerMonthlyBudgetCard />));
    await screen.findByRole("heading", { name: "Monthly advisory budget" });
    expect(container.querySelector(".overview-budget-dashboard")).toBeNull();
    expect(container.querySelector("details")).toBeNull();
    expect(screen.getByText("external-v2")).toBeVisible();
    expect(screen.getByRole("progressbar")).not.toHaveAttribute("aria-orientation");
  });
  it.each([false, true])("omits unknown badges without replacing or changing known partial figures (overview=%s)", async (overview) => {
    const api = apiFor();
    vi.mocked(api.monthlyBudget).mockResolvedValueOnce({ ...budget, status: "unknown", estimated_utilization_pct: 12.5,
      estimated_used_usd: "12.5", estimated_remaining_usd: null, estimated_overrun_usd: null });
    const { container } = render(view(api, <CustomerMonthlyBudgetCard overview={overview} />));
    await screen.findByRole("heading", { name: "Monthly advisory budget" });
    expect(screen.queryByText("Budget utilization unknown")).not.toBeInTheDocument();
    expect(container.querySelector(".badge")).toBeNull();
    expect(screen.getAllByText(/12.5%/).length).toBeGreaterThan(0);
    expect(screen.getAllByText("USD 12.50").length).toBeGreaterThan(0);
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "12.5");
    expect(screen.getByText(/Incomplete estimate coverage; known amounts are not a complete total/)).toBeInTheDocument();
    expect(screen.getAllByText(/Unknown/).length).toBeGreaterThan(0);
    expect(api.saveMonthlyBudget).not.toHaveBeenCalled();
  });
  it.each([null, "", "bad", "-1", "Infinity"])("omits every unknown-usage fallback badge for %j without replacing it", (estimated_used_usd) => {
    const { container } = render(<MonthlyBudgetGauge budget={{ ...budget, estimated_used_usd }} />);
    expect(container.querySelector(".badge")).toBeNull();
    expect(screen.queryByText("Budget utilization unknown")).not.toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuetext", "Unknown; advisory only");
    expect(screen.getByText(/Known estimated consumption \(incomplete coverage\)/)).toBeInTheDocument();
    expect(screen.getByText(/Estimated remaining: Unknown/)).toBeInTheDocument();
  });
  it.each(["unconfigured", "below_threshold", "threshold_reached", "over_budget"] as const)("keeps the existing %s gauge badge", (status) => {
    const labels = { unconfigured: "No monthly budget configured", below_threshold: "Below advisory threshold",
      threshold_reached: "On-screen advisory threshold reached", over_budget: "Over monthly budget — advisory only" };
    const { container } = render(<MonthlyBudgetGauge budget={{ ...budget, status, estimate_complete: true,
      allocated_usd: status === "unconfigured" ? null : "100" }} />);
    expect(container.querySelectorAll(".badge")).toHaveLength(1);
    expect(screen.getByText(labels[status])).toBeInTheDocument();
  });
  it.each([0, 79, 80, 100, 125])("overview gauge preserves actual %s%% and caps only fill", (pct) => {
    render(<MonthlyBudgetGauge budget={{ ...budget, estimated_used_usd: String(pct), estimated_utilization_pct: pct }} />);
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-orientation", "vertical");
    expect(bar).toHaveAttribute("aria-valuenow", String(Math.min(100, pct)));
    expect(bar).toHaveAttribute("aria-valuetext", `${pct}% known estimated utilization (incomplete coverage); advisory only`);
    expect(bar.querySelector(".monthly-gauge-fill")).toHaveStyle({ height: `${Math.min(100, pct)}%` });
    expect(screen.getByText(`${pct}%`)).toBeInTheDocument();
    expect(screen.getByText(/80% on-screen advisory threshold/)).toBeInTheDocument();
  });
  it.each(["0", "NaN", "Infinity", "-1", "", "bad"])("does not invent utilization for malformed allocation %j", (allocated_usd) => {
    const { container } = render(<MonthlyBudgetGauge budget={{ ...budget, allocated_usd }} />);
    expect(container.querySelector(".badge")).toBeNull();
    expect(screen.queryByText("Budget utilization unknown")).not.toBeInTheDocument();
    expect(screen.getByRole("progressbar")).not.toHaveAttribute("aria-valuenow");
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuetext", "Unknown; advisory only");
  });
  it.each([null, Number.NaN, Number.POSITIVE_INFINITY, -1])("does not render a numeric gauge for invalid percentage %s", (estimated_utilization_pct) => {
    const { container } = render(<MonthlyBudgetGauge budget={{ ...budget, estimated_utilization_pct }} />);
    expect(container.querySelector(".badge")).toBeNull();
    expect(screen.getByRole("progressbar")).not.toHaveAttribute("aria-valuenow");
    expect(screen.queryByText("125%")).not.toBeInTheDocument();
  });
  it("keeps incomplete below-threshold estimates qualified, tiny money precise and unknown remaining authoritative", async () => {
    const api = apiFor();
    vi.mocked(api.monthlyBudget).mockResolvedValueOnce({ ...budget, status: "below_threshold", estimated_utilization_pct: 1,
      estimated_used_usd: "0.000000000001", estimated_remaining_usd: null });
    render(view(api, <CustomerMonthlyBudgetCard overview />));
    await screen.findByText("1%");
    expect(screen.queryByText("Below advisory threshold")).not.toBeInTheDocument();
    expect(screen.getAllByText("Incomplete estimate — advisory status not confirmed")).toHaveLength(1);
    expect(screen.getAllByText("USD <0.00000001")).toHaveLength(1);
    expect(screen.getByText("Estimated remaining").nextElementSibling).toHaveTextContent("Unknown");
  });
  it.each([false, true])("preserves truthful unconfigured and unknown usage states (unconfigured=%s)", async (noAllocation) => {
    const api = apiFor();
    vi.mocked(api.monthlyBudget).mockResolvedValueOnce({ ...unconfigured, allocated_usd: noAllocation ? null : "100", status: noAllocation ? "unconfigured" : "unknown" });
    render(view(api, <CustomerMonthlyBudgetCard overview />));
    await screen.findByLabelText("Current monthly allocation");
    expect(screen.getByRole("progressbar")).not.toHaveAttribute("aria-valuenow");
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuetext", `${noAllocation ? "Not configured" : "Unknown"}; advisory only`);
    expect(screen.queryByText("USD 0.00")).not.toBeInTheDocument();
    expect(screen.queryByText("Budget utilization unknown")).not.toBeInTheDocument();
    expect(screen.queryAllByText("No monthly budget configured")).toHaveLength(noAllocation ? 1 : 0);
  });
  it("uses one snapshot for allocation, gauge and details, hides all old values during refresh, and retries together", async () => {
    const api = apiFor();
    const pending = deferred<MonthlyBudgetSummary>();
    vi.mocked(api.monthlyBudget).mockReturnValueOnce(pending.promise);
    render(view(api, <CustomerMonthlyBudgetCard overview />));
    expect(screen.getByRole("status")).toHaveTextContent("Loading");
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
    await act(async () => pending.resolve(budget));
    expect(await screen.findByText("125%")).toBeInTheDocument();
    expect(within(screen.getByLabelText("Current monthly allocation")).getByText("USD 100.00")).toBeInTheDocument();
    expect(screen.getAllByRole("progressbar")).toHaveLength(1);
    const refresh = deferred<MonthlyBudgetSummary>();
    vi.mocked(api.monthlyBudget).mockReturnValueOnce(refresh.promise);
    await userEvent.click(screen.getByRole("button", { name: "Refresh monthly budget" }));
    expect(screen.queryByText("125%")).not.toBeInTheDocument();
    expect(screen.queryByText("USD 100.00")).not.toBeInTheDocument();
    await act(async () => refresh.reject(new ApiError(503, "Snapshot unavailable")));
    expect(await screen.findByRole("alert")).toHaveTextContent("Snapshot unavailable");
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
    vi.mocked(api.monthlyBudget).mockResolvedValueOnce({ ...budget, allocated_usd: "200", estimated_utilization_pct: 62.5 });
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("62.5%")).toBeInTheDocument();
    expect(within(screen.getByLabelText("Current monthly allocation")).getByText("USD 200.00")).toBeInTheDocument();
    expect(api.monthlyBudget).toHaveBeenCalledTimes(3);
  });
  it("keeps UTC monthly snapshot independent of 7/30/90-day reporting and usage errors; excludes legacy credits and fake daily graph", async () => {
    const api = apiFor();
    const creditSummary = vi.spyOn(api, "creditSummary").mockResolvedValue({ organization_name: "Alpha", total_credits: "9999", currency: "USD", total_tokens: 40,
      total_requests: 2, by_model: [], by_product: [], by_channel: [] } as unknown as Awaited<ReturnType<ControlApi["creditSummary"]>>);
    render(view(api, <CustomerCreditsPage />));
    await screen.findByLabelText("Current monthly allocation");
    await screen.findByRole("heading", { name: "Token share by model" });
    expect(screen.queryByText(/Total credit allocation|Daily token volume|Stacked token distribution|9999/)).not.toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Reporting window"), "7");
    await waitFor(() => expect(creditSummary).toHaveBeenLastCalledWith(7));
    await userEvent.selectOptions(screen.getByLabelText("Reporting window"), "90");
    await waitFor(() => expect(creditSummary).toHaveBeenLastCalledWith(90));
    expect(api.monthlyBudget).toHaveBeenCalledTimes(1);
    creditSummary.mockRejectedValueOnce(new ApiError(503, "Usage unavailable"));
    await userEvent.selectOptions(screen.getByLabelText("Reporting window"), "30");
    expect(await screen.findByRole("alert")).toHaveTextContent("Usage unavailable");
    expect(screen.getByLabelText("Current monthly allocation")).toHaveTextContent("USD 100.00");
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "100");
    expect(api.monthlyBudget).toHaveBeenCalledTimes(1);
  });
  it("loads and refreshes current-principal budget independently, with honest errors and no writes", async () => {
    const api = apiFor();
    vi.mocked(api.monthlyBudget).mockRejectedValueOnce(new ApiError(503, "Budget summary unavailable"));
    render(view(api, <CustomerMonthlyBudgetCard />));
    expect(await screen.findByRole("alert")).toHaveTextContent("Budget summary unavailable");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("125%")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Refresh monthly budget" }));
    await waitFor(() => expect(api.monthlyBudget).toHaveBeenCalledTimes(3));
    expect(api.saveMonthlyBudget).not.toHaveBeenCalled();
    expect(api.adminMonthlyBudgets).not.toHaveBeenCalled();
  });
  it("clears old tenant data immediately and ignores its late response on session switch", async () => {
    const api = apiFor();
    const late = deferred<MonthlyBudgetSummary>();
    vi.mocked(api.monthlyBudget).mockResolvedValueOnce(budget).mockReturnValueOnce(late.promise)
      .mockResolvedValueOnce({ ...unconfigured, organization_id: "org-b", organization_name: "Beta" });
    const mounted = render(view(api, <CustomerMonthlyBudgetCard />));
    await screen.findByText("125%");
    await userEvent.click(screen.getByRole("button", { name: "Refresh monthly budget" }));
    mounted.rerender(view(api, <CustomerMonthlyBudgetCard />, { ...me, organization_id: "org-b", object_id: "user-b" }));
    expect(screen.queryByText("125%")).not.toBeInTheDocument();
    await screen.findByText("No monthly budget configured");
    await act(async () => late.resolve(budget));
    expect(screen.queryByText("125%")).not.toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Monthly advisory budget" })).getByText("Not configured")).toBeInTheDocument();
  });
  it("uses the exact principal/admin API contracts and URL-encodes identifiers", async () => {
    const calls: { path: string; init: RequestInit }[] = [];
    const api = new ControlApi("/api", async () => "test", async (input, init = {}) => {
      calls.push({ path: String(input), init });
      return new Response(JSON.stringify(budget), { status: 200 });
    });
    await api.monthlyBudget(); await api.adminMonthlyBudgets(100, 100); await api.monthlyBudgetHistory("org/a", 20, 20);
    const payload = { allocated_usd: "12.0001", advisory_threshold_pct: 80, expected_version: 0, reason: "Initial allocation" };
    await api.saveMonthlyBudget("org/a", payload);
    expect(calls.map((c) => c.path)).toEqual(["/api/budget/monthly", "/api/admin/monthly-budgets?offset=100&limit=100", "/api/admin/monthly-budgets/org%2Fa/history?offset=20&limit=20", "/api/admin/monthly-budgets/org%2Fa"]);
    expect(calls[3]?.init.method).toBe("PUT");
    expect(JSON.parse(String(calls[3]?.init.body))).toEqual(payload);
  });
});