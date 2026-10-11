import { useState, ReactNode } from "react";
import { Maximize2 } from "lucide-react";
import { ChartModal } from "./ChartModal";

interface ExpandableChartProps {
  title: string;
  children: ReactNode;
  expandedContent?: ReactNode;
}

export function ExpandableChart({ title, children, expandedContent }: ExpandableChartProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <>
      <div className="relative group">
        {children}
        <button
          onClick={() => setIsExpanded(true)}
          className="absolute top-2 right-2 rounded-lg bg-surface/80 p-2 text-muted opacity-0 transition-all hover:bg-surface hover:text-ink group-hover:opacity-100"
          aria-label="Expand chart"
        >
          <Maximize2 size={16} />
        </button>
      </div>
      
      <ChartModal isOpen={isExpanded} onClose={() => setIsExpanded(false)} title={title}>
        {expandedContent || children}
      </ChartModal>
    </>
  );
}
