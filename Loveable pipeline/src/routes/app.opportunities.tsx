import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { Sparkles, Handshake, Users, Loader2, ArrowRight } from "lucide-react";
import { useInsights } from "@/lib/use-items";
import type { Insight } from "@/lib/api";
import { useLang, t } from "@/lib/i18n";

export const Route = createFileRoute("/app/opportunities")({
  component: OpportunitiesPage,
});

const ICON_MAP: Record<string, React.ReactNode> = {
  "Potential partnership": <Handshake className="size-4" />,
  "Potential collaboration": <Users className="size-4" />,
  "Potential funding": <Sparkles className="size-4" />,
};

function OpportunitiesPage() {
  const { data, isLoading, error } = useInsights();
  const insights = data?.insights ?? [];
  const navigate = useNavigate();
  const lang = useLang();

  const handleCardClick = (insight: Insight) => {
    const firstId = insight.item_ids?.[0];
    if (!firstId) return;

    if (firstId.startsWith("funding-")) {
      navigate({ to: "/app/funding" });
    } else {
      navigate({ to: "/app/inbox", search: { id: firstId } });
    }
  };

  return (
    <div className="page-wide">
      <div className="eyebrow inline-flex items-center gap-1.5">
        <Sparkles className="size-3.5" /> {t("opp.eyebrow", lang)}
      </div>
      <h1 className="mt-3 h1-page">{t("opp.title", lang)}</h1>
      <p className="mt-3 body-text max-w-xl">
        {t("opp.subtitle", lang)}
      </p>

      {isLoading && (
        <div className="mt-10 flex items-center gap-2 body-text">
          <Loader2 className="size-4 animate-spin" /> {t("opp.analyzing", lang)}
        </div>
      )}

      {error && (
        <div className="mt-10 card-surface body-text text-priority-high">
          {t("opp.error", lang)}
        </div>
      )}

      {!isLoading && !error && insights.length === 0 && (
        <div className="mt-10 card-surface text-center body-text">
          {t("opp.empty", lang)}
        </div>
      )}

      {!isLoading && insights.length > 0 && (
        <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {insights.map((insight: Insight, idx: number) => (
            <Card
              key={idx}
              icon={ICON_MAP[insight.label] ?? <Sparkles className="size-4" />}
              kicker={insight.label}
              title={lang === "DE" ? (insight.title_de || insight.title_en) : insight.title_en}
              body={lang === "DE" ? (insight.description_de || insight.description_en) : insight.description_en}
              onClick={() => handleCardClick(insight)}
            />
          ))}
        </div>
      )}

      <div className="mt-10">
        <Link to="/app" className="text-sm text-ink-soft underline-offset-4 hover:underline hover:text-ink">
          {t("opp.back", lang)}
        </Link>
      </div>
    </div>
  );
}

function Card({
  icon,
  kicker,
  title,
  body,
  onClick,
}: {
  icon: React.ReactNode;
  kicker: string;
  title: string;
  body: string;
  onClick: () => void;
}) {
  const lang = useLang();
  return (
    <button
      onClick={onClick}
      className="card-surface text-left hover:border-ink/15 transition group cursor-pointer w-full"
    >
      <div className="flex items-center gap-1.5 eyebrow">
        {icon} {kicker}
      </div>
      <h3 className="mt-3 h3-card">{title}</h3>
      <p className="mt-2 body-text">{body}</p>
      <div className="mt-3 flex items-center gap-1 text-xs text-ink-faint group-hover:text-ink transition">
        {t("opp.viewDetails", lang)} <ArrowRight className="size-3" />
      </div>
    </button>
  );
}
