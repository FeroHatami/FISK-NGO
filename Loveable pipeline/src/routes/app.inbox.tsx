import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { z } from "zod";
import {
  ALL_REGIONS,
  ALL_TOPICS,
  TYPE_LABEL,
  daysUntil,
  formatRelative,
  type Item,
  type ItemType,
  type Priority,
} from "@/lib/mock-data";
import { useItems, useMeta } from "@/lib/use-items";
import { PriorityDot, Tag, TypeBadge, Badge, UrgencyBadge, TimeBadge } from "@/components/lumen/badges";
import { ChevronDown, FileText, Send, BookOpen, Eye, Sparkles, ExternalLink, Loader2, Mail, X, Check } from "lucide-react";
import { DailyBriefing } from "@/components/lumen/daily-briefing";
import { cn } from "@/lib/utils";
import { useLang, t } from "@/lib/i18n";
import { draftEmail, sendEmail, type EmailDraft } from "@/lib/api";
import { sortByPriority } from "@/lib/sort-items";

const search = z.object({
  id: z.string().optional(),
  type: z.array(z.string()).optional(),
  topic: z.array(z.string()).optional(),
  region: z.array(z.string()).optional(),
  priority: z.array(z.string()).optional(),
});

export const Route = createFileRoute("/app/inbox")({
  validateSearch: search,
  component: InboxPage,
});

const TYPES: ItemType[] = ["funding", "news", "email"];
const PRIORITIES: Priority[] = ["high", "med", "low"];
const PRIORITY_LABEL: Record<Priority, string> = { high: "High", med: "Medium", low: "Low" };

function InboxPage() {
  const navigate = useNavigate({ from: "/app/inbox" });
  const s = Route.useSearch();
  const [filtersOpen, setFiltersOpen] = useState(false);
  const lang = useLang();

  const { data: allItems = [], isLoading, error } = useItems();
  const { data: meta } = useMeta();

  const topics = meta?.topics ?? ALL_TOPICS;
  const regions = meta?.regions ?? ALL_REGIONS;

  const filtered = useMemo(() => {
    const list = allItems.filter((i) => {
      if (s.type?.length && !s.type.includes(i.type)) return false;
      if (s.priority?.length && !s.priority.includes(i.priority)) return false;
      if (s.topic?.length && !i.topic.some((t) => s.topic!.includes(t))) return false;
      if (s.region?.length && !i.region.some((r) => s.region!.includes(r))) return false;
      return true;
    });
    return sortByPriority(list);
  }, [s, allItems]);

  const activeId = s.id ?? filtered[0]?.id;
  const active = allItems.find((i) => i.id === activeId);

  const toggle = (key: "type" | "topic" | "region" | "priority", value: string) => {
    const current = (s[key] as string[] | undefined) ?? [];
    const next = current.includes(value) ? current.filter((v) => v !== value) : [...current, value];
    navigate({ search: (p: Record<string, unknown>) => ({ ...p, [key]: next.length ? next : undefined }) });
  };

  const filterCount =
    (s.type?.length ?? 0) + (s.topic?.length ?? 0) + (s.region?.length ?? 0) + (s.priority?.length ?? 0);

  if (isLoading) {
    return <div className="flex h-[calc(100vh-65px)] items-center justify-center"><p className="body-text">{t("inbox.loading", lang)}</p></div>;
  }
  if (error) {
    return <div className="flex h-[calc(100vh-65px)] items-center justify-center"><p className="body-text text-priority-high">{t("inbox.error", lang)}</p></div>;
  }

  return (
    <div className="flex h-[calc(100vh-65px)]">
      <div className="flex flex-col w-full lg:w-[440px] xl:w-[480px] shrink-0 hairline-r">
        <div className="px-8 pt-10 pb-6">
          <div className="eyebrow">{t("inbox.eyebrow", lang)}</div>
          <h1 className="mt-3 h1-page">{t("inbox.title", lang)}</h1>
          <p className="mt-2 body-text">
            {filtered.length} {t("inbox.items", lang)}
          </p>

          <button
            onClick={() => setFiltersOpen((o) => !o)}
            className="mt-4 inline-flex items-center gap-1.5 text-sm text-ink-soft hover:text-ink"
          >
            {t("inbox.filters", lang)}
            {filterCount > 0 && <Badge tone="ink">{filterCount}</Badge>}
            <ChevronDown className={cn("size-4 transition", filtersOpen && "rotate-180")} />
          </button>

          {filtersOpen && (
            <div className="mt-4 space-y-4 rounded-2xl bg-muted/60 p-4">
              <FilterGroup label={t("filter.type", lang)} options={TYPES.map((tp) => ({ value: tp, label: TYPE_LABEL[tp] }))} active={s.type} onToggle={(v) => toggle("type", v)} />
              <FilterGroup label={t("filter.priority", lang)} options={PRIORITIES.map((p) => ({ value: p, label: PRIORITY_LABEL[p] }))} active={s.priority} onToggle={(v) => toggle("priority", v)} />
              <FilterGroup label={t("filter.topic", lang)} options={topics.map((tp) => ({ value: tp, label: tp }))} active={s.topic} onToggle={(v) => toggle("topic", v)} />
              <FilterGroup label={t("filter.region", lang)} options={regions.map((r) => ({ value: r, label: r }))} active={s.region} onToggle={(v) => toggle("region", v)} />
            </div>
          )}
        </div>

        <div className="flex-1 overflow-y-auto pb-8">
          <div className="px-5">
            <DailyBriefing />
          </div>
          <div className="px-4 mt-2">
            {filtered.map((item) => (
              <button
                key={item.id}
                onClick={() => navigate({ search: (p: Record<string, unknown>) => ({ ...p, id: item.id }) })}
                className={cn(
                  "w-full text-left rounded-xl px-3 py-3 transition mb-1",
                  activeId === item.id ? "bg-muted" : "hover:bg-muted/60",
                )}
              >
                <div className="flex items-start gap-3">
                  <PriorityDot priority={item.priority} className="mt-1.5" />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1.5">
                      <TypeBadge type={item.type} />
                      <UrgencyBadge urgency={item.urgency} />
                      <TimeBadge timeEstimate={item.timeEstimate} />
                      <span className="text-[11px] text-ink-faint ml-auto shrink-0">{formatRelative(item.date)}</span>
                    </div>
                    <div className="text-sm font-medium text-ink leading-snug truncate">{lang === "DE" ? (item.title_de || item.title) : item.title}</div>
                    <div className="text-[13px] text-ink-soft mt-1 line-clamp-2 leading-relaxed">{lang === "DE" ? (item.translation_de || item.translation || item.summary) : (item.translation || item.summary)}</div>
                    {item.deadline && (
                      <div className="mt-2 text-[11px] font-medium text-priority-high">
                        Deadline in {daysUntil(item.deadline)} days
                      </div>
                    )}
                  </div>
                </div>
              </button>
            ))}
            {filtered.length === 0 && (
              <div className="px-3 py-10 text-center text-sm text-ink-faint">{t("inbox.noMatch", lang)}</div>
            )}
          </div>
        </div>
      </div>

      <div className="hidden lg:block flex-1 overflow-y-auto">
        {active ? <DetailView item={active} /> : <EmptyDetail />}
      </div>
    </div>
  );
}

function FilterGroup({
  label,
  options,
  active,
  onToggle,
}: {
  label: string;
  options: { value: string; label: string }[];
  active?: string[];
  onToggle: (v: string) => void;
}) {
  return (
    <div>
      <div className="eyebrow mb-2">{label}</div>
      <div className="flex flex-wrap gap-1.5">
        {options.map((o) => {
          const on = active?.includes(o.value);
          return (
            <button
              key={o.value}
              onClick={() => onToggle(o.value)}
              className={cn(
                "rounded-full border px-2.5 py-1 text-xs transition",
                on
                  ? "bg-ink text-background border-ink"
                  : "border-hairline bg-surface-elevated text-ink-soft hover:text-ink hover:border-ink/30",
              )}
            >
              {o.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function EmptyDetail() {
  const lang = useLang();
  return (
    <div className="h-full grid place-items-center text-center px-8">
      <div>
        <Sparkles className="size-6 text-ink-faint mx-auto" />
        <p className="mt-3 text-sm text-ink-faint">{t("inbox.selectItem", lang)}</p>
      </div>
    </div>
  );
}

const actionIcon = {
  Apply: <FileText className="size-4" />,
  Reply: <Send className="size-4" />,
  Read: <BookOpen className="size-4" />,
  Monitor: <Eye className="size-4" />,
} as const;

function DetailView({ item }: { item: Item }) {
  const lang = useLang();
  const summary = lang === "DE" ? (item.translation_de || item.translation || item.summary) : (item.translation || item.summary);
  return (
    <article className="mx-auto max-w-2xl px-8 py-10">
      <div className="flex items-center gap-2 mb-4">
        <PriorityDot priority={item.priority} />
        <TypeBadge type={item.type} />
        <UrgencyBadge urgency={item.urgency} />
        <TimeBadge timeEstimate={item.timeEstimate} />
        <span className="text-xs text-ink-faint ml-auto">
          {new Date(item.date).toLocaleDateString("en-US", { day: "2-digit", month: "short", year: "numeric" })}
        </span>
      </div>

      <h1 className="h1-page text-2xl lg:text-3xl">{lang === "DE" ? (item.title_de || item.title) : item.title}</h1>
      <div className="mt-2 flex items-center gap-3">
        <span className="text-sm text-ink-soft">{item.source}</span>
        {item.link && (
          <a
            href={item.link}
            target="_blank"
            rel="noopener"
            className="inline-flex items-center gap-1 text-xs text-ink-faint hover:text-ink rounded-full px-2.5 py-1 ring-1 ring-hairline hover:ring-ink/30 transition"
          >
            <ExternalLink className="size-3" /> {t("detail.viewSource", lang)}
          </a>
        )}
      </div>

      <div className="mt-4 flex flex-wrap gap-1.5">
        {item.topic.map((t) => (
          <Tag key={t}>{t}</Tag>
        ))}
        {item.region.map((r) => (
          <Tag key={r}>{r}</Tag>
        ))}
      </div>

      <div className="mt-8 card-surface">
        <div className="flex items-center gap-2 eyebrow mb-2">
          <Sparkles className="size-3.5" /> {t("inbox.aiSummary", lang)}
        </div>
        <ExpandableText text={summary} />
      </div>

      <div className="mt-6 relative flex items-center gap-3 rounded-2xl bg-ink p-4 text-background">
        <div className="flex size-9 items-center justify-center rounded-full bg-background/10">
          {actionIcon[item.suggestedAction]}
        </div>
        <div className="flex-1">
          <div className="eyebrow !text-background/60">{t("inbox.suggestedStep", lang)}</div>
          <div className="text-sm font-medium mt-0.5">{suggestionCopy(item, lang)}</div>
        </div>
        <ActionButton item={item} lang={lang} renderDraftOutside />
      </div>

      {item.type === "funding" && (
        <div className="mt-8 card-surface grid grid-cols-2 gap-x-6 gap-y-5">
          <Meta label={t("detail.deadline", lang)} value={item.deadline ? `${new Date(item.deadline).toLocaleDateString("en-US")} (${daysUntil(item.deadline)}d)` : "—"} />
          <Meta label={t("detail.amount", lang)} value={item.amount} />
          <Meta label={t("detail.organization", lang)} value={item.fundingOrg} />
          <Meta label={t("detail.eligibility", lang)} value={item.eligibility} />
          <div className="col-span-2">
            <Meta label={t("detail.requirements", lang)} value={item.requirements} />
          </div>
        </div>
      )}

      {item.type === "email" && (
        <div className="mt-8 card-surface grid grid-cols-2 gap-x-6 gap-y-5">
          <Meta label={t("detail.sender", lang)} value={item.sender} />
          <Meta label={t("detail.originalLanguage", lang)} value={item.originalLanguage} />
        </div>
      )}

      {item.type === "news" && item.originalLanguage && (
        <div className="mt-8 card-surface grid grid-cols-2 gap-x-6 gap-y-5">
          <Meta label={t("detail.originalLanguage", lang)} value={item.originalLanguage} />
        </div>
      )}

      <div className="h-24" />
    </article>
  );
}

function Meta({ label, value }: { label: string; value?: string }) {
  return (
    <div>
      <div className="eyebrow mb-1">{label}</div>
      <div className="text-sm text-ink">{value ?? "—"}</div>
    </div>
  );
}

const TRUNCATE_THRESHOLD = 150;

function ExpandableText({ text }: { text: string }) {
  const [expanded, setExpanded] = useState(false);
  const needsTruncation = text.length > TRUNCATE_THRESHOLD;

  if (!needsTruncation) {
    return <p className="text-[15px] leading-relaxed text-ink">{text}</p>;
  }

  return (
    <div>
      <p className="text-[15px] leading-relaxed text-ink">
        {expanded ? text : text.slice(0, TRUNCATE_THRESHOLD) + "…"}
      </p>
      <button
        onClick={() => setExpanded((v) => !v)}
        className="mt-1 text-xs text-ink-faint hover:text-ink underline-offset-4 hover:underline"
      >
        {expanded ? "Read less" : "Read more"}
      </button>
    </div>
  );
}

function suggestionCopy(i: Item, lang: import("@/lib/i18n").Lang): string {
  switch (i.suggestedAction) {
    case "Apply":
      return i.deadline ? `${t("action.startApplication", lang)} — ${daysUntil(i.deadline)} days` : t("action.startApplication", lang);
    case "Reply":
      return t("action.draftReply", lang);
    case "Read":
      return t("action.markRead", lang);
    case "Monitor":
      return t("action.addWatchlist", lang);
  }
}

function ActionButton({ item, lang }: { item: Item; lang: import("@/lib/i18n").Lang; renderDraftOutside?: boolean }) {
  const [drafting, setDrafting] = useState(false);
  const [draft, setDraft] = useState<EmailDraft | null>(null);
  const [recipients, setRecipients] = useState<string[]>([]);
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [newRecipient, setNewRecipient] = useState("");
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");

  const handleClick = async () => {
    if (item.suggestedAction === "Reply") {
      // Email draft flow
      setDrafting(true);
      try {
        const result = await draftEmail(`Reply to the article "${item.title}" from ${item.source}. ${item.summary || ""}`, lang.toLowerCase());
        if (result.error) { setError(result.error); setDrafting(false); return; }
        setDraft(result);
        setRecipients(result.suggested_recipients.length ? result.suggested_recipients : (item.contact_email ? [item.contact_email] : []));
        setSubject(result.subject);
        setBody(result.body);
      } catch { setError("Failed to draft."); }
      setDrafting(false);
    } else {
      // Apply / Monitor / Read — open link
      if (item.link) window.open(item.link, "_blank", "noopener");
    }
  };

  const handleSend = async () => {
    if (!recipients.length || !subject || !body) { setError("All fields required."); return; }
    setSending(true); setError("");
    try {
      const res = await sendEmail({ to: recipients, subject, body, confirmed: true });
      if (res.success) setSent(true);
      else setError(res.error || "Failed.");
    } catch (e) { setError(e instanceof Error ? e.message : "Failed."); }
    finally { setSending(false); }
  };

  const addRecipient = () => {
    const email = newRecipient.trim();
    if (email && email.includes("@") && !recipients.includes(email)) { setRecipients([...recipients, email]); setNewRecipient(""); }
  };

  // No link and not a reply — disable
  if (item.suggestedAction !== "Reply" && !item.link) return null;

  if (sent) {
    return <span className="rounded-full bg-green-100 px-4 py-2 text-xs font-medium text-green-700"><Check className="size-3 inline mr-1" />Sent</span>;
  }

  if (draft) {
    return (
      <div className="absolute left-0 right-0 top-full mt-2 z-20 rounded-xl border border-hairline bg-background p-4 space-y-3 text-ink shadow-lg">
        <div className="flex items-center gap-2 text-xs font-medium text-ink"><Mail className="size-3.5" /> Email Draft</div>
        <div>
          <label className="text-[11px] text-ink-faint uppercase">To</label>
          <div className="flex flex-wrap gap-1 mt-1">
            {recipients.map((r) => (<span key={r} className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-xs text-ink">{r}<button onClick={() => setRecipients(recipients.filter(x=>x!==r))} className="text-ink-faint hover:text-ink"><X className="size-3"/></button></span>))}
            <input value={newRecipient} onChange={(e)=>setNewRecipient(e.target.value)} onKeyDown={(e)=>{if(e.key==="Enter"){e.preventDefault();addRecipient();}}} placeholder="Add..." className="text-xs bg-transparent outline-none flex-1 min-w-[100px] px-1 text-ink"/>
          </div>
        </div>
        <div><label className="text-[11px] text-ink-faint uppercase">Subject</label><input value={subject} onChange={(e)=>setSubject(e.target.value)} className="mt-1 w-full rounded-lg border border-hairline px-3 py-1.5 text-sm outline-none text-ink"/></div>
        <div><label className="text-[11px] text-ink-faint uppercase">Body</label><textarea value={body} onChange={(e)=>setBody(e.target.value)} rows={4} className="mt-1 w-full rounded-lg border border-hairline px-3 py-2 text-sm outline-none resize-none text-ink"/></div>
        {error && <p className="text-xs text-red-600">{error}</p>}
        <div className="flex gap-2">
          <button onClick={handleSend} disabled={sending||!recipients.length} className="inline-flex items-center gap-1.5 rounded-full bg-ink px-4 py-2 text-xs font-medium text-background disabled:opacity-40">{sending?<Loader2 className="size-3 animate-spin"/>:<Send className="size-3"/>} Send</button>
          <button onClick={()=>setDraft(null)} className="text-xs text-ink-faint hover:text-ink">Cancel</button>
        </div>
      </div>
    );
  }

  return (
    <button
      onClick={handleClick}
      disabled={drafting}
      className="rounded-full bg-background px-4 py-2 text-sm font-medium text-ink hover:opacity-90 disabled:opacity-50"
    >
      {drafting ? <Loader2 className="size-3 animate-spin inline mr-1" /> : null}
      {t(`action.${item.suggestedAction.toLowerCase()}` as any, lang)}
    </button>
  );
}
