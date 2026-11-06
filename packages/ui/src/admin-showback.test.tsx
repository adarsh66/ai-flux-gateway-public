import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ControlApi } from "./client";
import { UsagePage } from "./pages/UsagePage";
import { SessionProvider } from "./session";
import * as ui from "./components/ui";

const totals = { requests: 2, input_tokens: 10, output_tokens: 20, total_tokens: 30, missing_token_requests: 1, incomplete_requests: 1 };
function response(url: URL): unknown {
  if (url.pathname.endsWith("/organization-costs")) return { items: [], total: 0, currency: "USD", start: url.searchParams.get("start"), end: url.searchParams.get("end"), order: "measured_tokens_desc_id_asc" };
  if (url.pathname.endsWith("/decision-scoring")) return { status: "unavailable", notice: null, retention_notice: "Test fixture: scoring telemetry unavailable." };
  if (url.pathname.endsWith("/organizations")) return { items: [{ id: "org-a", name: "Alpha org" }, { id: "org-b", name: "Beta org" }], total: 2 };
  if (url.pathname.endsWith("/subscriptions")) {
    const org = url.searchParams.get("organization_id") ?? "org-a";
    return { items: [{ id: `${org}-sub`, name: "Shared label", organization_id: org, organization_name: org }], total: 1 };
  }
  if (url.pathname.endsWith("/models")) return { items: ["model-a", "model-b"], total: 2 };
  if (url.pathname.endsWith("/rankings")) {
    const org = url.searchParams.get("organization_id");
    const dimension = url.searchParams.get("dimension");
    return { items: [{ ...totals, id: dimension === "organizations" ? "org-a" : `${org}-sub`, name: dimension === "organizations" ? "Top org" : "Top sub", share: 0.25 }],
      total: 12, totals, dimension, organization_id: org, start: url.searchParams.get("start"), end: url.searchParams.get("end") };
  }
  if (url.pathname.endsWith("/timeseries") || url.pathname.endsWith("/model-tokens")) return { items: [], start: url.searchParams.get("start"), end: url.searchParams.get("end"), interval_seconds: 86400 };
  if (url.pathname.endsWith("/export")) return new Response("id\nfixture", { headers: { "Content-Type": "text/csv" } });
  return { items: [{ id: "request", subscription_id: "org-a-sub", model: "model-a", provider: "fixture", region: "fixture", occurred_at: "2026-10-01T00:00:00Z", input_tokens: 10, output_tokens: 20, cached_input_tokens: null, cache_write_tokens: null, cost: null, currency: null, status_code: 200, e2e_ms: null, ttft_ms: null, completeness: "usage_missing" }], total: 100, summary: { ...totals, known_cost: null, currency: null, failed_requests: 0, throttled_requests: 0, e2e_p95_ms: null, ttft_supported: false, cache_tokens_supported: false, last_ingested_at: null } };
}

function mount(handler: (url: URL) => unknown | Promise<unknown> = response) {
  const urls: URL[] = [];
  const api = new ControlApi("/api", async () => "test", async input => {
    const url = new URL(String(input), "https://test.invalid");
    urls.push(url);
    const data = await handler(url);
    return data instanceof Response ? data : new Response(JSON.stringify(data));
  });
  render(<SessionProvider api={api} onSignOut={() => undefined}
    me={{ organization_id: "admin", organization_name: "Admin", tenant_id: "t", object_id: "u", role: "ids_admin" }}
    config={{ clientId: "c", authority: "a", apiScope: "s", controlApiUrl: "/api", gatewayUrl: "https://test.invalid" }}><UsagePage admin /></SessionProvider>);
  return urls;
}
const organizations = () => screen.getByRole("region", { name: "Organizations by token usage (global)" });
const subscriptions = () => screen.getByRole("region", { name: "Subscriptions by token usage — Alpha org" });

describe("admin showback", () => {
  it("loads all metadata pages and searches past the first hundred safely", async () => {
    const urls = mount(url => url.pathname.endsWith("/subscriptions") ? {
      items: Array.from({ length: url.searchParams.get("offset") === "0" ? 100 : 1 }, (_, i) => ({
        id: `s-${Number(url.searchParams.get("offset")) + i}`, name: `Sub ${Number(url.searchParams.get("offset")) + i}`, organization_name: "Duplicate org",
      })), total: 101,
    } : response(url));
    await screen.findByRole("option", { name: /Sub 100/ });
    expect(urls.some(u => u.pathname.endsWith("/subscriptions") && u.searchParams.get("offset") === "100")).toBe(true);
    await userEvent.type(screen.getByLabelText("Search subscriptions"), "Sub 100");
    expect(screen.getByRole("option", { name: /Sub 100/ })).toBeVisible();
    expect(screen.queryByRole("option", { name: /Sub 99/ })).not.toBeInTheDocument();
  });

  it("propagates detail subscription and exact UTC viewport to every request and CSV", async () => {
    const urls = mount();
    await screen.findByRole("option", { name: /Shared label/ });
    await userEvent.selectOptions(screen.getByLabelText("Organization"), "org-a");
    await screen.findByRole("option", { name: /Shared label/ });
    await userEvent.selectOptions(screen.getByLabelText("Subscription"), "org-a-sub");
    await waitFor(() => expect(urls.some(u => u.pathname.endsWith("/model-tokens") && u.searchParams.get("subscription_id") === "org-a-sub")).toBe(true));
    await userEvent.selectOptions(screen.getByLabelText("Model"), "model-a");
    const download = vi.spyOn(ui, "downloadBlob").mockImplementation(() => undefined);
    await waitFor(() => expect(screen.getByRole("button", { name: "Export completion-only CSV" })).toBeEnabled());
    await userEvent.click(screen.getByRole("button", { name: "Export completion-only CSV" }));
    await waitFor(() => expect(download).toHaveBeenCalled());
    const csv = urls.filter(u => u.pathname.endsWith("/export")).at(-1)!;
    for (const suffix of ["/usage", "/models", "/timeseries", "/model-tokens", "/export"]) {
      const request = urls.filter(u => u.pathname.endsWith(suffix)).at(-1)!;
      expect(request.searchParams.get("subscription_id")).toBe("org-a-sub");
      expect(request.searchParams.get("organization_id")).toBe("org-a");
      expect(request.searchParams.get("start")).toBe(csv.searchParams.get("start"));
      expect(request.searchParams.get("end")).toBe(csv.searchParams.get("end"));
      if (suffix !== "/models") expect(request.searchParams.get("model")).toBe("model-a");
    }
    download.mockRestore();
  });

  it("ranking selections filter details while declared comparison scopes remain independent", async () => {
    const urls = mount();
    await within(organizations()).findByRole("button", { name: "Top org" });
    expect(screen.getByText(/Select an organization to compare/)).toBeVisible();
    await userEvent.click(within(organizations()).getByRole("button", { name: "Top org" }));
    await within(subscriptions()).findByRole("button", { name: "Top sub" });
    await userEvent.click(within(subscriptions()).getByRole("button", { name: "Top sub" }));
    expect(screen.getByLabelText("Organization")).toHaveValue("org-a");
    expect(screen.getByLabelText("Subscription")).toHaveValue("org-a-sub");
    expect(within(organizations()).getByText("25.0%")).toBeVisible();
    await waitFor(() => expect(urls.filter(u => u.pathname.endsWith("/usage")).at(-1)!.searchParams.get("subscription_id")).toBe("org-a-sub"));
    for (const u of urls.filter(u => u.pathname.endsWith("/rankings"))) {
      expect(u.searchParams.has("subscription_id")).toBe(false);
      if (u.searchParams.get("dimension") === "organizations") expect(u.searchParams.has("organization_id")).toBe(false);
      else expect(u.searchParams.get("organization_id")).toBe("org-a");
    }
    await userEvent.click(within(organizations()).getByRole("button", { name: "Next" }));
    await waitFor(() => expect(urls.some(u => u.pathname.endsWith("/rankings") && u.searchParams.get("offset") === "10")).toBe(true));
  });

  it("clears selected subscription and detail pagination on organization change and discards stale metadata", async () => {
    let old: ((data: unknown) => void) | undefined;
    const urls = mount(url => url.pathname.endsWith("/subscriptions") && url.searchParams.get("organization_id") === "org-b"
      ? new Promise(resolve => { old = resolve; }) : response(url));
    await screen.findByRole("option", { name: /Shared label/ });
    await userEvent.selectOptions(screen.getByLabelText("Subscription"), "org-a-sub");
    await userEvent.click(screen.getByText("Transaction details"));
    const details = screen.getByText("Transaction details").closest("details")!;
    await userEvent.click(within(details).getByRole("button", { name: "Next" }));
    await waitFor(() => expect(urls.some(u => u.pathname.endsWith("/usage") && u.searchParams.get("offset") === "50")).toBe(true));
    await userEvent.selectOptions(screen.getByLabelText("Organization"), "org-b");
    expect(screen.getByLabelText("Subscription")).toHaveValue("");
    expect(screen.queryByRole("option", { name: /Shared label/ })).not.toBeInTheDocument();
    await waitFor(() => expect(old).toBeDefined());
    await userEvent.selectOptions(screen.getByLabelText("Organization"), "org-a");
    await screen.findByRole("option", { name: /Shared label/ });
    await act(async () => old!({ items: [{ id: "stale", name: "STALE" }], total: 1 }));
    expect(screen.queryByRole("option", { name: /STALE/ })).not.toBeInTheDocument();
    expect(urls.filter(u => u.searchParams.get("organization_id") === "org-b" && u.pathname.includes("/usage")).every(u => !u.searchParams.has("subscription_id") && (!u.searchParams.has("offset") || u.searchParams.get("offset") === "0"))).toBe(true);
  });

  it("shows scoped ranking loading, error, retry and empty states and ignores old model results", async () => {
    let old: ((data: unknown) => void) | undefined;
    let fail = true;
    mount(url => {
      if (!url.pathname.endsWith("/rankings")) return response(url);
      if (!url.searchParams.get("model")) return new Promise(resolve => { old = resolve; });
      return fail ? new Response(JSON.stringify({ detail: "Ranking unavailable" }), { status: 503 }) : { ...response(url) as object, items: [], total: 0 };
    });
    expect(within(organizations()).getByRole("status")).toHaveTextContent("Loading");
    await within(screen.getByLabelText("Model")).findByRole("option", { name: "model-b" });
    await userEvent.selectOptions(screen.getByLabelText("Model"), "model-b");
    await within(organizations()).findByText("Ranking unavailable");
    fail = false;
    await userEvent.click(within(organizations()).getByRole("button", { name: "Try again" }));
    await within(organizations()).findByText("No usage in this ranking scope");
    await act(async () => old!({ ...totals, items: [{ ...totals, id: "stale", name: "STALE", share: 1 }], total: 1, totals }));
    expect(screen.queryByText("STALE")).not.toBeInTheDocument();
  });

  it("refresh and zoom update rankings together with the shared UTC viewport", async () => {
    const urls = mount();
    await within(organizations()).findByRole("button", { name: "Top org" });
    const before = urls.filter(u => u.pathname.endsWith("/rankings")).at(-1)!.searchParams.get("start");
    await userEvent.click(screen.getByRole("button", { name: "Zoom in" }));
    await waitFor(() => expect(urls.filter(u => u.pathname.endsWith("/rankings")).at(-1)!.searchParams.get("start")).not.toBe(before));
    const count = urls.filter(u => u.pathname.endsWith("/rankings")).length;
    await userEvent.click(screen.getByRole("button", { name: "Refresh telemetry" }));
    await waitFor(() => expect(urls.filter(u => u.pathname.endsWith("/rankings")).length).toBeGreaterThan(count));
  });

  it("keeps metadata errors scoped, retries and never offers foreign subscriptions", async () => {
    let fail = true;
    mount(url => url.pathname.endsWith("/subscriptions") && fail
      ? new Response(JSON.stringify({ detail: "Metadata unavailable" }), { status: 503 }) : response(url));
    await screen.findByText(/Could not load subscriptions/);
    expect(screen.getByLabelText("Subscription")).toBeDisabled();
    fail = false;
    await userEvent.click(screen.getByRole("button", { name: "Retry subscriptions" }));
    await screen.findByRole("option", { name: /Shared label/ });
    expect(screen.getByLabelText("Subscription")).toBeEnabled();
    expect(within(organizations()).getByText(/Global: all organizations/)).toBeVisible();
  });
});