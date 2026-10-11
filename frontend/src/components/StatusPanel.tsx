/** Data status + advanced actions (full rebuild), tucked away at the bottom. */

import { useMemo, useState } from "react";
import useSWR from "swr";
import { AlertTriangle, ChevronDown, Database, Search } from "lucide-react";
import clsx from "clsx";
import type { Meta, StatusResponse } from "../lib/api";
import { fetcher } from "../lib/api";
import { mediumDate } from "../lib/format";
import { Card, Pill, Skeleton } from "./ui";

export function StatusPanel({
  meta,
  onFullRebuild,
  running,
}: {
  meta?: Meta;
  onFullRebuild: () => void;
  running: boolean;
}) {
  const [open, setOpen] = useState(false);
  const { data, isLoading } = useSWR<StatusResponse>(
    open ? "/api/status" : null,
    fetcher,
  );
  const [query, setQuery] = useState("");
  const [onlyProblems, setOnlyProblems] = useState(false);
  const [confirm, setConfirm] = useState(false);

  const rows = useMemo(() => {
    if (!data) return [];
    const q = query.trim().toLowerCase();
    return data.tickers.filter((t) => {
      if (onlyProblems && t.status === "ok") return false;
      if (!q) return true;
      return (
        t.ticker.toLowerCase().includes(q) ||
        (t.name ?? "").toLowerCase().includes(q) ||
        (t.kind ?? "").toLowerCase().includes(q)
      );
    });
  }, [data, query, onlyProblems]);

  return (
    <Card padded={false} className="overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-3 px-4 py-3.5 text-left transition hover:bg-surface-2 sm:px-5"
      >
        <Database size={16} className="text-muted" />
        <div className="min-w-0 flex-1">
          <p className="text-[13.5px] font-semibold text-ink">Data status</p>
          <p className="truncate text-[12px] text-muted">
            {meta
              ? `${meta.n_prices.toLocaleString()} price rows · ${meta.n_tickers} tickers · universe file ${meta.universe_file} (${meta.universe_count} symbols)`
              : "—"}
          </p>
        </div>
        {data?.n_problem ? (
          <Pill tone="warn">
            <AlertTriangle size={11} /> {data.n_problem} need attention
          </Pill>
        ) : null}
        <ChevronDown
          size={16}
          className={clsx("text-muted transition-transform", open && "rotate-180")}
        />
      </button>

      {open ? (
        <div className="border-t border-line px-4 py-4 sm:px-5">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <label className="flex flex-1 items-center gap-2 rounded-full border border-line bg-surface-2 px-3 py-1.5">
              <Search size={13} className="text-faint" />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search ticker, company or kind…"
                className="w-full bg-transparent text-[12.5px] text-ink outline-none placeholder:text-faint"
              />
            </label>
            <button
              type="button"
              onClick={() => setOnlyProblems((v) => !v)}
              className={clsx(
                "rounded-full border px-3 py-1.5 text-[12px] font-medium transition",
                onlyProblems
                  ? "border-transparent bg-down/10 text-down"
                  : "border-line text-muted hover:text-ink",
              )}
            >
              Problems only
            </button>
          </div>

          {isLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className="h-7 w-full" />
              ))}
            </div>
          ) : (
            <div className="scroll-thin max-h-[320px] overflow-auto rounded-lg border border-line">
              <table className="w-full text-left text-[12.5px]">
                <thead className="sticky top-0 bg-surface-2 text-[11px] uppercase tracking-wide text-faint">
                  <tr>
                    <th className="px-3 py-2 font-medium">Ticker</th>
                    <th className="px-3 py-2 font-medium">Name</th>
                    <th className="px-3 py-2 font-medium">Kind</th>
                    <th className="px-3 py-2 font-medium">Status</th>
                    <th className="px-3 py-2 text-right font-medium">Rows</th>
                    <th className="px-3 py-2 font-medium">Last date</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.slice(0, 400).map((t) => (
                    <tr key={t.ticker} className="border-t border-line/70">
                      <td className="px-3 py-1.5 font-mono text-[11.5px] text-ink">
                        {t.ticker}
                      </td>
                      <td className="max-w-[260px] truncate px-3 py-1.5 text-muted">
                        {t.name}
                      </td>
                      <td className="px-3 py-1.5 text-muted">{t.kind}</td>
                      <td className="px-3 py-1.5">
                        <span
                          className={clsx(
                            "rounded-full px-1.5 py-[2px] text-[11px] font-medium",
                            t.status === "ok"
                              ? "bg-up/10 text-up"
                              : "bg-down/10 text-down",
                          )}
                        >
                          {t.status}
                          {t.message ? ` · ${t.message}` : ""}
                        </span>
                      </td>
                      <td className="px-3 py-1.5 text-right font-mono text-[11.5px] text-muted">
                        {t.n_rows?.toLocaleString() ?? "0"}
                      </td>
                      <td className="px-3 py-1.5 text-muted">
                        {t.last_date ? mediumDate(t.last_date) : "—"}
                      </td>
                    </tr>
                  ))}
                  {!rows.length ? (
                    <tr>
                      <td colSpan={6} className="px-3 py-6 text-center text-muted">
                        Nothing matches that search.
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          )}

          <div className="mt-4 flex flex-wrap items-center gap-3 rounded-lg border border-line bg-surface-2 px-3.5 py-3">
            <div className="min-w-[220px] flex-1">
              <p className="text-[12.5px] font-semibold text-ink">Full rebuild</p>
              <p className="text-[11.5px] text-muted">
                Deletes every stored row and downloads the whole history again — several
                minutes. Only needed if the database looks wrong.
              </p>
            </div>
            <label className="flex items-center gap-2 text-[12px] text-muted">
              <input
                type="checkbox"
                checked={confirm}
                onChange={(e) => setConfirm(e.target.checked)}
                className="h-3.5 w-3.5 accent-[var(--color-accent)]"
              />
              I understand
            </label>
            <button
              type="button"
              disabled={!confirm || running}
              onClick={onFullRebuild}
              className={clsx(
                "rounded-full px-3.5 py-1.5 text-[12px] font-semibold transition",
                confirm && !running
                  ? "bg-down text-white hover:brightness-110"
                  : "cursor-not-allowed bg-line text-faint",
              )}
            >
              Rebuild everything
            </button>
          </div>

          {meta?.index_note ? (
            <p className="mt-3 text-[11.5px] text-faint">
              Index selection note: {meta.index_note}
            </p>
          ) : null}
        </div>
      ) : null}
    </Card>
  );
}
