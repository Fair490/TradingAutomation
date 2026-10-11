/**
 * Debug Terminal - Real-time log viewer and diagnostic tool.
 * 
 * Features:
 * - Live log streaming via SSE
 * - Filtering by level, source, and time
 * - Search functionality
 * - Pause/resume, clear, export
 * - Connection status indicator
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Download, Pause, Play, Search, Trash2 } from "lucide-react";
import { Card } from "./ui";

// Types
type LogLevel = "DEBUG" | "INFO" | "SUCCESS" | "WARNING" | "ERROR" | "CRITICAL";
type LogSource = "frontend" | "backend" | "api" | "trading" | "loader" | "system";
type TimeFilter = "recent" | "5min" | "1hour" | "all";

interface LogEvent {
  type: "log" | "connected";
  timestamp: number;
  level: LogLevel;
  source: LogSource;
  message: string;
  module?: string;
  request_id?: string;
  details?: Record<string, any>;
  exception?: string;
}

interface LogStats {
  total: number;
  max_size: number;
  level_debug: number;
  level_info: number;
  level_success: number;
  level_warning: number;
  level_error: number;
  level_critical: number;
}

// Color mapping for log levels
const LEVEL_COLORS: Record<LogLevel, string> = {
  DEBUG: "text-gray-500",
  INFO: "text-blue-600 dark:text-blue-400",
  SUCCESS: "text-green-600 dark:text-green-400",
  WARNING: "text-yellow-600 dark:text-yellow-400",
  ERROR: "text-red-600 dark:text-red-400",
  CRITICAL: "text-red-700 dark:text-red-500 font-bold",
};

const SOURCE_COLORS: Record<LogSource, string> = {
  frontend: "bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200",
  backend: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
  api: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
  trading: "bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200",
  loader: "bg-cyan-100 text-cyan-800 dark:bg-cyan-900 dark:text-cyan-200",
  system: "bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-200",
};

export function DebugTerminalPage() {
  const [events, setEvents] = useState<LogEvent[]>([]);
  const [stats, setStats] = useState<LogStats | null>(null);
  const [isPaused, setIsPaused] = useState(false);
  const [autoScroll, setAutoScroll] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [levelFilter, setLevelFilter] = useState<LogLevel | "ALL">("ALL");
  const [sourceFilter, setSourceFilter] = useState<LogSource | "ALL">("ALL");
  const [timeFilter, setTimeFilter] = useState<TimeFilter>("recent");
  const [connectionStatus, setConnectionStatus] = useState<"connected" | "disconnected" | "reconnecting">("disconnected");
  const [expandedEvent, setExpandedEvent] = useState<number | null>(null);

  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  // Fetch stats
  const fetchStats = useCallback(async () => {
    try {
      const response = await fetch("/api/debug/stats");
      if (response.ok) {
        const data = await response.json();
        setStats(data);
      }
    } catch (error) {
      console.error("Failed to fetch stats:", error);
    }
  }, []);

  // Set up SSE connection
  useEffect(() => {
    if (isPaused) return;

    const connectSSE = () => {
      setConnectionStatus("reconnecting");

      const params = new URLSearchParams();
      if (levelFilter !== "ALL") params.append("level", levelFilter);
      if (sourceFilter !== "ALL") params.append("source", sourceFilter);

      const url = `/api/debug/logs/stream?${params.toString()}`;
      const eventSource = new EventSource(url);
      eventSourceRef.current = eventSource;

      eventSource.onopen = () => {
        setConnectionStatus("connected");
      };

      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          
          if (data.type === "connected") {
            setConnectionStatus("connected");
            return;
          }

          if (data.type === "log") {
            setEvents((prev) => {
              const newEvents = [...prev, data];
              // Keep only last 10000 events in memory
              return newEvents.slice(-10000);
            });
          }
        } catch (error) {
          console.error("Failed to parse SSE event:", error);
        }
      };

      eventSource.onerror = () => {
        setConnectionStatus("disconnected");
        eventSource.close();
        // Reconnect after 3 seconds
        setTimeout(connectSSE, 3000);
      };
    };

    connectSSE();
    fetchStats();

    // Refresh stats every 5 seconds
    const statsInterval = setInterval(fetchStats, 5000);

    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
      clearInterval(statsInterval);
    };
  }, [isPaused, levelFilter, sourceFilter, fetchStats]);

  // Auto-scroll to bottom when new events arrive
  useEffect(() => {
    if (autoScroll && scrollContainerRef.current) {
      scrollContainerRef.current.scrollTop = scrollContainerRef.current.scrollHeight;
    }
  }, [events, autoScroll]);

  // Filter events
  const filteredEvents = useMemo(() => {
    let filtered = events;

    // Time filter
    if (timeFilter !== "all") {
      const now = Date.now() / 1000;
      const cutoff =
        timeFilter === "recent" ? now - 60 :
        timeFilter === "5min" ? now - 300 :
        timeFilter === "1hour" ? now - 3600 : 0;
      filtered = filtered.filter((e) => e.timestamp >= cutoff);
    }

    // Search filter
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter(
        (e) =>
          e.message.toLowerCase().includes(query) ||
          e.module?.toLowerCase().includes(query) ||
          e.request_id?.toLowerCase().includes(query)
      );
    }

    return filtered;
  }, [events, timeFilter, searchQuery]);

  // Handlers
  const handleClear = async () => {
    if (!confirm("Clear all logs from the buffer?")) return;
    
    try {
      const response = await fetch("/api/debug/logs", { method: "DELETE" });
      if (response.ok) {
        setEvents([]);
        fetchStats();
      }
    } catch (error) {
      console.error("Failed to clear logs:", error);
    }
  };

  const handleExport = () => {
    const data = JSON.stringify(filteredEvents, null, 2);
    const blob = new Blob([data], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `debug-logs-${new Date().toISOString()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleCopy = (event: LogEvent) => {
    const text = JSON.stringify(event, null, 2);
    navigator.clipboard.writeText(text);
  };

  const formatTimestamp = (timestamp: number) => {
    const date = new Date(timestamp * 1000);
    return date.toLocaleString("en-IN", {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    });
  };

  return (
    <div className="mx-auto max-w-[1600px] px-4 py-6 sm:px-6">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-ink">Debug Terminal</h1>
        <p className="mt-1 text-sm text-muted">
          Real-time logs and diagnostics for the trading system
        </p>
      </div>

      {/* Stats Bar */}
      <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
        <div className="rounded-lg border border-line bg-surface px-3 py-2">
          <div className="text-xs text-muted">Total</div>
          <div className="text-lg font-semibold text-ink">{stats?.total ?? 0}</div>
        </div>
        <div className="rounded-lg border border-line bg-surface px-3 py-2">
          <div className="text-xs text-muted">Debug</div>
          <div className="text-lg font-semibold text-gray-500">{stats?.level_debug ?? 0}</div>
        </div>
        <div className="rounded-lg border border-line bg-surface px-3 py-2">
          <div className="text-xs text-muted">Info</div>
          <div className="text-lg font-semibold text-blue-600 dark:text-blue-400">{stats?.level_info ?? 0}</div>
        </div>
        <div className="rounded-lg border border-line bg-surface px-3 py-2">
          <div className="text-xs text-muted">Success</div>
          <div className="text-lg font-semibold text-green-600 dark:text-green-400">{stats?.level_success ?? 0}</div>
        </div>
        <div className="rounded-lg border border-line bg-surface px-3 py-2">
          <div className="text-xs text-muted">Warning</div>
          <div className="text-lg font-semibold text-yellow-600 dark:text-yellow-400">{stats?.level_warning ?? 0}</div>
        </div>
        <div className="rounded-lg border border-line bg-surface px-3 py-2">
          <div className="text-xs text-muted">Error</div>
          <div className="text-lg font-semibold text-red-600 dark:text-red-400">{stats?.level_error ?? 0}</div>
        </div>
        <div className="rounded-lg border border-line bg-surface px-3 py-2">
          <div className="text-xs text-muted">Critical</div>
          <div className="text-lg font-bold text-red-700 dark:text-red-500">{stats?.level_critical ?? 0}</div>
        </div>
      </div>

      {/* Controls */}
      <Card className="mb-4">
        <div className="flex flex-wrap items-center gap-3">
          {/* Connection Status */}
          <div className="flex items-center gap-2">
            <div
              className={`h-2 w-2 rounded-full ${
                connectionStatus === "connected"
                  ? "bg-green-500"
                  : connectionStatus === "reconnecting"
                  ? "bg-yellow-500 animate-pulse"
                  : "bg-red-500"
              }`}
            />
            <span className="text-xs text-muted capitalize">{connectionStatus}</span>
          </div>

          {/* Search */}
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
            <input
              type="text"
              placeholder="Search logs..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full rounded-lg border border-line bg-surface-2 py-2 pl-10 pr-3 text-sm text-ink placeholder:text-muted focus:border-accent focus:outline-none"
            />
          </div>

          {/* Level Filter */}
          <select
            value={levelFilter}
            onChange={(e) => setLevelFilter(e.target.value as LogLevel | "ALL")}
            className="rounded-lg border border-line bg-surface-2 px-3 py-2 text-sm text-ink focus:border-accent focus:outline-none"
          >
            <option value="ALL">All Levels</option>
            <option value="DEBUG">Debug</option>
            <option value="INFO">Info</option>
            <option value="SUCCESS">Success</option>
            <option value="WARNING">Warning</option>
            <option value="ERROR">Error</option>
            <option value="CRITICAL">Critical</option>
          </select>

          {/* Source Filter */}
          <select
            value={sourceFilter}
            onChange={(e) => setSourceFilter(e.target.value as LogSource | "ALL")}
            className="rounded-lg border border-line bg-surface-2 px-3 py-2 text-sm text-ink focus:border-accent focus:outline-none"
          >
            <option value="ALL">All Sources</option>
            <option value="frontend">Frontend</option>
            <option value="backend">Backend</option>
            <option value="api">API</option>
            <option value="trading">Trading</option>
            <option value="loader">Loader</option>
            <option value="system">System</option>
          </select>

          {/* Time Filter */}
          <select
            value={timeFilter}
            onChange={(e) => setTimeFilter(e.target.value as TimeFilter)}
            className="rounded-lg border border-line bg-surface-2 px-3 py-2 text-sm text-ink focus:border-accent focus:outline-none"
          >
            <option value="recent">Last Minute</option>
            <option value="5min">Last 5 Minutes</option>
            <option value="1hour">Last Hour</option>
            <option value="all">All Time</option>
          </select>

          {/* Action Buttons */}
          <button
            onClick={() => setIsPaused(!isPaused)}
            className={`flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition ${
              isPaused
                ? "bg-green-100 text-green-800 hover:bg-green-200 dark:bg-green-900 dark:text-green-200"
                : "bg-yellow-100 text-yellow-800 hover:bg-yellow-200 dark:bg-yellow-900 dark:text-yellow-200"
            }`}
          >
            {isPaused ? <Play className="h-4 w-4" /> : <Pause className="h-4 w-4" />}
            {isPaused ? "Resume" : "Pause"}
          </button>

          <button
            onClick={() => setAutoScroll(!autoScroll)}
            className={`rounded-lg px-3 py-2 text-sm font-medium transition ${
              autoScroll
                ? "bg-blue-100 text-blue-800 hover:bg-blue-200 dark:bg-blue-900 dark:text-blue-200"
                : "bg-gray-100 text-gray-800 hover:bg-gray-200 dark:bg-gray-900 dark:text-gray-200"
            }`}
          >
            Auto-scroll: {autoScroll ? "ON" : "OFF"}
          </button>

          <button
            onClick={handleClear}
            className="flex items-center gap-1.5 rounded-lg bg-red-100 px-3 py-2 text-sm font-medium text-red-800 transition hover:bg-red-200 dark:bg-red-900 dark:text-red-200 dark:hover:bg-red-800"
          >
            <Trash2 className="h-4 w-4" />
            Clear
          </button>

          <button
            onClick={handleExport}
            className="flex items-center gap-1.5 rounded-lg bg-surface-2 px-3 py-2 text-sm font-medium text-ink transition hover:bg-surface"
          >
            <Download className="h-4 w-4" />
            Export
          </button>
        </div>
      </Card>

      {/* Log Display */}
      <Card className="overflow-hidden">
        <div
          ref={scrollContainerRef}
          className="h-[600px] overflow-y-auto bg-gray-50 dark:bg-gray-900 font-mono text-xs"
        >
          {filteredEvents.length === 0 ? (
            <div className="flex h-full items-center justify-center text-muted">
              {connectionStatus === "connected"
                ? "No logs to display. Logs will appear here as they are generated."
                : "Connecting to log stream..."}
            </div>
          ) : (
            <div className="divide-y divide-gray-200 dark:divide-gray-800">
              {filteredEvents.map((event, idx) => (
                <div
                  key={idx}
                  className="group cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-800"
                  onClick={() => setExpandedEvent(expandedEvent === idx ? null : idx)}
                >
                  <div className="flex items-start gap-3 px-4 py-2">
                    {/* Timestamp */}
                    <div className="shrink-0 text-gray-500 dark:text-gray-400">
                      {formatTimestamp(event.timestamp)}
                    </div>

                    {/* Level */}
                    <div className={`shrink-0 font-semibold ${LEVEL_COLORS[event.level]}`}>
                      {event.level.padEnd(8)}
                    </div>

                    {/* Source */}
                    <div className="shrink-0">
                      <span className={`rounded px-2 py-0.5 text-[10px] font-medium ${SOURCE_COLORS[event.source]}`}>
                        {event.source}
                      </span>
                    </div>

                    {/* Message */}
                    <div className="min-w-0 flex-1 text-ink">
                      <div className="break-words">{event.message}</div>
                      {event.module && (
                        <div className="mt-0.5 text-[10px] text-gray-500 dark:text-gray-400">
                          {event.module}
                          {event.request_id && ` • ${event.request_id}`}
                        </div>
                      )}
                    </div>

                    {/* Copy Button */}
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleCopy(event);
                      }}
                      className="shrink-0 opacity-0 transition group-hover:opacity-100"
                      title="Copy to clipboard"
                    >
                      <svg className="h-4 w-4 text-gray-400 hover:text-gray-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                      </svg>
                    </button>
                  </div>

                  {/* Expanded Details */}
                  {expandedEvent === idx && (
                    <div className="border-t border-gray-200 bg-gray-100 px-4 py-3 dark:border-gray-800 dark:bg-gray-800">
                      <div className="space-y-2">
                        <div>
                          <div className="text-[10px] font-semibold text-gray-600 dark:text-gray-400">TIMESTAMP</div>
                          <div className="text-ink">{new Date(event.timestamp * 1000).toISOString()}</div>
                        </div>
                        {event.module && (
                          <div>
                            <div className="text-[10px] font-semibold text-gray-600 dark:text-gray-400">MODULE</div>
                            <div className="text-ink">{event.module}</div>
                          </div>
                        )}
                        {event.request_id && (
                          <div>
                            <div className="text-[10px] font-semibold text-gray-600 dark:text-gray-400">REQUEST ID</div>
                            <div className="text-ink">{event.request_id}</div>
                          </div>
                        )}
                        {event.details && (
                          <div>
                            <div className="text-[10px] font-semibold text-gray-600 dark:text-gray-400">DETAILS</div>
                            <pre className="overflow-x-auto rounded bg-white p-2 text-ink dark:bg-gray-900">
                              {JSON.stringify(event.details, null, 2)}
                            </pre>
                          </div>
                        )}
                        {event.exception && (
                          <div>
                            <div className="text-[10px] font-semibold text-gray-600 dark:text-gray-400">EXCEPTION</div>
                            <pre className="overflow-x-auto rounded bg-red-50 p-2 text-red-900 dark:bg-red-900 dark:text-red-100">
                              {event.exception}
                            </pre>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </Card>

      {/* Footer */}
      <div className="mt-4 text-center text-xs text-muted">
        Showing {filteredEvents.length} of {events.length} events • Buffer: {stats?.total ?? 0} / {stats?.max_size ?? 10000}
      </div>
    </div>
  );
}
