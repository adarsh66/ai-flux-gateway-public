import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, it } from "vitest";
import { ControlApi } from "./client";
import { DeploymentStatus } from "./components/DeploymentStatus";
import { SessionProvider } from "./session";

it("shows external GLM as pending, unpriced and unavailable without exposing credentials", async () => {
  const api = new ControlApi("/api", async () => "synthetic-session", async () => new Response(JSON.stringify({
    verified_at: "2026-10-26", auto_enabled: false, items: [{
      id: "glm-5.3", provider: "ModelArts", model_name: "glm-5.3", model_version: "Unverified",
      role: "chat", status: "pending-verification", chat_selectable: false,
      pricing_status: "unknown", credential_healthy: false,
      limitation: "External ModelArts processing; PII redaction is best-effort, not anonymization.",
    }],
  }), { status: 200 }));
  render(<MemoryRouter><SessionProvider
    me={{ organization_id: "org", organization_name: "Test", tenant_id: "tenant", object_id: "user", role: "ids_admin" }}
    api={api} config={{ clientId: "c", authority: "a", apiScope: "s", controlApiUrl: "/api", gatewayUrl: "https://gateway.invalid/dev/llm/v1" }}
    onSignOut={() => undefined}>
    <DeploymentStatus />
  </SessionProvider></MemoryRouter>);
  expect(await screen.findByText("pending-verification")).toBeInTheDocument();
  expect(screen.getByText(/Pending — external route unavailable/)).toBeInTheDocument();
  expect(screen.getByText("Price: unknown")).toBeInTheDocument();
  expect(screen.getByText(/not anonymization/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /play|enable|key/i })).not.toBeInTheDocument();
  expect(document.body.textContent).not.toContain("vault.azure.net");
});