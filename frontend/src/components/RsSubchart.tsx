/**
 * Relative Strength sub-chart. Used inside every price-chart panel when the
 * global RS toggle is on. Shows the CRS ratio coloured green when rising
 * and red when declining, with the all-time-high of CRS marked.
 *
 * The line itself is rendered as two overlaid <Line />s - one green, one
 * red - using the same data, with the rising/declining flag per point
 * driving which one is actually drawn. Recharts doesn't support per-segment
 * colour on a single <Line />, so we split the path at direction flips.
 */

import { useMemo } from "react";
import {
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceDot,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { RsSeries } from "../lib/rs";
import { axisDate, mediumDate, num, thin } from "../lib/format";
import { ChartTooltip, type ThemeColors } from "./charts";

export function RsSubchart({
  rs,
  c,
  height = 110,
  benchmarkName,
}: {
  rs: RsSeries;
  c: ThemeColors;
  height?: number;
  benchmarkName: string;
}) {
  // Split the series into contiguous green / red runs. We emit one entry per
  // point in the original series, with either a green or red value so the
  // other line has nothing to draw at that x.
  const rows = useMemo(() => {
    return rs.points.map((p) => ({
      date: p.date,
      green: p.rising ? p.crs : null,
      red: p.rising ? null : p.crs,
      // keep the actual value for the tooltip regardless of colour
      crs: p.crs,
    }));
  }, [rs]);

  const thinned = thin(rows, 260);
  const span = thinned.length;

  if (!rs.points.length) {
    return (
      <div
        className="flex items-center justify-center rounded-lg border border-dashed border-line text-[11.5px] text-muted"
        style={{ height }}
      >
        No benchmark data for this range
      </div>
    );
  }

  // Y domain with padding so the ATH marker isn't clipped.
  const values = rs.points.map((p) => p.crs).filter((v): v is number => v !== null);
  const min = values.length > 0 ? Math.min(...values) : 0;
  const max = values.length > 0 ? Math.max(...values) : 0;
  const pad = (max - min) * 0.1 || 0.01;

  return (
    <div>
      <div className="mb-0.5 flex items-center justify-between text-[10.5px] font-medium uppercase tracking-wide text-faint">
        <span>
          RS vs {benchmarkName}
        </span>
        <span className="flex items-center gap-2">
          <span className="flex items-center gap-1">
            <span className="inline-block h-[2px] w-3 rounded" style={{ background: c.up }} />
            rising
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block h-[2px] w-3 rounded" style={{ background: c.down }} />
            declining
          </span>
          {rs.ath ? (
            <span className="flex items-center gap-1">
              <span
                className="inline-block h-1.5 w-1.5 rounded-full"
                style={{ background: c.accent }}
              />
              <span className="font-mono normal-case tracking-normal">
                ATH {num(rs.ath.crs, 3)} · {mediumDate(rs.ath.date)}
              </span>
            </span>
          ) : null}
        </span>
      </div>
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart
          data={thinned}
          margin={{ top: 4, right: 8, bottom: 0, left: -18 }}
        >
          <CartesianGrid stroke={c.line} vertical={false} />
          <XAxis
            dataKey="date"
            tickFormatter={(v) => axisDate(v, span)}
            tick={{ fill: c.faint, fontSize: 10 }}
            tickLine={false}
            axisLine={{ stroke: c.line }}
            minTickGap={40}
          />
          <YAxis
            domain={[min - pad, max + pad]}
            tick={{ fill: c.faint, fontSize: 10 }}
            tickLine={false}
            axisLine={false}
            width={52}
            tickFormatter={(v: number) => num(v, 3)}
          />
          <Tooltip
            content={
              <ChartTooltip
                formats={{
                  crs: (v) => num(v, 4),
                }}
              />
            }
            cursor={{ stroke: c.faint, strokeDasharray: "3 3" }}
          />
          <Line
            type="monotone"
            dataKey="green"
            name="RS"
            stroke={c.up}
            strokeWidth={1.6}
            dot={false}
            isAnimationActive={false}
            connectNulls={false}
          />
          <Line
            type="monotone"
            dataKey="red"
            name="RS"
            stroke={c.down}
            strokeWidth={1.6}
            dot={false}
            isAnimationActive={false}
            connectNulls={false}
          />
          {rs.ath ? (
            <ReferenceDot
              x={rs.ath.date}
              y={rs.ath.crs}
              r={4}
              fill={c.accent}
              stroke={c.surface}
              strokeWidth={2}
              isFront
            />
          ) : null}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
