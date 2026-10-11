/** Panel 1 - advance/decline ratio and cumulative A/D line. */

import { useMemo, useState } from "react";
import useSWR from "swr";
import {
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { AdResponse, RangeKey } from "../lib/api";
import { fetcher } from "../lib/api";
import { axisDate, compact, mediumDate, num, thin } from "../lib/format";
import {
  Card,
  CardHeader,
  ChartSkeleton,
  EmptyNote,
  ErrorNote,
  Footnote,
  Segmented,
  Switch,
} from "./ui";
import { ChartTooltip, useThemeColors, withAlpha } from "./charts";
import { ExpandableChart } from "./ExpandableChart";

type View = "ratio" | "line";

export function AdvanceDeclinePanel({
  range,
  theme,
}: {
  range: RangeKey;
  theme: string;
}) {
  const { data, error, isLoading } = useSWR<AdResponse>(
    `/api/advance-decline?range=${range}`,
    fetcher,
    { keepPreviousData: true },
  );
  const [view, setView] = useState<View>("ratio");
  const [smooth, setSmooth] = useState(true);
  const [showIndex, setShowIndex] = useState(true);
  const c = useThemeColors(theme);

  const rows = useMemo(() => {
    if (!data) return [];
    const indexByDate = new Map(data.index.map((p) => [p.date, p.close]));
    return thin(
      data.points.map((p) => ({
        date: p.date,
        value:
          view === "line"
            ? p.ad_line
            : smooth
              ? p.ad_ratio_smooth
              : p.ad_ratio,
        index: indexByDate.get(p.date) ?? null,
        advances: p.advances,
        declines: p.declines,
      })),
    );
  }, [data, view, smooth]);

  const hasIndex = Boolean(
    data?.index?.some((p) => typeof p.close === "number" && Number.isFinite(p.close)),
  );
  const overlay = showIndex && hasIndex;

  const latest = data?.points.at(-1) ?? null;
  const breadthOfDay = latest
    ? (latest.advances / Math.max(latest.advances + latest.declines, 1)) * 100
    : 0;
  const span = rows.length;

  const valueName =
    view === "line"
      ? "A/D line"
      : smooth
        ? `A/D ratio (${data?.smoothing_window ?? 10}d avg)`
        : "A/D ratio";

  return (
    <Card>
      <CardHeader
        title="Advance / Decline"
        subtitle="How many stocks rose versus fell each session — the cleanest read on participation."
        actions={
          <>
            <Segmented<View>
              size="sm"
              ariaLabel="Advance decline view"
              value={view}
              onChange={setView}
              options={[
                { value: "ratio", label: "Ratio" },
                { value: "line", label: "A/D line" },
              ]}
            />
            <Switch
              checked={smooth}
              onChange={setSmooth}
              disabled={view === "line"}
              label={`${data?.smoothing_window ?? 10}d smoothing`}
            />
            {hasIndex ? (
              <Switch
                checked={showIndex}
                onChange={setShowIndex}
                label={data?.index_name ?? "Index"}
              />
            ) : null}
          </>
        }
      />

      {error ? <ErrorNote message={`Could not load A/D: ${error.message}`} /> : null}
      {isLoading && !data ? <ChartSkeleton height={300} /> : null}

      {data && !data.points.length ? (
        <EmptyNote>No advance/decline data for this range yet.</EmptyNote>
      ) : null}

      {data && data.points.length ? (
        <>
          {latest ? (
            <div className="mb-4 flex flex-wrap items-center gap-x-5 gap-y-2 rounded-xl border border-line bg-surface-2 px-3.5 py-2.5">
              <span className="text-[11.5px] uppercase tracking-[0.08em] text-faint">
                {mediumDate(latest.date)}
              </span>
              <div className="flex min-w-[180px] flex-1 items-center gap-2">
                <span className="font-mono text-[13px] font-semibold text-up">
                  {latest.advances}
                </span>
                <span className="flex h-1.5 flex-1 overflow-hidden rounded-full bg-down/70">
                  <span
                    className="h-full bg-up transition-all duration-500"
                    style={{ width: `${breadthOfDay}%` }}
                  />
                </span>
                <span className="font-mono text-[13px] font-semibold text-down">
                  {latest.declines}
                </span>
              </div>
              <span className="text-[12px] text-muted">
                advancing vs declining
                {latest.unchanged ? ` · ${latest.unchanged} unchanged` : ""}
              </span>
              <span className="text-[12px] text-muted">
                ratio{" "}
                <span className="font-mono font-medium text-ink">
                  {num(latest.ad_ratio, 2)}
                </span>
              </span>
              <span className="text-[12px] text-muted">
                {data?.smoothing_window ?? 10}d avg{" "}
                <span className="font-mono font-medium text-ink">
                  {data?.latest_avg_ratio != null
                    ? num(data.latest_avg_ratio, 2)
                    : "—"}
                </span>
              </span>
            </div>
          ) : null}

          {data?.divergence ? (
            <div className="mb-3 flex items-start gap-2 rounded-xl border border-amber-400/40 bg-amber-400/10 px-3.5 py-2.5 text-[12px] text-ink">
              <span className="mt-0.5 text-amber-500">⚠</span>
              <span>
                <span className="font-semibold">Divergence:</span>{" "}
                <span className="text-muted">
                  the A/D line and the {data.index_name} have moved in opposite
                  directions for the last few sessions — momentum is weakening.
                </span>
              </span>
            </div>
          ) : null}

          <ExpandableChart title="Advance / Decline Ratio">
          <ResponsiveContainer width="100%" height={300}>
            <ComposedChart
              data={rows}
              margin={{ top: 6, right: overlay ? 4 : 10, bottom: 0, left: -10 }}
            >
              <CartesianGrid stroke={c.line} vertical={false} />
              <XAxis
                dataKey="date"
                tickFormatter={(v) => axisDate(v, span)}
                tick={{ fill: c.faint, fontSize: 11 }}
                tickLine={false}
                axisLine={{ stroke: c.line }}
                minTickGap={44}
              />
              <YAxis
                yAxisId="left"
                domain={view === "ratio" ? [0, "auto"] : ["auto", "auto"]}
                tick={{ fill: c.faint, fontSize: 11 }}
                tickLine={false}
                axisLine={false}
                width={48}
                tickFormatter={(v: number) =>
                  view === "line" ? compact(v) : num(v, 1)
                }
              />
              {overlay ? (
                <YAxis
                  yAxisId="right"
                  orientation="right"
                  domain={["auto", "auto"]}
                  tick={{ fill: c.faint, fontSize: 11 }}
                  tickLine={false}
                  axisLine={false}
                  width={52}
                  tickFormatter={(v: number) =>
                    v.toLocaleString(undefined, { maximumFractionDigits: 0 })
                  }
                />
              ) : null}

              {view === "ratio" ? (
                <ReferenceLine
                  yAxisId="left"
                  y={1}
                  stroke={c.faint}
                  strokeDasharray="4 4"
                  label={{
                    value: "parity",
                    position: "insideTopRight",
                    fill: c.faint,
                    fontSize: 10,
                  }}
                />
              ) : null}

              <Tooltip
                content={
                  <ChartTooltip
                    formats={{
                      value: (v) => (view === "line" ? num(v, 0) : num(v, 2)),
                      index: (v) => num(v, 0),
                    }}
                  />
                }
                cursor={{ stroke: c.faint, strokeDasharray: "3 3" }}
              />

              {overlay ? (
                <Line
                  yAxisId="right"
                  type="monotone"
                  dataKey="index"
                  name={data.index_name}
                  stroke={withAlpha(c.neutral, 0.7)}
                  strokeWidth={1.4}
                  strokeDasharray="5 4"
                  dot={false}
                  isAnimationActive={false}
                  connectNulls
                />
              ) : null}
              <Line
                yAxisId="left"
                type="monotone"
                dataKey="value"
                name={valueName}
                stroke={c["series-1"]}
                strokeWidth={1.9}
                dot={false}
                isAnimationActive={false}
                connectNulls
              />
            </ComposedChart>
          </ResponsiveContainer>
          </ExpandableChart>
        </>
      ) : null}

      <Footnote>
        Advance = close above the previous close, decline = close below; unchanged is
        ignored. The A/D line is the running total of advances minus declines.{" "}
        {data?.footnote}
      </Footnote>
    </Card>
  );
}
