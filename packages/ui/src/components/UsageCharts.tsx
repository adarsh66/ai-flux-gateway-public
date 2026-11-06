import { useEffect, useMemo, useState, type KeyboardEvent, type MouseEvent } from "react";
import type { UsageMinute, UsageSeries } from "../types";
import { fmtInt, NA } from "./ui";
import { bucketOrigin, bucketTimes, formatSgt } from "../time";

const CHART_WIDTH = 920;
const CHART_HEIGHT = 190;
const PADDING = { left: 48, right: 16, top: 16, bottom: 30 };
const TABLE_PAGE_SIZE = 25;
type Metric = "requests" | "tokens" | "latency";

interface Props {
  series: UsageSeries;
  start: number;
  end: number;
}

interface ChartDataProps extends Props {
  points: Map<number, UsageMinute>;
  times: number[];
  unit: string;
}

function minuteKey(value: string): number {
  return Date.parse(value);
}

function valueFor(point: UsageMinute | undefined, metric: Metric): number | null {
  if (!point) return metric === "latency" ? null : 0;
  if (metric === "requests") return point.requests;
  if (metric === "tokens") return point.total_tokens;
  return point.avg_e2e_seconds;
}

function formatMetric(value: number | null, metric: Metric, point?: UsageMinute): string {
  if (metric === "requests") return fmtInt(value);
  if (metric === "tokens") {
    if (value === null) return point?.requests ? `Missing (${fmtInt(point.missing_token_requests)} request(s))` : NA;
    return `${fmtInt(value)}${point?.missing_token_requests ? " (partial)" : ""}`;
  }
  return value === null ? "No latency samples" : `${value.toFixed(3)} s`;
}

function metricTitle(metric: Metric, unit: string): string {
  if (metric === "requests") return `Requests per ${unit}`;
  if (metric === "tokens") return `Tokens per ${unit}`;
  return `Average end-to-end latency per ${unit} (seconds)`;
}

function buildEnvelope(series: UsageSeries, metric: Metric, start: number, end: number) {
  const interval = series.interval_seconds * 1000;
  const times = bucketTimes(start, end, interval, bucketOrigin(series.bucket_origin));
  const range = Math.max(1, end - start);
  const minuteCount = Math.max(1, times.length);
  const bucketCount = Math.min(900, minuteCount);
  const reduced = times.length > 900;
  const indices = new Map(times.map((time, index) => [time, index]));
  const displayIndex = (time: number) => reduced
    ? Math.min(bucketCount - 1, Math.max(0, Math.floor(((time - start) / range) * bucketCount)))
    : indices.get(time);
  const buckets = Array.from({ length: bucketCount }, (_, index) => ({
    values: [] as number[], rows: 0,
    start: reduced ? start + index / bucketCount * range : times[index] ?? start,
    end: reduced ? start + (index + 1) / bucketCount * range : times[index + 1] ?? end,
  }));
  for (const point of series.items) {
    const time = minuteKey(point.minute);
    if (time < start || time >= end) continue;
    const index = displayIndex(time);
    if (index === undefined) continue;
    const bucket = buckets[index]!;
    bucket.rows++;
    const value = valueFor(point, metric);
    if (value !== null && Number.isFinite(value)) bucket.values.push(value);
  }
  if (metric !== "latency") {
    const expected = new Array<number>(bucketCount).fill(0);
    for (const time of times) expected[displayIndex(time)!]!++;
    buckets.forEach((bucket, index) => {
      if (bucket.rows < expected[index]!) bucket.values.push(0);
    });
  }
  return buckets;
}

function timeLabel(epoch: number): string {
  return formatSgt(epoch);
}

function MinuteTable({ start, end, metric, points, times, unit }: ChartDataProps & { metric: Metric }) {
  const [page, setPage] = useState(0);
  const count = times.length;
  const pageCount = Math.ceil(count / TABLE_PAGE_SIZE);
  useEffect(() => setPage(0), [start, end, metric, unit]);
  const rows = useMemo(() => {
    const first = page * TABLE_PAGE_SIZE;
    return Array.from({ length: Math.min(TABLE_PAGE_SIZE, count - first) }, (_, index) => {
      const time = times[first + index]!;
      const point = points.get(time);
      return { time, point, value: valueFor(point, metric) };
    });
  }, [points, times, count, page, metric]);
  return (
    <details className="chart-data">
      <summary>View exact {unit} data</summary>
      <div className="table-wrap">
        <table>
          <caption className="sr-only">{metricTitle(metric, unit)} {unit} data</caption>
          <thead><tr><th scope="col">SGT {unit} start (clipped)</th><th scope="col">Value</th><th scope="col">Data quality</th></tr></thead>
          <tbody>{rows.map((row) => (
            <tr key={row.time}>
              <td>{timeLabel(row.time)}{row.point?.partial_bucket ? " (partial interval)" : ""}</td>
              <td className="num">{formatMetric(row.value, metric, row.point)}</td>
              <td>{metric === "tokens" && row.point?.missing_token_requests
                ? `${fmtInt(row.point.missing_token_requests)} request(s) missing token usage`
                : metric === "latency" && row.value === null
                  ? "No latency samples"
                  : row.point ? "Measured" : "No requests"}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      <div className="chart-table-pager">
        <button className="btn" disabled={page === 0} onClick={() => setPage((p) => Math.max(0, p - 1))}>Earlier {unit}s</button>
        <span>{page + 1} of {pageCount}</span>
        <button className="btn" disabled={page + 1 >= pageCount} onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}>Later {unit}s</button>
      </div>
    </details>
  );
}

function ChartPanel({ series, start, end, metric, points, times, unit }: ChartDataProps & { metric: Metric }) {
  const [cursor, setCursor] = useState(start);
  const buckets = useMemo(() => buildEnvelope(series, metric, start, end), [series, metric, start, end]);
  useEffect(() => setCursor(start), [start, end, unit]);
  const point = points.get(cursor);
  const selected = valueFor(point, metric);
  const values = buckets.flatMap((bucket) => bucket.values);
  const maxValue = values.reduce((max, value) => Math.max(max, value), 0) || 1;
  const minValue = 0;
  const y = (value: number) => PADDING.top + ((maxValue - value) / (maxValue - minValue || 1)) * (CHART_HEIGHT - PADDING.top - PADDING.bottom);
  const plotWidth = CHART_WIDTH - PADDING.left - PADDING.right;
  const x = (time: number) => PADDING.left + ((time - start) / Math.max(1, end - start)) * plotWidth;
  const cursorIndex = Math.max(0, times.indexOf(cursor));
  const cursorX = x((cursor + (times[cursorIndex + 1] ?? end)) / 2);
  const reduced = times.length > buckets.length;
  const ticks = [0, 0.25, 0.5, 0.75, 1];
  const setCursorFromPosition = (event: MouseEvent<SVGSVGElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const svgX = rect.width > 0 ? ((event.clientX - rect.left) / rect.width) * CHART_WIDTH : PADDING.left;
    const fraction = (svgX - PADDING.left) / plotWidth;
    const clamped = Math.max(0, Math.min(1, fraction));
    const time = start + clamped * (end - start);
    setCursor(times.filter(value => value <= time).at(-1) ?? start);
  };
  const onKeyDown = (event: KeyboardEvent<SVGSVGElement>) => {
    const count = times.length - 1;
    const index = Math.max(0, times.indexOf(cursor));
    let next: number | undefined;
    if (event.key === "ArrowLeft" || event.key === "ArrowDown") next = times[Math.max(0, index - 1)];
    if (event.key === "ArrowRight" || event.key === "ArrowUp") next = times[Math.min(count, index + 1)];
    if (event.key === "Home") next = start;
    if (event.key === "End") next = times[count];
    if (next !== undefined) {
      event.preventDefault();
      setCursor(next);
    }
  };
  const metricText = formatMetric(selected, metric, point);

  return (
    <section className="chart-panel" aria-labelledby={`${metric}-chart-title`}>
      <h2 id={`${metric}-chart-title`}>{metricTitle(metric, unit)}</h2>
      <svg
        className="usage-chart"
        viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
        role="slider"
        aria-label={`${metricTitle(metric, unit)} chart. Use arrow keys for the previous or next ${unit}, Home for the start, and End for the latest ${unit}.`}
        aria-valuemin={start}
        aria-valuemax={times.at(-1) ?? start}
        aria-valuenow={cursor}
        aria-valuetext={`${timeLabel(cursor)}: ${metricText}`}
        tabIndex={0}
        onMouseMove={setCursorFromPosition}
        onFocus={() => setCursor(start)}
        onKeyDown={onKeyDown}
      >
        <title>{metricTitle(metric, unit)}. Zero-baseline bars{reduced ? "; peak summary after server aggregation" : ""}; {unit} values remain exact in the tooltip and data table.</title>
        {ticks.map((fraction) => {
          const gridY = PADDING.top + fraction * (CHART_HEIGHT - PADDING.top - PADDING.bottom);
          const value = maxValue - fraction * (maxValue - minValue);
          return <g key={fraction}><line className="chart-grid" x1={PADDING.left} x2={CHART_WIDTH - PADDING.right} y1={gridY} y2={gridY} /><text className="chart-axis-label" x={PADDING.left - 7} y={gridY + 4} textAnchor="end">{metric === "latency" ? `${value.toFixed(2)}s` : fmtInt(Math.round(value))}</text></g>;
        })}
        {buckets.map((bucket, index) => {
          if (!bucket.values.length) return null;
          const high = bucket.values.reduce((max, value) => Math.max(max, value), -Infinity);
          if (high <= 0) return null;
          // A minimum visible mark affects geometry only, never the measured value.
          const height = Math.min(CHART_HEIGHT - PADDING.top - PADDING.bottom, Math.max(1, y(0) - y(high)));
          const barWidth = Math.min(36, (x(bucket.end) - x(bucket.start)) * 0.72);
          return <rect key={index} className={`chart-mark ${metric}`} data-value={high}
            x={x((bucket.start + bucket.end) / 2) - barWidth / 2} y={y(0) - height} width={barWidth} height={height} />;
        })}
        <line className="chart-cursor" x1={cursorX} x2={cursorX} y1={PADDING.top} y2={CHART_HEIGHT - PADDING.bottom} />
        <text className="chart-axis-label" x={PADDING.left} y={CHART_HEIGHT - 7}>{timeLabel(start)}</text>
        <text className="chart-axis-label" x={CHART_WIDTH - PADDING.right} y={CHART_HEIGHT - 7} textAnchor="end">{timeLabel(end)}</text>
      </svg>
      <p className="chart-tooltip" role="status" aria-live="polite"><strong>{timeLabel(cursor)}</strong>: {metricText}{metric === "tokens" && point?.missing_token_requests ? `; partial, ${fmtInt(point.missing_token_requests)} request(s) missing token usage` : ""}{metric === "latency" && point ? `; ${fmtInt(point.latency_samples)} latency sample(s)` : ""}</p>
      {reduced && <p className="muted">Peak summary: at most 900 display groups; each bar shows the highest server-aggregated {unit} value in its group, not a sum or average. Exact {unit} values remain in the tooltip and table.</p>}
      <MinuteTable series={series} start={start} end={end} metric={metric} points={points} times={times} unit={unit} />
    </section>
  );
}

export function UsageCharts({ series, start, end }: Props) {
  // Legacy minute responses use the un-clipped UTC bucket start. Keep the
  // intersecting first row rather than presenting its measured values as idle.
  const alignedSeries = useMemo(() => series.bucket_origin ? series : {
    ...series,
    items: series.items.filter(item => {
      const time = minuteKey(item.minute);
      return time < end && time + series.interval_seconds * 1000 > start;
    }).map(item => minuteKey(item.minute) < start
      ? { ...item, minute: new Date(start).toISOString(), partial_bucket: true }
      : item),
  }, [series, start, end]);
  series = alignedSeries;
  const points = useMemo(() => new Map(series.items.map((item) => [minuteKey(item.minute), item])), [series.items]);
  const times = useMemo(() => bucketTimes(start, end, series.interval_seconds * 1000, bucketOrigin(series.bucket_origin)), [start, end, series.interval_seconds, series.bucket_origin]);
  const unit = series.interval_seconds === 86400 ? "day" : series.interval_seconds === 3600 ? "hour" : "minute";
  return (
    <div className="usage-charts" aria-label="Synchronized usage charts">
      <ChartPanel series={series} start={start} end={end} metric="requests" points={points} times={times} unit={unit} />
      <ChartPanel series={series} start={start} end={end} metric="tokens" points={points} times={times} unit={unit} />
      <ChartPanel series={series} start={start} end={end} metric="latency" points={points} times={times} unit={unit} />
    </div>
  );
}
