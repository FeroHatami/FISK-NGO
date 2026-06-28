import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { Sparkles, Send, Calendar, FileText, SlidersHorizontal, Search, Loader2 } from "lucide-react";
import { Badge } from "@/components/lumen/badges";
import { cn } from "@/lib/utils";
import { useItems } from "@/lib/use-items";
import { searchFunding, type FundingMatch } from "@/lib/api";
import type { Item } from "@/lib/mock-data";
import { useLang, t } from "@/lib/i18n";

export const Route = createFileRoute("/app/funding")({
  component: FundingPage,
});

type Filter = "all" | "30" | "60" | "60plus" | "rolling";

function FundingPage() {
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");
  const [brief, setBrief] = useState("");
  const [searching, setSearching] = useState(false);
  const [searchResults, setSearchResults] = useState<FundingMatch[] | null>(null);
  const [searchError, setSearchError] = useState("");
  const lang = useLang();

  const { data: allItems = [], isLoading } = useItems();
  const fundingItems = useMemo(() => allItems.filter((i: Item) => i.type === "funding"), [allItems]);

  const counts = useMemo(() => ({
    open: fundingItems.filter((o: Item) => o.deadline).length,
    urgent: fundingItems.filter((o: Item) => o.priority === "high").length,
    rolling: fundingItems.filter((o: Item) => !o.deadline).length,
  }), [fundingItems]);

  const daysUntilDeadline = (d?: string | null) => {
    if (!d) return null;
    return Math.ceil((new Date(d).getTime() - Date.now()) / 86400000);
  };

  const filtered = fundingItems.filter((o: Item) => {
    const days = daysUntilDeadline(o.deadline);
    if (filter === "30" && (days === null || days > 30)) return false;
    if (filter === "60" && (days === null || days > 60)) return false;
    if (filter === "60plus" && (days === null || days <= 60)) return false;
    if (filter === "rolling" && o.deadline) return false;
    if (query && !`${o.title} ${o.summary} ${o.source}`.toLowerCase().includes(query.toLowerCase())) return false;
    return true;
  });

  const handleSearch = async () => {
    if (!brief.trim()) return;
    setSearching(true);
    setSearchError("");
    setSearchResults(null);
    try {
      const res = await searchFunding(brief);
      if (res.error) setSearchError(res.error);
      setSearchResults(res.matches);
    } catch (e: unknown) {
      setSearchError(e instanceof Error ? e.message : "Search failed");
    } finally {
      setSearching(false);
    }
  };

  return (
    <div className="page-wide">
      <div className="eyebrow">{t("funding.eyebrow", lang)}</div>
      <h1 className="mt-3 h1-page">{t("funding.title", lang)}</h1>
      <p className="mt-3 body-text max-w-3xl">
        Pipeline tracked across BMZ, Brot für die Welt, Misereor, Terre des Hommes, VENRO, PHINEO, Engagement Global, MUTMACHEN, Caritas and political foundations — re-ranked to fit your brief.
      </p>

      <div className="mt-6 card-surface">
        <div className="flex items-center gap-6 text-sm text-ink">
          <Stat n={counts.open} label={t("funding.open", lang)} />
          <Stat n={counts.urgent} label={t("funding.urgent", lang)} dot="high" />
          <Stat n={counts.rolling} label={t("funding.rolling", lang)} dot="low" />
        </div>

        <div className="my-5 hairline-t" />

        <p className="body-text">
          {t("funding.describe", lang)}
        </p>

        <div className="mt-3 flex items-stretch gap-3">
          <textarea
            value={brief}
            onChange={(e) => setBrief(e.target.value)}
            rows={2}
            placeholder="e.g. Mobile vet clinic in northern Burundi, €200k, 18 months, German lead applicant…"
            className="flex-1 resize-none rounded-xl bg-background border border-hairline px-4 py-3 text-sm text-ink placeholder:text-ink-faint focus:outline-none focus:border-ink/30"
          />
          <button onClick={handleSearch} disabled={searching || !brief.trim()} className="btn-primary self-stretch !h-auto disabled:opacity-50">
            {searching ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />} {t("funding.search", lang)}
          </button>
        </div>

        {searchError && <p className="mt-2 text-sm text-priority-high">{searchError}</p>}

        {searchResults && searchResults.length > 0 && (
          <div className="mt-4 space-y-3">
            <div className="eyebrow">{t("funding.matched", lang)} ({searchResults.length})</div>
            {searchResults.map((m) => (
              <div key={m.id} className="rounded-xl border border-accent/50 bg-accent/10 p-4">
                <div className="flex items-center gap-2 text-xs text-ink-faint mb-1">
                  <Sparkles className="size-3" />
                  <span className="text-ink-soft font-medium">{t("funding.matchReason", lang)}</span>
                  <span>{m.matchReason}</span>
                </div>
                <h3 className="text-sm font-medium text-ink mt-1">{m.title}</h3>
                <p className="mt-1 text-[13px] text-ink-soft">{lang === "DE" ? ((m as Record<string, unknown>).translation_de as string || m.summary) : m.summary}</p>
                <div className="mt-2 flex flex-wrap gap-1.5 text-xs">
                  {m.amount && <Badge tone="accent">{m.amount}</Badge>}
                  {m.deadline && <Badge tone="outline"><Calendar className="size-3 inline mr-1" />{m.deadline}</Badge>}
                  {m.region?.map((r) => <Badge key={r} tone="outline">{r}</Badge>)}
                </div>
              </div>
            ))}
          </div>
        )}

        {searchResults && searchResults.length === 0 && !searchError && (
          <p className="mt-3 text-sm text-ink-faint">{t("funding.noResults", lang)}</p>
        )}
      </div>

      <div className="mt-8 flex flex-wrap items-center gap-2">
        <button className="btn-ghost !size-9 !px-0">
          <SlidersHorizontal className="size-4" />
        </button>
        {([
          ["all", "All"],
          ["30", "≤ 30 days"],
          ["60", "≤ 60 days"],
          ["60plus", "60+ days"],
          ["rolling", "Rolling"],
        ] as const).map(([k, label]) => (
          <button
            key={k}
            onClick={() => setFilter(k)}
            className={cn(
              "rounded-full px-3.5 h-9 text-sm transition border",
              filter === k
                ? "bg-ink text-background border-ink"
                : "bg-surface-elevated text-ink-soft border-hairline hover:text-ink",
            )}
          >
            {label}
          </button>
        ))}
        <div className="ml-auto flex items-center gap-2 rounded-full border border-hairline bg-surface-elevated px-3 h-9 text-sm text-ink-faint min-w-[240px]">
          <Search className="size-4" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t("funding.searchOpp", lang)}
            className="bg-transparent outline-none flex-1 text-ink placeholder:text-ink-faint"
          />
        </div>
      </div>

      <div className="mt-5 space-y-3">
        {isLoading ? (
          <div className="card-surface text-center body-text">{t("funding.loading", lang)}</div>
        ) : filtered.length === 0 ? (
          <div className="card-surface text-center body-text">{t("funding.noMatch", lang)}</div>
        ) : (
          filtered.map((o: Item) => (
            <OpportunityCard key={o.id} o={o} />
          ))
        )}
      </div>
    </div>
  );
}

function Stat({ n, label, dot }: { n: number; label: string; dot?: "high" | "low" }) {
  return (
    <div className="inline-flex items-center gap-2">
      {dot && <span className={cn("size-2 rounded-full", dot === "high" ? "bg-priority-high" : "bg-ink-faint/40")} />}
      <span className="text-xl font-semibold text-ink">{n}</span>
      <span className="inline-flex items-center gap-1 eyebrow">
        <Calendar className="size-3" /> {label}
      </span>
    </div>
  );
}

function OpportunityCard({ o }: { o: Item }) {
  const lang = useLang();
  const days = o.deadline ? Math.ceil((new Date(o.deadline).getTime() - Date.now()) / 86400000) : null;
  const dotClass = o.priority === "high" ? "bg-priority-high" : "bg-ink-faint/40";
  const desc = lang === "DE" ? (o.translation_de || o.translation || o.summary) : (o.translation || o.summary);
  return (
    <article className="card-surface hover:border-ink/15 transition">
      <div className="flex items-center gap-2 text-xs text-ink-faint">
        <span className={cn("size-2 rounded-full", dotClass)} />
        <span className="text-ink-soft">{o.source}</span>
        <span>·</span>
        <span>{t("badge.funding", lang)}</span>
        <span>·</span>
        <span className="inline-flex items-center gap-1">
          <Calendar className="size-3" />
          {days !== null ? `${days}d` : t("funding.rolling", lang)}
        </span>
      </div>
      <h3 className="mt-2 h3-card flex items-start gap-2">
        <FileText className="size-4 text-ink-faint mt-0.5 shrink-0" />
        {lang === "DE" ? (o.title_de || o.title) : o.title}
      </h3>
      <p className="mt-2 body-text">{desc}</p>
      <div className="mt-3 flex items-center gap-1.5 flex-wrap">
        {o.topic?.map((tp, i) => (
          <Badge key={tp} tone={i === 0 ? "accent" : "outline"}>{tp}</Badge>
        ))}
        {o.region?.map((r) => (
          <Badge key={r} tone="outline">{r}</Badge>
        ))}
      </div>
    </article>
  );
}
