/** Placeholder for pages in phase 2. Each one gets its own icon + a one-line
 *  description of what it will do, so the user can picture the finished app.
 */

import {
  BarChart3,
  Briefcase,
  LineChart,
  Radar,
  type LucideIcon,
} from "lucide-react";
import type { PageKey } from "./Nav";
import { Card } from "./ui";

const META: Record<
  Exclude<PageKey, "market" | "sector">,
  { title: string; blurb: string; Icon: LucideIcon }
> = {
  scanner: {
    title: "Scanner",
    blurb:
      "Screen the universe by RS, distance from moving averages, breakouts and volume.",
    Icon: Radar,
  },
  portfolio: {
    title: "Portfolio",
    blurb:
      "Track your holdings with live P&L, sector exposure and contribution to risk.",
    Icon: Briefcase,
  },
  terminal: {
    title: "Terminal",
    blurb: "Quick commands, watchlists and keyboard-driven research tools.",
    Icon: BarChart3,
  },
  trade: {
    title: "Trade Leader",
    blurb: "Relative-strength leaders across sectors — updated every session.",
    Icon: LineChart,
  },
};

export function ComingSoonPage({ page }: { page: Exclude<PageKey, "market" | "sector"> }) {
  const { title, blurb, Icon } = META[page];
  return (
    <div className="mx-auto max-w-[1400px] px-4 py-10 sm:px-6 sm:py-16">
      <Card className="mx-auto max-w-xl text-center">
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-accent/15 text-accent">
          <Icon size={26} />
        </div>
        <h2 className="mt-4 text-[18px] font-semibold tracking-tight text-ink">
          {title}
        </h2>
        <p className="mt-2 text-[13px] leading-relaxed text-muted">{blurb}</p>
        <p className="mt-5 text-[11.5px] font-medium uppercase tracking-[0.16em] text-faint">
          Coming soon
        </p>
      </Card>
    </div>
  );
}
