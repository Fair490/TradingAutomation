/** Market Health page — breadth, A/D, global, macro, commodities, status.
 *  Everything except the ETF panel, which lives on its own Sector Performance page.
 */

import { AlertTriangle, CheckCircle2, Info, X } from "lucide-react";
import type { Meta, RangeKey, RefreshState } from "../lib/api";
import { BreadthPanel } from "./BreadthPanel";
import { AdvanceDeclinePanel } from "./AdvanceDeclinePanel";
import { GlobalPanel } from "./GlobalPanel";
import { SeriesPanel } from "./SeriesPanel";
import { StatusPanel } from "./StatusPanel";
import { Card } from "./ui";
import { ErrorBoundary } from "./ErrorBoundary";

export function MarketHealthPage({
  range,
  theme,
  meta,
  rsOn,
  rsBenchmark,
  refresh,
  onFullRebuild,
  noticeClosed,
  onNoticeClose,
}: {
  range: RangeKey;
  theme: string;
  meta?: Meta;
  rsOn: boolean;
  rsBenchmark: string;
  refresh: { running: boolean; state?: RefreshState | null; error: string | null };
  onFullRebuild: () => void;
  noticeClosed: boolean;
  onNoticeClose: () => void;
}) {
  const state = refresh.state;
  const finished = state && !state.running && state.finished_at;

  return (
    <div className="mx-auto max-w-[1400px] space-y-7 px-4 py-6 sm:px-6 sm:py-8">
      <Banners
        refresh={refresh}
        finished={!!finished}
        meta={meta}
        noticeClosed={noticeClosed}
        onNoticeClose={onNoticeClose}
      />

      <section className="space-y-5">
        <ErrorBoundary label="Market breadth">
          <BreadthPanel range={range} theme={theme} />
        </ErrorBoundary>
        <ErrorBoundary label="Advance / Decline">
          <AdvanceDeclinePanel range={range} theme={theme} />
        </ErrorBoundary>
      </section>

      <ErrorBoundary label="Global markets">
        <GlobalPanel theme={theme} rsOn={rsOn} rsBenchmark={rsBenchmark} />
      </ErrorBoundary>

      <ErrorBoundary label="Currency, dollar and bond yield">
        <SeriesPanel
          title="Currency, dollar and bond yield"
          hint="USD/INR · Dollar Index · US 10-Year"
          endpoint="macro"
          range={range}
          theme={theme}
          palette={["series-1", "series-2", "series-3"]}
        />
      </ErrorBoundary>

      <ErrorBoundary label="Commodities">
        <SeriesPanel
          title="Commodities"
          hint="Gold · Silver · Brent crude"
          endpoint="commodities"
          range={range}
          theme={theme}
          palette={["gold", "silver", "oil"]}
        />
      </ErrorBoundary>

      <ErrorBoundary label="Data status">
        <StatusPanel
          meta={meta}
          running={refresh.running}
          onFullRebuild={onFullRebuild}
        />
      </ErrorBoundary>

      <footer className="pb-4 pt-2 text-center text-[11.5px] leading-relaxed text-faint">
        Daily closes from Yahoo Finance (yfinance) stored in DuckDB · current
        constituents only, so survivorship bias applies · built for positional
        trading research, not investment advice.
      </footer>
    </div>
  );
}

function Banners({
  refresh,
  finished,
  meta,
  noticeClosed,
  onNoticeClose,
}: {
  refresh: { running: boolean; state?: RefreshState | null; error: string | null };
  finished: boolean;
  meta?: Meta;
  noticeClosed: boolean;
  onNoticeClose: () => void;
}) {
  const state = refresh.state;
  return (
    <>
      {refresh.running ? (
        <Banner tone="info" icon={<Info size={15} />}>
          <span className="font-medium">{state?.message || "Working…"}</span>
          <span className="text-muted">
            {" "}
            Downloads run in batches of 50 with retries; you can keep using the
            dashboard while it works.
          </span>
        </Banner>
      ) : null}

      {!refresh.running && finished && !noticeClosed ? (
        <Banner
          tone={state?.ok ? "ok" : "error"}
          icon={state?.ok ? <CheckCircle2 size={15} /> : <AlertTriangle size={15} />}
          onClose={onNoticeClose}
        >
          {state?.ok ? state?.summary : state?.error}
          {state?.failures?.length ? (
            <span className="text-muted">
              {" "}
              First failure: {state.failures[0][0]} — {state.failures[0][1]}
            </span>
          ) : null}
        </Banner>
      ) : null}

      {refresh.error ? (
        <Banner tone="error" icon={<AlertTriangle size={15} />}>
          {refresh.error}
        </Banner>
      ) : null}

      {meta?.demo_data ? (
        <Banner tone="warn" icon={<AlertTriangle size={15} />}>
          <span className="font-medium">Synthetic demo data is loaded.</span>{" "}
          <span className="text-muted">
            Press <em>Refresh data</em> (or run{" "}
            <code className="font-mono text-[11.5px]">
              python backend/scripts/seed_demo_data.py --clear
            </code>
            ) to replace it with real Yahoo Finance prices.
          </span>
        </Banner>
      ) : null}

      {meta && !meta.has_data ? (
        <Card className="animate-rise">
          <h2 className="text-[15px] font-semibold text-ink">
            No market data stored yet
          </h2>
          <p className="mt-1.5 max-w-3xl text-[13px] leading-relaxed text-muted">
            The backend reads{" "}
            <code className="font-mono text-[12px] text-ink">
              backend/data/{meta.universe_file}
            </code>{" "}
            ({meta.universe_count} symbols) and downloads daily prices from Yahoo
            Finance. Press <em>Refresh data</em> to start — the first run fetches five
            years plus a 14-month warm-up for the 200-day average, so it takes a few
            minutes. Everything after that is incremental.
          </p>
        </Card>
      ) : null}
    </>
  );
}

function Banner({
  children,
  tone,
  icon,
  onClose,
}: {
  children: React.ReactNode;
  tone: "info" | "ok" | "warn" | "error";
  icon?: React.ReactNode;
  onClose?: () => void;
}) {
  const tones = {
    info: "border-accent/30 bg-accent/8 text-ink",
    ok: "border-up/30 bg-up/8 text-ink",
    warn: "border-amber-400/40 bg-amber-400/10 text-ink",
    error: "border-down/30 bg-down/8 text-ink",
  } as const;
  const iconTones = {
    info: "text-accent",
    ok: "text-up",
    warn: "text-amber-500",
    error: "text-down",
  } as const;
  return (
    <div
      className={`animate-rise flex items-start gap-2.5 rounded-xl border px-3.5 py-2.5 text-[12.5px] leading-relaxed ${tones[tone]}`}
    >
      <span className={`mt-[1px] shrink-0 ${iconTones[tone]}`}>{icon}</span>
      <div className="min-w-0 flex-1">{children}</div>
      {onClose ? (
        <button
          onClick={onClose}
          aria-label="Dismiss"
          className="shrink-0 rounded p-0.5 text-muted transition hover:text-ink"
        >
          <X size={14} />
        </button>
      ) : null}
    </div>
  );
}
