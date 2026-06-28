# System Architecture

FISK is a two-subsystem application: a **Python data + intelligence engine** and a **product layer** (Flask API + React SPA). They communicate through a single generated artifact — `items.json` — and over HTTP.

---

## High-level view

```
LIVE SOURCES                INTELLIGENCE ENGINE                 PRODUCT
─────────────               ───────────────────                 ───────
RSS feeds          ┐
Grant databases    ├─► ingest_*.py ─► *.csv ─► summarize (Bedrock) ─► export ─► items.json
Gmail IMAP alerts  ┘                                                              │
                                                                                  ▼
                                                          Flask API (Bedrock-powered endpoints)
                                                                                  │
                                                                                  ▼
                                                          React SPA (TanStack + Vite + Tailwind)
```

---

## Subsystem 1 — `Python pipeline/` (intelligence engine)

Responsible for turning messy real-world inputs into clean, bilingual, structured intelligence.

| Concern | Module |
|---------|--------|
| News ingestion | `ingest.py` |
| Funding ingestion | `ingest_funding.py` |
| Email ingestion | `ingest_inbox.py` |
| News/email summarization logic | `app.py` (`summarize_article`, `run_summarization`, `run_email_summarization`) |
| Funding summarization | `summarize_funding.py` |
| Standalone news summarizer | `summarize.py` |
| Summarization runner | `run_summarize.py` |
| AI client (Bedrock + fallback) | `bedrock_llm.py` |
| Unified export | `export_items.py` |

**Caching strategy:** each stage writes a CSV keyed by item `link`. Re-running only processes items not already in the cache, so Bedrock is never called twice for the same article. This keeps incremental runs cheap and fast.

**Concurrency:** summarization runs in parallel via `ThreadPoolExecutor` — 10 workers for news/email, up to 25 for funding.

## Subsystem 2 — `Loveable pipeline/` (product)

### Backend — `app.py` (Flask)
- Serves `items.json` over a REST/JSON API with CORS enabled.
- Hosts the **live AI endpoints** (copilot, insights, funding matching, email drafting) backed by `bedrock_client.py`.
- Handles guarded email sending over Gmail SMTP.

### Frontend — `src/` (React + TanStack)
- SPA consuming the API via TanStack Query.
- Routes for dashboard, smart inbox, funding finder, opportunity finder.
- Leaflet map, AI copilot widget, bilingual UI.

---

## Why two subsystems?

Separation of concerns and operational flexibility:

- The **engine** can run on a schedule (cron) to refresh data independently of the web app.
- The **product** stays responsive — it reads a precomputed `items.json` for instant page loads, and only calls Bedrock live for interactive features (copilot, search).
- Each can be deployed, scaled, and debugged independently.

---

## Stacking & rendering notes (frontend)

- The Leaflet map establishes an isolated stacking context (`isolation: isolate`) so its internal high z-index panes/controls don't bleed over overlays like the search dropdown and AI copilot panel (both at `z-[100]`).
- Map markers use hover tooltips (Leaflet `bindTooltip`) showing a compact location summary; clicking a marker filters the dashboard by region.

---

## Resilience

- **AI provider failover:** Bedrock primary → OpenAI fallback (see [AWS_BEDROCK.md](AWS_BEDROCK.md)).
- **Robust date parsing:** `export_items.py` handles RFC-2822, ISO, and plain date formats, with graceful fallback.
- **Validation:** model outputs are validated (category must be one of 9; urgency must be high/med/low) before storage; contacts are only kept if literally present in source text.
- **Single source of truth for config:** `.env` is loaded with `override=True` everywhere, so credential refreshes don't get shadowed by stale shell variables.
