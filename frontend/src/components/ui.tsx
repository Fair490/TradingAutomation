/** Shared UI primitives: cards, segmented controls, switches, pills, skeletons. */

import clsx from "clsx";
import type { CSSProperties, ReactNode } from "react";

export function Card({
  children,
  className,
  padded = true,
}: {
  children: ReactNode;
  className?: string;
  padded?: boolean;
}) {
  return (
    <section
      className={clsx(
        "rounded-[var(--radius-card)] border border-line bg-surface",
        "shadow-[0_1px_2px_rgba(15,23,32,0.04)]",
        padded && "p-4 sm:p-5",
        className,
      )}
    >
      {children}
    </section>
  );
}

export function CardHeader({
  title,
  subtitle,
  actions,
  className,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <header
      className={clsx(
        "mb-4 flex flex-wrap items-start justify-between gap-x-4 gap-y-3",
        className,
      )}
    >
      <div className="min-w-0">
        <h2 className="text-[15px] font-semibold tracking-[-0.01em] text-ink">
          {title}
        </h2>
        {subtitle ? (
          <p className="mt-0.5 text-[12.5px] leading-snug text-muted">{subtitle}</p>
        ) : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </header>
  );
}

export function SectionTitle({
  children,
  hint,
}: {
  children: ReactNode;
  hint?: ReactNode;
}) {
  return (
    <div className="mb-3 flex items-baseline justify-between gap-4">
      <h2 className="text-[13px] font-semibold uppercase tracking-[0.09em] text-muted">
        {children}
      </h2>
      {hint ? <span className="text-[12px] text-faint">{hint}</span> : null}
    </div>
  );
}

export function Segmented<T extends string>({
  options,
  value,
  onChange,
  size = "md",
  ariaLabel,
}: {
  options: readonly T[] | readonly { value: T; label: string }[];
  value: T;
  onChange: (next: T) => void;
  size?: "sm" | "md";
  ariaLabel?: string;
}) {
  const items = options.map((o) =>
    typeof o === "string" ? { value: o as T, label: o as string } : o,
  );
  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      className={clsx(
        "inline-flex items-center gap-0.5 rounded-full border border-line bg-surface-2 p-0.5",
      )}
    >
      {items.map((item) => {
        const active = item.value === value;
        return (
          <button
            key={item.value}
            role="tab"
            aria-selected={active}
            onClick={() => onChange(item.value)}
            className={clsx(
              "rounded-full font-medium transition-all duration-150",
              size === "sm" ? "px-2.5 py-1 text-[11.5px]" : "px-3 py-1.5 text-[12.5px]",
              active
                ? "bg-surface text-ink shadow-[0_1px_2px_rgba(15,23,32,0.10)] ring-1 ring-line"
                : "text-muted hover:text-ink",
            )}
          >
            {item.label}
          </button>
        );
      })}
    </div>
  );
}

export function Switch({
  checked,
  onChange,
  label,
  disabled,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  label: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={clsx(
        "group inline-flex items-center gap-2 text-[12.5px] font-medium transition",
        disabled ? "cursor-not-allowed text-faint" : "text-muted hover:text-ink",
      )}
    >
      <span
        className={clsx(
          "relative h-[18px] w-[32px] rounded-full transition-colors duration-200",
          checked && !disabled ? "bg-accent" : "bg-line",
        )}
      >
        <span
          className={clsx(
            "absolute top-[2px] h-[14px] w-[14px] rounded-full bg-white shadow transition-all duration-200",
            checked ? "left-[16px]" : "left-[2px]",
          )}
        />
      </span>
      {label}
    </button>
  );
}

export function Pill({
  children,
  tone = "neutral",
  className,
}: {
  children: ReactNode;
  tone?: "neutral" | "up" | "down" | "accent" | "warn";
  className?: string;
}) {
  const tones = {
    neutral: "border-line bg-surface-2 text-muted",
    up: "border-transparent bg-up/10 text-up",
    down: "border-transparent bg-down/10 text-down",
    accent: "border-transparent bg-accent/12 text-accent",
    warn: "border-amber-400/30 bg-amber-400/10 text-amber-600 dark:text-amber-300",
  } as const;
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 rounded-full border px-2 py-[3px] text-[11.5px] font-medium",
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function Skeleton({
  className,
  style,
}: {
  className?: string;
  style?: CSSProperties;
}) {
  return <div style={style} className={clsx("skeleton rounded-lg", className)} />;
}

export function ChartSkeleton({ height = 300 }: { height?: number }) {
  return (
    <div className="space-y-3">
      <Skeleton className="h-3 w-28" />
      <Skeleton style={{ height }} className="w-full" />
    </div>
  );
}

export function ErrorNote({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-down/30 bg-down/5 px-3 py-2 text-[12.5px] text-down">
      {message}
    </div>
  );
}

export function EmptyNote({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-[120px] items-center justify-center rounded-lg border border-dashed border-line px-4 py-6 text-center text-[12.5px] text-muted">
      {children}
    </div>
  );
}

export function Footnote({ children }: { children: ReactNode }) {
  return <p className="mt-3 text-[11.5px] leading-relaxed text-faint">{children}</p>;
}
