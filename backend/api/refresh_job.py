"""
Background refresh job.

The download takes minutes on a first run, so the HTTP request only *starts*
it; the frontend polls ``GET /api/refresh/status`` for the progress bar.
Only one job can run at a time.
"""

from __future__ import annotations

import datetime as dt
import threading

from backend.compute import breadth as breadth_calc
from backend.loaders import prices as price_loader

_LOCK = threading.Lock()


class RefreshJob:
    def __init__(self) -> None:
        self.running = False
        self.progress = 0.0
        self.message = ""
        self.started_at: dt.datetime | None = None
        self.finished_at: dt.datetime | None = None
        self.status: str = "idle"  # idle | running | success | success_with_warnings | failed
        self.summary: str | None = None
        self.rows_added = 0
        self.tickers_updated = 0
        self.tickers_attempted = 0
        self.tickers_succeeded = 0
        self.tickers_failed = 0
        self.tickers_skipped = 0
        self.failures: list[list[str]] = []
        self.error: str | None = None
        self.calculation_success: bool | None = None
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------ #
    def state(self) -> dict:
        return {
            "running": self.running,
            "status": self.status,
            "progress": round(self.progress, 4),
            "message": self.message,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "summary": self.summary,
            "rows_added": self.rows_added,
            "tickers_updated": self.tickers_updated,
            "tickers_attempted": self.tickers_attempted,
            "tickers_succeeded": self.tickers_succeeded,
            "tickers_failed": self.tickers_failed,
            "tickers_skipped": self.tickers_skipped,
            "failures": self.failures[:50],
            "error": self.error,
            "calculation_success": self.calculation_success,
        }

    def start(self, full_rebuild: bool = False) -> bool:
        """Returns False when a refresh is already in flight."""
        with _LOCK:
            if self.running:
                return False
            self.running = True
            self.progress = 0.0
            self.message = "Starting…"
            self.started_at = dt.datetime.now()
            self.finished_at = None
            self.status = "running"
            self.summary = None
            self.error = None
            self.rows_added = 0
            self.tickers_updated = 0
            self.tickers_attempted = 0
            self.tickers_succeeded = 0
            self.tickers_failed = 0
            self.tickers_skipped = 0
            self.failures = []
            self.calculation_success = None

        self._thread = threading.Thread(
            target=self._run, args=(full_rebuild,), daemon=True
        )
        self._thread.start()
        return True

    # ------------------------------------------------------------------ #
    def _on_progress(self, pct: float, msg: str) -> None:
        self.progress = pct
        self.message = msg

    def _run(self, full_rebuild: bool) -> None:
        try:
            report = price_loader.refresh(
                full_rebuild=full_rebuild, progress=self._on_progress
            )
            self.rows_added = report.rows_added
            self.tickers_updated = report.tickers_updated
            self.tickers_attempted = report.tickers_attempted
            self.tickers_succeeded = report.tickers_succeeded
            self.tickers_failed = report.tickers_failed
            self.tickers_skipped = report.tickers_skipped
            self.failures = [[t, e] for t, e in report.failures]

            self._on_progress(0.95, "Recomputing breadth and advance/decline…")
            computed = breadth_calc.recompute(full=full_rebuild)
            self.calculation_success = True

            # Determine final status based on outcomes
            if report.tickers_failed > 0:
                self.status = "success_with_warnings"
            elif report.rows_added == 0 and not report.failures:
                self.status = "success"
                self.summary = (
                    "No new data — the market was closed or Yahoo has nothing "
                    "newer yet. Everything is already up to date."
                )
            else:
                self.status = "success"
                self.summary = (
                    f"{report.summary()}. Recomputed {computed['breadth']} breadth "
                    f"days and {computed['advance_decline']} A/D days."
                )
            self._on_progress(1.0, "Done")
        except FileNotFoundError as exc:
            self.status = "failed"
            self.error = str(exc)
            self.message = "Failed"
        except Exception as exc:  # pragma: no cover - surfaced in the UI
            self.status = "failed"
            self.error = f"{type(exc).__name__}: {exc}"
            self.message = "Failed"
        finally:
            self.running = False
            self.finished_at = dt.datetime.now()


JOB = RefreshJob()
