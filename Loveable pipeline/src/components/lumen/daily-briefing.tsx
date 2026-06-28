import { useState } from "react";
import { Sparkles, ChevronDown, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/lumen/badges";
import { useBriefing } from "@/lib/use-items";
import { Link } from "@tanstack/react-router";
import { useLang, t } from "@/lib/i18n";

export function DailyBriefing() {
  const [open, setOpen] = useState(true);
  const { data: briefing, isLoading, error } = useBriefing();
  const lang = useLang();

  if (isLoading) {
    return (
      <div className="mb-4 card-surface flex items-center gap-3 px-4 py-3">
        <Loader2 className="size-4 animate-spin text-ink-faint" />
        <span className="text-sm text-ink-faint">{t("briefing.loading", lang)}</span>
      </div>
    );
  }

  if (error || !briefing) {
    return (
      <div className="mb-4 card-surface px-4 py-3">
        <p className="text-sm text-ink-faint">{t("briefing.error", lang)}</p>
      </div>
    );
  }

  const { summary_en, summary_de, highlights, stats } = briefing;
  const summary = lang === "DE" ? (summary_de || summary_en) : summary_en;

  return (
    <div className="mb-4 card-surface !p-0 overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-3 px-4 py-3 hover:bg-muted/40 transition"
      >
        <div className="flex size-7 items-center justify-center rounded-lg bg-accent">
          <Sparkles className="size-3.5 text-ink" />
        </div>
        <div className="flex-1 text-left">
          <div className="text-sm font-semibold text-ink tracking-tight">{t("briefing.title", lang)}</div>
          <div className="text-[11px] text-ink-faint mt-0.5">
            {stats.reviewed} items reviewed · {stats.newOvernight} need attention
          </div>
        </div>
        <ChevronDown className={cn("size-4 text-ink-faint transition", open && "rotate-180")} />
      </button>

      {open && (
        <div className="hairline-t">
          {/* Summary */}
          <div className="px-4 py-3">
            <p className="text-[13px] text-ink leading-relaxed">{summary}</p>
          </div>

          {/* Highlights */}
          {highlights.length > 0 && (
            <ul className="divide-y divide-hairline hairline-t">
              {highlights.map((h) => (
                <li key={h.id} className="px-4 py-3">
                  <div className="flex items-start gap-2 mb-1">
                    <Badge tone="accent">{t("briefing.actionNeeded", lang)}</Badge>
                  </div>
                  <Link
                    to="/app/inbox"
                    search={{ id: h.id }}
                    className="text-sm font-medium text-ink leading-snug hover:underline"
                  >
                    {lang === "DE" ? (h.title_de || h.title) : h.title}
                  </Link>
                  <p className="mt-1 text-[12.5px] text-ink-soft leading-relaxed line-clamp-2">
                    {lang === "DE" ? (h.summary_de || h.summary) : h.summary}
                  </p>
                </li>
              ))}
            </ul>
          )}

          {highlights.length === 0 && (
            <div className="px-4 py-3 hairline-t">
              <p className="text-[12px] text-ink-faint text-center">
                {t("briefing.caughtUp", lang)}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
