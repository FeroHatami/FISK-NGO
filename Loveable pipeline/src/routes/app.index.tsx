import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useState, Children } from "react";
import { z } from "zod";
import { daysUntil } from "@/lib/mock-data";
import type { Item } from "@/lib/mock-data";
import { useItems } from "@/lib/use-items";
import { PriorityDot, TypeBadge, Badge } from "@/components/lumen/badges";
import { ArrowRight, Calendar } from "lucide-react";
import { AfricaMap, type MapMarker } from "@/components/lumen/africa-map";
import { cn } from "@/lib/utils";
import { useLang, t } from "@/lib/i18n";
import { sortByPriority } from "@/lib/sort-items";

const search = z.object({
  region: z.string().optional(),
});

export const Route = createFileRoute("/app/")({
  validateSearch: search,
  component: BriefPage,
});

const REGION_MARKERS: { id: string; label: string; cx: number; cy: number }[] = [
  { id: "Burundi", label: "Burundi", cx: 290, cy: 290 },
  { id: "East Africa", label: "East Africa", cx: 320, cy: 250 },
  { id: "Germany", label: "Germany", cx: 250, cy: 40 },
  { id: "Malawi", label: "Malawi", cx: 310, cy: 330 },
  { id: "India", label: "India", cx: 410, cy: 180 },
  { id: "Thailand", label: "Thailand", cx: 440, cy: 220 },
  { id: "Indonesia", label: "Indonesia", cx: 450, cy: 290 },
  { id: "Global", label: "Global", cx: 150, cy: 460 },
];

function BriefPage() {
  const navigate = useNavigate({ from: "/app/" });
  const { region } = Route.useSearch();
  const selected = region ?? null;

  const { data: items = [], isLoading, error } = useItems();
  const lang = useLang();

  if (isLoading) {
    return <div className="page"><p className="body-text">{t("inbox.loading", lang)}</p></div>;
  }
  if (error) {
    return <div className="page"><p className="body-text text-priority-high">{t("inbox.error", lang)}</p></div>;
  }

  const visible = sortByPriority(
    selected ? items.filter((i: Item) => i.region.includes(selected)) : items
  );

  const markers: MapMarker[] = REGION_MARKERS.map((m) => ({
    ...m,
    count: items.filter((i: Item) => i.region.includes(m.id)).length,
  }));

  const high = visible.filter((i) => i.priority === "high");
  const med = visible.filter((i) => i.priority === "med");
  const deadlines = visible
    .filter((i) => i.deadline)
    .sort((a, b) => new Date(a.deadline!).getTime() - new Date(b.deadline!).getTime());

  const onSelect = (id: string | null) =>
    navigate({ search: () => ({ region: id ?? undefined }) });

  return (
    <div className="page">
      <div className="mb-8">
        <div className="eyebrow">{t("home.eyebrow", lang)}</div>
        <p className="mt-3 h1-page">
          {t("home.greeting", lang)}
        </p>
        {selected && (
          <div className="mt-4 inline-flex items-center gap-2">
            <Badge tone="accent">
              <span className="size-1.5 rounded-full bg-priority-high" />
              {t("home.filteringBy", lang)} {selected}
            </Badge>
          </div>
        )}
      </div>

      {/* Map — full-width dashboard panel */}
      <div className="mb-10">
        <h2 className="h2-section mb-4">{lang === "DE" ? "Wo etwas passiert" : "Where things are happening"}</h2>
        <div className="rounded-2xl overflow-hidden h-[320px] sm:h-[380px] isolate relative z-0">
          <AfricaMap compact={false} markers={markers} selected={selected} onSelect={onSelect} />
        </div>
      </div>

      <div className="space-y-10">
        <Section title={t("home.actionRequired", lang)} dot="high" count={high.length}>
          {high.map((i) => (
            <BriefCard key={i.id} item={i} />
          ))}
        </Section>

        <Section title={t("home.importantUpdates", lang)} dot="med" count={med.length}>
          {med.map((i) => (
            <BriefCard key={i.id} item={i} />
          ))}
        </Section>

        {high.length === 0 && med.length === 0 && (
          <div className="card-surface text-center body-text">
            {t("home.nothingInRegion", lang)}
          </div>
        )}

        <section>
          <h2 className="h2-section mb-4">{t("home.upcomingDeadlines", lang)}</h2>
          {deadlines.length === 0 ? (
            <div className="card-surface body-text">{t("home.noDeadlines", lang)}</div>
          ) : (
            <div className="card-surface !p-0 overflow-hidden">
              {deadlines.map((i, idx) => {
                const d = daysUntil(i.deadline!);
                return (
                  <Link
                    key={i.id}
                    to="/app/inbox"
                    search={{ id: i.id }}
                    className={cn(
                      "flex items-center gap-4 px-5 py-4 hover:bg-muted/50 transition",
                      idx > 0 && "hairline-t",
                    )}
                  >
                    <Calendar className="size-4 text-ink-faint shrink-0" />
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium text-ink truncate">{lang === "DE" ? (i.title_de || i.title) : i.title}</div>
                      <div className="text-xs text-ink-faint mt-0.5">{i.fundingOrg ?? i.source}</div>
                    </div>
                    <div className="text-right shrink-0">
                      <div className="text-sm font-medium text-ink">{d}d</div>
                      <div className="text-xs text-ink-faint">
                        {new Date(i.deadline!).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
                      </div>
                    </div>
                  </Link>
                );
              })}
            </div>
          )}
        </section>

        <div className="pt-2 pb-8">
          <Link to="/app/inbox" className="btn-primary">
            {t("home.openInbox", lang)} <ArrowRight className="size-4" />
          </Link>
        </div>
      </div>
    </div>
  );
}

function Section({
  title,
  dot,
  count,
  children,
}: {
  title: string;
  dot: "high" | "med" | "low";
  count: number;
  children: React.ReactNode;
}) {
  const lang = useLang();
  const [expanded, setExpanded] = useState(false);
  const INITIAL = 5;

  if (count === 0) return null;

  const allChildren = Children.toArray(children);
  const hasMore = allChildren.length > INITIAL;
  const shown = expanded ? allChildren : allChildren.slice(0, INITIAL);
  const hiddenCount = allChildren.length - INITIAL;

  return (
    <section>
      <div className="flex items-center gap-3 mb-4">
        <PriorityDot priority={dot} />
        <h2 className="h2-section">{title}</h2>
        <span className="text-sm text-ink-faint">{count}</span>
      </div>
      <div className="space-y-3">{shown}</div>
      {hasMore && (
        <button
          onClick={() => setExpanded((v) => !v)}
          className="mt-4 text-sm text-ink-soft hover:text-ink rounded-full px-4 py-1.5 ring-1 ring-hairline/70 hover:ring-ink/30 transition"
        >
          {expanded
            ? t("home.showLess", lang)
            : `${t("home.showMore", lang)} (${hiddenCount})`}
        </button>
      )}
    </section>
  );
}

function BriefCard({ item }: { item: Item }) {
  const lang = useLang();
  const summary = lang === "DE" ? (item.translation_de || item.translation || item.summary) : (item.translation || item.summary);
  return (
    <Link
      to="/app/inbox"
      search={{ id: item.id }}
      className="card-surface group block hover:border-ink/15 transition"
    >
      <div className="flex items-start gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-2">
            <TypeBadge type={item.type} />
            {item.deadline && (
              <span className="text-[11px] text-priority-high font-medium">
                Deadline · {daysUntil(item.deadline)}d
              </span>
            )}
          </div>
          <h3 className="h3-card">{lang === "DE" ? (item.title_de || item.title) : item.title}</h3>
          <p className="mt-2 body-text line-clamp-2">{summary}</p>
        </div>
        <ArrowRight className="size-4 text-ink-faint group-hover:text-ink transition mt-1 shrink-0" />
      </div>
    </Link>
  );
}
