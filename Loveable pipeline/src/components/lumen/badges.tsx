import type { Priority, ItemType, Urgency, TimeEstimate } from "@/lib/mock-data";
import { cn } from "@/lib/utils";
import { Clock, Zap } from "lucide-react";

const dotMap: Record<Priority, string> = {
  high: "bg-priority-high",
  med: "bg-ink-faint/60",
  low: "bg-ink-faint/30",
};

export function PriorityDot({ priority, className }: { priority: Priority; className?: string }) {
  return (
    <span
      aria-hidden
      className={cn("inline-block size-2 rounded-full shrink-0", dotMap[priority], className)}
    />
  );
}

const typeLabel: Record<ItemType, string> = {
  funding: "Funding",
  news: "News",
  email: "Email",
  report: "Report",
  alert: "Alert",
};

/** Single badge component. Color varies only via `tone`. */
export function Badge({
  children,
  tone = "neutral",
  className,
}: {
  children: React.ReactNode;
  tone?: "neutral" | "accent" | "outline" | "ink";
  className?: string;
}) {
  const tones: Record<string, string> = {
    neutral: "bg-muted text-ink-soft",
    accent: "bg-accent text-ink",
    outline: "border border-hairline text-ink-soft bg-transparent",
    ink: "bg-ink text-background",
  };
  return <span className={cn("badge", tones[tone], className)}>{children}</span>;
}

export function TypeBadge({ type }: { type: ItemType }) {
  return <Badge tone="neutral">{typeLabel[type]}</Badge>;
}

export function Tag({ children }: { children: React.ReactNode }) {
  return <Badge tone="outline">{children}</Badge>;
}

const urgencyTone: Record<Urgency, "neutral" | "accent" | "ink"> = {
  now: "ink",
  today: "accent",
  "this week": "neutral",
  later: "neutral",
};

const urgencyLabel: Record<Urgency, string> = {
  now: "Now",
  today: "Today",
  "this week": "This week",
  later: "Later",
};

export function UrgencyBadge({ urgency }: { urgency: Urgency }) {
  return (
    <Badge tone={urgencyTone[urgency]} className="gap-1">
      <Zap className="size-3" /> {urgencyLabel[urgency]}
    </Badge>
  );
}

export function TimeBadge({ timeEstimate }: { timeEstimate: TimeEstimate }) {
  return (
    <Badge tone="outline" className="gap-1">
      <Clock className="size-3" /> {timeEstimate}
    </Badge>
  );
}
