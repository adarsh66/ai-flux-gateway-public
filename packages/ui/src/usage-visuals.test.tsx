import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { ModelTokenShare, shareLabel, tokenShares } from "./components/ModelTokenShare";
import { UsageCharts } from "./components/UsageCharts";
import type { ModelTokenSeries, UsageSeries } from "./types";

const start = "2026-10-30T16:00:00Z";
const from = Date.parse(start);
function tokens(values: Array<[string, number | null, number?]>): ModelTokenSeries {
  return { start, end: "2026-10-31T16:00:00Z", interval_seconds: 86400,
    time_zone: "Asia/Singapore", bucket_origin: "1999-12-31T16:00:00Z",
    health: { status: "healthy", last_query_success_at: start, last_row_ingested_at: start,
      watermark: start, lag_seconds: 0, expected_delay_seconds: 300 },
    items: values.map(([model, total_tokens, missing_token_requests = 0]) => ({
      start, end: "2026-10-31T16:00:00Z", model, total_tokens, requests: 1,
      missing_token_requests, input_tokens: 9999, output_tokens: 9999,
    })) };
}

describe("usage visual bars", () => {
  it.each([60, 3600, 86400])("uses finite bounded zero-baseline bars and exact SGT cursors at interval %i", interval => {
    const end = from + interval * 4000;
    const series: UsageSeries = { start, end: new Date(end).toISOString(), interval_seconds: interval,
      bucket_origin: "1999-12-31T16:00:00Z", time_zone: "Asia/Singapore",
      items: [2, 2, null, 0].map((value, index) => ({
        minute: new Date(from + index * interval * 1000).toISOString(), requests: index === 3 ? 0 : 1,
        input_tokens: value, output_tokens: value, total_tokens: value, avg_e2e_seconds: value,
        latency_samples: value === null ? 0 : 1, missing_token_requests: value === null ? 1 : 0,
      })) };
    const { container } = render(<UsageCharts series={series} start={from} end={end} />);
    for (const mark of container.querySelectorAll("rect.chart-mark")) {
      for (const attr of ["x", "y", "width", "height"]) expect(Number.isFinite(Number(mark.getAttribute(attr)))).toBe(true);
      const x = Number(mark.getAttribute("x")), y = Number(mark.getAttribute("y"));
      const width = Number(mark.getAttribute("width")), height = Number(mark.getAttribute("height"));
      expect(x).toBeGreaterThanOrEqual(48);
      expect(x + width).toBeLessThanOrEqual(904);
      expect(width).toBeGreaterThan(0);
      expect(width).toBeLessThanOrEqual(36);
      expect(y).toBeGreaterThanOrEqual(16);
      expect(y + height).toBe(160);
      expect(height).toBeGreaterThan(0);
    }
    expect(container.querySelectorAll("rect.latency")).toHaveLength(2);
    expect(container.querySelectorAll("rect.tokens")).toHaveLength(2);
    expect(container.querySelectorAll("rect.latency")[0]).toHaveAttribute("height", "144");
    expect(container.querySelectorAll(".chart-mark[data-value='0']")).toHaveLength(0);
    expect(screen.queryByText(/Peak summary:/)).not.toBeInTheDocument();
    const latency = screen.getByRole("slider", { name: /Average end-to-end/ });
    fireEvent.keyDown(latency, { key: "ArrowRight" });
    fireEvent.keyDown(latency, { key: "ArrowRight" });
    expect(latency).toHaveAttribute("aria-valuetext", expect.stringContaining("No latency samples"));
    fireEvent.keyDown(latency, { key: "End" });
    expect(latency).toHaveAttribute("aria-valuetext", expect.stringContaining("0.000 s"));
    expect(within(latency).getByText("0.00s")).toBeInTheDocument();
  });

  it("caps groups at 900, labels peak reduction only then, and retains exact counts", () => {
    const end = from + 1000 * 60000;
    const items = Array.from({ length: 1000 }, (_, i) => ({ minute: new Date(from + i * 60000).toISOString(),
      requests: 1, input_tokens: 1, output_tokens: 1, total_tokens: i === 9 ? 1000000000 : 2,
      avg_e2e_seconds: i === 9 ? 200 : 0.00001, missing_token_requests: 0, latency_samples: 1 }));
    const { container } = render(<UsageCharts start={from} end={end} series={{ start, end: new Date(end).toISOString(), interval_seconds: 60, items }} />);
    expect(container.querySelectorAll("rect.chart-mark").length).toBeLessThanOrEqual(2700);
    expect(screen.getAllByText(/Peak summary:/)).toHaveLength(3);
    for (const metric of ["requests", "tokens", "latency"]) {
      const marks = [...container.querySelectorAll(`rect.${metric}`)];
      for (let i = 1; i < marks.length; i++) expect(Number(marks[i]!.getAttribute("x"))).toBeGreaterThan(
        Number(marks[i - 1]!.getAttribute("x")) + Number(marks[i - 1]!.getAttribute("width")));
    }
    const slider = screen.getByRole("slider", { name: /Tokens per minute/ });
    for (let i = 0; i < 9; i++) fireEvent.keyDown(slider, { key: "ArrowRight" });
    expect(slider).toHaveAttribute("aria-valuetext", expect.stringContaining("1,000,000,000"));
    expect(container.querySelector("rect.latency[data-value='0.00001']")).toHaveAttribute("height", "1");
  });
});

describe("customer model token share", () => {
  it("rejects unsafe, non-finite, negative and fractional totals without component-token substitution", () => {
    const data = tokens([["negative", -1], ["fraction", 1.5], ["infinite", Infinity], ["nan", NaN], ["unsafe", Number.MAX_SAFE_INTEGER + 1], ["known", 3]]);
    const result = tokenShares(data);
    expect(result.total).toBe(3n);
    expect(result.rows.filter(row => row.known).map(row => row.model)).toEqual(["known"]);
    expect(result.partial).toBe(true);
    const { container } = render(<ModelTokenShare series={data} />);
    expect(container.querySelectorAll("[data-share-model]")).toHaveLength(1);
    expect(screen.getAllByText("Unknown", { selector: "td" })).toHaveLength(10);
  });

  it("uses exact BigInt totals above the safe-number sum and contiguous true angles", () => {
    const data = tokens([["alpha", Number.MAX_SAFE_INTEGER], ["alpha", Number.MAX_SAFE_INTEGER], ["beta", 3]]);
    expect(tokenShares(data).total).toBe(18014398509481985n);
    const { container } = render(<ModelTokenShare series={data} />);
    const arcs = [...container.querySelectorAll("[data-share-model]")];
    let offset = 0;
    for (const arc of arcs) {
      const percent = Number(arc.getAttribute("stroke-dasharray")!.split(" ")[0]);
      expect(Number(arc.getAttribute("stroke-dashoffset"))).toBeCloseTo(-offset, 12);
      expect(Number.isFinite(percent)).toBe(true);
      offset += percent;
    }
    expect(offset).toBeCloseTo(100, 12);
    expect(screen.getByRole("img")).toHaveAccessibleName("Token share by model");
    expect(screen.getByRole("img")).toHaveAccessibleDescription(expect.stringContaining("no minimum angle"));
  });

  it("parses responsive scoped CSS, resolves every new theme token and provides focus and overflow affordances", () => {
    const css = readFileSync(resolve(process.cwd(), "packages/ui/src/styles.css"), "utf8");
    const begin = css.indexOf("/* Customer Usage only:");
    const end = css.indexOf("\n.gate {", begin);
    const owned = css.slice(begin, end);
    expect(begin).toBeGreaterThan(0);
    expect(end).toBeGreaterThan(begin);
    const defined = new Set([...css.matchAll(/(--[\w-]+)\s*:/g)].map(match => match[1]));
    // This per-model property is supplied inline, not by a global theme.
    const { container } = render(<div className="customer-usage-page"><ModelTokenShare series={tokens([["theme-probe", 1]])} /></div>);
    const row = container.querySelector("tbody tr") as HTMLElement;
    const shareColor = row.style.getPropertyValue("--share-color");
    expect(shareColor).toMatch(/^var\(--[\w-]+\)$/);
    expect(defined.has(shareColor.slice(4, -1))).toBe(true);
    defined.add("--share-color");
    for (const match of owned.matchAll(/var\((--[\w-]+)\)/g)) expect(defined.has(match[1])).toBe(true);
    const style = document.createElement("style");
    style.textContent = owned;
    document.head.append(style);
    try {
      const rules = [...style.sheet!.cssRules];
      expect(rules.length).toBeGreaterThan(20);
      for (const rule of rules) {
        if ("selectorText" in rule) expect(String(rule.selectorText).split(",").every(selector => selector.trim().startsWith(".customer-usage-page"))).toBe(true);
      }
      expect(owned).toContain("@media (max-width: 720px)");
      expect(owned).toContain("grid-template-columns: minmax(0, 1fr)");
      expect(owned).toContain("tr:focus-visible");
      expect(owned).toContain("overflow-wrap: anywhere");
      expect(owned).not.toMatch(/NaN|undefined|Infinity/);
      for (const token of ["--teal-500", "--info", "--ok", "--warn", "--bad", "--ink-dim"]) {
        for (const theme of ["daylight", "obsidian", "crimson", "emerald"]) {
          const block = css.slice(css.indexOf(`[data-theme="${theme}"]`)).split("}")[0]!;
          expect(block).toContain(`${token}:`);
        }
      }
    } finally { style.remove(); }
  });

  it("sums paired totals across all items exactly and exposes percentages plus keyboard-focusable rows", () => {
    const series = tokens([["alpha", 100], ["beta", 50], ["alpha", 50]]);
    const { container } = render(<ModelTokenShare series={series} />);
    expect(tokenShares(series).total).toBe(200n);
    const table = screen.getByRole("table");
    const alpha = within(table).getByRole("rowheader", { name: "alpha" }).closest("tr")!;
    expect(within(alpha).getByText("150")).toBeInTheDocument();
    expect(within(alpha).getByText("75.0%")).toBeInTheDocument();
    alpha.focus(); expect(alpha).toHaveFocus();
    expect(container.querySelector("[data-share-model='alpha']")).toHaveAttribute("stroke-dasharray", "75 25");
    expect(screen.getByText(/not provider-billed tokens/)).toBeInTheDocument();
  });

  it("renders all 22 models without Other or minimum angles, including tiny positive shares", () => {
    const data = tokens(Array.from({ length: 22 }, (_, i) => [`model-${i}`, i ? 1 : 1000000]));
    const { container } = render(<ModelTokenShare series={data} />);
    expect(screen.getAllByRole("rowheader")).toHaveLength(22);
    expect(container.querySelectorAll("[data-share-model]")).toHaveLength(22);
    expect(screen.getAllByText("<0.1%", { selector: "td" })).toHaveLength(21);
    expect(Number(container.querySelector("[data-share-model='model-1']")!.getAttribute("stroke-dasharray")!.split(" ")[0])).toBeLessThan(.001);
    expect(screen.queryByRole("rowheader", { name: "Other" })).not.toBeInTheDocument();
    expect(screen.getByText(/may not sum to 100%/)).toBeInTheDocument();
  });

  it("keeps null-only models unknown, explicit zero unsliced, and partial known totals in an honest denominator", () => {
    const { container } = render(<ModelTokenShare series={tokens([["unknown", null, 1], ["zero", 0], ["partial", 7, 1]])} />);
    expect(container.querySelectorAll("[data-share-model]")).toHaveLength(1);
    expect(container.querySelector("[data-share-model='partial']")).toHaveAttribute("stroke-dasharray", "100 0");
    const row = screen.getByRole("rowheader", { name: "unknown" }).closest("tr")!;
    expect(within(row).getAllByText("Unknown")).toHaveLength(2);
    expect(screen.getByText(/unknown totals are excluded/)).toBeInTheDocument();
    expect(screen.getByText("0.0%")).toBeInTheDocument();
  });

  it.each(["stale", "unverified", "disabled", "error"] as const)("reports %s source health without inventing traffic", status => {
    const data = tokens([]);
    render(<ModelTokenShare series={{ ...data, health: { ...data.health!, status } }} />);
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.getByText(/No measured token total available/)).toBeInTheDocument();
    expect(screen.getByText(new RegExp(`Telemetry ${status}:`))).toBeInTheDocument();
  });

  it("distinguishes known zero from all-unknown and keeps appearance stable after filtering", () => {
    const { container, rerender } = render(<ModelTokenShare series={tokens([["alpha", 2], ["beta", 3]])} />);
    const before = container.querySelector("tbody tr:last-child")!.getAttribute("style");
    rerender(<ModelTokenShare series={tokens([["beta", 3]])} />);
    expect(container.querySelector("tbody tr")!.getAttribute("style")).toBe(before);
    expect(screen.getByText("100.0%")).toBeInTheDocument();
    rerender(<ModelTokenShare series={tokens([["beta", 0]])} />);
    expect(screen.getByText(/Known measured token total is zero/)).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    rerender(<ModelTokenShare series={tokens([["beta", null]])} />);
    expect(screen.getByText(/No measured token total available/)).toBeInTheDocument();
    expect(shareLabel(1n, 100000n)).toBe("<0.1%");
  });
});