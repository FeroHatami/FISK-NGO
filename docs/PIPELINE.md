# Data & AI Pipeline

How raw, multilingual, unstructured inputs become clean bilingual intelligence. Every AI step runs on **AWS Bedrock (Amazon Nova)**.

---

## Stage 0 — Sources

### News (`ingest.py`)
RSS feeds, full-text scraped with BeautifulSoup:

| Source | Feed |
|--------|------|
| Iwacu English News | `iwacu-burundi.org/englishnews/feed/` |
| Radio Isanganiro | `isanganiro.org/feed/` |
| Burundi-Eco | `burundi-eco.com/feed/` |
| Burundi Forum | `burundi-forum.org/feed` |

Polite scraping: rotating user-agent, 30s timeout, 0.7s delay between requests to the same domain, 5 parallel workers.

### Funding (`ingest_funding.py`)
| Source | Method |
|--------|--------|
| Förderdatenbank Entwicklungsländer | JSON embedded in a `data-projects` HTML attribute |
| Förderkompass (Zero Waste Agentur) | Structured German-labeled bullet lists |

### Email (`ingest_inbox.py`)
Google Alert emails pulled over **Gmail IMAP**, filtered by sender (`googlealerts-noreply@google.com`) and a configurable lookback window (`ALERT_SINCE_DAYS`). Linked articles are de-referenced and their full text scraped.

Each collector writes a CSV cache: `articles.csv`, `funding_opportunities.csv`, `alert_articles.csv`. (All gitignored — they contain real contact data.)

---

## Stage 1 — Structured extraction (Bedrock Nova Lite, JSON mode)

Each raw item is sent through a strict JSON-schema prompt. The model performs, in a single call:

1. **Translation** — source (French/English/Kirundi/German) → English **and** German.
2. **Summarization** — 1–2 sentence gist + up to 3 key points, bilingual.
3. **Location extraction** — every place named (drives the map).
4. **Classification** — exactly one of 9 taxonomy categories (see [DATA_MODEL.md](DATA_MODEL.md)).
5. **Urgency scoring** — high / medium / low, with a content-based rationale.
6. **Contact extraction** — email/phone, **only if literally present** (never inferred).

Email items get an extra **classification step first** (news vs. funding), then the appropriate extraction. Funding items additionally extract `deadline`, `amount`, and bilingual `eligibility`.

### Validation & guardrails
- Category not in the allowed set → coerced to `Uncategorized`.
- Urgency not in {high, medium, low} → coerced to `low`.
- JSON wrapped in markdown fences → stripped before parsing.
- Funding **urgency is recomputed in Python** from days-until-deadline (deterministic), not trusted from the model:
  - `< 0 days` → expired (filtered out)
  - `≤ 30` → high · `≤ 60` → medium · else low

---

## Stage 2 — Unification (`export_items.py`)

Merges the three streams into one `items.json` with a single schema:

- Buckets free-text locations into 8 regions (Burundi, East Africa, Germany, India, Thailand, Malawi, Indonesia, Global).
- Maps internal urgency to the frontend's priority (`high/med/low`) and recency/deadline buckets (`now/today/this week/later`).
- Robust multi-format date parsing → ISO timestamps.
- Carries the original source text (truncated) for the detail view.

Typical run output: **40 news + 87 email + 87 funding = 214 items.**

---

## Stage 3 — Live AI endpoints (Bedrock Nova Pro)

Served by `Loveable pipeline/app.py` at request time — see [API.md](API.md). These are higher-order reasoning steps over the unified data:

- **Copilot** — retrieval-grounded Q&A (intent detection + keyword scoring selects context, Nova Pro answers only from it).
- **Insights** — partnership/synergy detection across all items (cached 1h).
- **Funding matching** — free-text project → ranked funding opportunities with reasons.
- **Email drafting** — outreach email constrained to real contacts.

---

## Running the pipeline

```bash
# Full run (scrape → summarize via Bedrock → export)
python run_all.py

# Re-summarize/export without re-scraping
python run_all.py --skip-ingest
```

`run_all.py` orchestrates: `ingest.py` → `ingest_funding.py` → `ingest_inbox.py` (if Gmail creds present) → `summarize_funding.py` → `run_summarize.py` → `export_items.py`, then starts the API.
