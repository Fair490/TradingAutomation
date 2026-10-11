import { useEffect, useState } from "react";
import useSWR from "swr";
import type { Meta, RangeKey } from "./lib/api";
import { fetcher } from "./lib/api";
import { useRefresh } from "./lib/useRefresh";
import { RS_DEFAULT_TICKER } from "./lib/rs";
import { TopBar } from "./components/TopBar";
import { Nav, type PageKey } from "./components/Nav";
import { MarketHealthPage } from "./components/MarketHealthPage";
import { SectorPerformancePage } from "./components/SectorPerformancePage";
import { DebugTerminalPage } from "./components/DebugTerminalPage";
import { ComingSoonPage } from "./components/ComingSoonPage";

type Theme = "light" | "dark";

function useTheme() {
  const [theme, setTheme] = useState<Theme>(() => {
    const saved = localStorage.getItem("mh-theme");
    if (saved === "light" || saved === "dark") return saved;
    return window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  });
  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    document.documentElement.style.colorScheme = theme;
    localStorage.setItem("mh-theme", theme);
  }, [theme]);
  return [theme, setTheme] as const;
}

export default function App() {
  const [range, setRange] = useState<RangeKey>("5Y");
  const [page, setPage] = useState<PageKey>("market");
  const [theme, setTheme] = useTheme();
  const [rsOn, setRsOn] = useState(false);
  const [rsBenchmark, setRsBenchmark] = useState<string>(RS_DEFAULT_TICKER);
  const { data: meta } = useSWR<Meta>("/api/meta", fetcher, {
    refreshInterval: 60_000,
  });
  const refresh = useRefresh();
  const [noticeClosed, setNoticeClosed] = useState(false);

  return (
    <div className="min-h-full">
      <TopBar
        meta={meta}
        range={range}
        onRange={setRange}
        theme={theme}
        onTheme={setTheme}
        onRefresh={() => refresh.start(false)}
        running={refresh.running}
        progress={refresh.state?.progress ?? 0}
        rsOn={rsOn}
        onRsToggle={() => setRsOn((v) => !v)}
        rsBenchmark={rsBenchmark}
        onRsBenchmark={setRsBenchmark}
      />

      <Nav active={page} onChange={setPage} />

      {page === "market" ? (
        <MarketHealthPage
          range={range}
          theme={theme}
          meta={meta}
          rsOn={rsOn}
          rsBenchmark={rsBenchmark}
          refresh={{
            running: refresh.running,
            state: refresh.state,
            error: refresh.error,
          }}
          onFullRebuild={() => refresh.start(true)}
          noticeClosed={noticeClosed}
          onNoticeClose={() => setNoticeClosed(true)}
        />
      ) : page === "sector" ? (
        <SectorPerformancePage
          range={range}
          theme={theme}
          rsOn={rsOn}
          rsBenchmark={rsBenchmark}
        />
      ) : page === "terminal" ? (
        <DebugTerminalPage />
      ) : (
        <ComingSoonPage page={page} />
      )}
    </div>
  );
}
