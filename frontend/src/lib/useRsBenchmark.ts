/**
 * Hook for fetching RS benchmark data.
 */

import useSWR from "swr";
import type { RangeKey, Point } from "./api";
import { fetcher } from "./api";

interface BenchmarkResponse {
  ticker: string;
  name: string;
  points: Point[];
  range: string;
}

export function useRsBenchmark(ticker: string, range: RangeKey) {
  const shouldFetch = ticker && ticker.length > 0;
  const url = shouldFetch ? `/api/rs-benchmark?ticker=${encodeURIComponent(ticker)}&range=${range}` : null;
  
  const { data, error } = useSWR<BenchmarkResponse>(url, fetcher, {
    revalidateOnFocus: false,
    dedupingInterval: 60000,
  });

  return {
    data: data ? { points: data.points, name: data.name } : null,
    error,
  };
}
