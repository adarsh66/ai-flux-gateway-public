import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ControlApi } from "./client";
import { SessionProvider } from "./session";
import { PricesPage } from "./pages/admin";
import { validateRates } from "./pages/RateCardEditor";
import type { RateCard, RateCardAutoPricingStatus, RateRow } from "./types";

const row = (model: string, over: Partial<RateRow> = {}): RateRow => ({
  model, provider: "OpenAI", region: "eastus", model_version: "1", sku: "s", origin: "public_list", note: null, source_url: null,
  input: "0.75", output: "4.5", cached: null, write: null, default_input: "0.75", default_output: "4.5", default_cached: null, default_write: null,
  configured_from: null, ...over,
});
const card = (items: RateRow[], version = 0): RateCard => ({ version, revision: "r", currency: "USD", unit: "per_million_tokens", items, total: items.length, changed: false });
const scoringRow = (over: Partial<RateRow> = {}) => row("Decision-1", {
  model_kind: "scoring", billing_dimensions: ["input"], provider: "Microsoft",
  input: "0.042", output: null, cached: null, write: null,
  default_input: "0.042", default_output: null, default_cached: null, default_write: null, ...over,
});
const admin = { organization_id: "o", organization_name: "IDS", tenant_id: "t", object_id: "a", role: "ids_admin" as const };
const config = { clientId: "c", authority: "a", apiScope: "s", controlApiUrl: "/api", gatewayUrl: "https://g/v1" };

function page(handler: (url: string, init: RequestInit) => unknown) {
  const f = (async (url: string, init: RequestInit) => {
    // PricesPage also loads the existing advanced recorded-cost table.
    // Keep those unrelated reads empty, not malformed rate-card fixtures.
    const response = url.endsWith("/admin/rate-card") ? await handler(url, init) : { items: [], total: 0 };
    return response instanceof Response ? response : new Response(JSON.stringify(response), { status: 200 });
  }) as unknown as typeof fetch;
  const api = new ControlApi("/api", async () => "tok", f);
  render(<MemoryRouter><SessionProvider me={admin} api={api} config={config} onSignOut={() => undefined}><PricesPage /></SessionProvider></MemoryRouter>);
}

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("validateRates", () => {
  const c = card([row("a"), row("b", { origin: "platform_default", input: "1", output: "2", default_input: "1", default_output: "2" })]);
  const drafts = (over: Record<string, Partial<{ input: string; output: string; cached: string; write: string }>>) =>
    Object.fromEntries(c.items.map((r) => [r.model, { input: r.input ?? "", output: r.output ?? "", cached: "", write: "", ...over[r.model] }]));

  it("sends only changed rows and trims blank cache rates to null", () => {
    expect(validateRates(c, drafts({ a: { input: " 3 ", cached: "0.3" } }))).toEqual({ ok: true, rates: [{ model: "a", input: "3", output: "4.5", cached: "0.3", write: null }] });
    expect(validateRates(c, drafts({}))).toEqual({ ok: true, rates: [] });
  });

  it.each([{ input: "-1" }, { output: "abc" }, { output: "" }, { input: "" }, { cached: "x" }, { write: "1,5" }])("rejects invalid %j", (bad) => {
    const r = validateRates(c, drafts({ b: bad }));
    expect(r.ok).toBe(false);
  });

  it.each(["1e2", "Infinity", "NaN", "0.123456789", "100001", "1,000"])("rejects non-contract decimals %s", (input) => {
    expect(validateRates(c, drafts({ a: { input } })).ok).toBe(false);
  });

  it("preserves zero and eight decimal places rather than treating them as unknown", () => {
    expect(validateRates(c, drafts({ a: { input: "0", output: "0.00000001" } }))).toMatchObject({ ok: true, rates: [{ input: "0", output: "0.00000001" }] });
  });

  it("accepts input-only scoring without relaxing mandatory chat output", () => {
    expect(validateRates(card([scoringRow(), row("chat")]), {
      "Decision-1": { input: " 0.05 ", output: "", cached: "", write: "" },
      chat: { input: "1", output: "4.5", cached: "", write: "" },
    })).toEqual({ ok: true, rates: [
      { model: "Decision-1", input: "0.05", output: null, cached: null, write: null },
      { model: "chat", input: "1", output: "4.5", cached: null, write: null },
    ] });
    expect(validateRates(card([scoringRow()]), {
      "Decision-1": { input: "0.042", output: "", cached: "", write: "" },
    })).toEqual({ ok: true, rates: [] });
  });

  it.each(["output", "cached", "write"] as const)("rejects a scoring %s rate, including zero", (dimension) => {
    for (const value of ["0", "1"]) {
      const result = validateRates(card([scoringRow()]), {
        "Decision-1": { input: "0.05", output: "", cached: "", write: "", [dimension]: value },
      });
      expect(result.ok).toBe(false);
      if (!result.ok) expect(result.error).toContain("scoring supports input only");
    }
  });

  it.each(["", "-1", "abc"])("rejects invalid scoring input %j", (input) => {
    expect(validateRates(card([scoringRow()]), {
      "Decision-1": { input, output: "", cached: "", write: "" },
    }).ok).toBe(false);
  });
});

describe("Rate card page", () => {
  const pendingLastGood: RateCardAutoPricingStatus = {
    enabled: true, state: "pending", source: "rate-card", access_gated: false,
    desired_revision: "rate-card-v2", applied_revision: "rate-card-v1", stale: true,
    applied_sha256: "a".repeat(64), applied_at: "2026-11-01T01:00:00Z",
    next_attempt_at: "2026-11-01T01:01:00Z",
    error: "Automatic pricing sync pending; last good prices remain active.",
  };

  it.each([
    { name: "last-good", status: pendingLastGood, applied: "rate-card-v1", desired: "rate-card-v2" },
    { name: "packaged-default", status: {
      enabled: true, state: "pending", source: "packaged-default", access_gated: false,
      desired_revision: "rate-card-v2", applied_revision: null, stale: false,
      error: "Automatic pricing sync pending; last good prices remain active.",
    } satisfies RateCardAutoPricingStatus, applied: "Packaged defaults", desired: "rate-card-v2" },
    { name: "after_save exception fallback", status: {
      enabled: true, state: "pending", source: "last-good-or-packaged-default", access_gated: false,
      error: "Rate card saved. Automatic pricing sync will retry.",
    } satisfies RateCardAutoPricingStatus, applied: "Last-good prices or packaged defaults (revision unavailable)", desired: "r" },
  ])("keeps Save successful with $name sync failure, informs fallback and permits another edit", async ({ status, applied, desired }) => {
    const requests: { url: string; method: string }[] = [];
    const saved: unknown[] = [];
    page((url, init) => {
      requests.push({ url, method: init.method ?? "GET" });
      if (init.method === "PUT") {
        saved.push(JSON.parse(init.body as string));
        return { ...card([row("alpha", { input: "5", origin: "configured" })], 2), changed: true, auto_pricing: status };
      }
      return { ...card([row("alpha")], 1), auto_pricing: pendingLastGood };
    });
    const user = userEvent.setup();
    const input = await screen.findByLabelText("alpha input rate");
    await user.clear(input);
    await user.type(input, "5");
    expect(screen.getByRole("button", { name: "Save 1 change" })).toBeEnabled();
    await user.click(screen.getByRole("button", { name: "Save 1 change" }));
    expect(await screen.findByText(/Saved 1 rate change/)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(saved).toHaveLength(1);
    expect(saved[0]).toMatchObject({ expected_version: 1, rates: [{ model: "alpha", input: "5", output: "4.5" }] });
    const notice = screen.getByRole("status", { name: "Auto pricing sync status" });
    expect(notice).toHaveTextContent(`Saved: ${desired}`);
    expect(notice).toHaveTextContent(`Applied: ${applied}`);
    expect(notice).toHaveTextContent("Automatic sync pending");
    expect(notice).toHaveTextContent("Sync retries automatically");
    expect(notice).toHaveTextContent("does not block saving rates, subscriptions, the Playground or API calls");
    expect(notice).toHaveTextContent(status.error!);
    expect(notice).toHaveClass("warn");
    if (status.source === "packaged-default") expect(notice).toHaveTextContent("Estimated defaults remain active");
    if (status.source === "rate-card") expect(notice).toHaveTextContent("Last-good prices remain active");
    expect(screen.queryByRole("button", { name: /retry|approve|reconcile/i })).not.toBeInTheDocument();
    await user.clear(screen.getByLabelText("alpha input rate"));
    await user.type(screen.getByLabelText("alpha input rate"), "6");
    expect(screen.getByRole("button", { name: "Save 1 change" })).toBeEnabled();
    expect(requests.every((request) => request.url === "/api/admin/rate-card" && ["GET", "PUT"].includes(request.method))).toBe(true);
  });

  it("shows packaged defaults without falsely reporting a pending sync", async () => {
    page(() => ({ ...card([row("alpha")]), auto_pricing: {
      enabled: true, state: "default", source: "packaged-default", access_gated: false,
      applied_revision: null, desired_revision: "rate-card-v0", stale: false, error: null,
    } satisfies RateCardAutoPricingStatus }));
    const notice = await screen.findByRole("status", { name: "Auto pricing sync status" });
    expect(notice).toHaveTextContent("Using packaged defaults");
    expect(notice).toHaveTextContent("Estimated defaults remain active");
    expect(notice).not.toHaveTextContent("Automatic sync pending");
  });

  it("reports matching saved and applied revisions normally after Save", async () => {
    page((_url, init) => init.method === "PUT" ? {
      ...card([row("alpha", { input: "5" })], 2), changed: true,
      auto_pricing: { enabled: true, state: "applied", source: "rate-card", access_gated: false,
        desired_revision: "rate-card-v2", applied_revision: "rate-card-v2", stale: false,
        error: null, applied_at: "2026-11-01T01:00:00Z", next_attempt_at: null,
      } satisfies RateCardAutoPricingStatus,
    } : card([row("alpha")], 1));
    const user = userEvent.setup();
    const input = await screen.findByLabelText("alpha input rate");
    await user.clear(input);
    await user.type(input, "5");
    await user.click(screen.getByRole("button", { name: "Save 1 change" }));
    expect(await screen.findByText(/Saved 1 rate change/)).toBeInTheDocument();
    const notice = screen.getByRole("status", { name: "Auto pricing sync status" });
    expect(notice).toHaveTextContent("Saved: rate-card-v2 · Applied: rate-card-v2 · In sync");
    expect(notice).toHaveTextContent("Applied at:");
    expect(notice).toHaveClass("ok");
    expect(notice).not.toHaveTextContent("pending");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it.each([undefined, null, { ...pendingLastGood, enabled: false }])("preserves legacy/disabled status responses (%j)", async (auto_pricing) => {
    page(() => ({ ...card([row("alpha")]), auto_pricing }));
    expect(await screen.findByLabelText("alpha input rate")).toBeEnabled();
    expect(screen.queryByRole("status", { name: "Auto pricing sync status" })).not.toBeInTheDocument();
  });

  it("keeps actual Save rejection an error and preserves drafts rather than claiming success", async () => {
    page((_url, init) => init.method === "PUT"
      ? new Response(JSON.stringify({ detail: "Rate card changed; reload before saving." }), { status: 409 })
      : { ...card([row("alpha")], 1), auto_pricing: pendingLastGood });
    const user = userEvent.setup();
    const input = await screen.findByLabelText("alpha input rate");
    await user.clear(input);
    await user.type(input, "5");
    await user.click(screen.getByRole("button", { name: "Save 1 change" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Rate card changed; reload before saving.");
    expect(screen.queryByText(/Saved 1 rate change/)).not.toBeInTheDocument();
    expect(input).toHaveValue("5");
    expect(screen.getByRole("button", { name: "Save 1 change" })).toBeEnabled();
  });

  it("reloads the latest internal version only after discard confirmation and preserves drafts on reload failure", async () => {
    let reads = 0;
    page((_url, init) => {
      if (init.method === "PUT") return new Response(JSON.stringify({ detail: "Rate card changed; reload before saving." }), { status: 409 });
      reads++;
      if (reads === 2) return new Response(JSON.stringify({ detail: "Reload temporarily unavailable" }), { status: 503 });
      return card([row("alpha", { input: reads === 1 ? "0.75" : "7" })], reads === 1 ? 1 : 3);
    });
    const user = userEvent.setup();
    const input = await screen.findByLabelText("alpha input rate");
    await user.clear(input); await user.type(input, "5");
    await user.click(screen.getByRole("button", { name: "Save 1 change" }));
    await screen.findByRole("alert");
    await user.click(screen.getByRole("button", { name: "Reload latest" }));
    expect(screen.getByRole("dialog", { name: "Reload latest rates?" })).toBeInTheDocument();
    expect(input).toHaveValue("5");
    expect(reads).toBe(1);
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(input).toHaveValue("5");
    await user.click(screen.getByRole("button", { name: "Reload latest" }));
    await user.click(screen.getByRole("button", { name: "Discard changes and reload" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Reload temporarily unavailable");
    expect(input).toHaveValue("5");
    expect(screen.getByRole("button", { name: "Save 1 change" })).toBeEnabled();
    await user.click(screen.getByRole("button", { name: "Reload latest" }));
    await user.click(screen.getByRole("button", { name: "Discard changes and reload" }));
    await waitFor(() => expect(screen.getByLabelText("alpha input rate")).toHaveValue("7"));
    expect(screen.getByText(/Version 3/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByText(/Saved 1 rate change/)).not.toBeInTheDocument();
  });

  it("refreshes only informational status, retains drafts on success/failure, and stops polling on unmount", async () => {
    const interval = vi.spyOn(globalThis, "setInterval");
    const clear = vi.spyOn(globalThis, "clearInterval");
    let reads = 0;
    page(() => {
      reads++;
      if (reads === 3) throw new Error("Status temporarily unavailable");
      return { ...card([row("alpha", { input: reads === 1 ? "0.75" : "99" })], reads), auto_pricing: reads === 1
        ? pendingLastGood : { ...pendingLastGood, state: "applied", stale: false, applied_revision: "rate-card-v2", error: null, next_attempt_at: null } };
    });
    const user = userEvent.setup();
    const input = await screen.findByLabelText("alpha input rate");
    await user.clear(input);
    await user.type(input, "6");
    const tick = interval.mock.calls.find((call) => call[1] === 15000)?.[0];
    expect(typeof tick).toBe("function");
    await act(async () => { if (typeof tick === "function") tick(); });
    expect(reads).toBe(2);
    expect(screen.getByRole("status", { name: "Auto pricing sync status" })).toHaveTextContent("In sync");
    expect(input).toHaveValue("6");
    expect(screen.getByText(/Version 1/)).toBeInTheDocument();
    await act(async () => { if (typeof tick === "function") tick(); });
    expect(reads).toBe(3);
    expect(input).toHaveValue("6");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByRole("status", { name: "Auto pricing sync status" })).toHaveTextContent("In sync");
    expect(screen.getByRole("button", { name: "Save 1 change" })).toBeEnabled();
    cleanup();
    const pollIndex = interval.mock.calls.findIndex((call) => call[1] === 15000);
    expect(clear).toHaveBeenCalledWith(interval.mock.results[pollIndex]?.value);
  });

  it("edits only scoring input, saves null non-billable dimensions with version, and resets defaults", async () => {
    const saved: unknown[] = [];
    const scoring = scoringRow({ origin: "configured", input: "0.06" });
    page((url, init) => {
      if (url.endsWith("/admin/rate-card") && init.method === "PUT") {
        saved.push(JSON.parse(init.body as string));
        return { ...card([scoringRow({ origin: "configured", input: "0.05" })], 8), changed: true };
      }
      return url.endsWith("/admin/rate-card") ? card([scoring], 7) : { items: [], total: 0 };
    });
    const user = userEvent.setup();
    const input = await screen.findByLabelText("Decision-1 input rate");
    expect(input).not.toBeDisabled();
    for (const label of ["output", "cached input", "cache write"]) {
      expect(screen.getByLabelText(`Decision-1 ${label} rate`)).toBeDisabled();
      expect(screen.getByLabelText(`Decision-1 ${label} rate`)).toHaveValue("N/A");
    }
    await user.click(screen.getByRole("button", { name: "Reset" }));
    expect(input).toHaveValue("0.042");
    await user.clear(input);
    await user.type(input, "0.05");
    await user.click(screen.getByRole("button", { name: "Save 1 change" }));
    await waitFor(() => expect(saved).toHaveLength(1));
    expect(saved[0]).toMatchObject({ expected_version: 7, rates: [
      { model: "Decision-1", input: "0.05", output: null, cached: null, write: null },
    ] });
    expect(await screen.findByText(/Saved 1 rate change/)).toBeInTheDocument();
    expect(screen.getByText("Configured")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Restore all defaults" }));
    expect(screen.getByLabelText("Decision-1 input rate")).toHaveValue("0.042");
    expect(screen.getByLabelText("Decision-1 output rate")).toHaveValue("N/A");
  });

  it("edits many models and saves in one request with the version guard", async () => {
    const saved: unknown[] = [];
    const items = [row("alpha"), row("beta", { origin: "platform_default", provider: "Fireworks", input: "0.9", output: "0.9", default_input: "0.9", default_output: "0.9" })];
    page((url, init) => {
      if (url.endsWith("/admin/rate-card") && init.method === "PUT") {
        saved.push(JSON.parse(init.body as string));
        return { ...card(items.map((r) => ({ ...r, input: "5", origin: "configured" as const })), 1), changed: true } satisfies RateCard;
      }
      if (url.endsWith("/admin/rate-card")) return card(items);
      return { items: [], total: 0 };
    });
    const user = userEvent.setup();
    expect(await screen.findByText("Estimated default")).toBeInTheDocument();
    await user.clear(screen.getByLabelText("alpha input rate"));
    await user.type(screen.getByLabelText("alpha input rate"), "5");
    await user.clear(screen.getByLabelText("beta input rate"));
    await user.type(screen.getByLabelText("beta input rate"), "5");
    await user.click(screen.getByRole("button", { name: "Save 2 changes" }));
    await waitFor(() => expect(saved).toHaveLength(1));
    expect(saved[0]).toMatchObject({ expected_version: 0, rates: [{ model: "alpha", input: "5", output: "4.5" }, { model: "beta", input: "5", output: "0.9" }] });
    expect(await screen.findByText(/Saved 2 rate change/)).toBeInTheDocument();
  });

  it("blocks an invalid rate locally and can restore defaults", async () => {
    page((url) => (url.endsWith("/admin/rate-card") ? card([row("alpha")]) : { items: [], total: 0 }));
    const user = userEvent.setup();
    const input = await screen.findByLabelText("alpha input rate");
    await user.clear(input);
    await user.type(input, "-2");
    await user.click(screen.getByRole("button", { name: "Save 1 change" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/non-negative decimals/);
    await user.click(screen.getByRole("button", { name: "Restore all defaults" }));
    expect(screen.getByLabelText("alpha input rate")).toHaveValue("0.75");
    expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();
  });
});
