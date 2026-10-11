/** Panel 6 - sector / thematic / broad-market / international / commodity ETFs.
 *
 *  Features
 *  --------
 *  - One sparkline card per configured ETF with the headline % change and the
 *    relative performance vs the benchmark.
 *  - Group filter chips + ranking by relative performance over a fixed period
 *    (1M / 3M / 6M / 1Y). The "since listing" note is a small badge on cards
 *    whose history is shorter than the ranking window.
 *  - Card footer shows % from 52-week high, % from 50-DMA and % from 150-DMA.
 *  - Clicking a card opens a pop-out with a full-sized chart.
 *  - Up to six cards can be selected to plot together, rebased to 100.
 */

import { useMemo, useState } from "react";
import useSWR from "swr";
import { X } from "lucide-react";
import type {
  EtfListResponse,
  EtfSummary,
  EtfCompareResponse,
  RangeKey,
} from "../lib/api";
import { fetcher } from "../lib/api";
import { aggregate, computeMA, mediumDate, num, signed, type Interval } from "../lib/format";
import { useRsBenchmark } from "../lib/useRsBenchmark";
import { computeRS } from "../lib/rs";
import { RsSubchart } from "./RsSubchart";
import {
  Card,
  ErrorNote,
  SectionTitle,
  Skeleton,
} from "./ui";
import {
  ChartTooltip,
  Sparkline,
  useThemeColors,
  withAlpha,
} from "./charts";
import {
  ComposedChart,
  Line,
  LineChart,
  ResponsiveContainer,
  XAxis,
  YAxis,
  CartesianGrid,
} from "recharts";

const RANK_OPTIONS: { key: string; label: string }[] = [
  { key: "1M", label: "1M" },
  { key: "3M", label: "3M" },
  { key: "6M", label: "6M" },
  { key: "1Y", label: "1Y" },
];

export function EtfPanel({
  range,
  theme,
  rsOn,
  rsBenchmark,
}: {
  range: RangeKey;
  theme: string;
  rsOn?: boolean;
  rsBenchmark?: string;
}) {
  const { data, error, isLoading } = useSWR<EtfListResponse>(
    `/api/etfs?range=${range}`,
    fetcher,
    { keepPreviousData: true },
  );
  const c = useThemeColors(theme);

  const [group, setGroup] = useState<string>("All");
  const [sort, setSort] = useState<"relative" | "listed" | "az">("relative");
  const [rankRange, setRankRange] = useState<string>("3M");
  const [selected, setSelected] = useState<string[]>([]);
  const [expanded, setExpanded] = useState<EtfSummary | null>(null);

  // Compare endpoint drives the pop-out + comparison chart
  const compareSymbols = useMemo(() => selected.join(","), [selected]);
  const { data: compare } = useSWR<EtfCompareResponse>(
    compareSymbols ? `/api/etfs/compare?symbols=${compareSymbols}&range=${range}` : null,
    fetcher,
    { keepPreviousData: true },
  );

  const groups = data?.groups ?? [];
  const etfs = data?.etfs ?? [];

  const filtered = useMemo(() => {
    const byGroup = group === "All" ? etfs : etfs.filter((e) => e.group === group);
    const ranked = [...byGroup].sort((a, b) => {
      if (sort === "az") return a.symbol.localeCompare(b.symbol);
      if (sort === "listed") return (a.first_date ?? "").localeCompare(b.first_date ?? "");
      // relative: best first; nulls sink
      const aRel = a.periods?.[rankRange]?.relative_pct;
      const bRel = b.periods?.[rankRange]?.relative_pct;
      if (aRel == null && bRel == null) return 0;
      if (aRel == null) return 1;
      if (bRel == null) return -1;
      return bRel - aRel;
    });
    return ranked;
  }, [etfs, group, sort, rankRange]);

  const toggleSelect = (symbol: string) => {
    setSelected((prev) =>
      prev.includes(symbol)
        ? prev.filter((s) => s !== symbol)
        : prev.length < 6
        ? [...prev, symbol]
        : prev,
    );
  };

  return (
    <div>
      <SectionTitle
        hint={`Leaderboard vs ${data?.benchmark_name ?? "the index"}${
          data?.benchmark_change_pct != null
            ? ` (${signed(data.benchmark_change_pct, 2, "%")})`
            : ""
        }`}
      >
        Sector & thematic ETFs
      </SectionTitle>

      {error ? (
        <ErrorNote message={`Could not load ETFs: ${error.message}`} />
      ) : null}

      {/* Controls row ---------------------------------------------- */}
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="flex flex-wrap items-center gap-1 rounded-xl border border-line/80 bg-surface p-0.5">
          {["All", ...groups].map((g) => (
            <button
              key={g}
              onClick={() => setGroup(g)}
              className={`rounded-[10px] px-2.5 py-1 text-[11.5px] font-medium transition ${
                group === g
                  ? "bg-accent/15 text-accent"
                  : "text-muted hover:text-ink"
              }`}
            >
              {g}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-1.5 rounded-xl border border-line/80 bg-surface px-2 py-1 text-[11.5px]">
          <span className="text-faint">Rank by</span>
          {RANK_OPTIONS.map((opt) => (
            <button
              key={opt.key}
              onClick={() => setRankRange(opt.key)}
              className={`rounded-md px-1.5 py-0.5 font-medium transition ${
                rankRange === opt.key
                  ? "bg-accent/15 text-accent"
                  : "text-muted hover:text-ink"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-1 rounded-xl border border-line/80 bg-surface px-2 py-1 text-[11.5px]">
          <span className="text-faint">Sort</span>
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value as typeof sort)}
            className="bg-transparent text-[11.5px] font-medium text-ink outline-none"
          >
            <option value="relative">Best first</option>
            <option value="listed">As listed</option>
            <option value="az">A → Z</option>
          </select>
        </div>

        {selected.length ? (
          <button
            onClick={() => setSelected([])}
            className="ml-auto rounded-full border border-line/80 px-2.5 py-1 text-[11.5px] font-medium text-muted transition hover:text-ink"
          >
            Clear comparison ({selected.length})
          </button>
        ) : null}
      </div>

      {/* Cards grid ------------------------------------------------ */}
      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-4">
        {isLoading && !data
          ? Array.from({ length: 12 }).map((_, i) => (
              <Card key={i} className="h-[170px]">
                <Skeleton className="h-3 w-16" />
                <Skeleton className="mt-3 h-5 w-24" />
                <Skeleton className="mt-4 h-10 w-full" />
              </Card>
            ))
          : null}

        {filtered.map((etf) => {
          const isSelected = selected.includes(etf.symbol);
          const period = etf.periods?.[rankRange];
          const rel = period?.relative_pct;
          const up = (rel ?? etf.relative_pct ?? 0) >= 0;
          const colour = rel == null ? c.neutral : up ? c.up : c.down;
          return (
            <button
              key={etf.symbol}
              onClick={() => {
                // first click = expand pop-out; shift/meta = toggle compare
                setExpanded(etf);
              }}
              className={`group relative animate-rise rounded-2xl border bg-surface px-3 py-2.5 text-left transition hover:shadow-[0_6px_18px_rgba(15,23,32,0.08)] ${
                isSelected
                  ? "border-accent ring-1 ring-accent/40"
                  : "border-line/80 hover:border-ink/20"
              }`}
            >
              <span
                onClick={(e) => {
                  e.stopPropagation();
                  toggleSelect(etf.symbol);
                }}
                className={`absolute right-2 top-2 flex h-5 w-5 items-center justify-center rounded-md border text-[10px] font-bold transition ${
                  isSelected
                    ? "border-accent bg-accent text-white"
                    : "border-line bg-surface text-transparent hover:border-ink/30"
                }`}
                aria-label="Add to compare"
                title={
                  isSelected
                    ? "Remove from compare"
                    : selected.length < 6
                    ? "Add to compare chart"
                    : "Max 6 in compare"
                }
              >
                ✓
              </span>

              <p className="truncate pr-6 text-[12.5px] font-semibold text-ink">
                {etf.name}
              </p>
              <p className="flex items-center gap-1 font-mono text-[10.5px] text-faint">
                {etf.symbol}
                <span className="text-[9.5px] font-medium text-accent/80">
                  {etf.group}
                </span>
                {etf.partial && etf.first_date ? (
                  <span className="ml-0.5 rounded-full bg-amber-400/15 px-1.5 text-[9px] font-semibold uppercase tracking-wide text-amber-600">
                    since {mediumDate(etf.first_date)}
                  </span>
                ) : null}
              </p>

              <div className="mt-1.5 flex items-baseline gap-1.5">
                <span className="font-mono text-[17px] font-semibold tracking-[-0.02em] text-ink">
                  {num(etf.last_value, 2)}
                </span>
                <span
                  className="font-mono text-[11.5px] font-semibold"
                  style={{ color: colour }}
                >
                  {rel != null
                    ? signed(rel, 2, `% vs ${data?.benchmark_name ?? "idx"}`)
                    : "—"}
                </span>
              </div>

              <div className="-mx-1 mt-1">
                <Sparkline data={etf.spark} color={colour} height={40} />
              </div>

              {/* Footer stats */}
              <div className="mt-1 grid grid-cols-3 gap-1 border-t border-line/60 pt-1.5 text-center font-mono">
                <FooterStat label="52w" value={etf.pct_from_52w_high} suffix="%" />
                <FooterStat label="50D" value={etf.pct_from_50dma} suffix="%" />
                <FooterStat label="150D" value={etf.pct_from_150dma} suffix="%" />
              </div>
            </button>
          );
        })}
      </div>

      {data?.etfs.length === 0 ? (
        <p className="mt-4 text-[12.5px] text-faint">
          No ETF data yet — press <em>Refresh data</em> to download prices.
        </p>
      ) : null}

      {/* Compare chart (when >=1 card is selected) -------------------- */}
      {selected.length && compare ? (
        <CompareChart
          compare={compare}
          selected={selected}
          theme={theme}
          range={range}
        />
      ) : null}

      {/* Pop-out expanded card --------------------------------------- */}
      {expanded ? (
        <ExpandedCard
          etf={expanded}
          onClose={() => setExpanded(null)}
          range={range}
          theme={theme}
          benchmarkName={data?.benchmark_name ?? "Index"}
          rsOn={rsOn}
          rsBenchmark={rsBenchmark}
        />
      ) : null}
    </div>
  );
}

function FooterStat({
  label,
  value,
  suffix,
}: {
  label: string;
  value: number | null;
  suffix?: string;
}) {
  if (value == null) {
    return (
      <div>
        <p className="text-[9.5px] font-semibold uppercase tracking-wide text-faint">
          {label}
        </p>
        <p className="text-[11px] text-muted">—</p>
      </div>
    );
  }
  const up = value >= 0;
  const colour = `var(--colour-${up ? "up" : "down"})`;
  return (
    <div>
      <p className="text-[9.5px] font-semibold uppercase tracking-wide text-faint">
        {label}
      </p>
      <p className="text-[11px] font-semibold" style={{ color: colour }}>
        {signed(value, 1, suffix)}
      </p>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Compare chart (selected cards rebased to 100)                       */
/* ------------------------------------------------------------------ */
const COMPARE_PALETTE = [
  "#2f6fdb",
  "#1a9b6c",
  "#e07b39",
  "#9b5de5",
  "#c9a227",
  "#d8453c",
];

function CompareChart({
  compare,
  selected,
  theme,
  range,
}: {
  compare: EtfCompareResponse;
  selected: string[];
  theme: string;
  range: RangeKey;
}) {
  const c = useThemeColors(theme);
  const [rebased, setRebased] = useState(true);

  // Merge selected series (and optionally the benchmark) into one series of
  // points keyed by date.
  const merged = useMemo(() => {
    const byDate = new Map<
      string,
      { date: string } & Record<string, number | null>
    >();
    const all = [
      ...compare.series,
      ...(compare.benchmark ? [compare.benchmark] : []),
    ];
    for (const s of all) {
      const base = rebased
        ? s.points.find((p) => p.value != null && p.value > 0)?.value ?? 1
        : 1;
      for (const p of s.points) {
        if (!p.date) continue;
        const row = byDate.get(p.date) ?? ({ date: p.date } as any);
        row[s.name] =
          p.value != null ? (p.value / base) * (rebased ? 100 : 1) : null;
        byDate.set(p.date, row);
      }
    }
    return Array.from(byDate.values()).sort((a, b) =>
      a.date.localeCompare(b.date),
    );
  }, [compare, rebased]);

  return (
    <Card className="mt-5 animate-rise">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div>
          <p className="text-[13px] font-semibold text-ink">Compare</p>
          <p className="text-[11.5px] text-muted">
            {rebased
              ? `Rebased to 100 at start of ${range} window`
              : `Actual prices over ${range}`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setRebased(!rebased)}
            className={`rounded-full border px-2.5 py-1 text-[11.5px] font-medium transition ${
              rebased
                ? "border-accent/40 bg-accent/15 text-accent"
                : "border-line text-muted hover:text-ink"
            }`}
          >
            {rebased ? "Rebased" : "Absolute"}
          </button>
        </div>
      </div>

      <div className="h-[340px] w-full">
        <ResponsiveContainer>
          <LineChart data={merged}>
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
            />
            <ChartTooltip />
            {selected.map((sym, i) => {
              const entry = compare.series.find((s) => s.symbol === sym);
              if (!entry) return null;
              return (
                <Line
                  key={sym}
                  dataKey={entry.name}
                  name={entry.name}
                  stroke={COMPARE_PALETTE[i % COMPARE_PALETTE.length]}
                  strokeWidth={2}
                  dot={false}
                  connectNulls
                  isAnimationActive={false}
                />
              );
            })}
            {compare.benchmark ? (
              <Line
                dataKey={compare.benchmark.name}
                name={compare.benchmark.name}
                stroke={c.neutral}
                strokeWidth={1.5}
                strokeDasharray="4 4"
                dot={false}
                connectNulls
                isAnimationActive={false}
              />
            ) : null}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/* Pop-out expanded card                                               */
/* ------------------------------------------------------------------ */
function ExpandedCard({
  etf,
  onClose,
  range,
  theme,
  benchmarkName,
  rsOn,
  rsBenchmark,
}: {
  etf: EtfSummary;
  onClose: () => void;
  range: RangeKey;
  theme: string;
  benchmarkName: string;
  rsOn?: boolean;
  rsBenchmark?: string;
}) {
  const c = useThemeColors(theme);
  // Re-fetch compare with just this one card + benchmark to get the full line
  const { data } = useSWR<EtfCompareResponse>(
    `/api/etfs/compare?symbols=${etf.symbol}&range=${range}`,
    fetcher,
    { keepPreviousData: true },
  );

  const myPoints = data?.series[0]?.points ?? [];
  const benchmarkPoints = data?.benchmark?.points ?? [];
  const { data: rsBenchData } = useRsBenchmark(
    rsOn && rsBenchmark ? rsBenchmark : "",
    range,
  );

  const [tf, setTf] = useState<Interval>("D");
  const [showMA50, setShowMA50] = useState(false);
  const [showMA150, setShowMA150] = useState(false);

  // Merge into one dataset for the chart, aggregated by the selected timeframe
  // and enriched with 50 / 150 MA overlays (computed client-side so the toggle
  // is instant).
  const merged = useMemo(() => {
    const byDate = new Map<
      string,
      { date: string; etf: number | null; benchmark: number | null; ma50?: number | null; ma150?: number | null }
    >();
    for (const p of myPoints) {
      if (!p.date) continue;
      const row = byDate.get(p.date) ?? { date: p.date, etf: null, benchmark: null };
      row.etf = p.value;
      byDate.set(p.date, row);
    }
    for (const p of benchmarkPoints) {
      if (!p.date) continue;
      const row = byDate.get(p.date) ?? { date: p.date, etf: null, benchmark: null };
      row.benchmark = p.value;
      byDate.set(p.date, row);
    }
    const daily = Array.from(byDate.values()).sort((a, b) =>
      a.date.localeCompare(b.date),
    );
    
    // Compute MAs on daily data first (50-DMA = 50 trading days, not 50 weeks/months)
    const ma50Daily = computeMA(daily, "etf", 50);
    const ma150Daily = computeMA(daily, "etf", 150);
    
    // Merge MAs into daily data
    const dailyWithMA = daily.map((row, i) => ({
      ...row,
      ...(showMA50 ? { ma50: ma50Daily[i] } : {}),
      ...(showMA150 ? { ma150: ma150Daily[i] } : {}),
    }));
    
    // Then aggregate to the selected timeframe
    return aggregate(dailyWithMA, tf);
  }, [myPoints, benchmarkPoints, tf, showMA50, showMA150]);

  const rel = etf.relative_pct;
  const up = (rel ?? 0) >= 0;
  const relColour = up ? c.up : c.down;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="animate-rise w-full max-w-3xl overflow-hidden rounded-2xl border border-line bg-surface shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3 border-b border-line px-5 py-4">
          <div>
            <p className="text-[16px] font-semibold text-ink">{etf.name}</p>
            <p className="mt-0.5 flex items-center gap-2 font-mono text-[11.5px] text-faint">
              {etf.ticker}
              <span className="rounded-full bg-accent/15 px-1.5 py-[1px] text-[9.5px] font-semibold uppercase tracking-wide text-accent">
                {etf.group}
              </span>
              {etf.partial && etf.first_date ? (
                <span>since {mediumDate(etf.first_date)}</span>
              ) : null}
            </p>
          </div>
          <button
            onClick={onClose}
            className="rounded-full p-1.5 text-muted transition hover:bg-line/50 hover:text-ink"
            aria-label="Close"
          >
            <X size={18} />
          </button>
        </div>

        <div className="grid grid-cols-3 gap-3 px-5 pt-4 sm:grid-cols-5">
          <StatBox
            label="Last"
            value={etf.last_value != null ? num(etf.last_value, 2) : "—"}
            sub={etf.last_date ? mediumDate(etf.last_date) : undefined}
          />
          <StatBox
            label={`% vs ${benchmarkName}`}
            value={rel != null ? signed(rel, 2, "%") : "—"}
            valueColour={relColour}
          />
          <StatBox
            label="vs 52w high"
            value={
              etf.pct_from_52w_high != null
                ? signed(etf.pct_from_52w_high, 1, "%")
                : "—"
            }
            valueColour={
              etf.pct_from_52w_high != null
                ? `var(--colour-${etf.pct_from_52w_high >= -5 ? "up" : "down"})`
                : undefined
            }
          />
          <StatBox
            label="vs 50D MA"
            value={
              etf.pct_from_50dma != null
                ? signed(etf.pct_from_50dma, 1, "%")
                : "—"
            }
            valueColour={
              etf.pct_from_50dma != null
                ? `var(--colour-${etf.pct_from_50dma >= 0 ? "up" : "down"})`
                : undefined
            }
          />
          <StatBox
            label="vs 150D MA"
            value={
              etf.pct_from_150dma != null
                ? signed(etf.pct_from_150dma, 1, "%")
                : "—"
            }
            valueColour={
              etf.pct_from_150dma != null
                ? `var(--colour-${etf.pct_from_150dma >= 0 ? "up" : "down"})`
                : undefined
            }
          />
        </div>

        <div className="flex items-center justify-between gap-2 px-5 pt-4">
          <p className="text-[11px] font-medium uppercase tracking-wide text-faint">
            Price vs {benchmarkName} ({range})
          </p>
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
        {rsOn && rsBenchData && myPoints.length ? (
          <div className="mx-5 mt-2 rounded-lg border border-line/60 bg-canvas/50 p-2">
            <RsSubchart
              rs={computeRS(myPoints, rsBenchData.points)}
              c={c}
              height={140}
              benchmarkName={rsBenchData.name}
            />
          </div>
        ) : null}
        <div className="h-[320px] w-full px-2 pb-4 pt-1">
          <ResponsiveContainer>
            <ComposedChart data={merged}>
              <CartesianGrid stroke={c.line} strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="date" stroke={c.faint} tick={{ fontSize: 11 }} minTickGap={40} />
              <YAxis
                yAxisId="left"
                stroke={c.faint}
                tick={{ fontSize: 11 }}
                width={60}
                domain={["dataMin - 2", "dataMax + 2"]}
              />
              <YAxis yAxisId="right" orientation="right" stroke={c.faint} tick={{ fontSize: 11 }} width={60} domain={["dataMin - 2", "dataMax + 2"]} />
              <ChartTooltip />
              <Line
                yAxisId="left"
                dataKey="etf"
                name={etf.name}
                stroke={c.accent}
                strokeWidth={2}
                dot={false}
                connectNulls
                isAnimationActive={false}
              />
              {benchmarkPoints.length ? (
                <Line
                  yAxisId="right"
                  dataKey="benchmark"
                  name={benchmarkName}
                  stroke={withAlpha(c.neutral, 0.75)}
                  strokeWidth={1.5}
                  strokeDasharray="4 4"
                  dot={false}
                  connectNulls
                  isAnimationActive={false}
                />
              ) : null}
              {showMA50 ? (
                <Line
                  yAxisId="left"
                  dataKey="ma50"
                  name="50 MA"
                  stroke={withAlpha(c.ink, 0.6)}
                  strokeWidth={1.3}
                  strokeDasharray="3 3"
                  dot={false}
                  connectNulls
                  isAnimationActive={false}
                />
              ) : null}
              {showMA150 ? (
                <Line
                  yAxisId="left"
                  dataKey="ma150"
                  name="150 MA"
                  stroke={withAlpha(c.ink, 0.4)}
                  strokeWidth={1.3}
                  strokeDasharray="2 4"
                  dot={false}
                  connectNulls
                  isAnimationActive={false}
                />
              ) : null}
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}

function StatBox({
  label,
  value,
  sub,
  valueColour,
}: {
  label: string;
  value: string;
  sub?: string;
  valueColour?: string;
}) {
  return (
    <div className="rounded-xl border border-line/70 bg-surface px-3 py-2.5">
      <p className="text-[10.5px] font-semibold uppercase tracking-wide text-faint">
        {label}
      </p>
      <p
        className="mt-0.5 font-mono text-[15px] font-semibold tracking-tight"
        style={{ color: valueColour ?? "var(--color-ink)" }}
      >
        {value}
      </p>
      {sub ? <p className="mt-0.5 text-[10.5px] text-faint">{sub}</p> : null}
    </div>
  );
}
