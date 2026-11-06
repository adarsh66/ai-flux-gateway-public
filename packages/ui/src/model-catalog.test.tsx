import type { ReactNode } from "react";
import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { ControlApi } from "./client";
import { SessionProvider } from "./session";
import { ModelsPage } from "./pages/ModelsPage";
import { ModelGardenPage } from "./pages/TokenExchangePages";

const internal = { input: "991.123", output: "992.456", currency: "USD", status: "configured" };
const chat = (id: string, extra = {}) => ({ id, provider: "OpenAI", enabled: true, capabilities: ["chat"], max_completion_tokens: 4096, ...extra });
const garden = (id: string, extra = {}) => ({ ...chat(id), display_name: id, vendor: "OpenAI", region: "eastus", coming_soon: false, description: "PRIVATE OPERATIONAL DIAGNOSTICS", display_price: internal, ...extra });
const row = (model: string, extra = {}) => ({ model, provider: "OpenAI", region: "eastus", model_version: "1", sku: "standard", origin: "configured", input: "7.12345678", output: "8.25", cached: "0", write: "1.50", ...extra });
const card = (items: unknown[]) => ({ version: 4, revision: "external-default:4", currency: "USD", unit: "per_million_tokens", items, total: items.length });

function setup(handler: (url: URL) => unknown | Promise<unknown>, node: ReactNode = <ModelsPage admin />) {
  const calls: { url: URL; method: string }[] = [];
  const api = new ControlApi("/api", async () => "test-token", async (input, init = {}) => {
    const url = new URL(String(input), "https://portal");
    calls.push({ url, method: init.method ?? "GET" });
    if (url.pathname === "/api/model-deployments") return new Response(JSON.stringify({ items: [], verified_at: "fixture" }));
    const data = await handler(url);
    return data instanceof Response ? data : new Response(JSON.stringify(data));
  });
  render(<MemoryRouter><SessionProvider api={api} me={{ organization_id: "org-sentinel", organization_name: "IDS", tenant_id: "t", object_id: "a", role: "ids_admin" }} config={{ clientId: "c", authority: "a", apiScope: "s", controlApiUrl: "/api", gatewayUrl: "https://gateway/v1" }} onSignOut={() => undefined}>{node}</SessionProvider></MemoryRouter>);
  return calls;
}

function handler(rates: unknown = card([row("gpt-5.6-luna")])) {
  return (url: URL) => {
    if (url.pathname === "/api/models") return { items: [chat("gpt-5.6-luna")] };
    if (url.pathname === "/api/admin/model-garden" || url.pathname === "/api/model-garden") return { items: [garden("gpt-5.6-luna")] };
    if (url.pathname === "/api/admin/external-rate-card") return rates;
    if (url.pathname.includes("/organizations/")) return card([row("gpt-5.6-luna", { input: "777.999" })]);
    throw new Error(`Unexpected request ${url.pathname}`);
  };
}

describe("external-default admin catalog", () => {
  it("preserves published context metadata without exposing operational descriptions", async () => {
    const base = handler();
    setup(url => url.pathname === "/api/admin/model-garden"
      ? { items: [garden("gpt-5.6-luna", { context_window: 128000 })] } : base(url));
    const list = await screen.findByRole("list", { name: "Model availability" });
    expect(list).toHaveTextContent("128,000 / 4,096");
    expect(list).not.toHaveTextContent("PRIVATE OPERATIONAL DIAGNOSTICS");
  });

  it.each(["loading", "missing", "failed"])("keeps scoring non-billing dimensions N/A with %s prices", async (state) => {
    const pending = new Promise<unknown>(() => undefined);
    setup(url => {
      if (url.pathname === "/api/models") return { items: [] };
      if (url.pathname === "/api/model-garden") return { items: [] };
      if (url.pathname === "/api/admin/model-garden") return { items: [garden("Decision-1", { model_kind: "scoring" })] };
      if (url.pathname === "/api/admin/external-rate-card") return state === "loading" ? pending : state === "failed" ? new Response('{"detail":"Unavailable"}', { status: 503 }) : card([]);
      throw new Error("Unexpected request");
    });
    const list = await screen.findByRole("list", { name: "Model availability" });
    if (state === "failed") expect(await screen.findByRole("alert")).toHaveTextContent("External default prices unavailable. Missing prices are not free; no internal or organization prices substituted.");
    await waitFor(() => expect(within(list).getAllByText("N/A")).toHaveLength(3));
    await within(list).findByText(state === "loading" ? "Loading…" : "Unavailable — not free");
  });

  it("uses external defaults instead of conflicting internal/org rates and shows all four exact dimensions plus SVG artwork", async () => {
    const calls = setup(handler());
    const list = await screen.findByRole("list", { name: "Model availability" });
    await within(list).findByText("USD 7.12345678");
    expect(within(list).getByText("USD 8.25")).toBeInTheDocument();
    expect(within(list).getByText("USD 0")).toBeInTheDocument();
    expect(within(list).getByText("USD 1.50")).toBeInTheDocument();
    expect(within(list).getByText("Cache write / 1M tokens")).toBeInTheDocument();
    expect(list.querySelector(".vendor-mark svg")).toHaveAttribute("aria-hidden", "true");
    expect(list).toHaveTextContent("estimates, not invoice amounts");
    expect(list).toHaveTextContent("An OpenAI chat model for drafting content");
    expect(list).not.toHaveTextContent(/991.123|992.456|777.999|PRIVATE OPERATIONAL/);
    expect(calls.filter(c => c.url.pathname === "/api/admin/external-rate-card")).toHaveLength(1);
    expect(calls.every(c => c.method === "GET" && !c.url.search && !c.url.pathname.includes("/organizations/"))).toBe(true);
    expect(screen.queryByRole("link", { name: /Playground/ })).not.toBeInTheDocument();
  });

  it("preserves eligible chats, excludes disabled/placeholder/nonchat/Decision-1, and separates scoring with input-only N/A", async () => {
    const models = [chat("gpt-5.6-luna"), chat("disabled", { enabled: false }), chat("placeholder", { placeholder: true }), chat("embedding", { capabilities: ["embeddings"] }), chat("Decision-1")];
    setup(url => {
      if (url.pathname === "/api/models") return { items: models };
      if (url.pathname === "/api/admin/model-garden") return { items: [garden("gpt-5.6-luna"), garden("Decision-1", { vendor: "Microsoft", model_kind: "scoring", scoring_available: null, capabilities: ["routing-only"] })] };
      if (url.pathname === "/api/admin/external-rate-card") return card([row("gpt-5.6-luna"), row("Decision-1", { model_kind: "scoring", billing_dimensions: ["input"], input: "0", output: null, cached: null, write: null })]);
      throw new Error("Unexpected request");
    });
    const list = await screen.findByRole("list", { name: "Model availability" });
    await waitFor(() => expect(within(list).getAllByText("USD 0")).toHaveLength(2));
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    const scorer = within(list).getByRole("heading", { name: "Microsoft Decision-1" }).closest("li")!;
    expect(within(scorer).getAllByText("N/A")).toHaveLength(3);
    expect(scorer).toHaveTextContent("Scoring availability unknown");
    expect(scorer).toHaveTextContent("not a completion endpoint");
    expect(within(scorer).queryByRole("link")).not.toBeInTheDocument();
  });

  it.each([
    ["missing", []],
    ["similar alias", [row("GPT-5.6-LUNA"), row("gpt-5.6-luna-preview")]],
    ["ambiguous identity", [row("gpt-5.6-luna"), row("gpt-5.6-luna", { region: "westus" })]],
    ["wrong model kind", [row("gpt-5.6-luna", { model_kind: "scoring" })]],
  ])("never substitutes internal prices for %s external rates", async (_label, rows) => {
    setup(handler(card(rows as unknown[])));
    const list = await screen.findByRole("list", { name: "Model availability" });
    await waitFor(() => expect(within(list).getAllByText("Unavailable — not free")).toHaveLength(4));
    expect(list).not.toHaveTextContent(/991.123|992.456|7.12345678/);
  });

  it("distinguishes known zero from nullable unknown cache/write rates", async () => {
    setup(handler(card([row("gpt-5.6-luna", { input: "0", output: null, cached: null, write: null })])));
    const list = await screen.findByRole("list", { name: "Model availability" });
    await within(list).findByText("USD 0");
    expect(within(list).getAllByText("Unknown — not free")).toHaveLength(3);
    expect(within(list).queryByText("N/A")).not.toBeInTheDocument();
  });

  it("keeps catalog cards while default rates are loading, never flashing internal prices", async () => {
    let resolve!: (value: unknown) => void;
    const pending = new Promise<unknown>(done => { resolve = done; });
    const base = handler();
    setup(url => url.pathname === "/api/admin/external-rate-card" ? pending : base(url));
    const list = await screen.findByRole("list", { name: "Model availability" });
    expect(within(list).getAllByText("Loading…")).toHaveLength(4);
    expect(list).not.toHaveTextContent("991.123");
    resolve(card([row("gpt-5.6-luna")]));
    await within(list).findByText("USD 7.12345678");
  });

  it("keeps cards visible on fetch failure with no fallback and a default-only retry", async () => {
    let attempts = 0;
    const base = handler();
    const calls = setup(url => url.pathname === "/api/admin/external-rate-card" && ++attempts === 1 ? new Response('{"detail":"Unavailable"}', { status: 503 }) : base(url));
    await screen.findByRole("alert");
    const list = await screen.findByRole("list", { name: "Model availability" });
    expect(within(list).getAllByText("Unavailable — not free")).toHaveLength(4);
    expect(list).not.toHaveTextContent("991.123");
    await userEvent.click(screen.getByRole("button", { name: "Retry external default prices" }));
    await within(list).findByText("USD 7.12345678");
    expect(calls.filter(c => c.url.pathname === "/api/admin/external-rate-card")).toHaveLength(2);
    expect(calls.every(c => c.method === "GET")).toBe(true);
  });

  it("shows generic vendor artwork without a new dependency", async () => {
    const base = handler();
    setup(url => url.pathname === "/api/admin/model-garden" ? { items: [garden("gpt-5.6-luna", { vendor: "Unrecognized vendor" })] } : base(url));
    const list = await screen.findByRole("list", { name: "Model availability" });
    expect(list.querySelector(".vendor-mark svg circle")).not.toBeNull();
    expect(list).toHaveTextContent("Unrecognized vendor");
  });

  it("preserves the non-admin ModelsPage data source without requesting admin defaults", async () => {
    const calls = setup(handler(), <ModelsPage />);
    const list = await screen.findByRole("list", { name: "Model availability" });
    expect(list).toHaveTextContent("input 991.123");
    expect(calls.some(c => c.url.pathname.startsWith("/api/admin/"))).toBe(false);
  });

  it("preserves customer garden copy, pricing, vendor SVG and Playground link", async () => {
    const calls = setup(handler(), <ModelGardenPage />);
    const list = await screen.findByRole("list", { name: "Model pricing cards" });
    expect(list).toHaveTextContent("USD 991.123");
    expect(list.querySelector(".vendor-mark svg")).not.toBeNull();
    expect(within(list).getByRole("link", { name: /Try in Playground/ })).toHaveAttribute("href", "/playground?model=gpt-5.6-luna");
    expect(calls.some(c => c.url.pathname.startsWith("/api/admin/"))).toBe(false);
  });
});