/** Sector Performance page — ETF leaderboard + compare chart. */

import type { RangeKey } from "../lib/api";
import { EtfPanel } from "./EtfPanel";
import { ErrorBoundary } from "./ErrorBoundary";

export function SectorPerformancePage({
  range,
  theme,
  rsOn,
  rsBenchmark,
}: {
  range: RangeKey;
  theme: string;
  rsOn: boolean;
  rsBenchmark: string;
}) {
  return (
    <div className="mx-auto max-w-[1400px] px-4 py-6 sm:px-6 sm:py-8">
      <ErrorBoundary label="Sector & thematic ETFs">
        <EtfPanel range={range} theme={theme} rsOn={rsOn} rsBenchmark={rsBenchmark} />
      </ErrorBoundary>
    </div>
  );
}
