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
import { axisDate, computeMA, mediumDate, num, signed, thin } from "../lib/format";
import type { RangeKey } from "../lib/api";
import { useRsBenchmark } from "../lib/useRsBenchmark";
import { computeRS } from "../lib/rs";
import { Card, ErrorNote, SectionTitle, Skeleton } from "./ui";
import { ChartTooltip, Sparkline, useThemeColors } from "./charts";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ChartModal } from "./ChartModal";

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
  const c = useThemeColors(theme);
  const { data: rsBenchData } = useRsBenchmark(
    rsOn && rsBenchmark ? rsBenchmark : "",
    range,
  );
  const [expandedCard, setExpandedCard] = useState<GlobalCard | null>(null);

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
            <div key={card.ticker} onClick={() => setExpandedCard(card)} className="cursor-pointer">
            <Card
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
            </div>
          );
        })}
      </div>

      {/* Expanded chart modal */}
      {expandedCard ? (
        <ExpandedGlobalCardModal
          card={expandedCard}
          range={range}
          onClose={() => setExpandedCard(null)}
          c={c}
        />
      ) : null}
    </div>
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

function ExpandedGlobalCardModal({
  card,
  range,
  onClose,
  c,
}: {
  card: GlobalCard;
  range: RangeKey;
  onClose: () => void;
  c: ReturnType<typeof useThemeColors>;
}) {
  const { data: seriesData } = useSWR<SeriesResponse>(
    `/api/series?ticker=${encodeURIComponent(card.ticker)}&range=${range}`,
    fetcher,
    { keepPreviousData: true }
  );

  const chartData = useMemo(() => {
    if (!seriesData || !seriesData.series || seriesData.series.length === 0) return [];
    const series = seriesData.series[0];
    const points = series.points.filter((p): p is { date: string; value: number } => p.value != null);
    
    // Compute MAs on the full series
    const ma50 = computeMA(points, "value", 50);
    const ma150 = computeMA(points, "value", 150);
    
    return points.map((p, idx) => ({
      date: p.date,
      value: p.value,
      ma50: ma50[idx],
      ma150: ma150[idx],
    }));
  }, [seriesData]);

  const up = (card.change_pct ?? 0) >= 0;
  const colour = up ? c.up : c.down;
  const unitLabel = unitHint(card.unit);
  const span = chartData.length;

  return (
    <ChartModal isOpen={true} onClose={onClose} title={`${card.name} (${card.ticker})`}>
      <div>
        {/* Header with current price and change */}
        <div className="mb-4 flex items-baseline justify-between">
          <div>
            <p className="font-mono text-2xl font-semibold text-ink">
              {num(card.last_close, card.unit === "bps" || card.unit === "index" ? 2 : 2)}
              {unitLabel ? (
                <span className="ml-1 text-sm font-medium text-faint">{unitLabel}</span>
              ) : null}
            </p>
            <p className="text-sm text-muted">
              Last close {card.last_date ? mediumDate(card.last_date) : "—"}
            </p>
          </div>
          <div className="text-right">
            <p className={`text-lg font-semibold ${up ? "text-up" : "text-down"}`}>
              {card.change_pct === null
                ? "—"
                : `${up ? "▲" : "▼"} ${Math.abs(card.change_pct).toFixed(2)}%`}
            </p>
            <p className="text-xs text-muted">Daily change</p>
          </div>
        </div>

        {/* Period changes */}
        <div className="mb-4 grid grid-cols-3 gap-3 rounded-lg border border-line/60 bg-surface p-3">
          <div className="text-center">
            <p className="text-xs text-muted">1M</p>
            <p className={`font-mono text-sm font-semibold ${toneClass(card.change_1m)}`}>
              {signed(card.change_1m, 2, "%")}
            </p>
          </div>
          <div className="text-center">
            <p className="text-xs text-muted">1Y</p>
            <p className={`font-mono text-sm font-semibold ${toneClass(card.change_1y)}`}>
              {signed(card.change_1y, 2, "%")}
            </p>
          </div>
          <div className="text-center">
            <p className="text-xs text-muted">5Y</p>
            <p className={`font-mono text-sm font-semibold ${toneClass(card.change_5y)}`}>
              {signed(card.change_5y, 2, "%")}
            </p>
          </div>
        </div>

        {/* Chart */}
        {chartData.length > 0 ? (
          <ResponsiveContainer width="100%" height={400}>
            <LineChart data={thin(chartData, 520)} margin={{ top: 10, right: 30, bottom: 0, left: 0 }}>
              <CartesianGrid stroke={c.line} strokeDasharray="3 3" vertical={false} />
              <XAxis
                dataKey="date"
                stroke={c.faint}
                tick={{ fontSize: 11 }}
                tickFormatter={(v) => axisDate(v, span)}
                minTickGap={40}
              />
              <YAxis
                stroke={c.faint}
                tick={{ fontSize: 11 }}
                width={80}
                domain={["auto", "auto"]}
                tickFormatter={(v: number) => v.toLocaleString(undefined, { maximumFractionDigits: 1 })}
              />
              <Tooltip
                content={
                  <ChartTooltip
                    formats={{
                      value: (v) => num(v, card.unit === "bps" || card.unit === "index" ? 2 : 2),
                      ma50: (v) => num(v, 2),
                      ma150: (v) => num(v, 2),
                    }}
                  />
                }
              />
              <Line
                type="monotone"
                dataKey="value"
                name="Price"
                stroke={colour}
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
                connectNulls
              />
              <Line
                type="monotone"
                dataKey="ma50"
                name="50 MA"
                stroke={c["series-2"]}
                strokeWidth={1.5}
                strokeDasharray="4 2"
                dot={false}
                isAnimationActive={false}
                connectNulls
              />
              <Line
                type="monotone"
                dataKey="ma150"
                name="150 MA"
                stroke={c["series-3"]}
                strokeWidth={1.5}
                strokeDasharray="4 2"
                dot={false}
                isAnimationActive={false}
                connectNulls
              />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div className="flex h-[400px] items-center justify-center text-muted">
            No data available for this market
          </div>
        )}
      </div>
    </ChartModal>
  );
}


function toneClass(value: number | null | undefined): string {
  if (value === null || value === undefined) return "text-muted";
  return value >= 0 ? "text-up" : "text-down";
}
