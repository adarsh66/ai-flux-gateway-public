import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { ControlApi } from "./client";
import { SessionProvider } from "./session";
import { PricingRevisionViewer } from "./pages/PricingRevisionViewer";
import { RateCardEditor } from "./pages/RateCardEditor";
import type { HistoricalRateRow, PricingHistoryDetail, PricingHistoryPoint, RateCard, RateRow } from "./types";

const point = (id = "latest", extra: Partial<PricingHistoryPoint> = {}): PricingHistoryPoint => ({ id, source: "internal", effective_at: "2026-11-04T10:00:00Z", reason: "Reviewed prices", internal_version: 4, default_version: null, organization_version: null, simultaneous: false, ...extra });
const row = (model = "alpha", extra: Partial<HistoricalRateRow> = {}): HistoricalRateRow => ({ model, canonical_model: model, provider: "OpenAI", region: "eastus", model_version: "2026-01", sku: "GlobalStandard", model_kind: "chat", billing_dimensions: ["input", "output"], state: "known", input: "1.00000001", output: "2.50000000", cached: "0", write: null, note: null, ...extra });
const detail = (source = point(), items = [row()], extra: Partial<PricingHistoryDetail> = {}): PricingHistoryDetail => ({ source, items, skipped: [], current_version: 7, requires_acknowledgement: false, ...extra });
const currentRow: RateRow = { model: "alpha", provider: "OpenAI", region: "eastus", model_version: "2026-01", sku: "GlobalStandard", model_kind: "chat", billing_dimensions: ["input", "output"], origin: "configured", note: null, source_url: null, input: "8", output: "12", cached: null, write: null, default_input: "8", default_output: "12", default_cached: null, default_write: null, configured_from: null };
const current: RateCard = { version: 7, revision: "current-v7", currency: "USD", unit: "per_million_tokens", items: [currentRow], total: 1, changed: false };
const config = { clientId: "c", authority: "a", apiScope: "s", controlApiUrl: "/api", gatewayUrl: "https://g/v1" };
type Handler = (url: string, init: RequestInit) => unknown | Promise<unknown>;
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}
function mount(handler: Handler = () => undefined, editor = false) {
  const requests: { url: string; method: string; body?: unknown }[] = [];
  const fetcher = (async (url: string, init: RequestInit) => {
    requests.push({ url, method: init.method ?? "GET", body: init.body ? JSON.parse(init.body as string) : undefined });
    const body = await handler(url, init) ?? (url.includes("/history/detail") ? detail() : url.includes("/history") ? { items: [point()], total: 1, next_offset: null } : url.endsWith("/organizations") ? { items: [{ id: "org1", name: "One" }, { id: "org2", name: "Two" }], total: 2 } : current);
    return body instanceof Response ? body : new Response(JSON.stringify(body), { status: 200 });
  }) as unknown as typeof fetch;
  const api = new ControlApi("/api", async () => "test-token", fetcher);
  render(<SessionProvider me={{ organization_id: "o", organization_name: "IDS", tenant_id: "t", object_id: "a", role: "ids_admin" }} api={api} config={config} onSignOut={() => undefined}>{editor ? <RateCardEditor /> : <PricingRevisionViewer />}</SessionProvider>);
  return requests;
}
const table = () => screen.findByRole("table", { name: "Historical model rates (USD per 1M tokens)" });
const httpError = (text: string) => new Response(JSON.stringify({ detail: text }), { status: 503 });
afterEach(cleanup);

describe("read-only pricing revision viewer", () => {
  it("auto-selects latest, renders exact decimals, zero, null, retired rows, metadata and warnings without editor controls", async () => {
    const requests = mount((url) => url.includes("/history/detail") ? detail(point("latest", { simultaneous: true }), [
      row(), row("unknown", { state: "unknown", input: null, output: null }),
      row("unavailable", { state: "unavailable", input: null, output: null, model_version: null }),
      row("retired", { note: "Retired model retained in source", input: "0.00000001", write: "1.25000000" }),
      row("Decision-1", { model_kind: "scoring", billing_dimensions: ["input"], input: "0", output: null, cached: null }),
    ], { requires_acknowledgement: true, skipped: ["Unverifiable old scope"] }) : undefined);
    const historical = await table();
    expect(screen.getByLabelText("Revision to view")).toHaveValue("latest");
    const alpha = within(historical).getByRole("rowheader", { name: /alpha/ }).closest("tr")!;
    expect(within(alpha).getByText("1.00000001")).toBeInTheDocument();
    expect(within(alpha).getByText("2.50000000")).toBeInTheDocument();
    expect(within(alpha).getByText("0")).toBeInTheDocument();
    expect(within(alpha).getByText("Unknown — not free")).toBeInTheDocument();
    expect(within(alpha).getByText("2026-01 · GlobalStandard")).toBeInTheDocument();
    const unknown = within(historical).getByRole("rowheader", { name: /^unknown/ }).closest("tr")!;
    expect(within(unknown).getAllByText("Unknown — not free")).toHaveLength(5);
    expect(within(unknown).queryByText("0")).not.toBeInTheDocument();
    expect(within(historical).getByText("0.00000001")).toBeInTheDocument();
    expect(within(historical).getByText("1.25000000")).toBeInTheDocument();
    const scorer = within(historical).getByRole("rowheader", { name: /Decision-1/ }).closest("tr")!;
    expect(within(scorer).getAllByText("N/A")).toHaveLength(3);
    expect(within(scorer).getByText("0")).toBeInTheDocument();
    const unavailable = within(historical).getByRole("rowheader", { name: /unavailable/ }).closest("tr")!;
    expect(within(unavailable).getAllByText("Unavailable")).toHaveLength(4);
    expect(screen.getByText("Unverifiable old scope")).toBeInTheDocument();
    expect(screen.getByText(/Simultaneous changes:/)).toBeInTheDocument();
    expect(screen.getByText("Reviewed prices", { selector: "dd" })).toBeInTheDocument();
    expect(screen.getByText("2026-11-04T10:00:00Z", { selector: "time" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /save|reset|restore|draft|load into/i })).not.toBeInTheDocument();
    expect(requests.every((request) => request.method === "GET")).toBe(true);
    expect(requests.every((request) => /\/history/.test(request.url))).toBe(true);
  });

  it("addresses all three scopes and both organization owners using GET only", async () => {
    const requests = mount();
    const user = userEvent.setup();
    await table();
    await user.selectOptions(screen.getByLabelText("Revision scope"), "external-default");
    await table();
    await user.selectOptions(screen.getByLabelText("Revision scope"), "organization-external");
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    await screen.findByRole("option", { name: "One · org1" });
    await user.selectOptions(screen.getByLabelText("Revision organization"), "org1");
    await table();
    await user.selectOptions(screen.getByLabelText("Revision organization"), "org2");
    await table();
    for (const prefix of ["/api/admin/rate-card", "/api/admin/external-rate-card", "/api/admin/organizations/org1/external-rate-card", "/api/admin/organizations/org2/external-rate-card"]) {
      expect(requests.some((r) => r.url.startsWith(`${prefix}/history?`))).toBe(true);
      expect(requests.some((r) => r.url.startsWith(`${prefix}/history/detail?`))).toBe(true);
    }
    expect(requests.every((r) => r.method === "GET")).toBe(true);
  });

  it("paginates without replacing selection and retries the failed page without duplicating points", async () => {
    let pages = 0;
    const requests = mount((url) => url.includes("/history?") ? url.includes("offset=25")
      ? ++pages === 1 ? httpError("Older page unavailable") : { items: [point(), point("older", { internal_version: 1 })], total: 2, next_offset: null }
      : { items: [point()], total: 2, next_offset: 25 } : undefined);
    const user = userEvent.setup();
    await table();
    await user.click(screen.getByRole("button", { name: "Load more revisions" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Older page unavailable");
    await user.click(screen.getByRole("button", { name: "Retry revisions" }));
    await waitFor(() => expect(within(screen.getByLabelText("Revision to view")).getAllByRole("option")).toHaveLength(2));
    expect(screen.getByLabelText("Revision to view")).toHaveValue("latest");
    expect(requests.filter((r) => r.url.includes("offset=25"))).toHaveLength(2);
    await user.selectOptions(screen.getByLabelText("Revision to view"), "older");
    await waitFor(() => expect(requests.some((r) => r.url.includes("revision=older"))).toBe(true));
    expect(requests.every((r) => r.method === "GET")).toBe(true);
  });

  it("disables the revision selector during initial loading and handles list error, retry and empty history", async () => {
    const pending = deferred<unknown>();
    let calls = 0;
    mount((url) => url.includes("/history?") ? ++calls === 1 ? pending.promise : { items: [], total: 0, next_offset: null } : undefined);
    expect(screen.getByLabelText("Revision to view")).toBeDisabled();
    expect(screen.getByText("Loading revisions…")).toBeInTheDocument();
    await act(async () => pending.resolve(httpError("List unavailable")));
    expect(await screen.findByRole("alert")).toHaveTextContent("List unavailable");
    await userEvent.setup().click(screen.getByRole("button", { name: "Retry revisions" }));
    expect(await screen.findByText("No retained historical revisions.")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("shows detail loading and errors independently, retries by GET, and reports empty details", async () => {
    const pending = deferred<unknown>();
    let calls = 0;
    const requests = mount((url) => url.includes("/history/detail") ? ++calls === 1 ? pending.promise : detail(point(), []) : undefined);
    await screen.findByText("Loading historical rates…");
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    await act(async () => pending.resolve(httpError("Detail unavailable")));
    expect(await screen.findByRole("alert")).toHaveTextContent("Detail unavailable");
    await userEvent.setup().click(screen.getByRole("button", { name: "Retry historical rates" }));
    expect(await screen.findByText("No historical rate rows available for this revision.")).toBeInTheDocument();
    expect(requests.every((r) => r.method === "GET")).toBe(true);
  });

  it("handles organization loading, errors, retry and empty results without a history request for an unspecified owner", async () => {
    const pending = deferred<unknown>();
    let calls = 0;
    const requests = mount((url) => url.endsWith("/organizations") ? ++calls === 1 ? pending.promise : { items: [], total: 0 } : undefined);
    await table();
    const user = userEvent.setup();
    await user.selectOptions(screen.getByLabelText("Revision scope"), "organization-external");
    expect(screen.getByLabelText("Revision organization")).toBeDisabled();
    await act(async () => pending.resolve(httpError("Organization list failed")));
    expect(await screen.findByRole("alert")).toHaveTextContent("Organization list failed");
    await user.click(screen.getByRole("button", { name: "Retry organizations" }));
    expect(await screen.findByText("No organizations available.")).toBeInTheDocument();
    expect(requests.filter((r) => r.url.includes("/history?"))).toHaveLength(1);
  });

  it.each(["list", "detail"] as const)("ignores stale %s completion after audience scope changes", async (kind) => {
    const pending = deferred<unknown>();
    mount((url) => url.startsWith("/api/admin/rate-card/history") && (kind === "list" ? !url.includes("/detail") : url.includes("/detail")) ? pending.promise
      : url.includes("/history/detail") ? detail(point("external"), [row("external-only")]) : undefined);
    if (kind === "detail") await screen.findByText("Loading historical rates…");
    const user = userEvent.setup();
    await user.selectOptions(screen.getByLabelText("Revision scope"), "external-default");
    await screen.findByRole("rowheader", { name: /external-only/ });
    await act(async () => pending.resolve(kind === "list" ? { items: [point("stale")], total: 1, next_offset: null } : detail(point("stale"), [row("stale-only")])));
    expect(screen.queryByRole("rowheader", { name: /stale-only/ })).not.toBeInTheDocument();
    expect(within(screen.getByLabelText("Revision to view")).queryByRole("option", { name: /stale/ })).not.toBeInTheDocument();
    expect(screen.getByRole("rowheader", { name: /external-only/ })).toBeInTheDocument();
  });

  it.each(["list", "detail"] as const)("clears the old table immediately and ignores stale organization %s responses", async (kind) => {
    const pending = deferred<unknown>();
    const requests = mount((url) => url.includes("/organizations/org1/") && (kind === "list" ? !url.includes("/detail") : url.includes("/detail")) ? pending.promise
      : url.includes("/organizations/org2/") && url.includes("/detail") ? detail(point("org2"), [row("two-only")]) : undefined);
    const user = userEvent.setup();
    await table();
    await user.selectOptions(screen.getByLabelText("Revision scope"), "organization-external");
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    await screen.findByRole("option", { name: "One · org1" });
    await user.selectOptions(screen.getByLabelText("Revision organization"), "org1");
    await waitFor(() => expect(requests.some((r) => r.url.includes("/organizations/org1/") && (kind === "list" ? !r.url.includes("/detail") : r.url.includes("/detail")))).toBe(true));
    await user.selectOptions(screen.getByLabelText("Revision organization"), "org2");
    await screen.findByRole("rowheader", { name: /two-only/ });
    await act(async () => pending.resolve(kind === "list" ? { items: [point("one-stale")], total: 1, next_offset: null } : detail(point("one-stale"), [row("one-stale")])));
    expect(screen.queryByRole("rowheader", { name: /one-stale/ })).not.toBeInTheDocument();
    expect(screen.getByRole("rowheader", { name: /two-only/ })).toBeInTheDocument();
    expect(requests.every((r) => r.method === "GET")).toBe(true);
  });

  it("ignores out-of-order details when a different revision is selected", async () => {
    const pending = deferred<unknown>();
    mount((url) => url.includes("/history?") ? { items: [point("slow"), point("fast")], total: 2, next_offset: null }
      : url.includes("revision=slow") ? pending.promise : detail(point("fast"), [row("fast-row")]));
    await screen.findByText("Loading historical rates…");
    await userEvent.setup().selectOptions(screen.getByLabelText("Revision to view"), "fast");
    await screen.findByRole("rowheader", { name: /fast-row/ });
    await act(async () => pending.resolve(detail(point("slow"), [row("slow-row")])));
    expect(screen.queryByRole("rowheader", { name: /slow-row/ })).not.toBeInTheDocument();
    expect(screen.getByLabelText("Revision to view")).toHaveValue("fast");
  });
});

describe("revision viewer and mounted editor isolation", () => {
  it("keeps an in-flight save bound to its original organization while other histories are viewed", async () => {
    const saving = deferred<unknown>();
    const requests = mount((_url, init) => init.method === "PUT" ? saving.promise : undefined, true);
    const user = userEvent.setup();
    await screen.findByLabelText("alpha input rate");
    await user.click(screen.getByRole("tab", { name: "External prices" }));
    await screen.findByRole("option", { name: "One" });
    await user.selectOptions(screen.getByLabelText("External price scope"), "org1");
    const input = await screen.findByLabelText("alpha input rate");
    await user.clear(input); await user.type(input, "9");
    await user.click(screen.getByRole("button", { name: "Save 1 change" }));
    await waitFor(() => expect(requests.filter((r) => r.method === "PUT")).toHaveLength(1));
    await user.click(screen.getByRole("tab", { name: "View revisions" }));
    await table();
    await user.selectOptions(screen.getByLabelText("Revision scope"), "organization-external");
    await screen.findByRole("option", { name: "Two · org2" });
    await user.selectOptions(screen.getByLabelText("Revision organization"), "org2");
    await table();
    await act(async () => saving.resolve({ ...current, version: 8, revision: "current-v8", changed: true, items: [{ ...currentRow, input: "9" }] }));
    await user.click(screen.getByRole("tab", { name: "External prices" }));
    expect(screen.getByLabelText("External price scope")).toHaveValue("org1");
    expect(screen.getByLabelText("alpha input rate")).toHaveValue("9");
    expect(screen.getByText(/Version 8/)).toBeInTheDocument();
    const writes = requests.filter((r) => r.method !== "GET");
    expect(writes).toHaveLength(1);
    expect(writes[0]?.url).toBe("/api/admin/organizations/org1/external-rate-card");
    expect(writes[0]?.body).toMatchObject({ expected_version: 7 });
  });

  it.each(["internal", "external-default", "organization-external"] as const)("preserves the %s unsaved draft while viewing a different history scope", async (scope) => {
    const requests = mount(undefined, true);
    const user = userEvent.setup();
    await screen.findByLabelText("alpha input rate");
    if (scope !== "internal") {
      await user.click(screen.getByRole("tab", { name: "External prices" }));
      await screen.findByLabelText("External price scope");
      if (scope === "organization-external") {
        await screen.findByRole("option", { name: "One" });
        await user.selectOptions(screen.getByLabelText("External price scope"), "org1");
      }
    }
    const input = await screen.findByLabelText("alpha input rate");
    await user.clear(input); await user.type(input, "77.00000001");
    await user.click(screen.getByRole("tab", { name: "View revisions" }));
    await table();
    expect(screen.queryByRole("button", { name: /save|restore|reset|load into editor/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Revision scope"), "external-default");
    await table();
    await user.click(screen.getByRole("tab", { name: scope === "internal" ? "Internal costs" : "External prices" }));
    expect(screen.getByLabelText("alpha input rate")).toBe(input);
    expect(input).toHaveValue("77.00000001");
    expect(screen.getByRole("button", { name: "Save 1 change" })).toBeEnabled();
    if (scope !== "internal") expect(screen.getByLabelText("External price scope")).toHaveValue(scope === "organization-external" ? "org1" : "");
    expect(requests.every((r) => r.method === "GET")).toBe(true);
  });

  it("preserves a historical restoration draft and CAS conflict across viewer visits", async () => {
    const requests = mount((_url, init) => init.method === "PUT" ? new Response(JSON.stringify({ detail: "Concurrent pricing revision" }), { status: 409 }) : undefined, true);
    const user = userEvent.setup();
    await screen.findByLabelText("alpha input rate");
    await screen.findByRole("option", { name: /internal v4/ });
    await user.selectOptions(screen.getByLabelText("Historical revision"), "latest");
    await user.click(screen.getByRole("button", { name: "Load into editor" }));
    await waitFor(() => expect(screen.getByLabelText("alpha input rate")).toHaveValue("1.00000001"));
    await user.click(screen.getByRole("button", { name: "Save 1 change" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Concurrent pricing revision");
    const writes = requests.filter((r) => r.method !== "GET");
    expect(writes).toHaveLength(1);
    expect(writes[0]?.body).toMatchObject({ expected_version: 7, reason: expect.stringContaining("Restore prices from internal v4") });
    await user.click(screen.getByRole("tab", { name: "View revisions" }));
    await table();
    await user.click(screen.getByRole("tab", { name: "Internal costs" }));
    expect(screen.getByLabelText("alpha input rate")).toHaveValue("1.00000001");
    expect(screen.getByRole("alert")).toHaveTextContent("Concurrent pricing revision");
    expect(screen.getByText(/Draft copied from internal v4/)).toBeInTheDocument();
    expect(requests.filter((r) => r.method !== "GET")).toHaveLength(1);
  });
});