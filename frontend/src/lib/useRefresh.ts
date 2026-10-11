/**
 * Hook for managing data refresh operations.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type { RefreshState } from "./api";
import { fetcher } from "./api";

interface UseRefreshReturn {
  running: boolean;
  state: RefreshState | null;
  error: string | null;
  start: (fullRebuild: boolean) => Promise<void>;
}

export function useRefresh(): UseRefreshReturn {
  const [running, setRunning] = useState(false);
  const [state, setState] = useState<RefreshState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const pollIntervalRef = useRef<number | null>(null);

  // Fetch current refresh status
  const fetchStatus = useCallback(async () => {
    try {
      const status = await fetcher<RefreshState>("/api/refresh/status");
      setState(status);
      setRunning(status.running);
      if (!status.running && status.ok === false && status.error) {
        setError(status.error);
      }
    } catch (err) {
      console.error("Failed to fetch refresh status:", err);
    }
  }, []);

  // Poll for status updates while refresh is running
  useEffect(() => {
    if (running) {
      pollIntervalRef.current = window.setInterval(fetchStatus, 1000);
    } else if (pollIntervalRef.current) {
      window.clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }

    return () => {
      if (pollIntervalRef.current) {
        window.clearInterval(pollIntervalRef.current);
      }
    };
  }, [running, fetchStatus]);

  // Initial status fetch
  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  // Start a refresh operation
  const start = useCallback(async (fullRebuild: boolean) => {
    setError(null);
    setRunning(true);
    
    try {
      const res = await fetch("/api/refresh", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ full_rebuild: fullRebuild }),
      });

      if (!res.ok) {
        const text = await res.text();
        throw new Error(`Refresh failed: ${res.status} ${text}`);
      }

      // Status will be updated by the polling interval
    } catch (err) {
      console.error("Refresh failed:", err);
      setError(err instanceof Error ? err.message : "Unknown error");
      setRunning(false);
    }
  }, []);

  return { running, state, error, start };
}
