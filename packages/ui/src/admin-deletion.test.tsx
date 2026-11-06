/** Authored offline; Vitest execution is a separately approved Linux release gate. */
import { useState } from "react";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { ControlApi } from "./client";
import { DeletionDialog } from "./components/DeletionDialog";
import { SessionProvider } from "./session";
import { OrganizationsPage, MembersPage } from "./pages/admin";
import { AdminLocalUsersPage } from "./pages/TokenExchangePages";
import { SubscriptionsPage } from "./pages/SubscriptionsPage";
import type { DeletionPreview } from "./types";

const me = { organization_id: "home", organization_name: "IDS", tenant_id: "t", object_id: "admin", role: "ids_admin" as const };
const config = { clientId: "c", authority: "a", apiScope: "s", controlApiUrl: "/api", gatewayUrl: "https://g/v1" };
const orgs = { items: [{ id: "org", name: "Acme", tenant_id: "tenant", enabled: true }], total: 1 };
const preview: DeletionPreview = { entity_type: "organization", entity_id: "org", label: "Acme", can_delete: true,
  blockers: [], dependencies: { subscriptions: 0, users: 0, members: 0 }, effect: "Archive; retain all history." };
const sub = { id: "sub", name: "Finance", team: "Team", organization_id: "org", organization_name: "Acme", team_id: "team",
  state: "active", created_at: "2026-01-01T00:00:00Z", gateway_access: "ready", gateway_message: null };

function setup(handler: (url: URL, init: RequestInit) => unknown | Promise<unknown>, page?: "subscriptions" | "organizations" | "users" | "members") {
  const calls: { url: URL; init: RequestInit }[] = [];
  const changed = vi.fn(), attempt = vi.fn();
  const api = new ControlApi("/api", async () => "test", async (input, init = {}) => {
    const url = new URL(String(input), "https://test.invalid");
    calls.push({ url, init });
    const data = url.pathname === "/api/admin/organizations" && init.method !== "DELETE" ? orgs : await handler(url, init);
    return data instanceof Response ? data : new Response(JSON.stringify(data));
  });
  function Harness() {
    const [open, setOpen] = useState(false);
    return <><button onClick={() => setOpen(true)}>Open deletion</button>{open && <DeletionDialog collection="organizations" entityId="org"
      onClose={() => setOpen(false)} onChanged={changed} onAttempt={attempt} />}</>;
  }
  render(<MemoryRouter initialEntries={page === "members" ? ["/members?organization_id=org"] : ["/"]}>
    <SessionProvider me={me} config={config} api={api} onSignOut={() => undefined}>
      {page === "subscriptions" ? <SubscriptionsPage /> : page === "organizations" ? <OrganizationsPage />
        : page === "users" ? <AdminLocalUsersPage /> : page === "members" ? <MembersPage /> : <Harness />}
    </SessionProvider>
  </MemoryRouter>);
  return { calls, changed, attempt };
}

async function fill(label = "Acme") {
  const dialog = await screen.findByRole("dialog");
  await within(dialog).findByText(label, { exact: true });
  await userEvent.type(within(dialog).getByLabelText("Type the exact record label"), label);
  await userEvent.type(within(dialog).getByLabelText("Audit reason"), "Retire account");
  return within(dialog);
}

describe("safe admin deletion", () => {
  it("requires exact typed label and a nonblank reason; cancellation never writes and restores focus", async () => {
    const { calls } = setup(() => preview);
    const trigger = screen.getByRole("button", { name: "Open deletion" });
    await userEvent.click(trigger);
    const dialog = within(await screen.findByRole("dialog"));
    expect(dialog.getByRole("button", { name: "Cancel" })).toHaveFocus();
    await dialog.findByText("Acme", { exact: true });
    const confirm = dialog.getByRole("button", { name: "Confirm deletion" });
    expect(confirm).toBeDisabled();
    await userEvent.type(dialog.getByLabelText("Type the exact record label"), "acme");
    await userEvent.type(dialog.getByLabelText("Audit reason"), "   ");
    expect(confirm).toBeDisabled();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
    expect(calls.every(c => c.init.method !== "DELETE")).toBe(true);
  });

  it("shows disabled/pending dependency counts and management links without enabling deletion", async () => {
    setup(() => ({ ...preview, can_delete: false, dependencies: { subscriptions: 2, users: 3, members: 4 }, blockers: ["Archive children first"] }));
    await userEvent.click(screen.getByRole("button", { name: "Open deletion" }));
    const d = await fill();
    expect(d.getByLabelText("Dependencies")).toHaveTextContent("Subscriptions: 2Local users: 3Memberships: 4");
    expect(d.getByRole("alert")).toHaveTextContent("Archive children first");
    expect(d.getByRole("link", { name: "Manage subscriptions" })).toHaveAttribute("href", "/subscriptions?organization_id=org");
    expect(d.getByRole("link", { name: "Manage local users" })).toHaveAttribute("href", "/local-users?organization_id=org");
    expect(d.getByRole("button", { name: "Confirm deletion" })).toBeDisabled();
  });

  it("latches double submission, disables cancel while busy and sends only the confirmed DELETE", async () => {
    let resolve!: (value: unknown) => void;
    const { calls, changed, attempt } = setup((_url, init) => init.method === "DELETE" ? new Promise(r => { resolve = r; }) : preview);
    await userEvent.click(screen.getByRole("button", { name: "Open deletion" }));
    const d = await fill();
    await userEvent.dblClick(d.getByRole("button", { name: "Confirm deletion" }));
    expect(d.getByRole("button", { name: "Cancel" })).toBeDisabled();
    await userEvent.keyboard("{Escape}");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(calls.filter(c => c.init.method === "DELETE")).toHaveLength(1);
    expect(attempt).toHaveBeenCalledTimes(1);
    const request = calls.find(c => c.init.method === "DELETE")!;
    expect(request.url.pathname).toBe("/api/admin/organizations/org");
    expect(JSON.parse(String(request.init.body))).toEqual({ confirmation: "Acme", reason: "Retire account" });
    await act(async () => resolve({ entity_id: "org", status: "archived", message: "History retained" }));
    expect(changed).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("retains a durable failed result and retries the same endpoint without losing confirmation", async () => {
    let deletes = 0;
    const { calls } = setup((_url, init) => init.method === "DELETE"
      ? ++deletes === 1 ? new Response(JSON.stringify({ entity_id: "org", status: "failed", message: "Revocation unverified" }), { status: 502 })
        : { entity_id: "org", status: "archived", message: "Verified" }
      : preview);
    await userEvent.click(screen.getByRole("button", { name: "Open deletion" }));
    const d = await fill();
    await userEvent.click(d.getByRole("button", { name: "Confirm deletion" }));
    expect(await d.findByRole("alert")).toHaveTextContent("Revocation unverified");
    expect(d.getByLabelText("Type the exact record label")).toHaveValue("Acme");
    await userEvent.click(d.getByRole("button", { name: "Retry deletion" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(calls.filter(c => c.init.method === "DELETE").map(c => c.url.pathname)).toEqual(["/api/admin/organizations/org", "/api/admin/organizations/org"]);
  });

  it("keeps pending outcomes visible rather than reporting terminal success", async () => {
    setup((_url, init) => init.method === "DELETE" ? { entity_id: "org", status: "pending", message: "Suspension not verified" } : preview);
    await userEvent.click(screen.getByRole("button", { name: "Open deletion" }));
    const d = await fill();
    await userEvent.click(d.getByRole("button", { name: "Confirm deletion" }));
    expect(await d.findByText(/pending: Suspension not verified/)).toBeInTheDocument();
    expect(d.getByRole("button", { name: "Retry deletion" })).toBeEnabled();
  });

  it("reloads new blockers after a server conflict without swallowing its error", async () => {
    let previews = 0;
    setup((_url, init) => init.method === "DELETE"
      ? new Response(JSON.stringify({ detail: { message: "Archive blocked", blockers: ["New child"], dependencies: { subscriptions: 1, users: 0, members: 0 } } }), { status: 409 })
      : ++previews === 1 ? preview : { ...preview, can_delete: false, blockers: ["New child"], dependencies: { subscriptions: 1, users: 0, members: 0 } });
    await userEvent.click(screen.getByRole("button", { name: "Open deletion" }));
    const d = await fill();
    await userEvent.click(d.getByRole("button", { name: "Confirm deletion" }));
    expect(await d.findByText("New child")).toBeInTheDocument();
    expect(await d.findByText("Archive blocked")).toBeInTheDocument();
    expect(d.getByRole("button", { name: "Confirm deletion" })).toBeDisabled();
  });

  it("shows preview failure with a safe reload and never writes", async () => {
    const { calls } = setup(() => new Response(JSON.stringify({ detail: "Forbidden" }), { status: 403 }));
    await userEvent.click(screen.getByRole("button", { name: "Open deletion" }));
    const d = within(await screen.findByRole("dialog"));
    expect(await d.findByRole("alert")).toHaveTextContent("Forbidden");
    expect(d.getByRole("button", { name: "Confirm deletion" })).toBeDisabled();
    expect(calls.every(c => c.init.method !== "DELETE")).toBe(true);
  });

  it("traps keyboard focus and restores preexisting background inert state", async () => {
    const outside = document.createElement("div"); outside.setAttribute("inert", "existing"); document.body.append(outside);
    try {
      setup(() => preview);
      await userEvent.click(screen.getByRole("button", { name: "Open deletion" }));
      const d = within(await screen.findByRole("dialog"));
      await d.findByText("Acme", { exact: true });
      d.getByRole("button", { name: "Reload preview" }).focus();
      await userEvent.tab();
      expect(d.getByRole("link", { name: "Manage subscriptions" })).toHaveFocus();
      await userEvent.keyboard("{Escape}");
      expect(outside.getAttribute("inert")).toBe("existing");
    } finally { outside.remove(); }
  });

  it("adds deletion to OrganizationsPage and refreshes the list after archive", async () => {
    const { calls } = setup(url => url.pathname.endsWith("deletion-preview") ? preview : { entity_id: "org", status: "archived", message: "Archived organization" }, "organizations");
    await userEvent.click(await screen.findByRole("button", { name: "Delete" }));
    const d = await fill();
    await userEvent.click(d.getByRole("button", { name: "Confirm deletion" }));
    expect(await screen.findByText("Archived organization")).toBeInTheDocument();
    expect(calls.filter(c => c.url.pathname === "/api/admin/organizations").length).toBeGreaterThan(1);
  });

  it("uses the existing local users page and never calls an Entra deletion endpoint", async () => {
    const user = { id: "user", email: "u@test.invalid", display_name: "User", organization_id: "org", organization_name: "Acme", role: "customer", enabled: false, created_at: sub.created_at };
    const { calls } = setup((url, init) => url.pathname.endsWith("deletion-preview") ? { ...preview, entity_type: "local_user", entity_id: "user", label: user.email }
      : init.method === "DELETE" ? { entity_id: "user", status: "archived", message: "Local user archived" } : { items: [user], total: 1 }, "users");
    await userEvent.click(await screen.findByRole("button", { name: "Delete" }));
    const d = await fill(user.email);
    await userEvent.click(d.getByRole("button", { name: "Confirm deletion" }));
    expect(await screen.findByText("Local user archived")).toBeInTheDocument();
    expect(calls.filter(c => c.init.method === "DELETE").map(c => c.url.pathname)).toEqual(["/api/admin/local-users/user"]);
  });

  it("clears revealed subscription keys before deletion and keeps failed revocation actions blocked", async () => {
    const { calls } = setup((url, init) => url.pathname.endsWith("deletion-preview") ? { ...preview, entity_type: "subscription", entity_id: "sub", label: "Finance" }
      : url.pathname.endsWith("reveal") ? { key: "memory-only-secret" }
        : init.method === "DELETE" ? new Response(JSON.stringify({ entity_id: "sub", status: "failed", message: "APIM unverified" }), { status: 502 })
          : { items: [sub], total: 1 }, "subscriptions");
    await screen.findByText("Finance");
    await userEvent.click(screen.getAllByRole("button", { name: "Reveal" })[0]!);
    await screen.findByLabelText("primary key value");
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(screen.queryByLabelText("primary key value")).not.toBeInTheDocument();
    const d = await fill("Finance");
    await userEvent.click(d.getByRole("button", { name: "Confirm deletion" }));
    expect(await d.findByRole("alert")).toHaveTextContent("APIM unverified");
    await userEvent.click(d.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("button", { name: "Reconcile" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reveal" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry deletion" })).toBeEnabled();
    expect(document.body.textContent).not.toContain("memory-only-secret");
    expect(calls.filter(c => c.init.method === "DELETE")).toHaveLength(1);
  });

  it("supports deletion of independent memberships through the existing Members page", async () => {
    const { calls } = setup((url, init) => url.pathname.endsWith("deletion-preview") ? { ...preview, entity_type: "member", entity_id: "member", label: "object-id" }
      : init.method === "DELETE" ? { entity_id: "member", status: "archived", message: "Member archived" }
        : { items: [{ id: "member", object_id: "object-id", organization_id: "org", enabled: false, role: "customer" }], total: 1 }, "members");
    await userEvent.click(await screen.findByRole("button", { name: "Delete" }));
    const d = await fill("object-id");
    await userEvent.click(d.getByRole("button", { name: "Confirm deletion" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(calls.filter(c => c.init.method === "DELETE").map(c => c.url.pathname)).toEqual(["/api/admin/members/member"]);
  });

  it("recovers pagination after archiving the last row on the final page", async () => {
    let removed = false;
    setup((url, init) => {
      if (url.pathname.endsWith("deletion-preview")) return { ...preview, entity_type: "subscription", entity_id: "sub", label: "Finance" };
      if (init.method === "DELETE") { removed = true; return { entity_id: "sub", status: "archived", message: "Subscription history retained" }; }
      const offset = Number(url.searchParams.get("offset") ?? 0);
      return { items: offset >= 25 ? removed ? [] : [sub] : Array.from({ length: 25 }, (_, i) => ({ ...sub, id: `sub-${i}`, name: `Finance ${i}` })), total: removed ? 25 : 26 };
    }, "subscriptions");
    await userEvent.click(await screen.findByRole("button", { name: "Next" }));
    await screen.findByText("Finance", { exact: true });
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    const d = await fill("Finance");
    await userEvent.click(d.getByRole("button", { name: "Confirm deletion" }));
    expect(await screen.findByText("Subscription history retained")).toBeInTheDocument();
    expect(await screen.findByText("Finance 0", { exact: true })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Next" })).not.toBeInTheDocument();
  });
});