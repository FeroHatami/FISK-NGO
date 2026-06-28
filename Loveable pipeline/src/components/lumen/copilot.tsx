import { useEffect, useRef, useState } from "react";
import { Sparkles, X, ArrowUp, Mail, Send, Check, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { sendEmail, type EmailDraft } from "@/lib/api";
import { useLang } from "@/lib/i18n";

const BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:5000";

type Msg = { role: "user" | "ai"; text: string };
type HistoryEntry = { role: "user" | "assistant"; content: string };

const suggestions = [
  "What deserves my attention today?",
  "Show funding opportunities for education.",
  "Summarize everything from Burundi this week.",
  "What deadlines are approaching?",
  "Draft an email about the Ebola response.",
];

async function callCopilot(message: string, history: HistoryEntry[]): Promise<string> {
  try {
    const res = await fetch(`${BASE}/api/copilot`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ message, history }),
    });
    if (!res.ok) return "Sorry, the backend didn't respond.";
    const data = await res.json();
    return data.reply || "No response.";
  } catch {
    return "Could not reach the backend. Is it running?";
  }
}

async function callDraftEmail(message: string, history: HistoryEntry[], language: string): Promise<EmailDraft & { error?: string }> {
  try {
    const res = await fetch(`${BASE}/api/copilot/draft-email`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ message, history, language }),
    });
    if (!res.ok) return { subject: "", body: "", suggested_recipients: [], error: "Backend error" };
    return res.json();
  } catch {
    return { subject: "", body: "", suggested_recipients: [], error: "Could not reach backend" };
  }
}

export function Copilot() {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState<Msg[]>([
    { role: "ai", text: "Good morning. I've already read everything overnight. Ask me anything — or ask me to draft an email." },
  ]);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [draft, setDraft] = useState<EmailDraft | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const lang = useLang();

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, open, draft]);

  async function send(text: string) {
    const q = text.trim();
    if (!q || loading) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", text: q }]);

    // Add user turn to history
    const updatedHistory: HistoryEntry[] = [...history, { role: "user", content: q }];
    setHistory(updatedHistory);
    setLoading(true);

    const isDraftRequest = /\b(draft|email|reply|write.*to|send.*to|compose)\b/i.test(q);

    if (isDraftRequest) {
      const result = await callDraftEmail(q, updatedHistory, lang.toLowerCase());
      if (result.error) {
        const errMsg = `Draft error: ${result.error}`;
        setMessages((m) => [...m, { role: "ai", text: errMsg }]);
        setHistory((h) => [...h, { role: "assistant", content: errMsg }]);
      } else {
        const aiMsg = "I've drafted an email for you. Review and edit below before sending.";
        setMessages((m) => [...m, { role: "ai", text: aiMsg }]);
        setHistory((h) => [...h, { role: "assistant", content: aiMsg }]);
        setDraft(result);
      }
    } else {
      const reply = await callCopilot(q, updatedHistory);
      setMessages((m) => [...m, { role: "ai", text: reply }]);
      setHistory((h) => [...h, { role: "assistant", content: reply }]);
    }
    setLoading(false);
  }

  return (
    <>
      <button
        onClick={() => setOpen((o) => !o)}
        className={cn(
          "fixed bottom-5 right-5 z-[100] inline-flex items-center gap-2 rounded-full bg-ink px-4 py-3 text-sm font-medium text-background shadow-lg transition hover:scale-[1.02]",
          open && "opacity-0 pointer-events-none",
        )}
      >
        <Sparkles className="size-4" /> Ask AI
      </button>

      <div
        className={cn(
          "fixed bottom-5 right-5 z-[100] flex w-[min(420px,calc(100vw-2.5rem))] flex-col overflow-hidden rounded-2xl bg-surface-elevated shadow-2xl ring-1 ring-hairline transition-all",
          open ? "h-[min(600px,calc(100vh-2.5rem))] opacity-100 translate-y-0" : "h-0 opacity-0 translate-y-3 pointer-events-none",
        )}
      >
        <div className="flex items-center justify-between hairline-b px-4 py-3">
          <div className="flex items-center gap-2">
            <span className="relative inline-flex size-5 items-center justify-center rounded-full bg-ink text-background"><Sparkles className="size-3" /></span>
            <span className="text-sm font-semibold tracking-tight">Ask AI</span>
          </div>
          <button onClick={() => setOpen(false)} className="rounded-md p-1 text-ink-soft hover:bg-muted"><X className="size-4" /></button>
        </div>

        <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
          {messages.map((m, i) => (
            <div key={i} className={cn("max-w-[85%] rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed whitespace-pre-wrap", m.role === "user" ? "ml-auto bg-ink text-background" : "bg-muted text-ink")}>
              {m.text}
            </div>
          ))}
          {loading && (
            <div className="flex items-center gap-2 text-xs text-ink-faint"><Loader2 className="size-3 animate-spin" /> Thinking...</div>
          )}
          {messages.length <= 1 && !loading && (
            <div className="pt-2 space-y-1.5">
              {suggestions.map((s) => (
                <button key={s} onClick={() => send(s)} className="block w-full rounded-xl border border-hairline px-3 py-2 text-left text-[13px] text-ink-soft hover:bg-muted hover:text-ink">{s}</button>
              ))}
            </div>
          )}
          {draft && <EmailDraftPanel draft={draft} onClose={() => setDraft(null)} />}
        </div>

        <form onSubmit={(e) => { e.preventDefault(); send(input); }} className="hairline-t flex items-center gap-2 px-3 py-3">
          <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask anything about your work..." className="flex-1 bg-transparent text-sm placeholder:text-ink-faint outline-none px-2" />
          <button type="submit" className="inline-flex size-8 items-center justify-center rounded-full bg-ink text-background disabled:opacity-40" disabled={!input.trim() || loading}>
            <ArrowUp className="size-4" />
          </button>
        </form>
      </div>
    </>
  );
}

function EmailDraftPanel({ draft, onClose }: { draft: EmailDraft; onClose: () => void }) {
  const [recipients, setRecipients] = useState<string[]>(draft.suggested_recipients);
  const [subject, setSubject] = useState(draft.subject);
  const [body, setBody] = useState(draft.body);
  const [newRecipient, setNewRecipient] = useState("");
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");

  const addRecipient = () => {
    const email = newRecipient.trim();
    if (email && email.includes("@") && !recipients.includes(email)) {
      setRecipients([...recipients, email]);
      setNewRecipient("");
    }
  };

  const removeRecipient = (email: string) => setRecipients(recipients.filter((r) => r !== email));

  const handleSend = async () => {
    if (!recipients.length || !subject || !body) { setError("Recipients, subject, and body are all required."); return; }
    setSending(true); setError("");
    try {
      const res = await sendEmail({ to: recipients, subject, body, confirmed: true });
      if (res.success) setSent(true);
      else setError(res.error || "Send failed.");
    } catch (e) { setError(e instanceof Error ? e.message : "Send failed."); }
    finally { setSending(false); }
  };

  if (sent) {
    return (
      <div className="rounded-xl border border-green-200 bg-green-50 p-4 text-sm">
        <div className="flex items-center gap-2 text-green-700 font-medium"><Check className="size-4" /> Email sent!</div>
        <p className="mt-1 text-xs text-green-600">To: {recipients.join(", ")}</p>
        <button onClick={onClose} className="mt-2 text-xs text-ink-faint hover:text-ink underline">Dismiss</button>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-hairline bg-background p-4 space-y-3">
      <div className="flex items-center gap-2 text-xs font-medium text-ink"><Mail className="size-3.5" /> Email Draft — review before sending</div>
      <div>
        <label className="text-[11px] text-ink-faint uppercase tracking-wider">To</label>
        <div className="flex flex-wrap gap-1 mt-1">
          {recipients.map((r) => (
            <span key={r} className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-xs text-ink">
              {r}<button onClick={() => removeRecipient(r)} className="text-ink-faint hover:text-ink"><X className="size-3" /></button>
            </span>
          ))}
          <input value={newRecipient} onChange={(e) => setNewRecipient(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addRecipient(); }}} placeholder="Add email..." className="text-xs bg-transparent outline-none flex-1 min-w-[120px] px-1 py-0.5" />
        </div>
      </div>
      <div>
        <label className="text-[11px] text-ink-faint uppercase tracking-wider">Subject</label>
        <input value={subject} onChange={(e) => setSubject(e.target.value)} className="mt-1 w-full rounded-lg border border-hairline px-3 py-1.5 text-sm text-ink outline-none focus:border-ink/30" />
      </div>
      <div>
        <label className="text-[11px] text-ink-faint uppercase tracking-wider">Body</label>
        <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={5} className="mt-1 w-full rounded-lg border border-hairline px-3 py-2 text-sm text-ink outline-none resize-none focus:border-ink/30" />
      </div>
      {error && <p className="text-xs text-red-600">{error}</p>}
      <div className="flex items-center gap-2">
        <button onClick={handleSend} disabled={sending || !recipients.length} className="inline-flex items-center gap-1.5 rounded-full bg-ink px-4 py-2 text-xs font-medium text-background disabled:opacity-40">
          {sending ? <Loader2 className="size-3 animate-spin" /> : <Send className="size-3" />} Send Email
        </button>
        <button onClick={onClose} className="text-xs text-ink-faint hover:text-ink">Cancel</button>
      </div>
    </div>
  );
}
