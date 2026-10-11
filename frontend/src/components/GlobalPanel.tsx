/** Panel 3 - global markets: one card per index with the daily % in a pill
 *  (coloured by direction), a 1-month sparkline labelled "1M trend", and
 *  1M / 1Y / 5Y changes beneath. India VIX and S&P 500 sit alongside the
 *  five traditional indices. A "stale" marker appears when the card's last
 *  close is a day (or more) behind the freshest card - i.e. weekend / holiday.
 */

import { useMemo, useState } from "react";
import useSWR from "swr";
import { Clock } from "lucide-react";
import type { GlobalCard, SeriesResponse } from "../lib/api";
import { fetcher } from "../lib/api";
import { aggregate, computeMA, mediumDate, num, signed, type Interval } from "../lib/format";
import type { RangeKey } from "../lib/api";
import { useRsBenchmark } from "../lib/useRsBenchmark";
import { computeRS } from "../lib/rs";
import { Card, ErrorNote, SectionTitle, Skeleton } from "./ui";
import { ChartTooltip, Sparkline, useThemeColors, withAlpha } from "./charts";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ExpandableChart } from "./ExpandableChart";

const GLOBAL_PALETTE = [
  "#2f6fdb",
  "#1a9b6c",
  "#e07b39",
  "#9b5de5",
  "#c9a227",
  "#d8453c",
];

export function GlobalPanel({
  theme,
  rsOn,
  rsBenchmark,
  range = "1Y",
}: {
  theme: string;
  rsOn?: boolean;
  rsBenchmark?: string;
  range?: RangeKey;
}) {
  const { data, error, isLoading } = useSWR<GlobalCard[]>("/api/global", fetcher, {
    keepPreviousData: true,
  });
  const { data: chartData } = useSWR<SeriesResponse>(
    `/api/global-chart?range=${range}`,
    fetcher,
    { keepPreviousData: true },
  );
  const c = useThemeColors(theme);
  const { data: rsBenchData } = useRsBenchmark(
    rsOn && rsBenchmark ? rsBenchmark : "",
    range,
  );
  const [tf, setTf] = useState<Interval>("D");
  const [showMA50, setShowMA50] = useState(false);
  const [showMA150, setShowMA150] = useState(false);

  return (
    <div>
      <SectionTitle hint="Pill = daily session change · sparkline = 1-month trend">
        Global markets today
      </SectionTitle>

      {error ? (
        <ErrorNote message={`Could not load global markets: ${error.message}`} />
      ) : null}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-4">
        {isLoading && !data
          ? Array.from({ length: 7 }).map((_, i) => (
              <Card key={i} className="h-[170px]">
                <Skeleton className="h-3 w-20" />
                <Skeleton className="mt-3 h-6 w-24" />
                <Skeleton className="mt-4 h-10 w-full" />
              </Card>
            ))
          : null}

        {data?.map((card) => {
          const up = (card.change_pct ?? 0) >= 0;
          const pillColour =
            card.change_pct === null ? c.neutral : up ? c.up : c.down;
          const sparkColour = trendColour(card, c);
          const unitLabel = unitHint(card.unit);
          return (
            <Card
              key={card.ticker}
              className="group animate-rise transition-shadow hover:shadow-[0_6px_18px_rgba(15,23,32,0.08)]"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate text-[12.5px] font-semibold text-ink">
                    {card.name}
                  </p>
                  <p className="flex items-center gap-1 font-mono text-[10.5px] text-faint">
                    {card.ticker}
                    {card.stale ? (
                      <span
                        className="inline-flex items-center gap-0.5 rounded-full bg-amber-400/15 px-1.5 text-[9.5px] font-semibold uppercase tracking-wide text-amber-600"
                        title="This market hasn't traded today — last close is older than the freshest card."
                      >
                        <Clock size={9} />
                        stale
                      </span>
                    ) : null}
                  </p>
                </div>
                <span
                  className="rounded-full px-1.5 py-[2px] text-[11px] font-semibold"
                  style={{ color: pillColour, background: `${pillColour}1a` }}
                >
                  {card.change_pct === null
                    ? "—"
                    : `${up ? "▲" : "▼"} ${Math.abs(card.change_pct).toFixed(2)}%`}
                </span>
              </div>

              <p className="mt-2 flex items-baseline gap-1 font-mono text-[19px] font-semibold tracking-[-0.02em] text-ink">
                {num(card.last_close, card.unit === "bps" || card.unit === "index" ? 2 : 2)}
                {unitLabel ? (
                  <span className="text-[10.5px] font-medium text-faint">
                    {unitLabel}
                  </span>
                ) : null}
              </p>
              <p className="text-[11px] text-faint">
                last close {card.last_date ? mediumDate(card.last_date) : "—"}
              </p>

              <div className="mt-2 -mx-1">
                <Sparkline data={card.spark} color={sparkColour} height={46} />
              </div>
              <p className="mt-0.5 text-right font-mono text-[9.5px] font-medium text-faint">
                1M trend
              </p>

              <div className="mt-1.5 grid grid-cols-3 gap-1.5 border-t border-line/60 pt-2 text-center font-mono">
                <PeriodStat label="1M" value={card.change_1m} />
                <PeriodStat label="1Y" value={card.change_1y} />
                <PeriodStat label="5Y" value={card.change_5y} />
              </div>

              {rsOn && rsBenchData ? (
                <RsIndicatorInline
                  card={card}
                  rsBenchData={rsBenchData}
                  c={c}
                />
              ) : null}
            </Card>
          );
        })}
      </div>

      {/* Combined price chart for all global markets */}
      {chartData && chartData.series.length ? (
        <Card className="mt-4">
          <div className="mb-2 flex items-center justify-between gap-2">
            <div>
              <p className="text-[13px] font-semibold text-ink">
                Global indices ({range})
              </p>
              <p className="text-[11.5px] text-muted">
                Each market rebased to 100, aggregated {tf === "D" ? "daily" : tf === "W" ? "weekly" : "monthly"}.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <div className="flex items-center gap-0.5 rounded-xl border border-line/80 bg-surface p-0.5 text-[11px]">
                {(["D", "W", "M"] as Interval[]).map((v) => (
                  <button
                    key={v}
                    onClick={() => setTf(v)}
                    className={`rounded-[10px] px-1.5 py-0.5 font-medium transition ${
                      tf === v ? "bg-accent/15 text-accent" : "text-muted hover:text-ink"
                    }`}
                  >
                    {v}
                  </button>
                ))}
              </div>
              <button
                onClick={() => setShowMA50((v) => !v)}
                className={`rounded-md px-1.5 py-0.5 text-[11px] font-medium transition ${
                  showMA50 ? "bg-ink/10 text-ink" : "text-muted hover:text-ink"
                }`}
                title="50-period moving average"
              >
                50 MA
              </button>
              <button
                onClick={() => setShowMA150((v) => !v)}
                className={`rounded-md px-1.5 py-0.5 text-[11px] font-medium transition ${
                  showMA150 ? "bg-ink/10 text-ink" : "text-muted hover:text-ink"
                }`}
                title="150-period moving average"
              >
                150 MA
              </button>
            </div>
          </div>

          <div className="h-[340px] w-full">
            <ExpandableChart title="Global Indices Comparison">
            <ResponsiveContainer>
              <GlobalCombinedChart
                series={chartData.series}
                interval={tf}
                showMA50={showMA50}
                showMA150={showMA150}
                c={c}
              />
            </ResponsiveContainer>
            </ExpandableChart>
          </div>
        </Card>
      ) : null}
    </div>
  );
}

function GlobalCombinedChart({
  series,
  interval,
  showMA50,
  showMA150,
  c,
}: {
  series: SeriesResponse["series"];
  interval: Interval;
  showMA50: boolean;
  showMA150: boolean;
  c: ReturnType<typeof useThemeColors>;
}) {
  const { rows } = useMemo(() => {
    // Build daily data with rebased prices and MAs
    const byDate = new Map<string, any>();
    
    for (const s of series) {
      const dailyPoints = s.points.filter((p): p is { date: string; value: number } => p.value != null);
      
      // Rebase on daily data first
      const first = dailyPoints.find((p) => p.value > 0)?.value ?? 1;
      
      // Compute MAs on daily rebased data
      const dailyRebased = dailyPoints.map((p) => ({
        date: p.date,
        value: (p.value / first) * 100,
      }));
      
      const ma50Daily = showMA50 ? computeMA(dailyRebased, "value", 50) : null;
      const ma150Daily = showMA150 ? computeMA(dailyRebased, "value", 150) : null;
      
      // Build daily rows with price and MAs
      for (let i = 0; i < dailyRebased.length; i++) {
        const p = dailyRebased[i];
        const row = byDate.get(p.date) ?? { date: p.date };
        row[s.name] = p.value;
        if (ma50Daily && ma50Daily[i] != null) {
          row[`${s.name} · 50`] = ma50Daily[i];
        }
        if (ma150Daily && ma150Daily[i] != null) {
          row[`${s.name} · 150`] = ma150Daily[i];
        }
        byDate.set(p.date, row);
      }
    }
    
    // Sort and aggregate to the selected interval
    const dailyRows = [...byDate.values()].sort((a, b) =>
      String(a.date).localeCompare(String(b.date)),
    );
    
    // Aggregate by taking the last value in each period
    const rows = aggregate(dailyRows as any, interval);
    
    return { rows };
  }, [series, interval, showMA50, showMA150]);

  // Filter out MA keys that have no data
  const maKeys = useMemo(() => {
    if (!rows.length) return [];
    const keys = new Set<string>();
    for (const row of rows) {
      for (const key of Object.keys(row)) {
        if (key.includes("· 50") || key.includes("· 150")) {
          if ((row as any)[key] != null) keys.add(key);
        }
      }
    }
    return [...keys];
  }, [rows]);

  return (
    <LineChart data={rows}>
      <CartesianGrid stroke={c.line} strokeDasharray="3 3" vertical={false} />
      <XAxis
        dataKey="date"
        stroke={c.faint}
        tick={{ fontSize: 11 }}
        minTickGap={40}
      />
      <YAxis
        stroke={c.faint}
        tick={{ fontSize: 11 }}
        width={52}
        domain={["dataMin - 3", "dataMax + 3"]}
        tickFormatter={(v: number) => v.toFixed(0)}
      />
      <Tooltip
        content={<ChartTooltip formats={{}} />}
        cursor={{ stroke: c.faint, strokeDasharray: "3 3" }}
      />
      <Legend
        verticalAlign="top"
        align="left"
        height={28}
        iconType="plainline"
        wrapperStyle={{ fontSize: 12, color: c.muted }}
      />
      {series.map((s, i) => (
        <Line
          key={s.name}
          type="monotone"
          dataKey={s.name}
          name={s.name}
          stroke={GLOBAL_PALETTE[i % GLOBAL_PALETTE.length]}
          strokeWidth={1.8}
          dot={false}
          isAnimationActive={false}
          connectNulls
        />
      ))}
      {maKeys.map((key) => (
        <Line
          key={key}
          type="monotone"
          dataKey={key}
          name={key}
          stroke={withAlpha(c.ink, key.endsWith("150") ? 0.4 : 0.6)}
          strokeWidth={1.3}
          strokeDasharray={key.endsWith("150") ? "2 4" : "3 3"}
          dot={false}
          isAnimationActive={false}
          connectNulls
          legendType="none"
        />
      ))}
    </LineChart>
  );
}

function PeriodStat({ label, value }: { label: string; value: number | null }) {
  if (value === null || value === undefined) {
    return (
      <div>
        <p className="text-[9.5px] font-semibold uppercase tracking-wide text-faint">
          {label}
        </p>
        <p className="mt-0.5 text-[11.5px] text-muted">—</p>
      </div>
    );
  }
  const up = value >= 0;
  const colour = `var(--color-${up ? "up" : "down"})`;
  return (
    <div>
      <p className="text-[9.5px] font-semibold uppercase tracking-wide text-faint">
        {label}
      </p>
      <p
        className="mt-0.5 text-[11.5px] font-semibold"
        style={{ color: colour }}
      >
        {signed(value, 2, "%")}
      </p>
    </div>
  );
}

/** Sparkline colour follows the 1-month trend (not the daily change pill),
 *  so a market that closed green today but is down over the month still shows
 *  red in the sparkline - that's what the user asked for.
 */
function trendColour(card: GlobalCard, c: ReturnType<typeof useThemeColors>) {
  const v = card.change_1m;
  if (v === null || v === undefined) return c.neutral;
  return v >= 0 ? c.up : c.down;
}

function unitHint(unit: string): string {
  switch (unit) {
    case "USD/oz":
    case "USD/bbl":
      return unit;
    case "₹ per $":
      return "₹/$";
    case "bps":
      return "bps";
    case "index":
      return "";
    default:
      return "";
  }
}


import type { ThemeColors } from "./charts";

function RsIndicatorInline({
  card,
  rsBenchData,
  c,
}: {
  card: { spark: { date: string; value: number | null }[]; name: string };
  rsBenchData: { points: { date: string; value: number | null }[]; name: string };
  c: ThemeColors;
}) {
  const rs = computeRS(card.spark, rsBenchData.points);
  if (!rs.points.length) return null;
  const last = rs.points[rs.points.length - 1];
  const colour = last.rising ? c.up : c.down;
  const arrow = last.rising ? "▲" : "▼";
  const ath = rs.ath;
  const atAth = ath && last.crs !== null ? Math.abs(last.crs - ath.crs) / ath.crs < 0.01 : false;
  return (
    <div className="mt-1.5 flex items-center justify-between border-t border-line/60 pt-1.5 text-[10.5px]">
      <span className="flex items-center gap-1" style={{ color: colour }}>
        <span className="font-semibold">{arrow}</span>
        <span className="font-medium">RS vs {rsBenchData.name}</span>
      </span>
      {atAth ? (
        <span className="rounded-full bg-accent/15 px-1.5 py-[1px] text-[9px] font-bold uppercase tracking-wide text-accent">
          ★ ATH
        </span>
      ) : null}
    </div>
  );
}
