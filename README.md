# FISK — NGO Intelligence Hub (Lumen)

An AI-powered press-monitoring, funding-research, and outreach platform for NGOs working in Burundi and in global animal welfare (built for **Welttierschutzgesellschaft / WTG** and **Burundikids e.V.**).

FISK ingests news, funding calls, and email alerts from live sources, runs them through a multi-stage **AWS Bedrock** AI pipeline (summarization, translation, classification, urgency scoring), and surfaces everything in a bilingual (EN/DE) dashboard with an AI copilot, partnership-insight detection, funding matching, and one-click email drafting.

Built for the **AI For Good Hackathon** — with AWS embedded as the core intelligence layer.

---

## Table of contents

1. [What it does](#what-it-does)
2. [AWS at the core — Amazon Bedrock](#aws-at-the-core--amazon-bedrock)
3. [Architecture](#architecture)
4. [AI orchestration pipeline](#ai-orchestration-pipeline)
5. [Tech stack](#tech-stack)
6. [Data flow](#data-flow)
7. [API reference](#api-reference)
8. [Setup & running locally](#setup--running-locally)
9. [Configuration](#configuration)
10. [Project structure](#project-structure)

---

## What it does

| Capability | Description | AI provider |
|-----------|-------------|-------------|
| **News monitoring** | Scrapes Burundian + international RSS feeds, translates (FR/EN/Kirundi → EN/DE), summarizes, classifies into 9 categories, scores urgency | Bedrock (Nova Lite) |
| **Funding research** | Scrapes German + international grant databases, extracts deadline/amount/eligibility, computes urgency from deadline proximity | Bedrock (Nova Lite) |
| **Email alert ingestion** | Pulls Google Alert emails over Gmail IMAP, classifies each as news vs. funding, extracts structured fields | Bedrock (Nova Lite) |
| **AI Copilot** | Conversational Q&A grounded in the ingested data (RAG-style retrieval + context injection) | Bedrock (Nova Pro) |
| **Partnership insights** | Cross-references all items to detect genuine collaboration/funding-synergy opportunities | Bedrock (Nova Pro) |
| **Funding matching** | Match a free-text project description against live funding opportunities, ranked with reasons | Bedrock (Nova Pro) |
| **Email drafting & sending** | Drafts professional outreach emails using only real contact addresses found in the data; sends via Gmail SMTP with explicit confirmation | Bedrock (Nova Lite) + SMTP |
| **Interactive map** | Geocodes mentioned locations and plots urgency-weighted markers (Leaflet) | — |
| **Daily briefing** | Deterministic prioritized summary of what needs attention | — |

---

## AWS at the core — Amazon Bedrock

**Every AI inference in this project runs on AWS Bedrock.** OpenAI is only a fallback that activates if Bedrock is unreachable.

### Models used (via cross-region inference profiles, `us-west-2`)

| Tier | Model ID | Used for |
|------|----------|----------|
| **Pro** | `us.amazon.nova-pro-v1:0` | Copilot reasoning, partnership insights, funding matching |
| **Lite** | `us.amazon.nova-lite-v1:0` | Article/funding/email summarization, translation, email drafting |
| **Micro** | `us.amazon.nova-micro-v1:0` | Fast/cheap tasks (available for lightweight ops) |

We use the **Amazon Nova** model family through Bedrock's `invoke_model` API with Nova's native request schema (`system` blocks, `messages` with content blocks, `inferenceConfig`). Model selection is tiered: heavier reasoning tasks route to **Nova Pro**, high-volume extraction routes to **Nova Lite**, keeping cost and latency proportional to task complexity.

### Why this is a real AWS integration (not a wrapper)

- **Native Bedrock Runtime calls** via `boto3` (`bedrock-runtime.invoke_model`) — no third-party abstraction layer.
- **Tiered model routing** across the Nova family based on task complexity (see `bedrock_client.py → MODELS` and the `tier` argument on `chat()`).
- **Cross-cloud resiliency**: every call attempts Bedrock first and transparently fails over to OpenAI `gpt-4o-mini` only if Bedrock errors — so the AWS path is always primary.
- **Cross-region inference profiles**: the workshop account's policy requires the `us.` inference-profile prefix (direct on-demand model IDs are denied); the client is configured accordingly.
- **JSON-mode hardening**: Nova occasionally wraps structured output in markdown fences; the client strips them so downstream `json.loads` is robust (`_strip_fences`).

Full deep-dive: [`docs/AWS_BEDROCK.md`](docs/AWS_BEDROCK.md).

### Where the two AI clients live

| File | Scope | Default model | Entry point |
|------|-------|---------------|-------------|
| `Python pipeline/bedrock_llm.py` | Ingestion/summarization pipeline | Nova Lite | `llm_chat(system_prompt, user_prompt, …)` |
| `Loveable pipeline/bedrock_client.py` | Live Flask API (copilot etc.) | Nova Pro (tiered) | `chat(messages, tier=…)` |

Both implement the same pattern: **Bedrock primary → OpenAI fallback**, controlled entirely by environment variables.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                          DATA SOURCES (live)                           │
│   RSS feeds  ·  Grant databases  ·  Gmail Google Alerts (IMAP)         │
└───────────────┬───────────────┬───────────────────┬───────────────────┘
                │               │                   │
        ingest.py      ingest_funding.py     ingest_inbox.py
                │               │                   │
                ▼               ▼                   ▼
        articles.csv   funding_opportunities.csv  alert_articles.csv
                │               │                   │
                └───────────────┴───────────────────┘
                                │
                                ▼
              ┌──────────────────────────────────────┐
              │   AI SUMMARIZATION LAYER              │
              │   summarize.py / summarize_funding.py │
              │   run_summarize.py                    │
              │   →  bedrock_llm.py  →  AWS Bedrock    │  ── OpenAI fallback
              │      (Amazon Nova Lite)               │
              └──────────────────┬───────────────────┘
                                 │
                          export_items.py
                                 │
                                 ▼
                    Loveable pipeline/data/items.json   (unified schema, 214 items)
                                 │
                                 ▼
              ┌──────────────────────────────────────┐
              │   FLASK API  (Loveable pipeline/app.py)│
              │   /api/copilot, /api/insights,        │
              │   /api/funding/search, /api/markers …  │
              │   →  bedrock_client.py  →  AWS Bedrock  │  ── OpenAI fallback
              │      (Amazon Nova Pro / Lite)          │
              └──────────────────┬───────────────────┘
                                 │  JSON over HTTP (CORS)
                                 ▼
              ┌──────────────────────────────────────┐
              │   REACT FRONTEND (TanStack + Vite)     │
              │   Dashboard · Smart Inbox · Funding    │
              │   Opportunity Finder · Map · Copilot   │
              └──────────────────────────────────────┘
```

Two cooperating subsystems:

- **`Python pipeline/`** — the data + intelligence engine: scraping, AI summarization/translation/classification via Bedrock, and unified export.
- **`Loveable pipeline/`** — the product: a Flask JSON API (with its own Bedrock-powered AI endpoints) plus a React SPA frontend.

---

## AI orchestration pipeline

The system is a **multi-stage LLM pipeline**, not a single prompt. Each stage has a dedicated structured prompt, a model tier, and validation. This is the "agent orchestration" of the project:

### Stage 1 — Ingestion (deterministic)
Three independent collectors (`ingest.py`, `ingest_funding.py`, `ingest_inbox.py`) gather raw text from RSS, grant databases, and Gmail IMAP. Each writes a CSV cache keyed by link, so re-runs never re-pay for already-processed items.

### Stage 2 — Structured extraction (Bedrock Nova Lite, JSON mode)
Each raw item is sent through a strict JSON-schema prompt that returns:
- `title_en` / `title_de` — translated titles
- `gist_en` / `gist_de` — bilingual summaries
- `key_points_en` / `key_points_de`
- `locations[]` — for map geocoding
- `category` — one of 9 fixed taxonomy values (validated; invalid → `Uncategorized`)
- `urgency` — high/medium/low (validated)
- `contact_email` / `contact_phone` — extracted **only if literally present** (no hallucinated contacts)
- For funding: `deadline`, `amount`, `eligibility_en/de`

Email items get an extra **classification step** (news vs. funding) before extraction. Funding urgency is then computed **deterministically in Python** from days-until-deadline, not by the model — keeping time-sensitive logic reliable.

Summarization runs in parallel via `ThreadPoolExecutor` (up to 10–25 workers) for throughput.

### Stage 3 — Unification (`export_items.py`)
Merges all three streams into one `items.json` with a consistent schema, buckets locations into regions, maps urgency tiers, and parses dates robustly.

### Stage 4 — Live AI endpoints (Bedrock Nova Pro)
The Flask API exposes higher-order reasoning, each a distinct orchestration:

- **Copilot** (`/api/copilot`) — a **RAG-style** flow: `select_relevant_items()` does intent detection (funding/news/email) + keyword scoring + a diverse fallback to retrieve the most relevant items, injects them as grounded context, and Nova Pro answers **only** from that context. Conversation history is threaded for follow-ups.
- **Insights** (`/api/insights`) — sends a compacted view of all items to Nova Pro to detect genuine partnership/funding synergies, returns structured JSON, cached for 1 hour.
- **Funding matching** (`/api/funding/search`) — matches a free-text project description against funding items, returns ranked matches with one-line justifications.
- **Email drafting** (`/api/copilot/draft-email`) — Nova Lite drafts subject/body, constrained to suggest **only** contact emails that actually exist in the data.

### Stage 5 — Action (guarded)
`/api/send-email` sends via Gmail SMTP but **only** on explicit `confirmed: true`, logs every send, and never invents recipients.

---

## Tech stack

**AI / Cloud**
- **AWS Bedrock** (Amazon Nova Pro / Lite / Micro) — primary inference, via `boto3`
- OpenAI `gpt-4o-mini` — automatic fallback only

**Backend**
- Python 3.11+, Flask, flask-cors
- `boto3` (Bedrock Runtime), `feedparser`, `beautifulsoup4`, `requests`
- Gmail IMAP (ingestion) + SMTP (sending)

**Frontend**
- React 19, TanStack Router + TanStack Start, Vite
- Tailwind CSS v4, Radix UI primitives, Lucide icons
- Leaflet (interactive map), TanStack Query (data fetching)
- Bilingual i18n (EN/DE)

---

## Data flow

1. **Ingest** → raw CSVs (gitignored — contain real contact data)
2. **Summarize** → Bedrock Nova produces bilingual structured records, cached in CSVs
3. **Export** → `items.json` (unified, gitignored)
4. **Serve** → Flask API reads `items.json`, adds live Bedrock-powered endpoints
5. **Render** → React frontend consumes the API

Caching at every stage means re-running the pipeline only processes *new* items, minimizing Bedrock calls.

---

## API reference

Base URL (local): `http://localhost:5001`

| Method | Endpoint | Purpose | AI |
|--------|----------|---------|-----|
| GET | `/api/items` | All items (filterable by `type`, `region`, `priority`) | — |
| GET | `/api/items/<id>` | Single item | — |
| GET | `/api/briefing` | Prioritized daily briefing | — |
| GET | `/api/search?q=` | Substring search | — |
| GET | `/api/markers` | Geocoded map markers | — |
| GET | `/api/meta` | Topics, regions, type labels | — |
| GET | `/api/insights` | Partnership/synergy detection | Nova Pro |
| POST | `/api/copilot` | Grounded conversational Q&A | Nova Pro |
| POST | `/api/copilot/draft-email` | Draft outreach email | Nova Lite |
| POST | `/api/funding/search` | Match project → funding | Nova Pro |
| POST | `/api/send-email` | Send email (requires `confirmed:true`) | — (SMTP) |

---

## Setup & running locally

You need **two terminals** — backend (Flask API) and frontend (Vite).

### 0. First-time setup

```bash
cd "Python pipeline"
cp .env.example .env
# edit .env — see Configuration below
pip install -r requirements.txt
```

### 1. Backend — run the pipeline, then serve the API

```bash
# From the repo root: scrape + summarize (via Bedrock) + export
python run_all.py             # full pipeline
# or, if data is already ingested:
python run_all.py --skip-ingest

# Serve the API (Loveable pipeline)
cd "Loveable pipeline"
PORT=5001 python app.py       # http://localhost:5001
```

> The backend loads AWS + Gmail credentials from `Python pipeline/.env` automatically.

### 2. Frontend

```bash
cd "Loveable pipeline"
npm install
VITE_API_BASE="http://localhost:5001" npm run dev   # http://localhost:5173
```

Open **http://localhost:5173**.

---

## Configuration

All secrets live in `Python pipeline/.env` (gitignored). Copy `.env.example` and fill in:

| Variable | Required | Description |
|----------|----------|-------------|
| `AWS_DEFAULT_REGION` | Yes | `us-west-2` |
| `AWS_ACCESS_KEY_ID` | Yes | AWS access key |
| `AWS_SECRET_ACCESS_KEY` | Yes | AWS secret |
| `AWS_SESSION_TOKEN` | Yes (temp creds) | Session token for temporary/workshop credentials |
| `BEDROCK_MODEL_PRO` | No | Default `us.amazon.nova-pro-v1:0` |
| `BEDROCK_MODEL_LITE` | No | Default `us.amazon.nova-lite-v1:0` |
| `BEDROCK_MODEL_MICRO` | No | Default `us.amazon.nova-micro-v1:0` |
| `OPENAI_API_KEY` | No | Fallback only; leave blank to use Bedrock exclusively |
| `OPENAI_MODEL` | No | Default `gpt-4o-mini` |
| `GMAIL_IMAP_USER` | For email features | Gmail address with Google Alerts |
| `GMAIL_APP_PASSWORD` | For email features | 16-char Gmail App Password (not your login password) |
| `IMAP_HOST` | No | Default `imap.gmail.com` |
| `ALERT_SENDER` | No | Default `googlealerts-noreply@google.com` |
| `ALERT_SINCE_DAYS` | No | Days of email history to scan (default 7) |

> **Note on AWS credentials:** if you use temporary/workshop credentials, `AWS_SESSION_TOKEN` is required and the credentials expire. When they expire, refresh all three AWS values in `.env` and restart the backend — `.env` is the single source of truth (loaded with `override=True`).

---

## Project structure

```
FISK/
├── README.md                       # this file
├── run_all.py                      # full-pipeline orchestrator
├── docs/
│   └── AWS_BEDROCK.md              # deep-dive on the Bedrock integration
│
├── Python pipeline/                # data + AI engine
│   ├── bedrock_llm.py              # Bedrock client (Nova Lite) + OpenAI fallback
│   ├── ingest.py                   # RSS news scraping
│   ├── ingest_funding.py           # grant-database scraping
│   ├── ingest_inbox.py             # Gmail Google-Alert ingestion (IMAP)
│   ├── summarize.py                # standalone news summarizer
│   ├── summarize_funding.py        # funding extraction (parallel)
│   ├── run_summarize.py            # news + email summarization runner
│   ├── app.py                      # summarization logic + internal dashboard
│   ├── export_items.py             # unify everything → items.json
│   ├── ARCHITECTURE.md             # original design notes
│   └── .env.example
│
└── Loveable pipeline/              # product (API + frontend)
    ├── bedrock_client.py           # Bedrock client (Nova Pro/Lite/Micro) + fallback
    ├── app.py                      # Flask JSON API + AI endpoints
    ├── src/                        # React app (routes, components, lib)
    │   ├── routes/                 # dashboard, inbox, funding, opportunities
    │   ├── components/lumen/       # map, copilot, briefing, badges
    │   └── lib/                    # api client, i18n, hooks
    └── package.json
```

---

## Credits

Built with **Kiro** (AWS) during the AI For Good Hackathon. AI inference powered by **Amazon Bedrock**.
