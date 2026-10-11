/**
 * Keeps a render fault contained.
 *
 * Without this, one bad chart throws, React unmounts the whole tree and the
 * page goes blank with nothing on screen to explain why. Each panel gets its
 * own boundary, so a failure stays limited to that card and the error is shown
 * in plain sight instead of only in the console.
 */

import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle, RotateCcw } from "lucide-react";

interface Props {
  children: ReactNode;
  label: string;
}

interface State {
  error: Error | null;
  info: string;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null, info: "" };

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Keep the component stack: it names the chart that failed.
    this.setState({ info: (info.componentStack ?? "").split("\n").slice(1, 5).join("\n") });
    console.error(`[${this.props.label}]`, error);
  }

  render() {
    const { error, info } = this.state;
    if (!error) return this.props.children;

    return (
      <section className="rounded-[var(--radius-card)] border border-down/40 bg-down/5 p-4 sm:p-5">
        <div className="flex items-start gap-2.5">
          <AlertTriangle size={16} className="mt-[2px] shrink-0 text-down" />
          <div className="min-w-0 flex-1">
            <h2 className="text-[14px] font-semibold text-ink">
              {this.props.label} could not be drawn
            </h2>
            <p className="mt-1 font-mono text-[12px] leading-relaxed break-words text-down">
              {error.message || String(error)}
            </p>
            {info ? (
              <pre className="scroll-thin mt-2 max-h-28 overflow-auto rounded-lg bg-surface-2 p-2 font-mono text-[11px] leading-relaxed text-muted">
                {info.trim()}
              </pre>
            ) : null}
            <p className="mt-2 text-[12px] text-muted">
              The rest of the dashboard keeps working. If this persists, note the
              message above — it names the exact component.
            </p>
            <button
              type="button"
              onClick={() => this.setState({ error: null, info: "" })}
              className="mt-2.5 inline-flex items-center gap-1.5 rounded-full border border-line bg-surface px-3 py-1.5 text-[12px] font-medium text-ink transition hover:bg-surface-2"
            >
              <RotateCcw size={13} /> Try again
            </button>
          </div>
        </div>
      </section>
    );
  }
}
