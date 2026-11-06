import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ControlApi } from "./client";
import { OrganizationModelAccessPage } from "./pages/OrganizationModelAccessPage";
import { SessionProvider } from "./session";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

function mount(api: ControlApi) {
  return render(<MemoryRouter><SessionProvider api={api} onSignOut={() => {}}
    me={{ organization_id: "admin", organization_name: "Admin", object_id: "u", tenant_id: "t", role: "ids_admin" }}
    config={{ clientId: "c", authority: "a", apiScope: "s", controlApiUrl: "/api", gatewayUrl: "https://invalid/v1" }}>
    <OrganizationModelAccessPage />
  </SessionProvider></MemoryRouter>);
}

function fixture(org: string, state = "applied") {
  return { organization_id: org, organization_enabled: true, version: 1, denied_models: [], auto_enabled: true,
    applied_version: state === "applied" ? 1 : null, applied_sha256: "hash", state, error: null,
    items: [{ id: `${org}-alpha`, display_name: "Alpha", provider: "P", model_kind: "chat", globally_enabled: true,
      internal_price_available: false, external_price_available: true },
      { id: `${org}-beta`, display_name: "Beta", provider: "Q", model_kind: "chat", globally_enabled: false,
        internal_price_available: true, external_price_available: false }] };
}

describe("organization model access editor", () => {
  it("ignores a stale organization response after switching scope", async () => {
    let finishOne!: (response: Response) => void;
    const api = new ControlApi("/api", async () => "fixture", async input => {
      const path = String(input);
      if (path.endsWith("/organizations")) return new Response(JSON.stringify({ items: [{ id: "one", name: "One" }, { id: "two", name: "Two" }], total: 2 }));
      if (path.includes("/one/")) return new Promise<Response>(resolve => { finishOne = resolve; });
      return new Response(JSON.stringify(fixture("two")));
    });
    mount(api);
    const selector = await screen.findByRole("combobox", { name: "Organization" });
    await userEvent.selectOptions(selector, "one");
    await waitFor(() => expect(finishOne).toBeTypeOf("function"));
    await userEvent.selectOptions(selector, "two");
    expect(await screen.findByRole("checkbox", { name: "Allow two-alpha" })).toBeChecked();
    finishOne(new Response(JSON.stringify(fixture("one"))));
    await waitFor(() => expect(selector).toHaveValue("two"));
    expect(screen.queryByRole("checkbox", { name: "Allow one-alpha" })).not.toBeInTheDocument();
  });

  it("retains hidden denies across filters and saves independent Auto with the CAS version", async () => {
    const writes: unknown[] = [];
    const api = new ControlApi("/api", async () => "fixture", async (input, init = {}) => {
      if (String(input).endsWith("/organizations")) return new Response(JSON.stringify({ items: [{ id: "one", name: "One" }], total: 1 }));
      if (init.method === "PUT") {
        writes.push(JSON.parse(String(init.body)));
        return new Response(JSON.stringify({ ...fixture("one", "pending"), version: 2, denied_models: ["one-alpha", "one-beta"], auto_enabled: false }), { status: 202 });
      }
      return new Response(JSON.stringify(fixture("one")));
    });
    mount(api);
    await userEvent.selectOptions(await screen.findByRole("combobox", { name: "Organization" }), "one");
    await screen.findByRole("checkbox", { name: "Allow one-alpha" });
    await userEvent.click(screen.getByRole("button", { name: "Disable all current models" }));
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Provider" }), "P");
    expect(screen.queryByRole("checkbox", { name: "Allow one-beta" })).not.toBeInTheDocument();
    await userEvent.type(screen.getByRole("textbox", { name: "Search models" }), "Alpha");
    await userEvent.click(screen.getByRole("checkbox", { name: "Auto routing" }));
    await userEvent.click(screen.getByRole("button", { name: "Save model access" }));
    await waitFor(() => expect(writes).toHaveLength(1));
    expect(writes[0]).toMatchObject({ expected_version: 1, denied_models: ["one-alpha", "one-beta"], auto_enabled: false });
    expect(await screen.findByRole("status")).toHaveTextContent("Applying");
  });

  it("retries publication without replacing a dirty draft or writing preferences", async () => {
    const methods: string[] = [];
    const api = new ControlApi("/api", async () => "fixture", async (input, init = {}) => {
      const path = String(input); methods.push(init.method ?? "GET");
      if (path.endsWith("/organizations")) return new Response(JSON.stringify({ items: [{ id: "one", name: "One" }], total: 1 }));
      return new Response(JSON.stringify(fixture("one", init.method === "POST" ? "pending" : "error")), { status: init.method === "POST" ? 202 : 200 });
    });
    mount(api);
    await userEvent.selectOptions(await screen.findByRole("combobox", { name: "Organization" }), "one");
    const allow = await screen.findByRole("checkbox", { name: "Allow one-alpha" });
    await userEvent.click(allow);
    await userEvent.click(screen.getByRole("button", { name: "Retry publication" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Applying"));
    expect(allow).not.toBeChecked();
    expect(methods.filter(m => m === "POST")).toHaveLength(1);
    expect(methods).not.toContain("PUT");
    expect(screen.getByRole("button", { name: "Save model access" })).toBeEnabled();
  });

  it("keeps conflict drafts, confirms organization changes, and separates pricing from permissions", async () => {
    const calls: string[] = [];
    const api = new ControlApi("/api", async () => "fixture", async (input, init = {}) => {
      const path = String(input); calls.push(`${init.method ?? "GET"} ${path}`);
      if (init.method === "PUT") return new Response(JSON.stringify({ detail: "conflict" }), { status: 409 });
      return new Response(JSON.stringify(path.endsWith("/organizations")
        ? { items: [{ id: "one", name: "One" }, { id: "two", name: "Two" }], total: 2 }
        : { organization_id: "one", organization_enabled: true, version: 1, denied_models: [], auto_enabled: true,
          applied_version: 1, applied_sha256: "hash", state: "applied", error: null,
          items: [{ id: "alpha", display_name: "Alpha", provider: "P", model_kind: "chat", globally_enabled: true,
            internal_price_available: false, external_price_available: true },
            { id: "Decision-1", display_name: "Decision-1", provider: "P", model_kind: "informational", globally_enabled: false }] }));
    });
    render(<MemoryRouter><SessionProvider api={api} onSignOut={() => {}}
      me={{ organization_id: "admin", organization_name: "Admin", object_id: "u", tenant_id: "t", role: "ids_admin" }}
      config={{ clientId: "c", authority: "a", apiScope: "s", controlApiUrl: "/api", gatewayUrl: "https://invalid/v1" }}>
      <OrganizationModelAccessPage />
    </SessionProvider></MemoryRouter>);
    await userEvent.selectOptions(await screen.findByRole("combobox", { name: "Organization" }), "one");
    const allow = await screen.findByRole("checkbox", { name: "Allow alpha" });
    expect(allow).toBeChecked();
    expect(screen.getByText(/Internal: missing/)).toBeVisible();
    expect(screen.queryByRole("checkbox", { name: "Allow Decision-1" })).not.toBeInTheDocument();
    await userEvent.click(allow);
    await userEvent.click(screen.getByRole("button", { name: "Save model access" }));
    expect(await screen.findByText(/Conflict: another administrator/)).toBeVisible();
    expect(allow).not.toBeChecked();
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    try {
      await userEvent.selectOptions(screen.getByRole("combobox", { name: "Organization" }), "two");
      expect(confirm).toHaveBeenCalled();
      await waitFor(() => expect(screen.getByRole("combobox", { name: "Organization" })).toHaveValue("one"));
      expect(calls.filter(c => c.startsWith("PUT"))).toHaveLength(1);
      expect(calls.some(c => c.includes("/two/model-access"))).toBe(false);
    } finally { confirm.mockRestore(); }
  });
});