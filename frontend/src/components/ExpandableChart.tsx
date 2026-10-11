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
      <div 
        className="relative group cursor-pointer h-full w-full"
        onClick={() => setIsExpanded(true)}
      >
        {children}
        <div className="absolute top-2 right-2 rounded-lg bg-surface/80 p-2 text-muted opacity-0 transition-all group-hover:opacity-100 pointer-events-none">
          <Maximize2 size={16} />
        </div>
      </div>
      
      <ChartModal isOpen={isExpanded} onClose={() => setIsExpanded(false)} title={title}>
        <div onClick={(e) => e.stopPropagation()}>
          {expandedContent || children}
        </div>
      </ChartModal>
    </>
  );
}
