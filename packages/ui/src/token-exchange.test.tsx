import { render, screen } from "@testing-library/react";
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
  it("renders ModelGardenPage pricing cards and simulates Microsoft Decision-1 auto route", async () => {
    const { mount } = setup((url) => {
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
      return {
        requested_model: "auto",
        selected_model: "DeepSeek-V3.2-Speciale",
        display_name: "DeepSeek V3.2 Speciale",
        provider: "deepseek",
        vendor: "DeepSeek",
        category: "coding_and_math",
        strategy: "microsoft-decision-1",
        decision_endpoint: "/providers/microsoft/v1/systemone",
        confidence: 0.94,
        reason: "Matched coding_and_math intent.",
        estimated_input_per_million: "0.2700",
        estimated_output_per_million: "1.1000",
      };
    });
    mount(<ModelGardenPage />);
    expect(await screen.findByText("Microsoft Decision-1 Auto Router")).toBeInTheDocument();
    expect(screen.getByText("DeepSeek V3.2 Speciale")).toBeInTheDocument();
    expect(screen.getByText("USD 0.2700")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Simulate Auto Route" }));
    expect(await screen.findByText(/Selected model: DeepSeek V3.2 Speciale/)).toBeInTheDocument();
  });

  it("renders CustomerCreditsPage with low-credit alert and 3-way breakdown", async () => {
    const { mount } = setup(() => ({
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
    expect(await screen.findByRole("alert")).toHaveTextContent(/Low credit alert/i);
    expect(screen.getAllByText("claude-sonnet-4-5").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Retail · Copilot Studio")).toBeInTheDocument();
    expect(screen.getByText("auto-router")).toBeInTheDocument();
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
      if (url.pathname.endsWith("/admin/budgets")) {
        return {
          items: [
            {
              id: "b-1",
              organization_id: "org-1",
              organization_name: "Acme OpCo",
              subscription_id: null,
              subscription_name: null,
              monthly_budget_usd: "5000.00",
              credit_allocation: "5000.00",
              used_credits: "120.0000",
              remaining_credits: "4880.0000",
              utilization_pct: 2.4,
              low_credit_alert: false,
              alert_threshold_pct: 80,
              allowed_models: ["*"],
              product_name: "Enterprise AI Token Exchange",
              channel: "api-gateway",
              hard_stop_enabled: true,
              ledger_row_key: "org:org-1",
              updated_at: "2026-01-01T00:00:00Z",
            },
          ],
          total: 1,
        };
      }
      if (url.pathname.endsWith("/admin/model-router")) {
        return {
          enabled: true,
          strategy: "microsoft-decision-1",
          decision_endpoint: "/providers/microsoft/v1/systemone",
          default_model: "gpt-5.4-mini",
          candidate_models: ["gpt-5.4-mini", "DeepSeek-V3.2-Speciale"],
          rules: [
            {
              category: "coding_and_math",
              description: "Code and SQL",
              keywords: ["python", "sql"],
              preferred_model: "DeepSeek-V3.2-Speciale",
              fallback_model: "gpt-5.4",
            },
          ],
          updated_at: "2026-01-01T00:00:00Z",
        };
      }
      if (url.pathname.endsWith("/admin/model-garden")) {
        return {
          items: [
            {
              id: "singtel-reai-70b",
              display_name: "Singtel RE:AI Sovereign 70B",
              provider: "singtel_reai",
              vendor: "Singtel RE:AI",
              region: "southeastasia",
              backend_model: "reai-70b",
              endpoint_url: "",
              context_window: 128000,
              max_completion_tokens: 8192,
              input_per_million: "0.6500",
              output_per_million: "2.2000",
              cached_input_per_million: null,
              currency: "USD",
              capabilities: ["chat"],
              description: "Sovereign GPU",
              enabled: false,
              coming_soon: true,
              content_safety_enabled: true,
              priority: 50,
            },
          ],
          total: 1,
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
    expect(await screen.findByText("org:org-1")).toBeInTheDocument();
    expect(await screen.findByText("/providers/microsoft/v1/systemone")).toBeInTheDocument();
    expect(await screen.findByText("Singtel RE:AI Sovereign 70B")).toBeInTheDocument();
    expect(await screen.findByText(/<llm-content-safety \/>/)).toBeInTheDocument();
  });

  it("supports PostgreSQL local email/password login in AuthGate when VITE_AUTH_MODE=local", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          access_token: "local-jwt-token",
          token_type: "bearer",
          email: "customer@opco.local",
          display_name: "OpCo Developer",
          user: customerMe,
        }),
        { status: 200 },
      ),
    );
    try {
      render(
        <AuthGate
          portalName="Customer portal"
          allowedRoles={["customer", "ids_admin"]}
          env={{ VITE_AUTH_MODE: "local", VITE_CONTROL_API_URL: "/api", VITE_GATEWAY_URL: "http://localhost:8000/v1" }}
        >
          <p>PORTAL READY VIA POSTGRESQL</p>
        </AuthGate>,
      );
      expect(screen.getByRole("heading", { name: /Sign in to Token Exchange/i })).toBeInTheDocument();
      await userEvent.type(screen.getByLabelText("Password"), "turnstile-customer");
      await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
      expect(await screen.findByText("PORTAL READY VIA POSTGRESQL")).toBeInTheDocument();
    } finally {
      fetchSpy.mockRestore();
    }
  });
});
