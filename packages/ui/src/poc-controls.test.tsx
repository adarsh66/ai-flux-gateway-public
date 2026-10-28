import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { ControlApi } from "./client";
import { PocControlsForm, POC_DEFAULTS, pocEffective } from "./pages/PocControlsForm";
import { SessionProvider } from "./session";
import type { GatewaySettings, PocGatewayConfiguration } from "./types";

const org = "11111111-1111-4111-8111-111111111111";
const sub = "22222222-2222-4222-8222-222222222222";
function mount(safetyPage = false, config: PocGatewayConfiguration = structuredClone(POC_DEFAULTS)) {
  const mutations: Record<string, unknown>[] = [];
  const row: GatewaySettings = { scope: "dev-unified", max_rpm: 60, max_tpm: 2048,
    version: 1, published_version: 1, desired: { version: 1, configuration: config,
      reason: "Explicit bootstrap", object_id: "admin", occurred_at: "2026-10-27T14:00:00Z", state: "published", error: null } };
  const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (init?.method === "PUT") {
      const payload = JSON.parse(String(init.body));
      mutations.push(payload);
      const configuration = safetyPage ? { ...config, safety: payload.configuration } : payload.configuration;
      return new Response(JSON.stringify({ ...row, version: 2, published_version: 2,
        desired: { ...row.desired, version: 2, configuration } }));
    }
    if (url.includes("/organizations")) return new Response(JSON.stringify({ items: [{ id: org, name: "Customer" }], total: 1 }));
    if (url.includes("gateway-targets")) return new Response(JSON.stringify({ items: [{ organization_id: org, subscription_id: sub, name: "New active subscription", state: "active" }], total: 1 }));
    return new Response(JSON.stringify({ items: [], total: 0 }));
  });
  const api = new ControlApi("/api", async () => "synthetic-token", fetcher);
  render(<MemoryRouter><SessionProvider me={{ organization_id: org, organization_name: "IDS", tenant_id: "t", object_id: "admin", role: "ids_admin" }} api={api}
    config={{ clientId: "c", authority: "a", apiScope: "s", controlApiUrl: "/api", gatewayUrl: "https://g" }} onSignOut={() => undefined}>
    <PocControlsForm row={row} refresh={() => undefined} safetyPage={safetyPage} />
  </SessionProvider></MemoryRouter>);
  return mutations;
}

describe("optional POC controls", () => {
  it("resolves subscription over organization over defaults independently", () => {
    const config: PocGatewayConfiguration = { ...POC_DEFAULTS, overrides: [
      { organization_id: org, subscription_id: null, limits: { ...POC_DEFAULTS.defaults, rpm: 20 }, safety: { ...POC_DEFAULTS.safety, hate: 0 } },
      { organization_id: org, subscription_id: sub, limits: { ...POC_DEFAULTS.defaults, rpm: 5 }, safety: null },
    ] };
    expect(pocEffective(config, org, sub).limits.rpm).toBe(5);
    expect(pocEffective(config, org, sub).safety.hate).toBe(0);
    expect(pocEffective(config, "unknown", "new").limits.rpm).toBe(60);
  });
  it("shows immediate default access and readonly unsupported features", () => {
    mount();
    expect(screen.getByText(/usable immediately with defaults/)).toBeInTheDocument();
    expect(screen.getByLabelText("Requests per minute per model")).toHaveValue(60);
    expect(screen.getByLabelText("Tokens per minute per model")).toHaveValue(2048);
    expect(screen.getByText(/Concurrency and monthly quotas unavailable/)).toBeInTheDocument();
  });
  it("creates an org override without erasing subscription safety and removes it to inherit", async () => {
    const config: PocGatewayConfiguration = { ...POC_DEFAULTS, overrides: [{ organization_id: org, subscription_id: sub, limits: null, safety: { ...POC_DEFAULTS.safety, hate: 0 } }] };
    const mutations = mount(false, config);
    await screen.findByRole("option", { name: "Customer" });
    await userEvent.selectOptions(screen.getByLabelText("Organization"), org);
    await userEvent.click(screen.getByRole("button", { name: "Add optional organization override" }));
    const rpm = screen.getByLabelText("Requests per minute per model");
    await userEvent.clear(rpm); await userEvent.type(rpm, "30");
    await userEvent.type(screen.getByLabelText("Reason for this revision"), "Reviewed org cap");
    await userEvent.click(screen.getByLabelText("I approve these optional settings."));
    await userEvent.click(screen.getByRole("button", { name: "Publish gateway settings" }));
    await waitFor(() => expect(mutations).toHaveLength(1));
    const saved = mutations[0]!.configuration as PocGatewayConfiguration;
    expect(saved.overrides.find((o) => o.subscription_id === sub)?.safety?.hate).toBe(0);
    expect(saved.overrides.find((o) => o.subscription_id === null)?.limits?.rpm).toBe(30);
    await userEvent.click(screen.getByRole("button", { name: "Remove override (inherit)" }));
    expect(screen.getByLabelText("Requests per minute per model")).toHaveValue(60);
  });
  it("safety page needs no gateway initialize and sends only target safety", async () => {
    const mutations = mount(true);
    expect(screen.queryByText(/initialize gateway/i)).not.toBeInTheDocument();
    expect(screen.getByLabelText(/Prompt shield/)).toBeDisabled();
    expect(screen.getByLabelText(/Protected material detection/)).toBeDisabled();
    expect(screen.getByText(/GLM ModelArts: Foundry RAI not applicable/)).toBeInTheDocument();
    const hate = screen.getByLabelText("Hate threshold (0–7)");
    await userEvent.clear(hate); await userEvent.type(hate, "2");
    await userEvent.click(screen.getByLabelText(/I acknowledge this relaxes APIM safety/));
    await userEvent.type(screen.getByLabelText("Reason for this revision"), "Reviewed APIM only threshold");
    await userEvent.click(screen.getByLabelText("I approve these optional settings."));
    await userEvent.click(screen.getByRole("button", { name: "Publish safety settings" }));
    await waitFor(() => expect(mutations).toHaveLength(1));
    expect(mutations[0]!.configuration).toEqual({ ...POC_DEFAULTS.safety, hate: 2 });
    expect(mutations[0]!.organization_id).toBeNull();
    expect(mutations[0]!.acknowledge_relaxation).toBe(true);
  });
});