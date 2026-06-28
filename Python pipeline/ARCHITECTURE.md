# Press Review & Funding Monitor — Canonical Architecture

**Challenge:** AI4Good Hackathon @ TUM (June 27–28) — Track 1: Welttierschutzgesellschaft (WTG) / Burundikids

> **Status of this document.** This is the single source of truth for the platform. It supersedes the
> earlier Mastra / multi-agent / Mutagent design in `Obsidian/02-Soloutions.md` and
> `Obsidian/04-Architecture.md`. Those notes are kept for history and the org/category research in
> `Obsidian/00-*` and `Obsidian/01-*` is still valid. See `Obsidian/00-Index.md` for the map.
>
> What changed and why: the team pivoted from an aspirational TypeScript/Mastra "self-healing multi-agent"
> design to a grounded Python pipeline with confirmed data sources, deterministic funding urgency, caching,
> and a real Flask output. The one idea worth keeping from the old design — an automated evaluation harness —
> has been ported into Section 7 (Evaluation & Reliability) so we can state quality with a number instead of
> asserting it.

---

## 1. The problem

WTG and Burundikids run campaigns and fundraising from abroad, across many countries. Today, staying
informed means:

- Manually checking news sites for relevant developments.
- Manually visiting funding-partner websites to dig out deadlines, amounts, and eligibility criteria, one
  site at a time.
- Manually reading, translating, and categorizing partner emails / newsletters.

This is the time sink the project targets. The MVP is **not a decision-making tool** — it surfaces
information; humans still decide what to act on.

---

## 2. Team & ownership

| Role | Owner |
|---|---|
| LLM layer (summarization, translation, extraction) | You |
| Filtering / relevance scoring | DS student |
| Pitch narrative & value proposition | Business student |
| Data licensing & translation liability | Law student |
| Sourcing sample articles (incl. WTG track) | Business + Law students |
| Simulated mailbox content | Teammate (separate from this doc's scope) |
| Output / web page | TBD — whoever finishes their stage first |

---

## 3. High-level shape

Three source tracks feed into one shared pipeline shape, converging on one website:

```
Sources → Ingestion → Filtering → Summarization (LLM) → Evaluation gate → Output (shared web page)
```

The three tracks:

1. **News** — RSS feeds + manually-sourced articles.
2. **Funding opportunities** — scraped funding listing pages.
3. **Simulated mailbox** — hand-authored sample emails (demo of the email pain point; built by a teammate,
   not detailed further here).

The **Evaluation gate** (Section 7) is new relative to the original doc: a golden-dataset scorecard that
measures pipeline accuracy so reliability is measured, not assumed.

---

## 4. Track 1 — News

### Sources

Confirmed working RSS feeds:

- Iwacu English News — `https://www.iwacu-burundi.org/englishnews/feed/`
- Radio Isanganiro — `https://isanganiro.org/feed/`
- Burundi-Eco — `https://burundi-eco.com/feed/`
- Yaga Burundi — `https://yaga-burundi.com/feed/`

**WTG (animal welfare) side — improved.** The original doc found no RSS feed for WTG and fell back to
manually-sourced articles only. That leaves the org whose name is on the track without a live-automation
story. **Add a Google News RSS query** as a live source for WTG:

```
https://news.google.com/rss/search?q=(animal+welfare+OR+donkey+hide+OR+wildlife+trafficking+OR+rabies+OR+livestock)+(Africa+OR+Kenya+OR+Malawi+OR+India)&hl=en-US&gl=US&ceid=US:en
```

Manually-sourced sample articles remain the curated backup for demo quality.

Radio sources (RTNB, Radio Bonesha FM, etc.) are MP3 audio — explicitly **out of scope** for this MVP
(would require speech-to-text). Flagged as future work in the pitch, not silently dropped.

### Ingestion — `ingest.py`

- Uses `feedparser` to pull title, link, published date, summary, source from each feed.
- Follows each `link` and scrapes full article text via `requests` + `BeautifulSoup` (tries common content
  selectors, falls back to all `<p>` tags).
- Outputs `articles.csv`: `source, title, link, published_date, summary, full_text`.
- Graceful error handling — a bad feed or failed scrape never crashes the run.
- Confirmed working: 30/30 test rows scraped cleanly, no empty `full_text`.
- Sources are mixed-language — Iwacu is English; Isanganiro and Burundi-Eco came back in French.
  Translation is required, not optional.

### Filtering

Owned by DS student. Scores relevance against the brief's criteria table (geographic, thematic,
organizational, funding-relevant) before any article reaches the LLM summarization step — keeps API cost and
noise down.

### Summarization — one LLM call per article

**Output JSON:**

```json
{
  "gist": "1-2 sentence summary (see Section 9 for target language)",
  "key_points": ["point 1", "point 2", "point 3"],
  "locations": ["all specific places mentioned"],
  "category": "one of the 9 category values (see Section 6)",
  "urgency": "high | medium | low",
  "urgency_reason": "one short sentence"
}
```

- **Urgency is judged from article content**, not recency — a water-scarcity report is high-urgency
  regardless of date; a road-repair update is low-urgency even if published today.
- To reduce run-to-run drift in LLM urgency, the prompt carries a short rubric + 2–3 few-shot examples
  (see Section 7 — this is exactly what the eval harness pins down).
- **Locations are a list**, not a single best guess — one article can be relevant to multiple regional teams.
- Translation happens inside this same call.
- Model: a mini/nano-tier model (e.g. `gpt-4o-mini`) — this is a structured-extraction task, not a reasoning
  task; flagship models would be 15–30x more expensive for no quality gain.
- `response_format={"type": "json_object"}` forces valid JSON instead of relying on instruction-following
  alone. (Upgrade path: a JSON-schema-constrained `response_format` for even stricter validation.)
- Results cached in `summaries.csv`, keyed by `link`, so re-runs never re-pay for already-summarized articles.

---

## 5. Track 2 — Funding opportunities

### Why this exists

Direct from the org: a person currently has to manually visit each funding partner's site, click through,
and read criteria — described as one of their most time-consuming tasks.

### Sources

Static listing pages (not RSS) — `ingest_funding.py` scrapes:

- Förderdatenbank Entwicklungsländer — `https://wirtschaft-entwicklung.de/digitale-services/foerderdatenbank-entwicklungslaender`
- Förderkompass — `https://www.zerowasteagentur.de/foerderkompass.html`

No email/inbox access — the org's actual inbox isn't reachable by the team, so this track works off public
funding listing pages instead.

### Ingestion — `ingest_funding.py`

- `requests` + `BeautifulSoup`, parsing list/table HTML (different selector logic than RSS-based scraping —
  these are static listing pages, no feed format).
- Extracts title, raw descriptive text block, link (if any), source.
- Output: `funding_opportunities.csv` — `source, title, link, raw_text`.
- Field-splitting (deadline, amount, eligibility) happens in the next stage, not here.

> **Reliability note (new).** Static-page scrapers are the most fragile part of the system — selectors break
> when sites change, and the original doc already flags 1–2 rounds of correction needed. Mitigations:
> defensive parsing with selector fallbacks, and **keep the last good `funding_summaries.csv`** so a broken
> scrape degrades to stale-but-present data instead of a blank board.

### Filtering

Same criteria-table relevance check as news, **plus an eligibility pre-check** (e.g. "German applicant
possible," funding size appropriate for a small NGO) — a dimension that didn't apply to news filtering.

### Summarization — `summarize_funding.py`

**Output JSON:**

```json
{
  "deadline": "YYYY-MM-DD, or null if rolling/no deadline mentioned",
  "amount": "funding amount with currency, or null if unspecified",
  "eligibility": ["bullet point 1", "bullet point 2"],
  "category": "one of the 9 category values (see Section 6)",
  "locations": ["relevant countries/regions"]
}
```

- **Eligibility as bullet points**, not a paragraph — reuses the news `key_points` pattern for at-a-glance
  scanning on a card.
- **No `gist` or `urgency` field from the LLM** — funding urgency is deadline-driven, computed
  deterministically in Python, not judged by the model.
- **Urgency, computed in plain Python after extraction** (the deterministic layer the eval harness verifies):
  - `deadline` is null → `"undefined"` (gray — distinct from "not urgent"; the concept doesn't apply).
  - `(deadline − today).days ≤ 30` → `"high"` (red).
  - `≤ 60` → `"medium"` (yellow).
  - else → `"low"` (green).
- Same caching pattern as news, keyed by `link`, written to `funding_summaries.csv`.
- Cards link back to the original listing (`link`, passed through from ingestion).

---

## 6. Shared category taxonomy

Categories are **not invented** — they're each organization's own stated breakdown of their work, taken
directly from their materials.

**WTG's 4 operation types** (from their "How They Deploy Aid" description):

1. Mobile Veterinary Support
2. Stray Population Infrastructure
3. Wildlife Trade Defenses
4. Emergency Relief Hub

**Burundikids' 4 project areas** (from their homepage navigation):

5. Bildung
6. Gesundheit
7. Kinder- und Frauenrechte
8. Kommunale Entwicklung und Umweltschutz

9. **Uncategorized** — fallback when the LLM can't confidently match a category.

Both news and funding map into this **same 9-value list**, since both answer the same question: "which
operational area does this relate to?"

A separate `content_type` field (`"news"` / `"funding"`) keeps the two tracks distinguishable inside a
category — category and content type are independent axes.

**Resolved open item:** general/unrestricted funding (not earmarked to a specific ops area) falls under
**Uncategorized** for now. Only promote it to a 10th value if it turns out to be common in practice.

---

## 7. Evaluation & Reliability *(new — ported from the old design)*

The original Python doc verifies *ingestion* (30/30 rows) but never measures whether the *LLM output* is
correct. This section closes that gap with a small automated harness. It also satisfies the spirit of the old
Mutagent side-challenge (a deterministic pass/fail scorecard) without the framework overhead.

Implementation lives in `App/Backend/eval/`:

- `golden_dataset.json` — hand-labeled news + funding cases with expected outputs, plus a fixed `as_of` date
  so deterministic urgency is reproducible.
- `scorecard.py` — computes per-field metrics and an aggregate pass/fail against a threshold. Two layers:
  - **Deterministic checks** (always runnable, no model): funding urgency from deadline. Should be 100%.
  - **Model-output checks**: category accuracy, news-urgency accuracy, deadline/amount correctness, location
    recall. Run `--live` against the real summarizer, or default **replay** mode against recorded predictions.
- `predictions.sample.json` — sample model outputs so a default run produces a real scorecard immediately.

Why this matters for the pitch: it turns "the system is reliable" into "the deterministic layer scores 100%
and the model layer scores X% on a held-out set." That is a measurable, defensible claim.

The same `compute_funding_urgency()` / date helpers used by the harness should be imported by
`summarize_funding.py` so the pipeline and the test share one implementation.

---

## 8. Output — the website

- **Flask app** (`app.py`), runs locally for the demo — no deployment needed to prove the concept.
- **Category tabs** — the 9 shared values from Section 6.
- **Within each category tab — two sub-sections**, not merged: **News** and **Funding Opportunities**,
  distinguished by `content_type`.
- **Urgency color-coding** — news uses content-judged high/medium/low; funding uses deadline-driven
  high/medium/low/undefined. Each track keeps its own urgency scale; they are not unified.
- **Africa map** with location-stamped markers, color = highest urgency among items tied to that location.
  - **Fix required before demo:** `LOCATION_COORDS` currently covers only Burundi/East Africa. WTG operates
    in India, Thailand, Malawi, Indonesia/Sumatra too — add these or WTG markers silently fail to render.
- Each card links back to the original source article/listing.

---

## 9. Language

The original doc outputs **English** for all tracks. Since Burundikids' actual working language is German and
the demo audience is German NGOs, the recommendation is to **default Burundikids (news + funding) output to
German now** — it is a one-line prompt change (swap "English" for "German" in each system prompt), not a
structural rework. WTG-track content can stay English or also move to German depending on the demo framing.
Target language is therefore a per-track setting rather than a global English default.

---

## 10. Cross-cutting: deduplication

If a mailbox email and a scraped news article describe the same underlying event, metadata alone
(location + date + category) is **not sufficient** to detect duplicates — multiple distinct projects can
share all three. Planned approach:

1. **Narrow by metadata first** (location + date + category match) to a small candidate pool.
2. **LLM comparison only on that narrowed pool** — ask "are these the same event?" rather than comparing
   everything against everything (keeps cost low).
3. Embeddings-based similarity was considered but deprioritized — the team is comfortable with the
   chat-completions pattern, not the embeddings API, so reusing the existing pattern is faster to build
   correctly in the time available.

**Status: designed, not yet built.**

---

## 11. Cost

Using a mini/nano-tier model, each article/listing costs roughly **$0.0003–0.0005** per LLM call
(~1,700–2,000 tokens in+out). On a $50 hackathon credit budget, tens of thousands of items could be processed
before cost matters — **time, not API cost, is the binding constraint.**

---

## 12. Security (for when this ships beyond a demo)

1. OpenAI API key lives in `.env`, loaded via `python-dotenv` — never hardcoded; `.env` is in `.gitignore`.
2. Scraped content is rendered via Flask/Jinja2, which auto-escapes by default — protects against XSS from
   untrusted scraped text.
3. Access control: an internal tool (not public-facing), so a simple shared password is sufficient for now —
   no full user accounts at this stage.
4. `debug=True` in `app.run()` must be turned off before any demo or deployment reachable by others.

---

## 13. Scheduling (future / production, not built for the demo)

For the demo, the pipeline runs manually (`python ingest.py`, etc.) whenever fresh data is wanted.

For an always-on version:

- **Cheapest:** GitHub Actions scheduled workflow (free for reasonable usage, no server) — runs the ingestion
  scripts on cron, commits updated CSVs back to the repo.
- **Given AWS credits are available:** AWS Lambda + EventBridge writing to S3/DynamoDB — more
  production-grade, but with real setup overhead (dependency packaging, IAM) not worth it during the hackathon.
- Either way, a **deduplication-on-ingest check** (skip items already seen, by `link`) is needed before this
  runs unattended, to avoid re-summarizing the same content and wasting credits.

---

## 14. Explicitly out of scope (per the org's own stated constraints)

- **No auto-recommend / auto-apply logic.** The org explicitly said "not decision-making."
- **"Send to everyone" notification/routing** — a real ask, scoped as roadmap.
- **Weekly newsbrief digest** (currently done by hand via Google Alerts) — roadmap.
- **Real inbox integration** — not feasible to access; replaced by the simulated mailbox demo.
- **Speech-to-text for radio sources** — future work.
- **Real-time/instant updates** — periodic batch runs (hours, not seconds) are sufficient.

---

## 15. Build status

| Component | Status |
|---|---|
| `ingest.py` — news RSS scraping + full-text extraction | ✅ working (30/30 test rows clean) |
| `app.py` — Flask app, summarization w/ caching, category grouping, map | ✅ working (3 fixes: expand map coords, force JSON response, validate urgency) |
| `ingest_funding.py` — funding listing scraper | ✅ sources confirmed (selectors may need 1–2 corrections) |
| WTG Google News RSS feed | ⏳ recommended, not added |
| `summarize_funding.py` | ⏳ designed, prompt written, not yet run against real data |
| `app.py` funding integration (merged tabs, sub-sections) | ⏳ prompt written, not applied |
| `eval/` harness (scorecard + golden set) | ✅ scaffolded (this commit) — wire `--live` to real summarizer |
| German output for Burundikids | ⏳ one-line change, not applied |
| Deduplication across tracks | ⏳ designed, not built |
| Simulated mailbox | ⏳ owned by a teammate |

---

## 16. Recommended next steps (priority order)

1. Harden the funding scrapers (defensive parsing + last-good cache) and run `summarize_funding.py` against
   real scraped data — the only core piece unproven against live data.
2. Fill out `eval/golden_dataset.json` with real labeled examples and run `scorecard.py` so reliability has a
   number.
3. Add the WTG Google News RSS feed and extend `LOCATION_COORDS` so WTG isn't a dead spot in the demo.
4. Switch Burundikids output to German.
5. Wire funding into `app.py` (news/funding sub-sections); add cross-track dedup only if time remains.
