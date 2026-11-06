import { fireEvent, render, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { UsageCharts } from "./components/UsageCharts";
import { bucketTimes, SGT_BUCKET_ORIGIN } from "./time";
import type { UsageSeries } from "./types";

describe("UsageCharts partial semantic buckets", () => {
  it.each([60, 3600, 86400])("keeps two populated partial buckets distinct at %i seconds with exact data and matching cursors", seconds => {
    const interval = seconds * 1000;
    const boundary = Date.parse("2026-10-30T16:00:00Z");
    // Both starts fell into the old first equal-range fraction: floor(.2 * 2) = 0.
    const start = boundary - interval * .2, end = boundary + interval * .8;
    const times = bucketTimes(start, end, interval, SGT_BUCKET_ORIGIN);
    expect(times).toEqual([start, boundary]);
    const series: UsageSeries = { start: new Date(start).toISOString(), end: new Date(end).toISOString(),
      interval_seconds: seconds, bucket_origin: new Date(SGT_BUCKET_ORIGIN).toISOString(), time_zone: "Asia/Singapore",
      items: times.map((time, index) => ({ minute: new Date(time).toISOString(), requests: [1, 15][index]!,
        input_tokens: 0, output_tokens: 0, total_tokens: [164, 1412][index]!,
        avg_e2e_seconds: [3.641, 3.292][index]!, missing_token_requests: 0, latency_samples: [1, 15][index]!, partial_bucket: true })) };
    const { container } = render(<UsageCharts series={series} start={start} end={end} />);
    const metrics = ["requests", "tokens", "latency"];
    const values = [[1, 15], [164, 1412], [3.641, 3.292]];
    const exact = [["1", "15"], ["164", "1,412"], ["3.641 s", "3.292 s"]];
    for (const [index, panel] of [...container.querySelectorAll(".chart-panel")].entries()) {
      const bars = [...panel.querySelectorAll(`rect.${metrics[index]}`)];
      expect(bars.map(bar => Number(bar.getAttribute("data-value")))).toEqual(values[index]);
      const geometry = bars.map(bar => ({x: Number(bar.getAttribute("x")), width: Number(bar.getAttribute("width"))}));
      expect(geometry[0]!.x + geometry[0]!.width).toBeLessThan(geometry[1]!.x);
      for (const bar of geometry) { expect(bar.width).toBeGreaterThan(0); expect(bar.x).toBeGreaterThanOrEqual(48); expect(bar.x + bar.width).toBeLessThanOrEqual(904); }
      const slider = within(panel as HTMLElement).getByRole("slider");
      const cursor = panel.querySelector(".chart-cursor")!;
      for (let row = 0; row < 2; row++) {
        fireEvent.keyDown(slider, {key: row ? "End" : "Home"});
        expect(slider).toHaveAttribute("aria-valuenow", String(times[row]));
        expect(slider).toHaveAttribute("aria-valuetext", expect.stringContaining(exact[index]![row]!));
        expect(Number(cursor.getAttribute("x1"))).toBeCloseTo(geometry[row]!.x + geometry[row]!.width / 2, 8);
        // jsdom's zero-width SVG rect takes the safe left-edge fallback; override only geometry for mouse mapping.
        const bounds = slider.getBoundingClientRect;
        slider.getBoundingClientRect = () => ({left:0, width:920} as DOMRect);
        fireEvent.mouseMove(slider, {clientX:geometry[row]!.x + geometry[row]!.width / 2});
        expect(slider).toHaveAttribute("aria-valuenow", String(times[row]));
        slider.getBoundingClientRect = bounds;
      }
      const rows = [...panel.querySelectorAll("tbody tr")];
      expect(rows).toHaveLength(2);
      expect(rows.map(row => row.querySelector("td.num")!.textContent)).toEqual(exact[index]);
      expect(rows.every(row => row.textContent!.includes("partial interval"))).toBe(true);
    }
    expect(container.textContent).not.toContain("Peak summary:");
  });

  it("keeps very short first and last partial widths proportional without overlap", () => {
    const boundary = Date.parse("2026-10-30T16:00:00Z"), interval = 60000;
    const start = boundary - 1, end = boundary + interval + 3;
    const times = bucketTimes(start, end, interval, SGT_BUCKET_ORIGIN);
    const {container} = render(<UsageCharts start={start} end={end} series={{start:new Date(start).toISOString(), end:new Date(end).toISOString(),
      interval_seconds:60, bucket_origin:new Date(SGT_BUCKET_ORIGIN).toISOString(), items:times.map(time => ({minute:new Date(time).toISOString(),
        requests:1, input_tokens:1, output_tokens:1, total_tokens:2, avg_e2e_seconds:1, latency_samples:1, missing_token_requests:0}))}} />);
    const bars = [...container.querySelectorAll("rect.requests")];
    expect(bars).toHaveLength(3);
    expect(Number(bars[2]!.getAttribute("width")) / Number(bars[0]!.getAttribute("width"))).toBeCloseTo(3, 7);
    for (let i=1; i<bars.length; i++) expect(Number(bars[i-1]!.getAttribute("x")) + Number(bars[i-1]!.getAttribute("width"))).toBeLessThan(Number(bars[i]!.getAttribute("x")));
  });
});