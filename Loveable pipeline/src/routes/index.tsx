import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import { Logo } from "@/components/lumen/logo";
import { ArrowRight } from "lucide-react";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Burundi Kids — From Information to Impact" },
      { name: "description", content: "Spend less time managing information. Spend more time changing the world." },
    ],
  }),
  component: Landing,
});

const copy = {
  EN: { hello: "Hello.", quote: "Spend less time managing information.", quote2: "Spend more time changing the world.", login: "Login" },
  DE: { hello: "Hallo.", quote: "Weniger Zeit mit Informationen verbringen.", quote2: "Mehr Zeit, die Welt zu verändern.", login: "Anmelden" },
} as const;

function Landing() {
  const [lang, setLang] = useState<"EN" | "DE">("EN");
  const t = copy[lang];

  return (
    <div className="relative min-h-screen bg-background text-foreground">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-8 py-6">
        <Logo />
        <div className="inline-flex items-center rounded-full border border-hairline bg-surface-elevated p-0.5 text-xs">
          {(["EN", "DE"] as const).map((l) => (
            <button
              key={l}
              onClick={() => setLang(l)}
              className={`rounded-full px-3 py-1 transition ${
                lang === l ? "bg-accent text-ink font-medium" : "text-ink-faint hover:text-ink"
              }`}
            >
              {l}
            </button>
          ))}
        </div>
      </header>

      <main className="mx-auto flex max-w-3xl flex-col items-center px-8 pt-24 pb-32 text-center md:pt-40">
        <h1 className="text-6xl md:text-7xl font-semibold tracking-tight text-ink">
          {t.hello}
        </h1>
        <p className="mt-10 text-xl md:text-2xl font-medium leading-snug text-ink tracking-tight">
          {t.quote}
          <br />
          <span className="text-ink-faint">{t.quote2}</span>
        </p>
        <Link to="/app" className="mt-14 btn-primary !h-11 !px-6">
          {t.login} <ArrowRight className="size-4" />
        </Link>
      </main>
    </div>
  );
}
