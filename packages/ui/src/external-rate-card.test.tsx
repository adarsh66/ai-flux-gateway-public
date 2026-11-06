import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ControlApi } from "./client";
import { SessionProvider } from "./session";
import { RateCardEditor, validateExternalRates } from "./pages/RateCardEditor";
import { CustomerCreditsPage } from "./pages/TokenExchangePages";
import { UsagePage } from "./pages/UsagePage";
import { DecisionScoringUsage } from "./components/DecisionScoringUsage";
import type { DecisionScoringTelemetry, ExternalRateCard, RateRow } from "./types";

const config = { clientId: "c", authority: "a", apiScope: "s", controlApiUrl: "/api", gatewayUrl: "https://g/v1" };
const me = { organization_id: "own", organization_name: "Own organization", tenant_id: "t", object_id: "a", role: "ids_admin" as const };
const row = (over: Partial<RateRow> = {}): RateRow => ({ model: "alpha", provider: "OpenAI", region: "eastus", model_version: "1", sku: "s", origin: "configured", note: "Inherited from external baseline", source_url: null, input: "3", output: "6", cached: null, write: null, default_input: "3", default_output: "6", default_cached: null, default_write: null, configured_from: null, ...over });
const card = (items = [row()], version = 1): ExternalRateCard => ({ items, version, revision: `external-v${version}`, currency: "USD", unit: "per_million_tokens", total: items.length, changed: false });
const draft = { input: "3", output: "6", cached: "", write: "" };
type Handler = (url: string, init: RequestInit) => unknown | Promise<unknown>;
function setup(handler: Handler, element = <RateCardEditor />, customer = false) {
  const fetcher = vi.fn(async (url: string, init: RequestInit) => {
    const body = await handler(url, init);
    return body instanceof Response ? body : new Response(JSON.stringify(body), { status: 200 });
  });
  const api = new ControlApi("/api", async () => "test-token", fetcher as unknown as typeof fetch);
  render(<MemoryRouter><SessionProvider me={{ ...me, role: customer ? "customer" : "ids_admin" }} api={api} config={config} onSignOut={() => undefined}>{element}</SessionProvider></MemoryRouter>);
  return { api, fetcher };
}
const organizations = { items: [{ id: "org/a", name: "Organization A" }, { id: "org-b", name: "Organization B" }], total: 2 };
const defaultHandler: Handler = (url) => url.endsWith("/organizations") ? organizations : card();
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("External price contract", () => {
  it("only sends explicit operations; no inherit is allowed on the baseline", () => {
    expect(validateExternalRates(card(), { alpha: draft }, {}, true)).toEqual({ ok: true, rates: [] });
    expect(validateExternalRates(card(), { alpha: draft }, { alpha: "set" }, true)).toEqual({ ok: true, rates: [{ model: "alpha", operation: "set", input: "3", output: "6", cached: null, write: null }] });
    for (const operation of ["unknown", "inherit"] as const) expect(validateExternalRates(card(), {}, { alpha: operation }, true)).toEqual({ ok: true, rates: [{ model: "alpha", operation }] });
    expect(validateExternalRates(card(), {}, { alpha: "inherit" }, false).ok).toBe(false);
  });
  it.each(["", "-1", "1e2", "NaN", "0.123456789", "100001"])("rejects invalid external decimal %j", (input) => {
    expect(validateExternalRates(card(), { alpha: { ...draft, input } }, { alpha: "set" }, false).ok).toBe(false);
  });
  it("requires chat output but makes Decision-1 strictly input-only", () => {
    expect(validateExternalRates(card(), { alpha: { ...draft, output: "" } }, { alpha: "set" }, false).ok).toBe(false);
    const scoring = card([row({ model: "Decision-1", model_kind: "scoring", input: "0.042", output: null, default_output: null })]);
    expect(validateExternalRates(scoring, { "Decision-1": { input: "0", output: "", cached: "", write: "" } }, { "Decision-1": "set" }, true)).toMatchObject({ ok: true, rates: [{ operation: "set", input: "0", output: null, cached: null, write: null }] });
    for (const dimension of ["output", "cached", "write"]) expect(validateExternalRates(scoring, { "Decision-1": { input: "0.04", output: "", cached: "", write: "", [dimension]: "0" } }, { "Decision-1": "set" }, true).ok).toBe(false);
  });
  it("encodes organization IDs and uses the own-organization effective endpoint", async () => {
    const { api, fetcher } = setup(defaultHandler);
    await act(async () => {
      await api.effectiveRateCard();
      await api.externalRateCard("org/a");
      await api.saveExternalRateCard({ expected_version: 7, reason: "reviewed", rates: [{ model: "alpha", operation: "unknown" }] }, "org/a");
    });
    expect(fetcher.mock.calls.map(([url]) => url)).toContain("/api/rate-card");
    const saved = fetcher.mock.calls.find(([url, init]) => url === "/api/admin/organizations/org%2Fa/external-rate-card" && init.method === "PUT")!;
    expect(JSON.parse(saved[1].body as string)).toEqual({ expected_version: 7, reason: "reviewed", rates: [{ model: "alpha", operation: "unknown" }] });
  });
});

describe("External editor scope and races", () => {
  it("loads a future organization's inherited card without writes or Auto polling and saves inherit / unknown explicitly", async () => {
    const writes: unknown[] = [];
    const interval = vi.spyOn(globalThis, "setInterval");
    setup((url, init) => {
      if (init.method === "PUT") { writes.push(JSON.parse(init.body as string)); return { ...card([row({ input: null, output: null, note: "Explicit unknown override" })], 2), changed: true }; }
      return defaultHandler(url, init);
    });
    const user = userEvent.setup();
    await screen.findByLabelText("alpha input rate");
    await user.click(screen.getByRole("tab", { name: "External prices" }));
    const selector = await screen.findByLabelText("External price scope");
    expect(screen.queryByRole("button", { name: "Return to default" })).not.toBeInTheDocument();
    await user.selectOptions(selector, "org/a");
    expect(await screen.findByText("Inherited", { selector: ".badge" })).toBeInTheDocument();
    expect(writes).toEqual([]);
    expect(interval.mock.calls.filter(call => call[1] === 15000)).toHaveLength(0);
    await user.click(screen.getByRole("button", { name: "alpha return to default" }));
    await user.click(screen.getByRole("button", { name: "Save 1 change" }));
    await screen.findByText(/Saved 1 rate change/);
    expect(writes[0]).toMatchObject({ expected_version: 1, rates: [{ model: "alpha", operation: "inherit" }] });
    await user.click(screen.getByRole("button", { name: "alpha mark unknown" }));
    await user.click(screen.getByRole("button", { name: "Save 1 change" }));
    await waitFor(() => expect(writes).toHaveLength(2));
    expect(writes[1]).toMatchObject({ expected_version: 2, rates: [{ model: "alpha", operation: "unknown" }] });
  });
  it("offers cancel or discard on audience and organization switches", async () => {
    setup(defaultHandler);
    const user = userEvent.setup();
    const input = await screen.findByLabelText("alpha input rate");
    await user.clear(input); await user.type(input, "9");
    await user.click(screen.getByRole("tab", { name: "External prices" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Cancel" }));
    expect(input).toHaveValue("9");
    await user.click(screen.getByRole("tab", { name: "External prices" }));
    await user.click(screen.getByRole("button", { name: "Discard changes" }));
    await screen.findByLabelText("External price scope");
    await screen.findByLabelText("alpha input rate");
    await user.click(screen.getByRole("button", { name: "alpha mark unknown" }));
    await user.selectOptions(screen.getByLabelText("External price scope"), "org-b");
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByLabelText("External price scope")).toHaveValue("");
    expect(screen.getByLabelText("alpha input rate")).toHaveValue("");
  });
  it("never applies a late organization GET or save to another scope with the same version", async () => {
    let resolveGet!: (value: ExternalRateCard) => void;
    let resolveSave!: (value: ExternalRateCard) => void;
    const lateGet = new Promise<ExternalRateCard>(resolve => { resolveGet = resolve; });
    const lateSave = new Promise<ExternalRateCard>(resolve => { resolveSave = resolve; });
    setup((url, init) => init.method === "PUT" ? lateSave : url.includes("org%2Fa") ? lateGet : defaultHandler(url, init));
    const user = userEvent.setup();
    await screen.findByLabelText("alpha input rate");
    await user.click(screen.getByRole("tab", { name: "External prices" }));
    await user.selectOptions(await screen.findByLabelText("External price scope"), "org/a");
    await user.selectOptions(screen.getByLabelText("External price scope"), "org-b");
    await screen.findByLabelText("alpha input rate");
    await act(async () => resolveGet(card([row({ input: "999" })])));
    expect(screen.getByLabelText("alpha input rate")).toHaveValue("3");
    await user.click(screen.getByRole("button", { name: "alpha mark unknown" }));
    await user.click(screen.getByRole("button", { name: "Save 1 change" }));
    await user.selectOptions(screen.getByLabelText("External price scope"), "");
    await user.click(screen.getByRole("button", { name: "Discard changes" }));
    await screen.findByLabelText("alpha input rate");
    await user.clear(screen.getByLabelText("alpha input rate"));
    await user.type(screen.getByLabelText("alpha input rate"), "4");
    await act(async () => resolveSave({ ...card([row({ input: "888" })]), changed: true }));
    expect(screen.getByLabelText("alpha input rate")).toHaveValue("4");
    expect(screen.queryByText(/Saved 1 rate change/)).not.toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Internal costs" }));
    expect(screen.getByRole("dialog", { name: "Discard unsaved rate changes?" })).toBeInTheDocument();
  });
  it("retains external drafts on conflict and never silently falls back to internal costs", async () => {
    setup((url, init) => init.method === "PUT" ? new Response(JSON.stringify({ detail: "External card changed; reload." }), { status: 409 }) : defaultHandler(url, init));
    const user = userEvent.setup();
    await screen.findByLabelText("alpha input rate");
    await user.click(screen.getByRole("tab", { name: "External prices" }));
    const input = await screen.findByLabelText("alpha input rate");
    await user.clear(input); await user.type(input, "0");
    await user.click(screen.getByRole("button", { name: "Save 1 change" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("External card changed; reload.");
    expect(input).toHaveValue("0");
  });
  it("reloads only the selected organization after confirmation and saves against the latest version", async () => {
    let orgReads = 0;
    const writes: unknown[] = [];
    const { fetcher } = setup((url, init) => {
      if (init.method === "PUT") {
        writes.push(JSON.parse(init.body as string));
        return { ...card([row({ input: "8" })], 3), changed: true };
      }
      if (new URL(url, "https://portal").pathname.endsWith("/history")) return { items: [], total: 0, next_offset: null };
      if (url === "/api/admin/organizations/org%2Fa/external-rate-card") return card([row({ input: ++orgReads === 1 ? "3" : "7", note: "Inherited external default" })], orgReads);
      return defaultHandler(url, init);
    });
    const user = userEvent.setup();
    await screen.findByLabelText("alpha input rate");
    await user.click(screen.getByRole("tab", { name: "External prices" }));
    await user.selectOptions(await screen.findByLabelText("External price scope"), "org/a");
    const input = await screen.findByLabelText("alpha input rate");
    expect(screen.getByText("Inherited", { selector: ".badge" })).toBeInTheDocument();
    await user.clear(input); await user.type(input, "9");
    await user.click(screen.getByRole("button", { name: "Reload latest" }));
    expect(orgReads).toBe(1);
    expect(input).toHaveValue("9");
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(input).toHaveValue("9");
    const readsBeforeReload = fetcher.mock.calls.length;
    await user.click(screen.getByRole("button", { name: "Reload latest" }));
    await user.click(screen.getByRole("button", { name: "Discard changes and reload" }));
    await waitFor(() => expect(screen.getByLabelText("alpha input rate")).toHaveValue("7"));
    expect(fetcher.mock.calls.slice(readsBeforeReload).map(([url, init]) => ({ url, method: init.method ?? "GET" }))).toEqual([
      { url: "/api/admin/organizations/org%2Fa/external-rate-card", method: "GET" },
      { url: "/api/admin/organizations/org%2Fa/external-rate-card/history?offset=0", method: "GET" },
    ]);
    expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();
    await user.clear(screen.getByLabelText("alpha input rate"));
    await user.type(screen.getByLabelText("alpha input rate"), "8");
    await user.click(screen.getByRole("button", { name: "Save 1 change" }));
    await waitFor(() => expect(writes).toHaveLength(1));
    expect(writes[0]).toMatchObject({ expected_version: 2, rates: [{ model: "alpha", operation: "set", input: "8" }] });
  });
});

describe("Customer financial visibility", () => {
  it("does not render legacy internal balance signals or fallback costs, even if returned", async () => {
    setup(() => ({ organization_name: "Own organization", currency: "USD", total_credits: "5000", used_credits: "4321.98", remaining_credits: "678.02", utilization_pct: 86.4, low_credit_alert: true, total_requests: 2, total_tokens: 30, by_model: [{ model: "alpha", vendor: "OpenAI", requests: 2, input_tokens: 10, output_tokens: 20, total_tokens: 30, cost_usd: "4321.98", share_pct: 100 }], by_product: [], by_channel: [] }), <CustomerCreditsPage />, true);
    await screen.findByText("Own organization");
    expect(screen.getByRole("heading", { name: /External estimated cost \(30d\)/ })).toBeInTheDocument();
    expect(screen.queryByText(/4321.98|678.02|86.4|Low credit alert|Credits used|Remaining credits/)).not.toBeInTheDocument();
    expect(screen.getAllByText(/Unknown/).length).toBeGreaterThan(0);
    expect(screen.getByText("2 reqs · 30 tokens")).toBeInTheDocument();
  });
  it.each([false, true])("shows recorded completion costs only with admin=%s", async (admin) => {
    const summary = { requests: 1, input_tokens: 10, output_tokens: 20, known_cost: "8765.43", currency: "USD", incomplete_requests: 0, failed_requests: 0, throttled_requests: 0, e2e_p95_ms: null, ttft_supported: false, cache_tokens_supported: false, last_ingested_at: null, pricing_revision: "external-v1", estimated_cost_usd: "1.25" };
    setup(url => url.includes("/usage?") ? { items: [], total: 0, summary } : url.includes("timeseries") ? { items: [], interval_seconds: 86400 } : url.includes("model-tokens") ? { items: [], interval_seconds: 86400 } : url.includes("decision-scoring") ? { status: "unavailable", notice: null, retention_notice: "retained" } : { items: [], total: 0 }, <UsagePage admin={admin} />, !admin);
    await screen.findByText("USD 1.25");
    expect(screen.queryByText("Recorded cost") !== null).toBe(admin);
    expect(screen.queryByText(/8765.43/) !== null).toBe(admin);
  });
  it.each([false, true])("shows recorded Decision-1 costs only with admin=%s", async (admin) => {
    const telemetry: DecisionScoringTelemetry = { model: "Decision-1", source: "log_analytics", status: "available", notice: null, retention_notice: "retained", start: "2026-11-01T00:00:00Z", end: "2026-11-02T00:00:00Z", granularity: "day", time_zone: "Asia/Singapore", offset: 0, limit: 50, total: 0, summary: { invocations: 1, input_tokens: 10, output_tokens: 0, total_tokens: 10, measured_invocations: 1, missing_token_invocations: 0, estimated_cost_usd: "0.01", recorded_cost_usd: "9876.54", estimated_invocations: 1, unestimated_invocations: 0, avg_latency_ms: null, pricing_revision: "external-v1" }, items: [], series: [], breakdown: [] };
    const { fetcher } = setup(() => telemetry, <DecisionScoringUsage admin={admin} query={{ organization_id: "not-own" }} />, !admin);
    await screen.findByText("USD 0.01");
    expect(screen.queryByText("Recorded scoring cost") !== null).toBe(admin);
    expect(screen.queryByText("USD 9,876.54") !== null).toBe(admin);
    if (!admin) expect(fetcher.mock.calls[0]![0]).not.toContain("organization_id");
  });
});