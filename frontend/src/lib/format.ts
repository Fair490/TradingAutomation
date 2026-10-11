/**
 * Formatting and data transformation utilities.
 */

import type { Interval } from "./api";
export type { Interval } from "./api";

/**
 * Format a number with commas for thousands.
 */
export function num(value: number | null | undefined, decimals = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toLocaleString("en-IN", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

/**
 * Format a number in compact notation (K, M, B).
 */
export function compact(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const abs = Math.abs(value);
  if (abs >= 1e9) return (value / 1e9).toFixed(2) + "B";
  if (abs >= 1e7) return (value / 1e6).toFixed(1) + "M";
  if (abs >= 1e5) return (value / 1e6).toFixed(2) + "M";
  if (abs >= 1e3) return (value / 1e3).toFixed(1) + "K";
  return value.toFixed(0);
}

/**
 * Format a signed number with + or - prefix and optional suffix.
 */
export function signed(value: number | null | undefined, decimals = 2, suffix = ""): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const prefix = value > 0 ? "+" : "";
  return prefix + value.toFixed(decimals) + suffix;
}

/**
 * Format a date for display (medium format).
 */
export function mediumDate(dateStr: string | null | undefined): string {
  if (!dateStr) return "—";
  const d = new Date(dateStr);
  return d.toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

/**
 * Format a date for axis labels (short format).
 */
export function axisDate(dateStr: string, span?: number): string {
  const d = new Date(dateStr);
  // If span is very large, show less detail
  if (span && span > 365) {
    return d.toLocaleDateString("en-IN", {
      month: "short",
      year: "2-digit",
    });
  }
  return d.toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
  });
}

/**
 * Thin an array to a maximum number of points.
 */
export function thin<T>(arr: T[], maxPoints = 520): T[] {
  if (arr.length <= maxPoints) return arr;
  const step = arr.length / maxPoints;
  const result: T[] = [];
  for (let i = 0; i < maxPoints; i++) {
    result.push(arr[Math.floor(i * step)]);
  }
  return result;
}

/**
 * Aggregate data by interval (weekly or monthly).
 */
export function aggregate<T extends { date: string }>(
  data: T[],
  interval: Interval
): T[] {
  if (interval === "D" || data.length === 0) return data;

  const groups = new Map<string, T[]>();

  for (const point of data) {
    const d = new Date(point.date);
    let key: string;

    if (interval === "W") {
      // ISO week
      const year = d.getUTCFullYear();
      const week = getISOWeek(d);
      key = `${year}-W${week.toString().padStart(2, "0")}`;
    } else {
      // Monthly
      key = `${d.getUTCFullYear()}-${(d.getUTCMonth() + 1).toString().padStart(2, "0")}`;
    }

    if (!groups.has(key)) {
      groups.set(key, []);
    }
    groups.get(key)!.push(point);
  }

  // Take the last point from each group
  const result: T[] = [];
  for (const group of groups.values()) {
    result.push(group[group.length - 1]);
  }

  return result;
}

/**
 * Get ISO week number for a date.
 */
function getISOWeek(date: Date): number {
  const d = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate()));
  const dayNum = d.getUTCDay() || 7;
  d.setUTCDate(d.getUTCDate() + 4 - dayNum);
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  return Math.ceil(((d.getTime() - yearStart.getTime()) / 86400000 + 1) / 7);
}

/**
 * Compute a moving average for a series of data.
 */
export function computeMA<T extends Record<string, any>>(
  data: T[],
  key: string,
  window: number
): (number | null)[] {
  const result: (number | null)[] = [];

  for (let i = 0; i < data.length; i++) {
    if (i < window - 1) {
      result.push(null);
      continue;
    }

    let sum = 0;
    let count = 0;
    for (let j = i - window + 1; j <= i; j++) {
      const val = data[j][key];
      if (val !== null && val !== undefined && !Number.isNaN(val)) {
        sum += val;
        count++;
      }
    }

    if (count === window) {
      result.push(sum / window);
    } else {
      result.push(null);
    }
  }

  return result;
}

/**
 * Check if a series has at least one finite (non-null, non-NaN) value.
 */
export function hasFinite<T extends Record<string, any>>(
  data: T[],
  key: keyof T
): boolean {
  return data.some((row) => {
    const val = row[key];
    return val !== null && val !== undefined && Number.isFinite(val);
  });
}

/**
 * Rebase multiple series to 100 at their first common non-null value.
 */
export function rebase(
  data: Record<string, any>[],
  keys: string[]
): Record<string, any>[] {
  if (data.length === 0 || keys.length === 0) return data;

  // Find the first row where all keys have non-null values
  const baseRow = data.find((row) =>
    keys.every((key) => {
      const val = row[key];
      return val !== null && val !== undefined && Number.isFinite(val) && val !== 0;
    })
  );

  if (!baseRow) return data;

  // Calculate base values for each key
  const baseValues: Record<string, number> = {};
  for (const key of keys) {
    baseValues[key] = baseRow[key];
  }

  // Rebase all rows
  return data.map((row) => {
    const rebased = { ...row };
    for (const key of keys) {
      const val = row[key];
      if (val !== null && val !== undefined && Number.isFinite(val)) {
        rebased[key] = (val / baseValues[key]) * 100;
      }
    }
    return rebased;
  });
}

/**
 * Return a CSS color class based on the sign of a value.
 */
export function toneClass(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "text-gray-500";
  }
  if (value > 0) return "text-green-600 dark:text-green-400";
  if (value < 0) return "text-red-600 dark:text-red-400";
  return "text-gray-500";
}

/**
 * Format a timestamp as "X minutes/hours/days ago".
 */
export function timeAgo(timestamp: string | null | undefined): string {
  if (!timestamp) return "never";

  const date = new Date(timestamp);
  const now = new Date();
  const seconds = Math.floor((now.getTime() - date.getTime()) / 1000);

  if (seconds < 60) return "just now";
  if (seconds < 3600) {
    const minutes = Math.floor(seconds / 60);
    return `${minutes} ${minutes === 1 ? "minute" : "minutes"} ago`;
  }
  if (seconds < 86400) {
    const hours = Math.floor(seconds / 3600);
    return `${hours} ${hours === 1 ? "hour" : "hours"} ago`;
  }
  const days = Math.floor(seconds / 86400);
  return `${days} ${days === 1 ? "day" : "days"} ago`;
}
