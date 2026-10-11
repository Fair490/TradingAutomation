/** Chart building blocks: resolved theme colours, a shared tooltip, sparklines. */

import { useEffect, useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  ResponsiveContainer,
  XAxis,
  YAxis,
  type TooltipProps,
} from "recharts";
import { mediumDate, num } from "../lib/format";

const TOKENS = [
  "accent",
  "ink",
  "muted",
  "faint",
  "line",
  "surface",
  "up",
  "down",
  "neutral",
  "series-1",
  "series-2",
  "series-3",
  "gold",
  "silver",
  "oil",
] as const;

export type ThemeColors = Record<(typeof TOKENS)[number], string>;

/**
 * Recharts writes colours as SVG attributes, where `var(--x)` does not
 * resolve - so read the computed values and refresh them when the theme flips.
 */
export function useThemeColors(theme: string): ThemeColors {
  const [, force] = useState(0);
  useEffect(() => {
    const id = requestAnimationFrame(() => force((n) => n + 1));
    return () => cancelAnimationFrame(id);
  }, [theme]);

  return useMemo(() => {
    const styles = getComputedStyle(document.documentElement);
    const out = {} as ThemeColors;
    for (const token of TOKENS) {
      out[token] = styles.getPropertyValue(`--color-${token}`).trim() || "#888";
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [theme]);
}

export function withAlpha(hex: string, alpha: number): string {
  const clean = hex.replace("#", "");
  if (clean.length !== 6) return hex;
  const r = parseInt(clean.slice(0, 2), 16);
  const g = parseInt(clean.slice(2, 4), 16);
  const b = parseInt(clean.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

export interface TooltipFormat {
  [key: string]: (value: number) => string;
}

export function ChartTooltip({
  active,
  payload,
  label,
  formats,
}: TooltipProps<number, string> & { formats?: TooltipFormat }) {
  if (!active || !payload?.length) return null;
  const rows = payload.filter((p) => p.value !== null && p.value !== undefined);
  if (!rows.length) return null;
  return (
    <div className="pointer-events-none min-w-[168px] rounded-xl border border-line bg-surface/95 px-3 py-2 shadow-lg backdrop-blur">
      <p className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-faint">
        {typeof label === "string" ? mediumDate(label) : label}
      </p>
      <div className="space-y-1">
        {rows.map((row) => {
          const key = String(row.dataKey ?? row.name ?? "");
          const value = Number(row.value);
          const fmt = formats?.[key];
          return (
            <div key={key} className="flex items-center justify-between gap-4">
              <span className="flex items-center gap-1.5 text-[12px] text-muted">
                <span
                  className="inline-block h-[7px] w-[7px] rounded-full"
                  style={{ background: row.color ?? row.stroke ?? "currentColor" }}
                />
                {row.name}
              </span>
              <span className="font-mono text-[12.5px] font-medium text-ink">
                {fmt ? fmt(value) : num(value)}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function Sparkline({
  data,
  color,
  height = 44,
}: {
  data: { date: string; value: number | null }[];
  color: string;
  height?: number;
}) {
  const id = useMemo(() => `spark-${Math.random().toString(36).slice(2)}`, []);
  const values = data.map((d) => d.value).filter((v): v is number => v !== null);
  if (values.length < 2) return <div style={{ height }} />;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const pad = (max - min) * 0.14 || 1;

  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 2, right: 0, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.3} />
            <stop offset="100%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <YAxis hide domain={[min - pad, max + pad]} />
        <XAxis hide dataKey="date" />
        <Area
          type="monotone"
          dataKey="value"
          stroke={color}
          strokeWidth={1.6}
          fill={`url(#${id})`}
          isAnimationActive={false}
          dot={false}
          connectNulls
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
