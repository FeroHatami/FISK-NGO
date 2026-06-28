import { createFileRoute, Link, Outlet, useNavigate } from "@tanstack/react-router";
import { useCallback, useEffect, useRef, useState } from "react";
import { Logo } from "@/components/lumen/logo";
import { Copilot } from "@/components/lumen/copilot";
import { Home, Inbox, Sparkles, Search, FileText } from "lucide-react";
import { LangContext, useLang, t, setGlobalLang, type Lang } from "@/lib/i18n";
import { searchItems } from "@/lib/api";

export const Route = createFileRoute("/app")({
  component: AppShell,
});

function AppShell() {
  const lang = useLang();
  const handleLang = (l: Lang) => setGlobalLang(l);
  return (
    <LangContext.Provider value={lang}>
    <div className="min-h-screen bg-background text-foreground">
      <div className="mx-auto flex min-h-screen w-full max-w-[1400px]">
        {/* Sidebar */}
        <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col px-5 py-7 md:flex hairline-r">
          <div className="mb-2">
            <Logo />
          </div>
          <nav className="mt-8 flex flex-col gap-0.5 text-sm">
            <NavItem to="/app" icon={<Home className="size-4" />} label={t("nav.home", lang)} exact />
            <NavItem to="/app/inbox" icon={<Inbox className="size-4" />} label={t("nav.inbox", lang)} />
            <NavItem to="/app/funding" icon={<FileText className="size-4" />} label={t("nav.funding", lang)} />
            <NavItem to="/app/opportunities" icon={<Sparkles className="size-4" />} label={t("nav.opportunities", lang)} />
          </nav>


          <Link
            to="/"
            className="mt-auto flex items-center gap-3 rounded-xl bg-muted p-3 text-xs text-ink-soft hover:bg-muted/80 transition"
            title="Back to landing page"
          >
            <div className="size-7 rounded-full bg-ink text-background grid place-items-center font-medium">A</div>
            <div className="leading-tight flex-1">
              <div className="text-ink font-medium">Anja Werner</div>
              <div>Programs · Burundi Kids</div>
            </div>
            <span className="text-[10px] text-ink-faint">Log out</span>
          </Link>
        </aside>

        {/* Main */}
        <main className="flex-1 min-w-0">
          {/* Top bar */}
          <div className="sticky top-0 z-10 flex items-center gap-3 bg-background/80 px-6 py-4 backdrop-blur hairline-b">
            <SearchBar lang={lang} />
            <div className="ml-auto inline-flex items-center rounded-full border border-hairline bg-surface-elevated p-0.5 text-xs">
              {(["EN", "DE"] as const).map((l) => (
                <button
                  key={l}
                  onClick={() => handleLang(l)}
                  className={`rounded-full px-2.5 py-1 transition ${
                    lang === l ? "bg-accent text-ink font-medium" : "text-ink-faint hover:text-ink"
                  }`}
                >
                  {l}
                </button>
              ))}
            </div>
          </div>
          <Outlet />
        </main>
      </div>
      <Copilot />
    </div>
    </LangContext.Provider>
  );
}

function NavItem({
  to,
  icon,
  label,
  exact,
}: {
  to: string;
  icon: React.ReactNode;
  label: string;
  exact?: boolean;
}) {
  return (
    <Link
      to={to}
      activeOptions={{ exact }}
      className="group relative flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-ink-soft transition hover:bg-accent/40 hover:text-ink data-[status=active]:bg-accent data-[status=active]:text-ink data-[status=active]:font-medium"
    >
      {icon}
      <span>{label}</span>
    </Link>
  );
}

function SearchBar({ lang }: { lang: Lang }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Array<{ id: string; title: string; type: string; summary?: string }>>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();

  // Cmd+K shortcut
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") { e.preventDefault(); inputRef.current?.focus(); setOpen(true); }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  // Click outside to close
  useEffect(() => {
    const handler = (e: MouseEvent) => { if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const doSearch = useCallback((q: string) => {
    if (timerRef.current) clearTimeout(timerRef.current);
    if (!q.trim()) { setResults([]); return; }
    timerRef.current = setTimeout(async () => {
      setLoading(true);
      try {
        const res = await searchItems(q) as Array<{ id: string; title: string; type: string; summary?: string; translation?: string }>;
        setResults(res.map((r) => ({ id: r.id, title: r.title, type: r.type, summary: (r.translation || r.summary || "").slice(0, 80) })));
      } catch { setResults([]); }
      setLoading(false);
    }, 300);
  }, []);

  return (
    <div ref={wrapRef} className="relative flex-1 max-w-md">
      <div className="flex items-center gap-2 rounded-full border border-hairline bg-surface-elevated px-3 py-1.5 text-sm text-ink-faint">
        <Search className="size-4" />
        <input
          ref={inputRef}
          value={query}
          onChange={(e) => { setQuery(e.target.value); setOpen(true); doSearch(e.target.value); }}
          onFocus={() => { if (query) setOpen(true); }}
          placeholder={t("nav.search", lang)}
          className="flex-1 bg-transparent outline-none text-ink placeholder:text-ink-faint"
        />
        <kbd className="rounded bg-muted px-1.5 py-0.5 text-[10px] text-ink-soft">⌘K</kbd>
      </div>

      {open && query.trim() && (
        <div className="absolute top-full left-0 right-0 mt-2 rounded-xl border border-hairline bg-surface-elevated shadow-lg z-[100] overflow-hidden max-h-80 overflow-y-auto">
          {loading && <div className="px-4 py-3 text-xs text-ink-faint">Searching...</div>}
          {!loading && results.length === 0 && <div className="px-4 py-3 text-xs text-ink-faint">No results found.</div>}
          {results.map((r) => (
            <button
              key={r.id}
              onClick={() => { setOpen(false); setQuery(""); navigate({ to: "/app/inbox", search: { id: r.id } }); }}
              className="w-full text-left px-4 py-3 hover:bg-muted/60 transition border-b border-hairline/50 last:border-0"
            >
              <div className="flex items-center gap-2 text-[11px] text-ink-faint mb-0.5">
                <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-medium uppercase">{r.type}</span>
              </div>
              <div className="text-sm font-medium text-ink truncate">{r.title}</div>
              {r.summary && <div className="text-xs text-ink-soft mt-0.5 truncate">{r.summary}</div>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
