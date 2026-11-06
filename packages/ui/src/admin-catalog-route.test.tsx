import type { ReactNode } from "react";
import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ControlApi } from "./client";
import { SessionProvider } from "./session";

const root = vi.hoisted(() => ({ tree: null as unknown }));
vi.mock("react-dom/client", () => ({ createRoot: () => ({ render: (tree: unknown) => { root.tree = tree; } }) }));
vi.mock("@aiflux/ui", async (original) => {
  const actual = await original<typeof import("./index")>();
  const { Outlet, Link } = await import("react-router-dom");
  return {
    ...actual,
    AuthGate: ({ children }: { children: ReactNode }) => <>{children}</>,
    Shell: ({ nav }: { nav: { to: string; label: string }[] }) => <><nav>{nav.map(n => <Link key={n.to} to={n.to}>{n.label}</Link>)}</nav><main><Outlet /></main></>,
    AdminBudgetsAndFinOpsPage: () => <h1>Budget wildcard destination</h1>,
  };
});

const chat = Array.from({ length: 22 }, (_, i) => ({ id: `chat-${i + 1}`, provider: "test", enabled: true, placeholder: false, capabilities: ["chat"] }));
const scorer = { id: "Decision-1", display_name: "Microsoft Decision-1", provider: "microsoft", model_kind: "scoring", capabilities: ["routing-only"], scoring_available: true };
const price = { input: "0.4", output: "1.6", status: "configured", checked_at: "2026-11-02", billing_dimensions: ["input", "output"] };

async function mount(path: string) {
  history.replaceState(null, "", `/admin${path}`);
  document.body.innerHTML = '<div id="root"></div>';
  await import("../../../apps/admin-portal/src/main");
  const calls: { path: string; method: string }[] = [];
  const api = new ControlApi("/api", async () => "test-token", async (input, init = {}) => {
    const path = new URL(String(input), "https://portal").pathname;
    calls.push({ path, method: init.method ?? "GET" });
    if (path === "/api/admin/auto-routing") return new Response('{"detail":"Not Found"}', { status: 404 });
    let data: unknown;
    if (path === "/api/models") data = { items: [...chat, { ...scorer, enabled: true }], total: 23 };
    else if (path === "/api/admin/model-garden") data = { items: [...chat.map(m => ({ ...m, display_price: price })), { ...scorer, display_price: { ...price, output: null, billing_dimensions: ["input"] } }], total: 23 };
    else if (path === "/api/admin/external-rate-card") data = { version: 1, revision: "external-default:1", currency: "USD", unit: "per_million_tokens", items: [...chat.map(m => ({ model: m.id, input: "8.25", output: "16.50", cached: "0", write: "2.5", origin: "configured" })), { model: "Decision-1", model_kind: "scoring", billing_dimensions: ["input"], input: "0.12", origin: "configured" }] };
    else if (path === "/api/model-deployments") data = { items: [], verified_at: "fixture" };
    else if (path === "/api/model-garden") data = { items: [], total: 0 };
    else if (path === "/api/auto-routing/availability") data = { ready: true, profiles: ["balanced", "cost", "quality"], architecture: "gateway-direct", runtime_verified: false };
    else throw new Error(`Unexpected catalog request ${path}`);
    return new Response(JSON.stringify(data), { status: 200 });
  });
  render(<SessionProvider me={{ organization_id: "org", organization_name: "IDS", tenant_id: "tenant", object_id: "admin", role: "ids_admin" }} api={api} config={{ clientId: "c", authority: "a", apiScope: "s", controlApiUrl: "/api", gatewayUrl: "https://gateway/v1" }} onSignOut={() => undefined}>{root.tree as ReactNode}</SessionProvider>);
  return calls;
}

describe("actual admin entrypoint catalog routing", () => {
  it("binds /admin/models to the existing admin ModelsPage, not the budget wildcard", async () => {
    const calls = await mount("/models");
    const catalog = await screen.findByRole("list", { name: "Model availability" });
    expect(within(catalog).getAllByRole("listitem")).toHaveLength(23);
    expect(within(catalog).getAllByRole("heading", { level: 2 })).toHaveLength(23);
    expect(within(catalog).getByRole("heading", { name: "Microsoft Decision-1" })).toBeInTheDocument();
    expect(within(catalog).getAllByText(/External default prices · USD per 1M/)).toHaveLength(23);
    expect(within(catalog).queryByText(/Internal estimated costs/)).not.toBeInTheDocument();
    expect(calls.some(c => c.path === "/api/admin/external-rate-card")).toBe(true);
    expect(screen.queryByText("Budget wildcard destination")).not.toBeInTheDocument();
    expect(location.pathname).toBe("/admin/models");
    expect(calls.some(c => c.path === "/api/admin/model-garden")).toBe(true);
    expect(calls.some(c => c.path === "/api/models")).toBe(true);
    expect(calls.every(c => c.method === "GET")).toBe(true);
    expect(screen.queryByRole("button", { name: /save|initialize|reset/i })).not.toBeInTheDocument();
    expect(screen.getByRole("navigation")).toHaveTextContent("Model catalog");
  });

  it("follows the real availability fallback link to a read-only catalog without Not Found", async () => {
    const calls = await mount("/model-router");
    const status = await screen.findByRole("region", { name: "Auto routing availability" });
    await userEvent.click(within(status).getByRole("link", { name: "Model catalog" }));
    expect(await screen.findByRole("list", { name: "Model availability" })).toBeInTheDocument();
    expect(location.pathname).toBe("/admin/models");
    expect(screen.queryByText(/Something needs attention|Not Found|Budget wildcard destination/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /save|initialize|reset/i })).not.toBeInTheDocument();
    expect(calls.every(c => c.method === "GET")).toBe(true);
  });

  it("preserves the existing unknown-route budget redirect", async () => {
    await mount("/unknown-route");
    expect(await screen.findByRole("heading", { name: "Budget wildcard destination" })).toBeInTheDocument();
    await waitFor(() => expect(location.pathname).toBe("/admin/budgets"));
  });
});