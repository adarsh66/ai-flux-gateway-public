import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { ControlApi } from "./client";
import { UsageCharts } from "./components/UsageCharts";
import { ModelTokenChart } from "./components/ModelTokenChart";
import { fmtDate, NA } from "./components/ui";
import { UsagePage } from "./pages/UsagePage";
import { validatePrice } from "./pages/admin";
import { SessionProvider } from "./session";
import { bucketCount, bucketOrigin, bucketTimes, defaultUsageGranularity, formatSgt, parseSgtInput, SGT_BUCKET_ORIGIN, UTC_BUCKET_ORIGIN, usageBucketNotice } from "./time";
import type { UsageSeries } from "./types";

describe("SGT display and input", () => {
  it("formats Singapore midnight across month and year boundaries independently of host timezone", () => {
    expect(formatSgt("2026-10-31T16:00:00Z")).toBe("2026-11-01 00:00 SGT");
    expect(formatSgt("2026-12-31T16:00:01Z", true)).toBe("2027-01-01 00:00:01 SGT");
    expect(formatSgt("2027-01-01T00:00:01+08:00", true)).toBe("2027-01-01 00:00:01 SGT");
    expect(fmtDate(null)).toBe(NA);
    expect(fmtDate(undefined)).toBe(NA);
    expect(fmtDate("invalid")).toBe("invalid");
    expect(fmtDate("2026-12-31T16:00:00Z")).toBe("2027-01-01 00:00:00 SGT");
  });
  it("strictly converts SGT wall inputs to UTC and rejects normalized calendar dates", () => {
    expect(parseSgtInput("2026-11-01T00:00")?.toISOString()).toBe("2026-10-31T16:00:00.000Z");
    expect(parseSgtInput("2024-02-29T23:59:58")?.toISOString()).toBe("2024-02-29T15:59:58.000Z");
    for (const value of ["2026-02-29T00:00", "2026-04-31T00:00", "2026-01-01T24:00", "2026-13-01T00:00", "2026-01-01T00:60", "2026-01-01T00:00:60", "2026-01-01T00:00Z", ""]) expect(parseSgtInput(value)).toBeNull();
    const form = { model: "m", provider: "p", region: "r", currency: "USD", effective_from: "2026-11-01T00:00", effective_to: "2026-11-02T00:00", input_per_million: "1", output_per_million: "2", cached_input_per_million: "", cache_write_per_million: "", input_includes_cached: "false" };
    const result = validatePrice(form);
    expect(result.ok && result.value.effective_from).toBe("2026-10-31T16:00:00.000Z");
    expect(result.ok && result.value.effective_to).toBe("2026-11-01T16:00:00.000Z");
    expect(validatePrice({ ...form, effective_from: "2026-02-30T00:00" }).ok).toBe(false);
  });
});

describe("semantic bucket lattice", () => {
  it("retains measured legacy UTC minute values in a clipped first viewport bucket", () => {
    const start = Date.parse("2026-10-01T16:00:17Z"), end = start + 60_000;
    render(<UsageCharts start={start} end={end} series={{ start: new Date(start).toISOString(), end: new Date(end).toISOString(), interval_seconds: 60, items: [
      { minute: "2026-10-01T16:00:00Z", requests: 11, input_tokens: 10, output_tokens: 1, total_tokens: 11, avg_e2e_seconds: 21 / 11, latency_samples: 11, missing_token_requests: 0 },
    ] }} />);
    expect(screen.getByRole("slider", { name: /Requests per minute/ })).toHaveAttribute("aria-valuetext", expect.stringContaining(": 11"));
    expect(screen.getByRole("slider", { name: /Average end-to-end/ })).toHaveAttribute("aria-valuetext", expect.stringContaining("1.909 s"));
  });
  it("counts edge buckets and keeps legacy UTC fallback and documented period defaults", () => {
    const start = Date.parse("2026-10-01T16:00:00Z");
    expect(bucketOrigin()).toBe(UTC_BUCKET_ORIGIN);
    expect(bucketOrigin("invalid")).toBe(UTC_BUCKET_ORIGIN);
    expect(bucketCount(start, start + 7 * 86400_000, 60_000, SGT_BUCKET_ORIGIN)).toBe(10080);
    expect(usageBucketNotice(start, start + 7 * 86400_000, "minute")).toBeUndefined();
    expect(usageBucketNotice(start + 1, start + 7 * 86400_000 + 1, "minute")).toContain("10,080");
    expect(usageBucketNotice(start + 1, start + 31 * 86400_000 + 1, "hour")).toContain("744");
    expect([1, 7, 30, 90].map(defaultUsageGranularity)).toEqual(["hour", "hour", "day", "day"]);
    expect(bucketTimes(start + 1234, start + 2 * 86400_000, 86400_000, SGT_BUCKET_ORIGIN)).toEqual([start + 1234, start + 86400_000]);
  });
  it.each([60, 3600, 86400])("uses interval %s with clipped first bucket, exact nulls and keyboard steps", async interval => {
    const origin = "1999-12-31T16:00:00Z";
    const boundary = Date.parse("2026-10-01T16:00:00Z");
    const start = boundary + 17_000, end = boundary + interval * 2000;
    const second = boundary + interval * 1000;
    const unit = interval === 60 ? "minute" : interval === 3600 ? "hour" : "day";
    const series: UsageSeries = { start: new Date(start).toISOString(), end: new Date(end).toISOString(), interval_seconds: interval, bucket_origin: origin, time_zone: "Asia/Singapore", items: [
      { minute: new Date(start).toISOString(), requests: 11, input_tokens: 10, output_tokens: 1, total_tokens: 11, avg_e2e_seconds: 21 / 11, latency_samples: 11, missing_token_requests: 0, partial_bucket: true },
      { minute: new Date(second).toISOString(), requests: 1, input_tokens: null, output_tokens: 1, total_tokens: null, avg_e2e_seconds: null, latency_samples: 0, missing_token_requests: 1 },
    ] };
    render(<UsageCharts series={series} start={start} end={end} />);
    const tokens = screen.getByRole("slider", { name: new RegExp(`Tokens per ${unit}`) });
    expect(tokens).toHaveAttribute("aria-valuetext", expect.stringContaining(": 11"));
    fireEvent.keyDown(tokens, { key: "ArrowRight" });
    expect(tokens).toHaveAttribute("aria-valuenow", String(second));
    expect(tokens).toHaveAttribute("aria-valuetext", expect.stringContaining("Missing (1 request(s))"));
    fireEvent.keyDown(tokens, { key: "End" });
    expect(tokens).toHaveAttribute("aria-valuenow", String(second));
    const latency = screen.getByRole("slider", { name: /Average end-to-end/ });
    expect(latency).toHaveAttribute("aria-valuetext", expect.stringContaining("1.909 s"));
    await userEvent.click(screen.getAllByText(`View exact ${unit} data`)[0]!);
    expect(screen.getAllByText(/2026-10-02 00:00 SGT \(partial interval\)/, { selector: "td" })).toHaveLength(3);
  });
  it("aligns model token daily rows to the supplied SGT origin including clipped partial rows", () => {
    const start = "2026-10-01T17:00:00Z", end = "2026-10-03T16:00:00Z";
    const { container } = render(<ModelTokenChart series={{ start, end, interval_seconds: 86400, time_zone: "Asia/Singapore", bucket_origin: "1999-12-31T16:00:00Z", items: [
      { start, end: "2026-10-02T16:00:00Z", model: "m", requests: 1, total_tokens: 5, missing_token_requests: 0, partial_bucket: true },
      { start: "2026-10-02T16:00:00Z", end, model: "m", requests: 1, total_tokens: 7, missing_token_requests: 0 },
    ] }} />);
    expect([...container.querySelectorAll("[data-bucket-total]")].map(node => node.getAttribute("data-bucket-total"))).toEqual(["5", "7"]);
    const slider = screen.getByRole("slider");
    expect(slider).toHaveAttribute("aria-valuetext", expect.stringContaining("2026-10-02 01:00 SGT"));
    fireEvent.keyDown(slider, { key: "ArrowRight" });
    expect(slider).toHaveAttribute("aria-valuetext", expect.stringContaining("2026-10-03 00:00 SGT"));
  });
  it("retains all 22 model fixtures and known zero versus missing token observations", () => {
    const models = ["gpt-5.6-luna", "gpt-5.4-mini", "DeepSeek-V4-Flash", "DeepSeek-V4-Pro", "FW-GLM-5.3", "FW-MiniMax-M3", "glm-5.3", "gpt-4o", "gpt-6.1-sol", "grok-4-1-fast-reasoning", "grok-4-20-reasoning", "grok-4.3", "Kimi-K2.7-Code", "claude-sonnet-5-5", "claude-opus-5-5", "claude-opus-5-5-fast", "claude-haiku-5-5", "gpt-6.1-terra", "gpt-6-luna", "claude-opus-4-8", "Mistral-Large-3", "mistral-medium-3-5"];
    const start = "2026-10-01T16:00:00Z", end = "2026-10-02T16:00:00Z";
    render(<ModelTokenChart series={{ start, end, interval_seconds: 86400, bucket_origin: "1999-12-31T16:00:00Z", time_zone: "Asia/Singapore", items: models.map((model, index) => ({
      start, end, model, requests: 1, total_tokens: index === 0 ? 0 : index === 1 ? null : index,
      missing_token_requests: index === 1 ? 1 : 0,
    })) }} />);
    expect(screen.getAllByRole("listitem")).toHaveLength(22);
    expect(screen.getByRole("slider")).toHaveAttribute("aria-valuetext", expect.stringContaining("gpt-5.6-luna: 0"));
    expect(screen.getByRole("slider")).toHaveAttribute("aria-valuetext", expect.stringContaining(`gpt-5.4-mini: ${NA} (partial)`));
  });
});

function mountUsage(handler?: (url: URL) => Promise<unknown> | unknown) {
  const urls: URL[] = [];
  const api = new ControlApi("/api", async () => "fixture", async input => {
    const url = new URL(String(input), "https://portal");
    urls.push(url);
    const custom = await handler?.(url);
    if (custom !== undefined) return new Response(JSON.stringify(custom));
    const result = url.pathname.endsWith("/decision-scoring") ? { status: "unavailable", notice: null, retention_notice: "Test fixture: scoring telemetry unavailable." }
      : url.pathname.endsWith("/models") ? { items: ["m"], total: 1 }
      : url.pathname.endsWith("/subscriptions") ? { items: [], total: 0 }
        : url.pathname.endsWith("/timeseries") || url.pathname.endsWith("/model-tokens") ? {
          items: [], start: url.searchParams.get("start"), end: url.searchParams.get("end"),
          interval_seconds: url.searchParams.get("granularity") === "day" ? 86400 : url.searchParams.get("granularity") === "hour" ? 3600 : 60,
          time_zone: "Asia/Singapore", bucket_origin: "1999-12-31T16:00:00Z",
        } : { items: [], total: 0, summary: { requests: 0, input_tokens: 0, output_tokens: 0, known_cost: null, currency: null, incomplete_requests: 0, failed_requests: 0, throttled_requests: 0, e2e_p95_ms: null, ttft_supported: false, cache_tokens_supported: false, last_ingested_at: null } };
    return new Response(JSON.stringify(result));
  });
  render(<MemoryRouter><SessionProvider api={api} config={{ clientId: "c", authority: "a", apiScope: "s", controlApiUrl: "/api", gatewayUrl: "https://example.invalid" }} me={{ organization_id: "o", organization_name: "Fixture", tenant_id: "t", object_id: "u", role: "customer" }} onSignOut={() => undefined}><UsagePage /></SessionProvider></MemoryRouter>);
  return urls;
}

describe("usage granularity requests and stale protection", () => {
  it("synchronizes three charts with independent token control and blocks oversized requests without coarsening", async () => {
    const urls = mountUsage();
    await screen.findByRole("heading", { name: "Requests per day" });
    expect(screen.getByLabelText("Usage chart granularity")).toHaveValue("day");
    expect(urls.filter(url => url.pathname.endsWith("/timeseries")).at(-1)?.searchParams.get("time_zone")).toBe("Asia/Singapore");
    const count = urls.filter(url => url.pathname.endsWith("/timeseries")).length;
    await userEvent.selectOptions(screen.getByLabelText("Usage chart granularity"), "minute");
    expect(await screen.findByText(/Usage chart: This viewport exceeds 10,080/)).toBeInTheDocument();
    expect(urls.filter(url => url.pathname.endsWith("/timeseries"))).toHaveLength(count);
    expect(screen.getByLabelText("Usage chart granularity")).toHaveValue("minute");
    await userEvent.selectOptions(screen.getByLabelText("Period"), "7");
    await screen.findByRole("heading", { name: "Requests per hour" });
    await userEvent.selectOptions(screen.getByLabelText("Usage chart granularity"), "minute");
    await screen.findByRole("heading", { name: "Requests per minute" });
    expect(screen.getByRole("heading", { name: "Tokens per minute" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Average end-to-end latency per minute (seconds)" })).toBeInTheDocument();
    expect(screen.getByLabelText("Token chart granularity")).toHaveValue("day");
    const usageCount = urls.filter(url => url.pathname.endsWith("/timeseries")).length;
    await userEvent.selectOptions(screen.getByLabelText("Token chart granularity"), "hour");
    await waitFor(() => expect(urls.filter(url => url.pathname.endsWith("/model-tokens")).at(-1)?.searchParams.get("granularity")).toBe("hour"));
    expect(urls.filter(url => url.pathname.endsWith("/timeseries"))).toHaveLength(usageCount);
    await userEvent.selectOptions(screen.getByLabelText("Model"), "m");
    expect(screen.getByLabelText("Usage chart granularity")).toHaveValue("minute");
  });
  it("rejects stale day responses after selecting hour", async () => {
    let finish!: (value: unknown) => void;
    mountUsage(url => url.pathname.endsWith("/timeseries") && url.searchParams.get("granularity") === "day"
      ? new Promise(resolve => { finish = resolve; }) : undefined);
    await waitFor(() => expect(finish).toBeDefined());
    await userEvent.selectOptions(screen.getByLabelText("Period"), "1");
    await screen.findByRole("heading", { name: "Requests per hour" });
    await act(async () => finish({ items: [], start: "2026-10-01T00:00:00Z", end: "2026-10-02T00:00:00Z", interval_seconds: 86400 }));
    expect(screen.queryByRole("heading", { name: "Requests per day" })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Requests per hour" })).toBeInTheDocument();
  });
});