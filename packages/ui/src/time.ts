/** Display/input policy only. API and CSV instants remain UTC. */
export const DISPLAY_TIME_ZONE = "Asia/Singapore" as const;
export const UTC_BUCKET_ORIGIN = Date.UTC(2000, 0, 1);
export const SGT_BUCKET_ORIGIN = Date.UTC(1999, 11, 31, 16);

const formatter = new Intl.DateTimeFormat("en-SG", {
  timeZone: DISPLAY_TIME_ZONE, hourCycle: "h23",
  year: "numeric", month: "2-digit", day: "2-digit",
  hour: "2-digit", minute: "2-digit", second: "2-digit",
});

export function formatSgt(value: string | number, seconds = false): string {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return String(value);
  const parts = Object.fromEntries(formatter.formatToParts(date).map(part => [part.type, part.value]));
  return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}${seconds ? `:${parts.second}` : ""} SGT`;
}

/** Strict datetime-local calendar parsing, independent of the host timezone. */
export function parseSgtInput(value: string): Date | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?$/.exec(value);
  if (!match) return null;
  const [year, month, day, hour, minute, second] = match.slice(1).map(part => Number(part ?? 0));
  if (!year || month! < 1 || month! > 12 || day! < 1 || day! > 31 || hour! > 23 || minute! > 59 || second! > 59) return null;
  const calendar = new Date(0);
  calendar.setUTCFullYear(year, month! - 1, day);
  calendar.setUTCHours(hour!, minute!, second!, 0);
  if (calendar.getUTCFullYear() !== year || calendar.getUTCMonth() !== month! - 1 || calendar.getUTCDate() !== day) return null;
  return new Date(calendar.getTime() - 8 * 3600_000);
}

export function bucketOrigin(origin?: string): number {
  const parsed = origin ? Date.parse(origin) : NaN;
  return Number.isFinite(parsed) ? parsed : UTC_BUCKET_ORIGIN;
}

export function bucketCount(start: number, end: number, interval: number, origin: number): number {
  return Math.max(0, Math.ceil((end - origin) / interval) - Math.floor((start - origin) / interval));
}

/** Exact semantic bucket coordinates; the first coordinate is clipped to the viewport. */
export function bucketTimes(start: number, end: number, interval: number, origin: number): number[] {
  if (!(interval > 0) || !Number.isFinite(interval) || !(end > start)) return [];
  const first = origin + Math.floor((start - origin) / interval) * interval;
  return Array.from({ length: bucketCount(start, end, interval, origin) }, (_, index) => Math.max(start, first + index * interval));
}

export type UsageGranularity = "minute" | "hour" | "day";
export const usageInterval = (granularity: UsageGranularity) => ({ minute: 60_000, hour: 3600_000, day: 86400_000 })[granularity];
export const defaultUsageGranularity = (days: number): UsageGranularity => days <= 7 ? "hour" : "day";
export function usageBucketNotice(start: number, end: number, granularity: UsageGranularity): string | undefined {
  const limit = granularity === "minute" ? 10080 : 744;
  return bucketCount(start, end, usageInterval(granularity), SGT_BUCKET_ORIGIN) > limit
    ? `This viewport exceeds ${limit.toLocaleString("en-US")} ${granularity} buckets. Zoom in to narrow the viewport or select Day; granularity has not been changed.`
    : undefined;
}