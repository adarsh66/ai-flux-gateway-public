import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { ControlApi } from "../client";
import { SessionProvider } from "../session";
import type { DecisionScoringTelemetry } from "../types";
import { ModelsPage } from "../pages/ModelsPage";
import { UsagePage } from "../pages/UsagePage";
import { DecisionScoringUsage } from "./DecisionScoringUsage";
import * as ui from "./ui";

const query = { days: 1, start: "2026-10-30T16:00:00Z", end: "2026-10-31T16:00:00Z", granularity: "hour" as const, time_zone: "Asia/Singapore" as const };
const aggregate = { invocations: 2, input_tokens: 100, output_tokens: 0, total_tokens: 100 };
const scoring = (overrides: Partial<DecisionScoringTelemetry> = {}): DecisionScoringTelemetry => ({
  model: "Decision-1", source: "log_analytics", status: "partial", notice: "Some estimates missing.", retention_notice: "Log Analytics retention applies.",
  start: query.start, end: query.end, granularity: "hour", time_zone: "Asia/Singapore", offset: 0, limit: 50, total: 51,
  summary: { ...aggregate, measured_invocations: 2, missing_token_invocations: 0, estimated_cost_usd: null, recorded_cost_usd: null, estimated_invocations: 0, unestimated_invocations: 2, avg_latency_ms: 12, pricing_revision: "revision" },
  items: [{ id: "trace", parent_request_id: "parent-correlation", subscription_id: "sub-a", organization_id: "org-a", occurred_at: query.start, routing_profile: "balanced", selected_model: "chat-a", config_version: "config-hash", input_tokens: 100, output_tokens: 0, total_tokens: 100, latency_ms: 12, recorded_cost_usd: null, estimated_cost_usd: null, estimate_basis: "unestimated", pricing_revision: "revision", parent_status_code: 200, usage_kind: "decision_scoring" }],
  series: [{ ...aggregate, start: query.start, end: query.end, partial_bucket: true, avg_latency_ms: 12 }],
  breakdown: [{ ...aggregate, organization_id: "org-a", subscription_id: "sub-a", estimated_cost_usd: null }], ...overrides,
});

function fixture(url: URL): unknown {
  if (url.pathname.endsWith("/decision-scoring")) return scoring();
  if (url.pathname.endsWith("/export.csv")) return new Response("metadata,value\nmodel,Decision-1\n\nid\ntrace", { headers: { "Content-Type": "text/csv" } });
  if (url.pathname.endsWith("/organizations")) return { items: [{ id: "org-a", name: "Alpha" }, { id: "org-b", name: "Beta" }], total: 2 };
  if (url.pathname.endsWith("/subscriptions")) return { items: [], total: 0 };
  if (url.pathname.endsWith("/models")) return { items: ["chat-a", "Decision-1", "Decision-1"], total: 3 };
  if (url.pathname.endsWith("/rankings")) return { items: [], total: 0, totals: aggregate };
  if (url.pathname.endsWith("/timeseries") || url.pathname.endsWith("/model-tokens")) return { items: [], start: query.start, end: query.end, interval_seconds: 86400 };
  return { items: [], total: 0, summary: { requests: 0, input_tokens: 0, output_tokens: 0, total_tokens: 0, known_cost: null, currency: null, incomplete_requests: 0, failed_requests: 0, throttled_requests: 0, e2e_p95_ms: null, ttft_supported: false, cache_tokens_supported: false, last_ingested_at: null } };
}

function setup(handler: (url: URL) => unknown | Promise<unknown> = fixture, admin = false) {
  const urls: URL[] = [];
  const api = new ControlApi("/api", async () => "test", async input => {
    const url = new URL(String(input), "https://test.invalid");
    urls.push(url);
    const data = await handler(url);
    return data instanceof Response ? data : new Response(JSON.stringify(data));
  });
  const wrap = (children: ReactNode) => <SessionProvider api={api} onSignOut={() => undefined}
    me={{ organization_id: "org-a", organization_name: "Alpha", tenant_id: "t", object_id: "u", role: admin ? "ids_admin" : "customer" }}
    config={{ clientId: "c", authority: "a", apiScope: "s", controlApiUrl: "/api", gatewayUrl: "https://test.invalid" }}>{children}</SessionProvider>;
  return { api, urls, wrap };
}

afterEach(() => vi.restoreAllMocks());

describe("Decision-1 frontend integration", () => {
  it.each([false, true])("keeps Decision-1 unique and excludes completion calls when selected (admin=%s)", async admin => {
    const { urls, wrap } = setup(fixture, admin);
    render(wrap(<UsagePage admin={admin} />));
    await screen.findByRole("option", { name: "chat-a" });
    expect(screen.getAllByRole("option", { name: "Decision-1" })).toHaveLength(1);
    await screen.findByText("parent-correlation");
    expect(screen.getByText(/Completion-only totals/)).toBeVisible();
    expect(screen.getByRole("button", { name: "Export completion-only CSV" })).toBeVisible();
    await userEvent.selectOptions(screen.getByLabelText("Model"), "Decision-1");
    await screen.findByText("parent-correlation");
    expect(screen.queryByRole("button", { name: "Export completion-only CSV" })).not.toBeInTheDocument();
    expect(screen.queryByText("Transaction details")).not.toBeInTheDocument();
    expect(screen.queryByText("Completion usage over time")).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Organizations by token usage (global)" })).not.toBeInTheDocument();
    const mark = urls.length;
    await userEvent.click(screen.getByRole("button", { name: "Refresh telemetry" }));
    await waitFor(() => expect(urls.slice(mark).some(url => url.pathname.endsWith("/decision-scoring"))).toBe(true));
    expect(urls.slice(mark).some(url => /\/(usage|timeseries|model-tokens|rankings)$/.test(url.pathname))).toBe(false);
    expect(urls.every(url => url.searchParams.get("model") !== "Decision-1")).toBe(true);
    const beforeZoom = urls.filter(url => url.pathname.endsWith("/decision-scoring")).at(-1)!.searchParams.get("start");
    await userEvent.click(screen.getByRole("button", { name: "Zoom in" }));
    await waitFor(() => expect(urls.filter(url => url.pathname.endsWith("/decision-scoring")).at(-1)!.searchParams.get("start")).not.toBe(beforeZoom));
    await userEvent.selectOptions(screen.getByLabelText("Usage chart granularity"), "hour");
    await waitFor(() => expect(urls.filter(url => url.pathname.endsWith("/decision-scoring")).at(-1)!.searchParams.get("granularity")).toBe("hour"));
  });

  it("offers scoring even without a historical-model response", async () => {
    const { wrap } = setup(url => url.pathname.endsWith("/models") ? new Response("{}", { status: 503 }) : fixture(url));
    render(wrap(<UsagePage />));
    await userEvent.selectOptions(screen.getByLabelText("Model"), "Decision-1");
    await screen.findByText("parent-correlation");
    expect(screen.getByLabelText("Model")).toHaveValue("Decision-1");
  });

  it("renders partial null money, details and pre-page aggregate rankings without inventing totals", async () => {
    const { wrap } = setup(() => scoring({ breakdown: [
      { ...aggregate, organization_id: "org", subscription_id: "small", total_tokens: 1, estimated_cost_usd: null },
      { ...aggregate, organization_id: "org", subscription_id: "large", total_tokens: 900, estimated_cost_usd: "0.0000001" },
      { ...aggregate, organization_id: "org", subscription_id: "unknown", total_tokens: null, estimated_cost_usd: null },
    ] }));
    render(wrap(<DecisionScoringUsage query={query} />));
    await screen.findByText("Telemetry partial");
    expect(screen.getByText("Recorded scoring cost").nextElementSibling).toHaveTextContent("Unknown");
    expect(screen.getByText("Estimated scoring cost").nextElementSibling).toHaveTextContent("Unknown");
    expect(screen.getByText("config-hash")).toBeVisible();
    expect(screen.getByText("parent-correlation")).toBeVisible();
    expect(screen.getByText(/Source completeness is unknown/)).toBeVisible();
    const rows = within(screen.getByRole("region", { name: "Scoring organization and subscription showback" })).getAllByRole("row");
    expect(rows[1]).toHaveTextContent("large");
    expect(rows[3]).toHaveTextContent("unknown");
    expect(screen.getByRole("img", { name: /Decision-1 scoring token chart in SGT/ })).toBeVisible();
  });

  it("treats unavailable telemetry as unknown, not zero", async () => {
    const { wrap } = setup(() => scoring({ status: "unavailable", items: [], series: [], breakdown: [], total: null, summary: { ...scoring().summary, invocations: null, input_tokens: null, output_tokens: null, total_tokens: null } }));
    render(wrap(<DecisionScoringUsage query={query} />));
    await screen.findByText("Scoring telemetry unavailable");
    expect(screen.getByText(/Counts, tokens, latency and cost are unknown, not zero/)).toBeVisible();
    expect(screen.queryByText("Scoring invocations")).not.toBeInTheDocument();
  });

  it("retries API failures and distinguishes an available empty query from complete source coverage", async () => {
    let fail = true;
    const { wrap } = setup(() => fail ? new Response(JSON.stringify({ detail: "Scoring query unavailable" }), { status: 503 }) : scoring({
      status: "available", notice: null, items: [], series: [], breakdown: [], total: 0,
      summary: { ...scoring().summary, invocations: 0, input_tokens: 0, output_tokens: 0, total_tokens: 0, measured_invocations: 0, estimated_invocations: 0, unestimated_invocations: 0, avg_latency_ms: null },
    }));
    render(wrap(<DecisionScoringUsage query={query} />));
    await screen.findByText("Scoring query unavailable");
    expect(screen.getByRole("button", { name: "Export scoring page CSV" })).toBeDisabled();
    fail = false;
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    await screen.findByText("Telemetry available");
    expect(screen.getByText("Scoring invocations", { selector: "dt" }).nextElementSibling).toHaveTextContent("0");
    expect(screen.getByText(/No observed traces is not proof of no scoring activity/)).toBeVisible();
    expect(screen.getByText(/Source completeness is unknown/)).toBeVisible();
  });

  it("exports the displayed page through the scoring route with identical scope, viewport and granularity", async () => {
    const download = vi.spyOn(ui, "downloadBlob").mockImplementation(() => undefined);
    const { wrap, urls } = setup(fixture, true);
    render(wrap(<DecisionScoringUsage admin query={{ ...query, organization_id: "org-a", subscription_id: "sub-a" }} />));
    await screen.findByText("parent-correlation");
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => expect(urls.at(-1)!.searchParams.get("offset")).toBe("50"));
    await waitFor(() => expect(screen.getByRole("button", { name: "Export scoring page CSV" })).toBeEnabled());
    await userEvent.click(screen.getByRole("button", { name: "Export scoring page CSV" }));
    await waitFor(() => expect(download).toHaveBeenCalled());
    const csv = urls.find(url => url.pathname.endsWith("/export.csv"))!;
    const page = urls.filter(url => url.pathname.endsWith("/decision-scoring")).at(-1)!;
    expect(csv.pathname).toBe("/api/admin/usage/decision-scoring/export.csv");
    expect(csv.search).toBe(page.search);
    expect(csv.searchParams.get("offset")).toBe("50");
    expect(csv.searchParams.get("time_zone")).toBe("Asia/Singapore");
    expect(csv.searchParams.has("model")).toBe(false);
  });

  it("discards a late response from the previous scope", async () => {
    let resolveOld!: (value: unknown) => void;
    const { wrap } = setup(url => url.searchParams.get("organization_id") === "old" ? new Promise(resolve => { resolveOld = resolve; }) : scoring({ items: [] }), true);
    const view = render(wrap(<DecisionScoringUsage key="old" admin query={{ ...query, organization_id: "old" }} />));
    await waitFor(() => expect(resolveOld).toBeDefined());
    view.rerender(wrap(<DecisionScoringUsage key="new" admin query={{ ...query, organization_id: "new" }} />));
    await screen.findByText("No scoring traces on this page");
    await act(async () => resolveOld(scoring()));
    expect(screen.queryByText("parent-correlation")).not.toBeInTheDocument();
  });

  it("does not send customer organization overrides", async () => {
    const { api, urls } = setup();
    await api.decisionScoring({ ...query, organization_id: "foreign", subscription_id: "sub-a" });
    await api.exportDecisionScoringCsv(false, { ...query, organization_id: "foreign" });
    expect(urls.every(url => !url.searchParams.has("organization_id"))).toBe(true);
    expect(urls[0]!.pathname).toBe("/api/usage/decision-scoring");
  });

  it.each([false, true])("renders the existing 22 chat models plus a separate unknown-availability scorer (admin=%s)", async admin => {
    const chats = Array.from({ length: 22 }, (_, i) => ({ id: `chat-${i}`, provider: "fixture", capabilities: ["chat"], enabled: true }));
    const { wrap, urls } = setup(url => {
      if (url.pathname.endsWith("/model-garden")) return { items: [{ id: "Decision-1", display_name: "Decision-1 scorer", provider: "fixture", model_kind: "scoring", capabilities: [], enabled: false, scoring_available: null }], total: 1 };
      if (url.pathname.endsWith("/models")) return { items: chats, total: 22 };
      return { items: [], total: 0 };
    }, admin);
    render(wrap(<ModelsPage admin={admin} />));
    await screen.findByText("Decision-1 scorer");
    const catalog = screen.getByRole("list", { name: "Model availability" });
    expect(within(catalog).getAllByRole("listitem")).toHaveLength(23);
    expect(screen.getByText("Scoring availability unknown")).toBeVisible();
    expect(within(catalog).queryByRole("link", { name: /chat|playground/i })).not.toBeInTheDocument();
    expect(urls.some(url => url.pathname === (admin ? "/api/admin/model-garden" : "/api/model-garden"))).toBe(true);
  });
});