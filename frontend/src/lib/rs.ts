/**
 * Relative strength calculation utilities.
 */

import type { Point } from "./api";

export const RS_DEFAULT_TICKER = "^CRSLDX"; // Nifty 500 as default benchmark

export interface RsBenchmark {
  ticker: string;
  label: string;
}

export const RS_BENCHMARKS: RsBenchmark[] = [
  { ticker: "^CRSLDX", label: "Nifty 500" },
  { ticker: "^NSEI", label: "Nifty 50" },
  { ticker: "^NSEBANK", label: "Bank Nifty" },
];

export interface RsPoint {
  date: string;
  crs: number | null;
  rising: boolean;
}

export interface RsAth {
  date: string;
  crs: number;
}

export interface RsSeries {
  points: RsPoint[];
  ath: RsAth | null;
}

/**
 * Compute relative strength between two price series (as Point arrays).
 * Returns an RsSeries object with points and ath.
 */
export function computeRS(
  stockPoints: Point[],
  benchmarkPoints: Point[]
): RsSeries {
  return computeRsSeries(stockPoints, benchmarkPoints);
}

/**
 * Compute relative strength as a series of points.
 */
export function computeRsSeries(
  stockPoints: Point[],
  benchmarkPoints: Point[]
): RsSeries {
  const points: RsPoint[] = [];
  const benchmarkMap = new Map<string, number | null>();

  // Index benchmark by date
  for (const bp of benchmarkPoints) {
    benchmarkMap.set(bp.date, bp.value);
  }

  // Compute RS for each stock point
  let prevRs: number | null = null;
  let ath: RsAth | null = null;
  let maxCrs = -Infinity;
  
  for (const sp of stockPoints) {
    const benchmarkValue = benchmarkMap.get(sp.date);
    
    if (sp.value === null || sp.value === undefined || benchmarkValue === null || benchmarkValue === undefined) {
      points.push({ date: sp.date, crs: null, rising: true });
    } else if (benchmarkValue === 0) {
      points.push({ date: sp.date, crs: null, rising: true });
    } else {
      const crs = (sp.value / benchmarkValue) * 100;
      const rising = prevRs === null || crs >= prevRs;
      points.push({ date: sp.date, crs, rising });
      
      // Track all-time high
      if (crs > maxCrs) {
        maxCrs = crs;
        ath = { date: sp.date, crs };
      }
      
      prevRs = crs;
    }
  }

  return { points, ath };
}

/**
 * Compute relative strength percentage change from initial value.
 */
export function computeRSPercent(
  stockPoints: Point[],
  benchmarkPoints: Point[]
): RsSeries {
  const rsSeries = computeRS(stockPoints, benchmarkPoints);
  
  if (rsSeries.points.length === 0) return rsSeries;

  const initialValue = rsSeries.points[0]?.crs;
  if (initialValue === null || initialValue === undefined || initialValue === 0) {
    return rsSeries;
  }

  const rebasedPoints = rsSeries.points.map((p) => ({
    ...p,
    crs: p.crs === null ? null : ((p.crs - initialValue) / initialValue) * 100,
  }));

  return { points: rebasedPoints, ath: rsSeries.ath };
}
