import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { ControlApi } from "./client";
import { ModelTokenChart } from "./components/ModelTokenChart";
import { NA } from "./components/ui";
import { UsagePage } from "./pages/UsagePage";
import { SessionProvider } from "./session";
import type { ModelTokenSeries } from "./types";

const start = "2026-10-01T00:00:00Z", end = "2026-10-01T00:03:00Z";
const series: ModelTokenSeries = {
  start, end, interval_seconds: 60,
  items: [
    { start, end: "2026-10-01T00:01:00Z", model: "alpha", total_tokens: 100, requests: 1, missing_token_requests: 0 },
    { start, end: "2026-10-01T00:01:00Z", model: "beta", total_tokens: 50, requests: 2, missing_token_requests: 1 },
    { start: "2026-10-01T00:02:00Z", end, model: "beta", total_tokens: null, requests: 1, missing_token_requests: 1 },
  ],
};

describe("ModelTokenChart", () => {
  it("stacks exact known totals, fills idle buckets, and labels missing observations rather than zeros", async () => {
    const { container } = render(<ModelTokenChart series={series} />);
    expect([...container.querySelectorAll("[data-bucket-total]")].map(el => el.getAttribute("data-bucket-total"))).toEqual(["150", "0", "0"]);
    expect([...container.querySelectorAll("[data-tokens]")].map(el => Number(el.getAttribute("data-tokens")))).toEqual([100, 50]);
    const alpha = container.querySelector('rect[data-model="alpha"]')!;
    const beta = container.querySelector('rect[data-model="beta"]')!;
    expect(Number(alpha.getAttribute("height"))).toBeCloseTo(2 * Number(beta.getAttribute("height")));
    expect(Number(beta.getAttribute("y")) + Number(beta.getAttribute("height"))).toBeCloseTo(Number(alpha.getAttribute("y")));
    expect(screen.getByText(/Partial data: 2 request/)).toBeInTheDocument();
    expect(within(screen.getByRole("list", { name: "Model legend" })).getAllByRole("listitem")).toHaveLength(2);
    const slider = screen.getByRole("slider", { name: /Token consumption by model/ });
    fireEvent.keyDown(slider, { key: "ArrowRight" });
    expect(slider).toHaveAttribute("aria-valuenow", "1");
    expect(slider).toHaveAttribute("aria-valuetext", expect.stringContaining("No measured total available"));
    fireEvent.keyDown(slider, { key: "End" });
    expect(slider).toHaveAttribute("aria-valuetext", expect.stringContaining(`beta: ${NA} (partial)`));
    fireEvent.keyDown(slider, { key: "Home" });
    expect(slider).toHaveAttribute("aria-valuetext", expect.stringContaining("150 known tokens (partial)"));
    await userEvent.click(screen.getByText("View exact model token data"));
    const table = screen.getByRole("table");
    expect(within(table).getAllByText(`${NA} (partial)`)).toHaveLength(2);
    expect(within(table).getByText("150 (partial)")).toBeInTheDocument();
  });

  it("renders an empty viewport without inventing models or measured usage", () => {
    render(<ModelTokenChart series={{ ...series, items: [] }} />);
    expect(screen.getByText("No measured token rows available; ingestion health is not confirmed.")).toBeInTheDocument();
    expect(screen.queryByRole("slider")).not.toBeInTheDocument();
  });

  it("only describes an idle bucket as zero when source health is confirmed", () => {
    render(<ModelTokenChart series={{ ...series, health: { status: "healthy", last_query_success_at: start,
      last_row_ingested_at: start, watermark: end, lag_seconds: 0, expected_delay_seconds: 300 } }} />);
    const slider = screen.getByRole("slider");
    fireEvent.keyDown(slider, { key: "ArrowRight" });
    expect(slider).toHaveAttribute("aria-valuetext", expect.stringContaining("0 known tokens"));
    fireEvent.keyDown(slider, { key: "End" });
    expect(slider).toHaveAttribute("aria-valuetext", expect.stringContaining("No measured total available"));
  });

  it("keeps 744 hourly buckets and all eleven models without downsampling", () => {
    const from = "2026-09-01T00:00:00Z", to = "2026-10-02T00:00:00Z";
    const { container } = render(<ModelTokenChart series={{ start: from, end: to, interval_seconds: 3600,
      items: Array.from({ length: 11 }, (_, i) => ({ start: from, end: "2026-09-01T01:00:00Z",
        model: `model-${i}`, requests: 1, total_tokens: i + 1, missing_token_requests: 0 })) }} />);
    expect(container.querySelectorAll("[data-bucket-total]")).toHaveLength(744);
    expect(screen.getAllByRole("listitem")).toHaveLength(11);
    expect(container.querySelector("[data-bucket-total]")).toHaveAttribute("data-bucket-total", "66");
  });

  it("labels unattributed telemetry explicitly without losing its token count", () => {
    render(<ModelTokenChart series={{ ...series, items: [{ ...series.items[0]!, model: "" }] }} />);
    expect(within(screen.getByRole("list", { name: "Model legend" })).getByText("Unknown model")).toBeVisible();
    expect(screen.getByRole("slider")).toHaveAttribute("aria-valuetext", expect.stringContaining("Unknown model: 100"));
  });

  it("keeps every model and assigns repeated palette entries a distinct pattern", () => {
    const { container } = render(<ModelTokenChart series={{ ...series, items: Array.from({ length: 9 }, (_, index) => ({
      start, end: "2026-10-01T00:01:00Z", model: `model-${index}`, total_tokens: index + 1,
      requests: 1, missing_token_requests: 0,
    })) }} />);
    expect(screen.getAllByRole("listitem")).toHaveLength(9);
    expect(container.querySelectorAll("[data-tokens]")).toHaveLength(9);
    expect(container.querySelectorAll("pattern path").length).toBeGreaterThan(0);
    expect(container.querySelector("[data-bucket-total]")).toHaveAttribute("data-bucket-total", "45");
  });
});

function mount(handler: (url: URL) => unknown | Promise<unknown>, admin = false) {
  const urls: URL[] = [];
  const api = new ControlApi("/api", async () => "fixture", async (input) => {
    const url = new URL(String(input), "https://portal");
    urls.push(url);
    const result = await handler(url);
    return result instanceof Response ? result : new Response(JSON.stringify(result));
  });
  render(<MemoryRouter><SessionProvider
    me={{ organization_id: "org", organization_name: "Fixture", tenant_id: "t", object_id: "u", role: admin ? "ids_admin" : "customer" }}
    config={{ clientId: "c", authority: "a", apiScope: "s", controlApiUrl: "/api", gatewayUrl: "https://example.invalid" }}
    api={api} onSignOut={() => undefined}><UsagePage admin={admin} />
  </SessionProvider></MemoryRouter>);
  return urls;
}

// Match model_token_response: requested granularity, SGT epoch and clipped edges.
// Never stretch the three-minute component fixture over a monthly viewport.
function requestedModelSeries(url: URL, items: ModelTokenSeries["items"] = []): ModelTokenSeries {
  const from = Date.parse(url.searchParams.get("start")!);
  const to = Date.parse(url.searchParams.get("end")!);
  const time_zone = url.searchParams.get("time_zone") === "Asia/Singapore" ? "Asia/Singapore" : "UTC";
  const bucket_origin = time_zone === "Asia/Singapore" ? "1999-12-31T16:00:00Z" : "2000-01-01T00:00:00Z";
  const origin = Date.parse(bucket_origin);
  const granularity = url.searchParams.get("granularity") ?? "auto";
  const count = (seconds: number) => Math.ceil((to - origin) / (seconds * 1000)) - Math.floor((from - origin) / (seconds * 1000));
  const interval_seconds = granularity === "hour" ? 3600 : granularity === "day" ? 86400
    : [60, 300, 900, 3600, 21600, 43200, 86400, 604800].find(seconds => count(seconds) <= 120)!;
  if (!(from < to) || !interval_seconds || count(interval_seconds) > 744) throw new Error("Unsupported fixture viewport");
  const interval = interval_seconds * 1000;
  const first = origin + Math.floor((from - origin) / interval) * interval;
  const last = origin + (Math.ceil((to - origin) / interval) - 1) * interval;
  return {
    start: new Date(from).toISOString(), end: new Date(to).toISOString(), interval_seconds,
    granularity: granularity as ModelTokenSeries["granularity"], time_zone, bucket_origin,
    items: items.map((item, index) => {
      const bucket = index === items.length - 1 && items.length > 1 ? last : first;
      return { ...item, start: new Date(Math.max(from, bucket)).toISOString(),
        end: new Date(Math.min(to, bucket + interval)).toISOString(),
        partial_bucket: bucket < from || bucket + interval > to };
    }),
  };
}

function response(url: URL) {
  if (url.pathname === "/api/admin/usage/organization-costs") return { items: [], total: 0 };
  if (url.pathname.endsWith("/decision-scoring")) return { status: "unavailable", notice: null, retention_notice: "Test fixture: scoring telemetry unavailable." };
  if (url.pathname.endsWith("/rankings")) return { items: [], total: 0, totals: { requests: 0, total_tokens: null, missing_token_requests: 0, incomplete_requests: 0 } };
  if (url.pathname.endsWith("/models")) return { items: ["alpha", "beta"], total: 2 };
  if (url.pathname.endsWith("/subscriptions")) return { items: [{ id: "sub", name: "Team" }], total: 1 };
  if (url.pathname.endsWith("/organizations")) return { items: [], total: 0 };
  if (url.pathname.endsWith("/timeseries")) return {
    items: [], start: url.searchParams.get("start"), end: url.searchParams.get("end"), interval_seconds: 60,
  };
  if (url.pathname.endsWith("/model-tokens")) return requestedModelSeries(url);
  return { items: [{
    id: "request", subscription_id: "sub", model: "beta", provider: "test", region: "test", occurred_at: start,
    input_tokens: 1, output_tokens: 2, cached_input_tokens: null, cache_write_tokens: null,
    cost: null, currency: null, status_code: 200, e2e_ms: null, ttft_ms: null, completeness: "complete",
  }], total: 100, summary: {
    requests: 100, input_tokens: 0, output_tokens: 0, known_cost: null, currency: null,
    incomplete_requests: 0, failed_requests: 0, throttled_requests: 0, e2e_p95_ms: null,
    ttft_supported: false, cache_tokens_supported: false, last_ingested_at: null,
  } };
}

describe("customer model-token integration", () => {
  it("uses one aggregate request, follows filters and viewport, and ignores request pagination", async () => {
    const urls = mount(response);
    await screen.findByRole("heading", { name: "Token consumption by model" });
    expect(screen.getByRole("heading", { name: "Token share by model" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Tokens per minute" })).toBeInTheDocument();
    const requests = () => urls.filter(url => url.pathname.endsWith("/model-tokens"));
    expect(requests()).toHaveLength(1);
    await userEvent.selectOptions(screen.getByLabelText("Model"), "beta");
    await waitFor(() => expect(requests().at(-1)!.searchParams.get("model")).toBe("beta"));
    await userEvent.selectOptions(screen.getByLabelText("Subscription"), "sub");
    await waitFor(() => expect(requests().at(-1)!.searchParams.get("subscription_id")).toBe("sub"));
    await userEvent.selectOptions(screen.getByLabelText("Period"), "7");
    await waitFor(() => expect(requests().at(-1)!.searchParams.get("days")).toBe("7"));
    const previous = requests().at(-1)!.searchParams.get("start");
    await userEvent.click(screen.getByRole("button", { name: "Zoom in" }));
    await waitFor(() => expect(requests().at(-1)!.searchParams.get("start")).not.toBe(previous));
    const count = requests().length;
    await userEvent.click(screen.getByText("Transaction details"));
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => expect(urls.some(url => url.searchParams.get("offset") === "50")).toBe(true));
    expect(requests()).toHaveLength(count);
  });

  it("requests and displays the shared chart in admin showback", async () => {
    const urls = mount(response, true);
    await screen.findByRole("heading", { name: "Tokens per minute" });
    await screen.findByRole("heading", { name: "Token consumption by model" });
    expect(screen.queryByRole("heading", { name: "Token share by model" })).not.toBeInTheDocument();
    expect(document.querySelector(".customer-usage-page")).not.toBeInTheDocument();
    expect(urls.some(url => url.pathname === "/api/admin/usage/model-tokens" && url.searchParams.get("granularity") === "day")).toBe(true);
  });

  it("passes organization and explicit SGT granularity to admin aggregation", async () => {
    const urls = mount(url => url.pathname.endsWith("/organizations") ? { items: [{ id: "org-selected", name: "Selected" }], total: 1 } : response(url), true);
    await screen.findByRole("heading", { name: "Token consumption by model" });
    await userEvent.selectOptions(screen.getByLabelText("Organization"), "org-selected");
    await userEvent.selectOptions(screen.getByLabelText("Period"), "7");
    await userEvent.selectOptions(screen.getByLabelText("Token chart granularity"), "hour");
    await waitFor(() => expect(urls.some(url => url.pathname === "/api/admin/usage/model-tokens"
      && url.searchParams.get("organization_id") === "org-selected" && url.searchParams.get("granularity") === "hour"
      && url.searchParams.get("time_zone") === "Asia/Singapore")).toBe(true));
    await userEvent.selectOptions(screen.getByLabelText("Period"), "1");
    expect(screen.getByLabelText("Token chart granularity")).toHaveValue("hour");
  });

  it("shows errors explicitly and retries without hiding existing charts", async () => {
    let fail = true;
    mount(url => url.pathname.endsWith("/model-tokens") && fail
      ? new Response(JSON.stringify({ detail: "Token aggregation unavailable" }), { status: 503 }) : response(url));
    expect(await screen.findByText("Token aggregation unavailable")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Tokens per minute" })).toBeInTheDocument();
    fail = false;
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    await screen.findByRole("heading", { name: "Token consumption by model" });
    expect(screen.queryByText("Token aggregation unavailable")).not.toBeInTheDocument();
  });

  it("ignores stale aggregate responses after a model change", async () => {
    let resolveOld: ((value: unknown) => void) | undefined;
    mount(url => {
      if (url.pathname.endsWith("/model-tokens") && !url.searchParams.get("model"))
        return new Promise(resolve => { resolveOld = resolve; });
      return response(url);
    });
    await waitFor(() => expect(resolveOld).toBeDefined());
    await userEvent.selectOptions(screen.getByLabelText("Model"), "beta");
    await screen.findByRole("heading", { name: "Token consumption by model" });
    await act(async () => resolveOld!({ ...series, items: [{ ...series.items[0]!, model: "STALE" }] }));
    expect(screen.queryByText("STALE")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Token share by model" })).toBeInTheDocument();
  });

  it("shares the filtered aggregate across every bucket, not the transaction page, and hides shares on fetch errors", async () => {
    let fail = false;
    const urls = mount(url => {
      if (!url.pathname.endsWith("/model-tokens")) return response(url);
      if (fail) return new Response(JSON.stringify({ detail: "Share aggregation unavailable" }), { status: 503 });
      const model = url.searchParams.get("model");
      return requestedModelSeries(url, series.items.filter(item => !model || item.model === model));
    });
    await screen.findByRole("heading", { name: "Token share by model" });
    let table = screen.getByRole("table", { name: /Exact model token shares/ });
    expect(within(table).getByText("66.7%")).toBeInTheDocument();
    expect(document.querySelectorAll("[data-bucket-total]").length).toBeLessThanOrEqual(32);
    expect(document.querySelectorAll("[data-bucket-total]").length).toBeGreaterThan(0);
    await userEvent.selectOptions(screen.getByLabelText("Model"), "beta");
    await waitFor(() => expect(screen.getByRole("table", { name: /Exact model token shares/ })).not.toHaveTextContent("alpha"));
    table = screen.getByRole("table", { name: /Exact model token shares/ });
    expect(within(table).getByText("100.0%")).toBeInTheDocument();
    const count = urls.filter(url => url.pathname.endsWith("/model-tokens")).length;
    await userEvent.click(screen.getByText("Transaction details"));
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => expect(urls.some(url => url.searchParams.get("offset") === "50")).toBe(true));
    expect(urls.filter(url => url.pathname.endsWith("/model-tokens"))).toHaveLength(count);
    expect(screen.getByRole("table", { name: /Exact model token shares/ })).toHaveTextContent("100.0%");
    fail = true;
    await userEvent.click(screen.getByRole("button", { name: "Refresh telemetry" }));
    await screen.findByText("Share aggregation unavailable");
    expect(screen.queryByRole("heading", { name: "Token share by model" })).not.toBeInTheDocument();
  });

  it("hides old shares during a new scope fetch and for an oversized hourly token viewport", async () => {
    let resolveNext: ((value: unknown) => void) | undefined;
    mount(url => url.pathname.endsWith("/model-tokens") && url.searchParams.get("model") === "beta"
      ? new Promise(resolve => { resolveNext = () => resolve(requestedModelSeries(url, series.items.filter(item => item.model === "beta"))); }) : response(url));
    await screen.findByRole("heading", { name: "Token share by model" });
    await userEvent.selectOptions(screen.getByLabelText("Model"), "beta");
    await waitFor(() => expect(resolveNext).toBeDefined());
    expect(screen.queryByRole("heading", { name: "Token share by model" })).not.toBeInTheDocument();
    await act(async () => resolveNext!({ ...series, items: series.items.filter(item => item.model === "beta") }));
    await screen.findByRole("heading", { name: "Token share by model" });
    await userEvent.selectOptions(screen.getByLabelText("Period"), "90");
    await userEvent.selectOptions(screen.getByLabelText("Token chart granularity"), "hour");
    await waitFor(() => expect(screen.queryByRole("heading", { name: "Token share by model" })).not.toBeInTheDocument());
    expect(screen.getByText(/^Token chart:/)).toBeInTheDocument();
  });
});

describe("requested model-token fixture contract", () => {
  it.each(["day", "hour"])("honors %s granularity, SGT origin, clipped viewport and unknown totals", granularity => {
    const url = new URL("https://portal/api/usage/model-tokens");
    url.search = new URLSearchParams({ start: "2026-10-01T00:30:00Z", end: "2026-10-31T00:30:00Z",
      time_zone: "Asia/Singapore", granularity }).toString();
    const result = requestedModelSeries(url, series.items);
    const seconds = granularity === "day" ? 86400 : 3600;
    expect(result.interval_seconds).toBe(seconds);
    expect(result.bucket_origin).toBe("1999-12-31T16:00:00Z");
    expect(result.time_zone).toBe("Asia/Singapore");
    expect(result.start).toBe("2026-10-01T00:30:00.000Z");
    expect(result.end).toBe("2026-10-31T00:30:00.000Z");
    expect(result.items[0]!.start).toBe(result.start);
    expect(result.items.at(-1)!.end).toBe(result.end);
    expect(result.items[0]!.partial_bucket).toBe(true);
    expect(result.items.at(-1)!.partial_bucket).toBe(true);
    expect(result.items.map(item => item.total_tokens)).toEqual([100, 50, null]);
    expect(result.items.map(item => item.missing_token_requests)).toEqual([0, 1, 1]);
    expect(result.health).toBeUndefined();
    const buckets = Math.ceil((Date.parse(result.end) - Date.parse(result.bucket_origin!)) / (seconds * 1000))
      - Math.floor((Date.parse(result.start) - Date.parse(result.bucket_origin!)) / (seconds * 1000));
    expect(buckets).toBe(granularity === "day" ? 31 : 721);
    expect(buckets).toBeLessThanOrEqual(744);
  });

  it("rejects an hourly viewport the server would reject instead of masking its bucket guard", () => {
    const url = new URL("https://portal/api/usage/model-tokens?start=2026-08-01T00:00:00Z&end=2026-10-31T00:00:00Z&granularity=hour&time_zone=Asia/Singapore");
    expect(() => requestedModelSeries(url)).toThrow("Unsupported fixture viewport");
  });
});
