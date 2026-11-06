import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { routingLabels, routingProfiles, type AutoCandidate, type AutoConfiguration, type RoutingProfile } from "./autoRouting";
import { ControlApi } from "./client";
import { AdminAutoRouterPage } from "./pages/AdminAutoRouterPage";
import { PlaygroundPage } from "./pages/PlaygroundPage";
import { SessionProvider } from "./session";

const version = "2026-10-29T10:00:00+00:00";
const nextVersion = "2026-10-29T10:01:00+00:00";
const candidate = (id: string, price_status: AutoCandidate["price_status"] = "published"): AutoCandidate => ({
  id, provider: "openai", model_name: id, model_version: "1", capabilities: ["chat"], max_completion_tokens: 1024,
  price_status, price: price_status === "unknown" ? null : {
    input: "1", output: "2", source_url: "https://example.invalid/prices", revision: "price-1",
  },
});
function configuration(): AutoConfiguration {
  return {
    items: routingProfiles.map((profile) => ({
      profile, enabled: false, candidate_models: ["alpha", "beta"], eligible_models: ["alpha", "beta"],
      fallback_model: "alpha", version, valid: true, updated_at: version,
    })),
    candidates: [candidate("alpha"), candidate("beta", "provisional"), candidate("gamma"), candidate("unknown", "unknown")],
    feature_enabled: false, gateway_ready: false, contract_verified: false,
    descriptor_version: "descriptor-1", pricing_revision: "price-1",
  };
}
function setup(handler: (url: URL, init: RequestInit) => unknown | Promise<unknown>, node: ReactNode, entry = "/") {
  const calls: { url: URL; init: RequestInit }[] = [];
  const api = new ControlApi("/api", async () => "fixture-token", async (input, init = {}) => {
    const url = new URL(String(input), "https://portal.invalid");
    calls.push({ url, init });
    const result = await handler(url, init);
    return result instanceof Response ? result : new Response(JSON.stringify(result));
  });
  render(<MemoryRouter initialEntries={[entry]}><SessionProvider
    me={{ organization_id: "org", organization_name: "Fixture", tenant_id: "t", object_id: "u", role: "ids_admin" }}
    config={{ clientId: "c", authority: "a", apiScope: "s", controlApiUrl: "/api", gatewayUrl: "https://gateway.invalid/v1" }}
    api={api} onSignOut={() => undefined}>{node}
  </SessionProvider></MemoryRouter>);
  return calls;
}

describe("admin Auto routing", () => {
  it("falls back only from the optional editor 404 to read-only availability without writes", async () => {
    const calls = setup(url => url.pathname === "/api/admin/auto-routing"
      ? new Response(JSON.stringify({ detail: "Not Found" }), { status: 404 })
      : { ready: true, profiles: routingProfiles, config_version: "current-platform", architecture: "gateway-direct" }, <AdminAutoRouterPage />);
    expect(await screen.findByText("Auto routing advertised available")).toBeVisible();
    expect(screen.getByText("Configuration version: current-platform")).toBeVisible();
    expect(screen.getByText("Architecture: gateway-direct")).toBeVisible();
    for (const profile of routingProfiles) expect(screen.getByText(routingLabels[profile])).toBeVisible();
    expect(screen.queryByText("Something needs attention")).not.toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Save|Initialize/ })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Model catalog" })).toHaveAttribute("href", "/models");
    expect(screen.getByRole("link", { name: "Rate card & pricing" })).toHaveAttribute("href", "/prices");
    expect(calls.map(c => [c.url.pathname, c.init.method ?? "GET"])).toEqual([
      ["/api/admin/auto-routing", "GET"], ["/api/auto-routing/availability", "GET"],
    ]);
  });

  it("renders ready false as a normal unavailable status without invented configuration", async () => {
    const calls = setup(url => url.pathname === "/api/admin/auto-routing"
      ? new Response("{}", { status: 404 }) : { ready: false, profiles: [] }, <AdminAutoRouterPage />);
    expect(await screen.findByText("Auto routing currently unavailable")).toBeVisible();
    expect(screen.getByText("Configuration version: not provided")).toBeVisible();
    expect(screen.getByText("No routing profiles reported.")).toBeVisible();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(calls.every(c => !c.init.method || c.init.method === "GET")).toBe(true);
  });

  it.each([401, 403, 429, 500, 503])("does not fall back or hide an editor HTTP %s", async status => {
    const calls = setup(() => new Response(JSON.stringify({ detail: `Actual error ${status}` }), { status }), <AdminAutoRouterPage />);
    expect(await screen.findByText(`Actual error ${status}`)).toBeVisible();
    expect(screen.getByRole("button", { name: "Try again" })).toBeVisible();
    expect(calls).toHaveLength(1);
  });

  it("does not fall back on a network error", async () => {
    const calls = setup(() => { throw new TypeError("Network unavailable"); }, <AdminAutoRouterPage />);
    expect(await screen.findByText("Could not reach the control plane. Check your connection and try again.")).toBeVisible();
    expect(calls).toHaveLength(1);
  });

  it("surfaces a failed availability read and retries the read-only load without a stale error", async () => {
    let failed = true;
    const calls = setup(url => url.pathname === "/api/admin/auto-routing"
      ? new Response("{}", { status: 404 })
      : failed ? new Response(JSON.stringify({ detail: "Availability service unavailable" }), { status: 503 })
      : { ready: true, profiles: ["balanced"] }, <AdminAutoRouterPage />);
    expect(await screen.findByText("Availability service unavailable")).toBeVisible();
    expect(screen.queryByText("Auto routing advertised available")).not.toBeInTheDocument();
    failed = false;
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Auto routing advertised available")).toBeVisible();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(calls).toHaveLength(4);
    expect(calls.every(c => !c.init.method || c.init.method === "GET")).toBe(true);
  });

  it("does not treat legacy flags as published proof or offer initialization for a missing snapshot", async () => {
    setup(() => ({ ...configuration(), items: [], feature_enabled: true, gateway_ready: true, contract_verified: true }), <AdminAutoRouterPage />);
    expect(await screen.findByText(/Platform snapshot unavailable/)).toBeVisible();
    expect(screen.getByText("Not live — release gates are off or unverified")).toBeVisible();
    expect(screen.queryByRole("button", { name: /Initialize/ })).not.toBeInTheDocument();
  });

  it("labels optional edits desired-only and shows the separately verified published version", async () => {
    const config = configuration();
    config.feature_enabled = config.publication_verified = true;
    config.published_version = "published-fixture-version";
    config.items[0]!.source = "desired-override";
    setup(() => config, <AdminAutoRouterPage />);
    expect(await screen.findByText(/Desired override — not published/)).toBeVisible();
    expect(screen.getByText(/Published version: published-fixture-version/)).toBeVisible();
    expect(screen.getByText(/No seed POST, subscriber whitelist/)).toBeVisible();
  });
  it("shows all platform defaults without initialization, tenant approval or publication calls", async () => {
    const seeded = configuration();
    const calls = setup((url) => {
      expect(url.pathname).toBe("/api/admin/auto-routing");
      return seeded;
    }, <AdminAutoRouterPage />);
    await screen.findByText(/no database profile row required/);
    expect(calls).toHaveLength(1);
    expect(calls[0]!.init.method).toBeUndefined();
    expect(within(screen.getByLabelText("Routing profile")).getAllByRole("option").map(o => o.getAttribute("value")))
      .toEqual(["balanced", "cost", "quality"]);
    await screen.findByRole("region", { name: "balanced candidate pool" });
    expect(calls.map(c => [c.url.pathname, c.init.method ?? "GET"])).toEqual([
      ["/api/admin/auto-routing", "GET"],
    ]);
    expect(screen.queryByRole("button", { name: /Initialize/ })).not.toBeInTheDocument();
    for (const profile of routingProfiles) {
      await userEvent.selectOptions(screen.getByLabelText("Routing profile"), profile);
      expect(screen.getByRole("region", { name: `${profile} candidate pool` })).toBeVisible();
      expect(screen.getByLabelText(/Enable this profile/)).not.toBeChecked();
    }
    expect(screen.getByText("Not live — release gates are off or unverified")).toBeVisible();
  });

  it.each(routingProfiles)("edits %s and saves the fetched version, then uses the refreshed version on the next save", async (profile) => {
    let config = configuration();
    let saved = false;
    let resolveRefresh: ((value: AutoConfiguration) => void) | undefined;
    const calls = setup((_url, init) => {
      if (init.method === "PUT") { saved = true; return config.items.find(p => p.profile === profile); }
      if (saved) return new Promise<AutoConfiguration>(resolve => { resolveRefresh = resolve; });
      return config;
    }, <AdminAutoRouterPage />);
    await screen.findByLabelText("Routing profile");
    await userEvent.selectOptions(screen.getByLabelText("Routing profile"), profile);
    await userEvent.click(screen.getByLabelText("gamma"));
    await userEvent.selectOptions(screen.getByLabelText("Fallback model"), "gamma");
    await userEvent.click(screen.getByLabelText(/Enable this profile/));
    await userEvent.click(screen.getByRole("button", { name: "Save audited profile" }));
    await waitFor(() => expect(resolveRefresh).toBeDefined());
    const first = calls.find(c => c.init.method === "PUT")!;
    expect(first.url.pathname).toBe(`/api/admin/auto-routing/${profile}`);
    expect(JSON.parse(first.init.body as string)).toEqual({
      enabled: true, candidate_models: ["alpha", "beta", "gamma"], fallback_model: "gamma", expected_version: version,
    });
    config = { ...config, items: config.items.map(p => p.profile === profile ? {
      ...p, enabled: true, candidate_models: ["alpha", "beta", "gamma"], fallback_model: "gamma", version: nextVersion,
    } : p) };
    await act(async () => resolveRefresh!(config));
    expect(screen.getByText(new RegExp(`Version ${nextVersion.replace(/[+]/g, "\\+")}`))).toBeVisible();
    expect(screen.getByLabelText("gamma")).toBeChecked();
    expect(screen.getByLabelText("Fallback model")).toHaveValue("gamma");
    await userEvent.click(screen.getByLabelText("beta"));
    await userEvent.click(screen.getByRole("button", { name: "Save audited profile" }));
    const writes = calls.filter(c => c.init.method === "PUT");
    expect(writes).toHaveLength(2);
    expect(JSON.parse(writes[1]!.init.body as string)).toEqual({
      enabled: true, candidate_models: ["alpha", "gamma"], fallback_model: "gamma", expected_version: nextVersion,
    });
  });

  it("excludes missing and explicitly unknown prices from Cost, not from Balanced or Quality", async () => {
    const config = configuration();
    config.candidates.push({ ...candidate("stale-price"), price_status: "unknown" });
    setup(() => config, <AdminAutoRouterPage />);
    await screen.findByLabelText("Routing profile");
    for (const profile of ["balanced", "quality"] as RoutingProfile[]) {
      await userEvent.selectOptions(screen.getByLabelText("Routing profile"), profile);
      expect(screen.getByLabelText("unknown")).toBeEnabled();
      expect(screen.getByLabelText("stale-price")).toBeEnabled();
    }
    await userEvent.selectOptions(screen.getByLabelText("Routing profile"), "cost");
    expect(screen.getByLabelText("unknown")).toBeDisabled();
    expect(screen.getByLabelText("stale-price")).toBeDisabled();
    expect(screen.getByLabelText("beta")).toBeEnabled();
    expect(screen.getAllByText("Price unknown — not free; excluded from Cost")).toHaveLength(2);
    await userEvent.click(screen.getByLabelText("gamma"));
    const options = within(screen.getByLabelText("Fallback model")).getAllByRole("option");
    expect(options.map(o => o.textContent)).toEqual(["Select eligible fallback", "alpha", "beta", "gamma"]);
  });

  it("blocks a pool smaller than two and a fallback outside the selected pool", async () => {
    const calls = setup(() => configuration(), <AdminAutoRouterPage />);
    await screen.findByLabelText("alpha");
    await userEvent.click(screen.getByLabelText("alpha"));
    expect(screen.getByRole("button", { name: "Save audited profile" })).toBeDisabled();
    await userEvent.click(screen.getByLabelText("gamma"));
    expect(screen.getByRole("button", { name: "Save audited profile" })).toBeDisabled();
    await userEvent.selectOptions(screen.getByLabelText("Fallback model"), "beta");
    expect(screen.getByRole("button", { name: "Save audited profile" })).toBeEnabled();
    expect(calls).toHaveLength(1);
  });

  it("surfaces a version conflict without automatically retrying or initializing", async () => {
    const calls = setup((_url, init) => init.method === "PUT"
      ? new Response(JSON.stringify({ detail: "Profile version changed; reload." }), { status: 409 }) : configuration(), <AdminAutoRouterPage />);
    await screen.findByRole("button", { name: "Save audited profile" });
    await userEvent.click(screen.getByRole("button", { name: "Save audited profile" }));
    expect(await screen.findByText("Profile version changed; reload.")).toBeVisible();
    expect(calls.filter(c => c.init.method === "PUT")).toHaveLength(1);
    expect(calls).toHaveLength(2);
  });
});

const catalog = { items: ["explicit", "auto"].map(id => ({ id, enabled: true, placeholder: false, capabilities: ["chat"], max_completion_tokens: 1024 })), total: 2 };
function playgroundResponse(url: URL) {
  if (url.pathname === "/api/models") return catalog;
  if (url.pathname === "/api/subscriptions") return { items: [{ id: "sub", name: "Fixture", state: "active" }], total: 1 };
  throw new Error(`Unexpected control-plane request: ${url.pathname}`);
}
afterEach(() => vi.unstubAllGlobals());

describe("Playground Auto", () => {
  it("offers all three defaults to a newly provisioned active subscription using read-only availability", async () => {
    const calls = setup(url => url.pathname.endsWith("/availability")
      ? { ready: true, profiles: routingProfiles, architecture: "gateway-direct", config_version: "fixture" }
      : url.pathname === "/api/subscriptions" ? { items: [{ id: "brand-new-subscription", name: "New organization", state: "active" }], total: 1 }
      : playgroundResponse(url), <PlaygroundPage />);
    await screen.findByRole("option", { name: "auto" });
    await userEvent.selectOptions(screen.getByLabelText("Model"), "auto");
    expect(screen.getByLabelText("Routing profile")).toHaveValue("balanced");
    expect(within(screen.getByLabelText("Routing profile")).getAllByRole("option")).toHaveLength(3);
    expect(calls.every(c => !c.init.method || c.init.method === "GET")).toBe(true);
    expect(calls.some(c => /initialize|publish/.test(c.url.pathname))).toBe(false);
  });
  it("hides catalog Auto while readiness is pending, then offers it only after ready is true", async () => {
    let resolveAvailability: ((value: unknown) => void) | undefined;
    const calls = setup(url => url.pathname.endsWith("/availability")
      ? new Promise(resolve => { resolveAvailability = resolve; }) : playgroundResponse(url), <PlaygroundPage />, "/playground?model=auto");
    await screen.findByLabelText("Model");
    expect(within(screen.getByLabelText("Model")).queryByRole("option", { name: "auto" })).not.toBeInTheDocument();
    expect(screen.getByLabelText("Model")).toHaveValue("explicit");
    expect(screen.queryByLabelText("Routing profile")).not.toBeInTheDocument();
    await act(async () => resolveAvailability!({ ready: true, profiles: routingProfiles }));
    await userEvent.selectOptions(screen.getByLabelText("Model"), "auto");
    expect(screen.getByLabelText("Routing profile")).toHaveValue("balanced");
    expect(within(screen.getByLabelText("Routing profile")).getAllByRole("option").map(o => o.textContent)).toEqual(routingProfiles.map(p => routingLabels[p]));
    expect(calls).toHaveLength(3);
  });

  it.each(["not ready", "failed"])("keeps Auto hidden when availability is %s without hiding explicit models", async (state) => {
    let resolved = false;
    setup(url => {
      if (!url.pathname.endsWith("/availability")) return playgroundResponse(url);
      resolved = true;
      return state === "failed" ? new Response(JSON.stringify({ detail: "Unavailable" }), { status: 503 }) : { ready: false, profiles: [] };
    }, <PlaygroundPage />);
    await screen.findByLabelText("Model");
    await waitFor(() => expect(resolved).toBe(true));
    expect(within(screen.getByLabelText("Model")).getAllByRole("option").map(o => o.textContent)).toEqual(["explicit"]);
    expect(screen.queryByLabelText("Routing profile")).not.toBeInTheDocument();
  });

  it("does not mount an empty Chat when the catalog contains only gated Auto", async () => {
    setup(url => url.pathname.endsWith("/availability") ? { ready: false, profiles: [] }
      : url.pathname === "/api/models" ? { items: [catalog.items[1]], total: 1 } : playgroundResponse(url), <PlaygroundPage />);
    expect(await screen.findByText("No enabled models")).toBeVisible();
    expect(screen.queryByLabelText("Model")).not.toBeInTheDocument();
  });

  it("sends routing_profile only for Auto and puts it in extra_body only in the Auto SDK example", async () => {
    const gateway = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => new Response(JSON.stringify({
      model: "actual-model", choices: [{ message: { content: "Fixture reply" }, finish_reason: "stop" }],
      routing: { selected_model: "alpha", routing_profile: "quality", config_version: version, fallback_used: false },
    })));
    vi.stubGlobal("fetch", gateway);
    setup(url => url.pathname.endsWith("/availability") ? { ready: true, profiles: routingProfiles } : playgroundResponse(url), <PlaygroundPage />);
    await screen.findByLabelText("Model");
    await screen.findByRole("option", { name: "auto" });
    await userEvent.selectOptions(screen.getByLabelText("Model"), "auto");
    await userEvent.selectOptions(screen.getByLabelText("Routing profile"), "quality");
    expect(screen.getByLabelText(/Stream response/)).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Code" }));
    const examples = screen.getByRole("dialog");
    const code = examples.querySelectorAll("pre code");
    expect(code[0]!.textContent).toContain('"routing_profile":"quality"');
    expect(code[0]!.textContent).not.toContain("extra_body");
    expect(code[1]!.textContent).toContain('request["extra_body"] = {"routing_profile": request.pop("routing_profile")}');
    expect(examples.textContent).not.toContain("pasted-fixture-key");
    await userEvent.click(screen.getByRole("button", { name: "Close code examples" }));
    await userEvent.type(screen.getByLabelText("Or paste a key"), "pasted-fixture-key");
    await userEvent.type(screen.getByLabelText("Message"), "Hello");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByLabelText("Actual Auto routing result");
    expect(screen.getByLabelText("Actual Auto routing result")).toHaveTextContent("Decision cost: unknown");
    const autoInit = gateway.mock.calls[0]![1]!;
    expect(JSON.parse(autoInit.body as string)).toMatchObject({ model: "auto", routing_profile: "quality", stream: false });
    expect(JSON.parse(autoInit.body as string)).not.toHaveProperty("extra_body");
    await userEvent.selectOptions(screen.getByLabelText("Model"), "explicit");
    expect(screen.queryByLabelText("Routing profile")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Code" }));
    expect(screen.getByRole("dialog").textContent).not.toMatch(/routing_profile|extra_body/);
    await userEvent.click(screen.getByRole("button", { name: "Close code examples" }));
    await userEvent.type(screen.getByLabelText("Message"), "Hello again");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(gateway).toHaveBeenCalledTimes(2));
    const explicitInit = gateway.mock.calls[1]![1]!;
    expect(JSON.parse(explicitInit.body as string)).toMatchObject({ model: "explicit", stream: false });
    expect(JSON.parse(explicitInit.body as string)).not.toHaveProperty("routing_profile");
    expect(JSON.parse(explicitInit.body as string)).not.toHaveProperty("extra_body");
    await screen.findAllByText("Fixture reply");
  });
});