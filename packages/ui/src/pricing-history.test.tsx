import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { ControlApi } from "./client";
import { SessionProvider } from "./session";
import { RateCardEditor, historicalDraft, validateExternalRates } from "./pages/RateCardEditor";
import type { HistoricalRateRow, PricingHistoryDetail, PricingHistoryPoint, RateCard, RateRow } from "./types";

const row = (model: string, extra: Partial<RateRow> = {}): RateRow => ({ model, provider: "OpenAI", region: "eastus", model_version: "1", sku: "s", model_kind: "chat", billing_dimensions: ["input", "output"], origin: "configured", note: null, source_url: null, input: "8", output: "12", cached: null, write: null, default_input: "8", default_output: "12", default_cached: null, default_write: null, configured_from: null, ...extra });
const card = (items = [row("alpha")], version = 4): RateCard => ({ items, version, revision: `current-v${version}`, total: items.length, changed: false, currency: "USD", unit: "per_million_tokens", auto_pricing: { enabled: true, state: "pending", source: "rate-card", desired_revision: "current-v4", applied_revision: "current-v3", stale: true, access_gated: false } });
const point = (id = "i1"): PricingHistoryPoint => ({ id, source: "internal", effective_at: "2026-10-30T00:00:00Z", reason: "Old prices", internal_version: 1, default_version: null, organization_version: null, simultaneous: false });
const historic = (extra: Partial<HistoricalRateRow> = {}): HistoricalRateRow => ({ model: "alpha", canonical_model: "alpha", provider: "OpenAI", region: "eastus", model_version: "1", sku: "s", model_kind: "chat", billing_dimensions: ["input", "output"], state: "known", input: "2", output: "3", cached: "0", write: null, note: null, ...extra });
const detail = (items = [historic()]): PricingHistoryDetail => ({ source: point(), items, skipped: [], current_version: 4, requires_acknowledgement: false });
const admin = { organization_id: "o", organization_name: "IDS", tenant_id: "t", object_id: "a", role: "ids_admin" as const };
const config = { clientId: "c", authority: "a", apiScope: "s", controlApiUrl: "/api", gatewayUrl: "https://g/v1" };
type Handler = (url: string, init: RequestInit) => unknown | Promise<unknown>;
function page(handler: Handler = () => undefined) {
  const requests: { url: string; method: string; body?: unknown }[] = [];
  const fetcher = (async (url: string, init: RequestInit) => {
    requests.push({ url, method: init.method ?? "GET", body: init.body ? JSON.parse(init.body as string) : undefined });
    const body = await handler(url, init) ?? (url.includes("/history/detail") ? detail() : url.includes("/history") ? { items: [point()], total: 1, next_offset: null } : url.endsWith("/organizations") ? { items: [{ id: "org1", name: "One" }, { id: "org2", name: "Two" }], total: 2 } : card());
    return body instanceof Response ? body : new Response(JSON.stringify(body), { status: 200 });
  }) as unknown as typeof fetch;
  const api = new ControlApi("/api", async () => "tok", fetcher);
  render(<SessionProvider me={admin} api={api} config={config} onSignOut={() => undefined}><RateCardEditor /></SessionProvider>);
  return requests;
}
afterEach(cleanup);

async function selectHistory(user: ReturnType<typeof userEvent.setup>, id = "i1") {
  // The current card and history list are independent GETs. Wait for the
  // actual option, not merely the already-mounted card/select control.
  await waitFor(() => expect(screen.getAllByRole("option").some((option) => (option as HTMLOptionElement).value === id)).toBe(true));
  await user.selectOptions(screen.getByLabelText("Historical revision"), id);
}

describe("historical canonical drafts", () => {
  it("sets inherited numerically-equal external values explicitly, preserves unknown and nullable caches", () => {
    const current = card([row("alpha", { input: "2", output: "3", cached: "0", note: "Inherited external default" }), row("unknown")]);
    const loaded = historicalDraft(current, detail([historic(), historic({ model: "unknown", canonical_model: "unknown", state: "unknown", input: null, output: null, cached: null })]), true);
    expect(loaded.operations).toEqual({ alpha: "set", unknown: "unknown" });
    expect(validateExternalRates(current, loaded.drafts, loaded.operations, true)).toEqual({ ok: true, rates: [
      { model: "alpha", operation: "set", input: "2", output: "3", cached: "0", write: null }, { model: "unknown", operation: "unknown" },
    ] });
  });
  it.each(["provider", "region", "model_version", "sku", "model_kind"] as const)("skips changed %s identity and new/retired rows without changing current values", (key) => {
    const loaded = historicalDraft(card([row("alpha"), row("new")]), detail([historic({ [key]: key === "model_kind" ? "scoring" : "changed" }), historic({ model: "retired" })]), true);
    expect(loaded.loaded).toBe(0);
    expect(loaded.operations).toEqual({});
    expect(loaded.drafts.alpha?.input).toBe("8");
    expect(loaded.drafts.new?.input).toBe("8");
    expect(loaded.skipped.length).toBe(3);
  });
  it("preserves scoring input only and measured zero", () => {
    const score = row("alpha", { model_kind: "scoring", billing_dimensions: ["input"], output: null });
    const loaded = historicalDraft(card([score]), detail([historic({ model_kind: "scoring", billing_dimensions: ["input"], input: "0", output: null, cached: null })]), false);
    expect(loaded.loaded).toBe(1);
    expect(loaded.drafts.alpha).toEqual({ input: "0", output: "", cached: "", write: "" });
  });
});

describe("history editor", () => {
  it("loads by GET only, uses latest current CAS on explicit Save and preserves current full status after table", async () => {
    let heads = 0;
    const requests = page((url, init) => {
      if (init.method === "PUT") return { ...card([row("alpha", { input: "2" })], 10), changed: true };
      if (url.endsWith("/rate-card")) return card(undefined, ++heads === 1 ? 4 : 9);
      return undefined;
    });
    const user = userEvent.setup();
    await screen.findByLabelText("alpha input rate");
    await selectHistory(user);
    expect(screen.getByLabelText("alpha input rate")).toHaveValue("8");
    await user.click(screen.getByRole("button", { name: "Load into editor" }));
    await waitFor(() => expect(screen.getByLabelText("alpha input rate")).toHaveValue("2"));
    expect(requests.every((r) => r.method === "GET")).toBe(true);
    expect(screen.getByText(/Version 9/)).toBeInTheDocument();
    const table = screen.getByRole("table");
    const status = screen.getByRole("status", { name: "Auto pricing sync status" });
    expect(table.compareDocumentPosition(status) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(status).toHaveTextContent("Saved: current-v4 · Applied: current-v3");
    expect(status).toHaveTextContent("Missing rates are not free");
    await user.click(screen.getByRole("button", { name: "Save 1 change" }));
    await waitFor(() => expect(requests.filter((r) => r.method === "PUT")).toHaveLength(1));
    expect(requests.find((r) => r.method === "PUT")?.body).toMatchObject({ expected_version: 9, reason: expect.stringContaining("Restore prices from internal v1") });
    await screen.findByText(/Saved 1 rate change/);
    expect(screen.getByLabelText("Historical revision")).toHaveValue("");
  });
  it("dirty replacement cancellation and failed GET preserve all unsaved edits", async () => {
    const requests = page((url) => url.includes("/history/detail") ? new Response(JSON.stringify({ detail: "Historical source unavailable" }), { status: 409 }) : undefined);
    const user = userEvent.setup();
    const input = await screen.findByLabelText("alpha input rate");
    await user.clear(input); await user.type(input, "77");
    await selectHistory(user);
    await user.click(screen.getByRole("button", { name: "Load into editor" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(input).toHaveValue("77");
    expect(requests.some((r) => r.url.includes("/history/detail"))).toBe(false);
    await user.click(screen.getByRole("button", { name: "Load into editor" }));
    await user.click(screen.getByRole("button", { name: "Replace draft" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Historical source unavailable");
    expect(input).toHaveValue("77");
    expect(requests.every((r) => r.method === "GET")).toBe(true);
  });
  it("requires explicit partial acknowledgement and all-unavailable never replaces editor", async () => {
    page((url) => url.endsWith("/rate-card") ? card([row("alpha"), row("new")]) : undefined);
    const user = userEvent.setup();
    await screen.findByLabelText("alpha input rate");
    await selectHistory(user);
    await user.click(screen.getByRole("button", { name: "Load into editor" }));
    await screen.findByRole("dialog", { name: "Acknowledge skipped historical rows" });
    expect(screen.getByLabelText("alpha input rate")).toHaveValue("8");
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByLabelText("alpha input rate")).toHaveValue("8");
    await user.click(screen.getByRole("button", { name: "Load into editor" }));
    await user.click(await screen.findByRole("button", { name: "Acknowledge skipped rows and load draft" }));
    expect(screen.getByLabelText("alpha input rate")).toHaveValue("2");
    expect(screen.getByLabelText("new input rate")).toHaveValue("8");
    cleanup();
    page((url) => url.includes("/history/detail") ? detail([historic({ state: "unavailable", model_version: null })]) : undefined);
    await screen.findByLabelText("alpha input rate");
    await selectHistory(user);
    await user.click(screen.getByRole("button", { name: "Load into editor" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("No reconstructible");
    expect(screen.getByLabelText("alpha input rate")).toHaveValue("8");
  });
  it("pagination and save conflict retain historical source/draft/current baseline", async () => {
    const requests = page((url, init) => init.method === "PUT" ? new Response(JSON.stringify({ detail: "Prices changed; refresh" }), { status: 409 }) : url.includes("/history?") ? url.includes("offset=1") ? { items: [point("i2")], total: 2, next_offset: null } : { items: [point()], total: 2, next_offset: 1 } : undefined);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Load more revisions" }));
    await waitFor(() => expect(screen.getAllByRole("option")).toHaveLength(3));
    await selectHistory(user);
    await user.click(screen.getByRole("button", { name: "Load into editor" }));
    await waitFor(() => expect(screen.getByLabelText("alpha input rate")).toHaveValue("2"));
    await user.click(screen.getByRole("button", { name: "Save 1 change" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Prices changed");
    expect(screen.getByLabelText("alpha input rate")).toHaveValue("2");
    expect(screen.getByText(/Draft copied from internal v1/)).toBeInTheDocument();
    expect(requests.filter((r) => r.method === "PUT")).toHaveLength(1);
  });
  it("ignores out-of-order historical loads after scope switch", async () => {
    let resolve!: (value: unknown) => void;
    const requests = page((url) => url.includes("/history/detail") ? new Promise((r) => { resolve = r; }) : undefined);
    const user = userEvent.setup();
    await screen.findByLabelText("alpha input rate");
    await selectHistory(user);
    await user.click(screen.getByRole("button", { name: "Load into editor" }));
    await user.click(screen.getByRole("tab", { name: "External prices" }));
    await user.click(screen.getByRole("button", { name: "Discard changes" }));
    await screen.findByLabelText("External price scope");
    await act(async () => resolve(detail()));
    await waitFor(() => expect(screen.getByLabelText("alpha input rate")).toHaveValue("8"));
    expect(screen.queryByText(/Draft copied/)).not.toBeInTheDocument();
    expect(requests.every((r) => r.method === "GET")).toBe(true);
  });
});