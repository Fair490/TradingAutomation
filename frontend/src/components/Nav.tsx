/** Top-level page tabs. Six pages: Market Health, Sector Performance, and
 *  four coming-soon placeholders (Scanner, Portfolio, Terminal, Trade Leader).
 */

export type PageKey =
  | "market"
  | "sector"
  | "scanner"
  | "portfolio"
  | "terminal"
  | "trade";

const PAGES: { key: PageKey; label: string; comingSoon?: boolean }[] = [
  { key: "market", label: "Market Health" },
  { key: "sector", label: "Sector Performance" },
  { key: "scanner", label: "Scanner", comingSoon: true },
  { key: "portfolio", label: "Portfolio", comingSoon: true },
  { key: "terminal", label: "Terminal", comingSoon: true },
  { key: "trade", label: "Trade Leader", comingSoon: true },
];

export function Nav({
  active,
  onChange,
}: {
  active: PageKey;
  onChange: (page: PageKey) => void;
}) {
  return (
    <nav
      role="tablist"
      className="sticky top-[60px] z-20 border-b border-line bg-surface/95 backdrop-blur"
    >
      <div className="mx-auto flex max-w-[1400px] gap-0.5 overflow-x-auto px-4 sm:px-6">
        {PAGES.map((p) => {
          const isActive = p.key === active;
          return (
            <button
              key={p.key}
              role="tab"
              aria-selected={isActive}
              onClick={() => onChange(p.key)}
              className={[
                "relative flex shrink-0 items-center gap-1.5 px-3.5 py-2.5 text-[12.5px] font-medium transition",
                isActive
                  ? "text-ink"
                  : "text-muted hover:text-ink",
              ].join(" ")}
            >
              {p.label}
              {p.comingSoon ? (
                <span className="rounded-full bg-accent/15 px-1.5 py-[1px] text-[9.5px] font-semibold uppercase tracking-wide text-accent">
                  soon
                </span>
              ) : null}
              {isActive ? (
                <span className="absolute inset-x-2 bottom-0 h-[2px] rounded-full bg-accent" />
              ) : null}
            </button>
          );
        })}
      </div>
    </nav>
  );
}
