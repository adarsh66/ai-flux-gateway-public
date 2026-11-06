import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { AuthGate } from "./auth";
import { ControlApi } from "./client";
import { SessionProvider } from "./session";
import {
  AdminBudgetsAndFinOpsPage,
  AdminModelRouterPage,
  CustomerCreditsPage,
  CustomerKeysPage,
  ModelGardenPage,
} from "./pages/TokenExchangePages";

const customerMe = {
  organization_id: "org-1",
  organization_name: "Acme OpCo",
  tenant_id: "tenant-1",
  object_id: "user-1",
  role: "customer" as const,
};

const adminMe = {
  ...customerMe,
  role: "ids_admin" as const,
};

const config = {
  clientId: "c",
  authority: "a",
  apiScope: "s",
  controlApiUrl: "/api",
  gatewayUrl: "https://g/v1",
};

function setup(handler: (url: URL, init: RequestInit) => unknown, admin = false) {
  const calls: { url: URL; init: RequestInit }[] = [];
  const api = new ControlApi("/api", async () => "tok", async (input, init = {}) => {
    const url = new URL(String(input), "https://portal");
    calls.push({ url, init });
    const data = handler(url, init);
    return data instanceof Response ? data : new Response(JSON.stringify(data), { status: 200 });
  });
  return {
    calls,
    mount: (node: React.ReactNode) =>
      render(
        <MemoryRouter>
          <SessionProvider me={admin ? adminMe : customerMe} api={api} config={config} onSignOut={() => undefined}>
            {node}
          </SessionProvider>
        </MemoryRouter>,
      ),
  };
}

describe("Token Exchange Customer & Admin Portal Pages", () => {
  it("renders customer copy and the exact Luna title while retaining model links and pricing disclosures", async () => {
    const diagnostics = "APIM chat verified 2026-10-26. Persistent POC: output1024; RPM60; TPM2048; daily10000; no expiry/retries.";
    const { mount } = setup(() => ({
      items: ["gpt-5.6-luna", "DeepSeek-V4-Flash", "future-model"].map((id) => ({
        id, display_name: id === "gpt-5.6-luna" ? "Luna — bounded demo (2026-07-09)" : id,
        vendor: "Test provider", region: "eastus", capabilities: ["chat"],
        enabled: true, coming_soon: false, description: diagnostics,
        max_completion_tokens: 1024, content_safety_enabled: false,
      })), total: 3,
    }));
    mount(<ModelGardenPage />);
    expect(await screen.findByRole("heading", { name: "gpt-5.6-luna" })).toBeInTheDocument();
    expect(screen.queryByText(/bounded demo/)).not.toBeInTheDocument();
    expect(screen.queryByText(/APIM chat verified|Persistent POC|RPM60|TPM2048/)).not.toBeInTheDocument();
    expect(screen.getByText("Use DeepSeek V4 Flash for text-based questions, writing, and everyday conversations.")).toBeInTheDocument();
    expect(screen.getByText("A conversational AI model for text-based questions, writing, and exploring ideas.")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /Try in Playground/ }).map((link) => link.getAttribute("href"))).toEqual([
      "/playground?model=gpt-5.6-luna", "/playground?model=DeepSeek-V4-Flash", "/playground?model=future-model",
    ]);
    expect(screen.getAllByText("Unknown — not free")).toHaveLength(6);
    await userEvent.selectOptions(screen.getByLabelText("Provider family"), "Test provider");
    await userEvent.click(screen.getByRole("tab", { name: "Deployed & Active (3)" }));
    expect(screen.getAllByRole("link", { name: /Try in Playground/ })).toHaveLength(3);
  });

  it("renders unknown pricing honestly without a customer route simulator or route-decision request", async () => {
    const { mount, calls } = setup((url) => {
      if (url.pathname.endsWith("/model-garden")) {
        return {
          items: [
            {
              id: "auto",
              display_name: "Microsoft Decision-1 Auto Router",
              provider: "microsoft_decision",
              vendor: "Microsoft Foundry",
              region: "eastus2",
              backend_model: "Decision-1",
              endpoint_url: "/providers/microsoft/v1/systemone",
              context_window: 200000,
              max_completion_tokens: 16384,
              input_per_million: "0.4000",
              output_per_million: "1.6000",
              cached_input_per_million: "0.1000",
              currency: "USD",
              capabilities: ["chat", "auto-routing"],
              description: "Intelligent router",
              enabled: true,
              coming_soon: false,
              content_safety_enabled: true,
              priority: 1,
            },
            {
              id: "DeepSeek-V3.2-Speciale",
              display_name: "DeepSeek V3.2 Speciale",
              provider: "deepseek",
              vendor: "DeepSeek",
              region: "eastus2",
              backend_model: "DeepSeek-V3.2-Speciale",
              endpoint_url: "https://apim/foundrymodels",
              context_window: 128000,
              max_completion_tokens: 16384,
              input_per_million: "0.2700",
              output_per_million: "1.1000",
              cached_input_per_million: "0.0700",
              currency: "USD",
              capabilities: ["chat", "coding"],
              description: "Reasoning model",
              enabled: true,
              coming_soon: false,
              content_safety_enabled: true,
              priority: 40,
            },
          ],
          total: 2,
        };
      }
      throw new Error(`Unexpected catalog request: ${url.pathname}`);
    });
    mount(<ModelGardenPage />);
    expect(await screen.findByText("Microsoft Decision-1 Auto Router")).toBeInTheDocument();
    expect(screen.getByText("DeepSeek V3.2 Speciale")).toBeInTheDocument();
    expect(screen.getAllByText("Unknown — not free").length).toBeGreaterThan(0);
    expect(screen.queryByText("USD 0.2700")).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /Routing simulator/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Simulate Auto Route/ })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Sample prompt")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Routing strategy")).not.toBeInTheDocument();
    expect(screen.queryByText(/Auto-routing is disabled until/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Selected model:/)).not.toBeInTheDocument();
    expect(calls.every(({ url, init }) => url.pathname.endsWith("/model-garden") && (!init.method || init.method === "GET"))).toBe(true);
  });

  it.each([true, false, null])("separates scoring availability %s from chat eligibility and never offers scorer Playground", async (available) => {
    const { mount } = setup(() => ({ items: [
      { id: "Decision-1", display_name: "Legacy Decision router", model_kind: "scoring", scoring_available: available,
        vendor: "Microsoft", region: "eastus", capabilities: ["scoring", "chat"], enabled: false,
        coming_soon: available !== true, context_window: available === true ? null : 32768, max_completion_tokens: 0,
        display_price: { input: "0.042", model_kind: "scoring", billing_dimensions: ["input"],
          currency: "USD", status: "public_list", source_url: "https://example.com/pricing", checked_at: "2026-10-31",
          revision: "scoring-v1", source_model: "Microsoft-Decision-1", sku: "scoring", model_version: "1",
          assumptions: "Output and cache tokens are N/A, not free.", basis: "Scoring input tokens only",
          provenance: { pricing_table: { input: "$0.042", output: "N/A" } } } },
      { id: "gpt-4o", display_name: "GPT-4o", vendor: "OpenAI", region: "eastus", capabilities: ["chat"],
        enabled: true, coming_soon: false, max_completion_tokens: 1024 },
    ], total: 2 }));
    mount(<ModelGardenPage />);
    const heading = await screen.findByRole("heading", { name: "Microsoft Decision-1" });
    const scorer = within(heading.closest("li")!);
    expect(scorer.getByText("Scoring-only · Used by Auto")).toBeInTheDocument();
    expect(scorer.getByText(available === true ? "Scoring available" : available === false ? "Scoring unavailable" : "Scoring availability unverified")).toBeInTheDocument();
    expect(scorer.queryByText("Coming soon")).not.toBeInTheDocument();
    expect(scorer.queryByText("Active")).not.toBeInTheDocument();
    expect(scorer.getByText("USD 0.042")).toBeInTheDocument();
    expect(scorer.getAllByText("N/A")).toHaveLength(2);
    expect(scorer.getByText("32,768")).toBeInTheDocument();
    expect(scorer.queryByText("Context / Max output")).not.toBeInTheDocument();
    expect(scorer.getByLabelText("Pricing provenance")).toHaveTextContent("$0.042");
    expect(scorer.queryByRole("link", { name: /Try in Playground/ })).not.toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /Try in Playground/ })).toHaveLength(1);
    await userEvent.click(screen.getByRole("tab", { name: `Deployed & Active (${available === true ? 2 : 1})` }));
    expect(Boolean(screen.queryByRole("heading", { name: "Microsoft Decision-1" }))).toBe(available === true);
    await userEvent.click(screen.getByRole("tab", { name: `Available to Onboard (${available === true ? 0 : 1})` }));
    expect(Boolean(screen.queryByRole("heading", { name: "Microsoft Decision-1" }))).toBe(available !== true);
  });

  it("renders CustomerCreditsPage with external estimates and 3-way breakdown, not internal credit signals", async () => {
    const { mount } = setup((url) => url.pathname.endsWith("/budget/monthly") ? new Response(JSON.stringify({ detail: "Monthly budget unavailable" }), { status: 503 }) : ({
      organization_id: "org-1",
      organization_name: "Acme OpCo",
      currency: "USD",
      total_credits: "5000.00",
      used_credits: "4250.0000",
      remaining_credits: "750.0000",
      utilization_pct: 85.0,
      alert_threshold_pct: 80,
      low_credit_alert: true,
      hard_stop_enabled: true,
      estimated_cost_usd: "12.50",
      estimated_requests: 120,
      unestimated_requests: 0,
      total_requests: 120,
      total_tokens: 450000,
      by_model: [
        {
          model: "claude-sonnet-4-5",
          provider: "anthropic",
          vendor: "Anthropic",
          requests: 80,
          input_tokens: 200000,
          output_tokens: 100000,
          total_tokens: 300000,
          cost_usd: "2100.0000",
          share_pct: 66.7,
        },
      ],
      by_product: [
        {
          subscription_id: "sub-1",
          subscription_name: "Copilot Studio",
          team: "Retail",
          product_name: "Retail · Copilot Studio",
          requests: 80,
          total_tokens: 300000,
          cost_usd: "2100.0000",
          share_pct: 66.7,
        },
      ],
      by_channel: [
        {
          channel: "auto-router",
          requests: 80,
          total_tokens: 300000,
          cost_usd: "2100.0000",
          share_pct: 66.7,
        },
      ],
    }));
    mount(<CustomerCreditsPage />);
    expect(await screen.findByText("External estimated cost (30d)")).toBeInTheDocument();
    expect(screen.getByText("USD 12.50")).toBeInTheDocument();
    expect(screen.queryByText(/Daily token volume by provider family|Total credit allocation|Monthly Cap/)).not.toBeInTheDocument();
    expect(await screen.findByRole("alert")).toHaveTextContent("Monthly budget unavailable");
    expect(screen.getByRole("heading", { name: "Token share by model" })).toBeInTheDocument();
    expect(screen.queryByText(/Low credit alert|Credits used|Remaining credits|4250|750\.0000|2100\.0000/)).not.toBeInTheDocument();
    expect(screen.getAllByText("claude-sonnet-4-5").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Retail · Copilot Studio")).toBeInTheDocument();
    expect(screen.getByText("auto-router")).toBeInTheDocument();
    const kpis = screen.getByLabelText("Usage summary");
    expect(kpis.children).toHaveLength(3);
    expect(within(kpis).getByText("Requests (30d)")).toBeInTheDocument();
    expect(within(kpis).getByText("Tokens (30d)")).toBeInTheDocument();
    expect(screen.getByText("Usage activity")).toBeInTheDocument();
    const coverage = screen.getByText(/Selected-window estimate coverage/).closest("details")!;
    expect(coverage).not.toHaveAttribute("open");
    await userEvent.click(within(coverage).getByText(/Selected-window estimate coverage/));
    expect(coverage).toHaveAttribute("open");
    expect(within(coverage).getByText(/standard-input approximation/)).toBeVisible();
    expect(screen.getByLabelText("Model share donut chart")).toBeVisible();
  });

  it("allows customer self-service key reveal and rotation on CustomerKeysPage", async () => {
    const { calls, mount } = setup((url) => {
      if (url.pathname.endsWith("/reveal")) return { key: "CUST-SECRET-999" };
      if (url.pathname.endsWith("/customer-rotate")) return { state: "active", rotated_key: "primary" };
      return {
        items: [{ id: "sub-1", name: "Retail API", team: "Retail", state: "active", created_at: "2026-01-01T00:00:00Z" }],
        total: 1,
      };
    });
    mount(<CustomerKeysPage />);
    expect(await screen.findByText("Retail API")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Reveal primary" }));
    expect(await screen.findByText("CUST-SECRET-999")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Rotate primary" }));
    expect(await screen.findByText(/primary key rotated successfully/i)).toBeInTheDocument();
    expect(calls.some((c) => c.url.pathname === "/api/subscriptions/sub-1/customer-rotate")).toBe(true);
  });

  it("renders AdminBudgetsAndFinOpsPage and AdminModelRouterPage", async () => {
    const { mount } = setup((url) => {
      if (url.pathname.endsWith("/model-deployments")) {
        return { items: [], total: 0, verified_at: "2026-01-01T00:00:00Z", auto_enabled: false };
      }
      if (url.pathname.endsWith("/admin/monthly-budgets")) {
        return {
          items: [], total: 0,
        };
      }
      if (url.pathname.endsWith("/admin/auto-routing")) {
        return {
          items: [], candidates: [], feature_enabled: false, gateway_ready: false, contract_verified: false,
          descriptor_version: "descriptor-1", pricing_revision: "price-1",
        };
      }
      return {
        ledger_storage_account: "aifluxfunc",
        ledger_table_name: "TurnstileLedger",
        model_routes_table_name: "ModelRoutes",
        decision_router_enabled: true,
        decision_endpoint: "/providers/microsoft/v1/systemone",
        policy_xml: "<policies><inbound><llm-content-safety /></inbound></policies>",
      };
    }, true);
    mount(
      <>
        <AdminBudgetsAndFinOpsPage />
        <AdminModelRouterPage />
      </>,
    );
    expect(await screen.findByRole("heading", { name: "Monthly organization budgets" })).toBeInTheDocument();
    expect(await screen.findByText("No organizations")).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Decision-1 Auto routing" })).toBeInTheDocument();
    expect(await screen.findByText(/GET requests never seed configuration/)).toBeInTheDocument();
    expect(await screen.findByText("Not live — release gates are off or unverified")).toBeInTheDocument();
    expect(screen.queryByText("/providers/microsoft/v1/systemone")).not.toBeInTheDocument();
    expect(screen.queryByText(/<llm-content-safety \/>/)).not.toBeInTheDocument();
  });

  it.each([
    { portalName: "Customer portal", allowedRoles: ["customer", "ids_admin"] as const, user: customerMe, email: "developer@caldova.com" },
    { portalName: "IDS Admin portal", allowedRoles: ["ids_admin"] as const, user: adminMe, email: "admin@tokenx-ids.com" },
  ])("supports PostgreSQL local login without registration in $portalName when VITE_AUTH_MODE=local", async ({ portalName, allowedRoles, user, email }) => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          access_token: "local-jwt-token",
          token_type: "bearer",
          email: "customer@opco.local",
          display_name: "OpCo Developer",
          user,
        }),
        { status: 200 },
      ),
    );
    try {
      render(
        <AuthGate
          portalName={portalName}
          allowedRoles={[...allowedRoles]}
          env={{ VITE_AUTH_MODE: "local", VITE_CONTROL_API_URL: "/api", VITE_GATEWAY_URL: "http://localhost:8000/v1" }}
        >
          <p>PORTAL READY VIA POSTGRESQL</p>
        </AuthGate>,
      );
      expect(screen.getByRole("heading", { name: /Sign in to Token Exchange/i })).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /Create a new OpCo account/i })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /Create account/i })).not.toBeInTheDocument();
      expect(screen.getByLabelText("Email")).toHaveValue(email);
      expect(fetchSpy).not.toHaveBeenCalled();
      await userEvent.type(screen.getByLabelText("Password"), "turnstile-customer");
      await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
      expect(await screen.findByText("PORTAL READY VIA POSTGRESQL")).toBeInTheDocument();
      expect(fetchSpy).toHaveBeenCalledOnce();
      expect(fetchSpy.mock.calls[0]?.[0]).toBe("/api/auth/login");
      expect(fetchSpy.mock.calls[0]?.[1]).toMatchObject({
        method: "POST",
        body: JSON.stringify({ email, password: "turnstile-customer" }),
      });
    } finally {
      fetchSpy.mockRestore();
      sessionStorage.removeItem(`aiflux_local_pg_session:${portalName}`);
    }
  });
});
