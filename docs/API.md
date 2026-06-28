# API Reference

Flask JSON API served by `Loveable pipeline/app.py`. CORS is enabled. Base URL (local): `http://localhost:5001`.

AI-backed endpoints route to **AWS Bedrock (Amazon Nova)** with OpenAI fallback.

---

## Data endpoints

### `GET /api/items`
All items. Optional query filters:
- `type` — `funding | news | email | report | alert`
- `region` — e.g. `Burundi`
- `priority` — `high | med | low`

```bash
curl "http://localhost:5001/api/items?type=funding&region=Burundi"
```

### `GET /api/items/<id>`
A single item by id (e.g. `funding-12`). `404` if not found.

### `GET /api/search?q=<query>`
Case-insensitive substring search across title, summary, translation, topic, region, source. Capped at 20 results.

### `GET /api/meta`
Topic list, region list, and type labels for populating filters.

### `GET /api/markers`
Geocoded map markers — each with `name`, `lat`, `lng`, `urgency`, `count`, and the top items at that location.

### `GET /api/briefing`
Deterministic prioritized briefing: bilingual summary, high-priority highlights, and stats.

---

## AI endpoints (AWS Bedrock)

### `POST /api/copilot` — Nova Pro
Grounded conversational Q&A.

```json
// request
{ "message": "What funding has deadlines this month?", "history": [] }
// response
{ "reply": "..." }
```
`history` is an array of `{ "role": "user"|"assistant", "content": "..." }` for follow-ups. The server retrieves relevant items (intent + keyword scoring), injects them as context, and Nova Pro answers only from that context.

### `GET /api/insights` — Nova Pro
Detected partnership/collaboration opportunities across all items. Cached for 1 hour; `?refresh=true` forces re-analysis.

```json
{ "insights": [
  { "label": "Potential partnership",
    "title_en": "...", "title_de": "...",
    "description_en": "...", "description_de": "...",
    "item_ids": ["news-3", "funding-7"] }
] }
```

### `POST /api/funding/search` — Nova Pro
Match a free-text project description against funding opportunities.

```json
// request
{ "query": "We run education programs for children in Burundi and need grants" }
// response
{ "matches": [ { "...item fields...", "matchReason": "Why this fits" } ] }
```

### `POST /api/copilot/draft-email` — Nova Lite
Draft an outreach email. Suggests **only** contact emails that exist in the data.

```json
// request
{ "message": "Ask about the KfW funding deadline", "history": [], "language": "en" }
// response
{ "subject": "...", "body": "...", "suggested_recipients": ["..."], "contact_note": "..." }
```

### `POST /api/send-email` — SMTP (guarded)
Sends via Gmail SMTP. **Requires** `confirmed: true`; rejects otherwise. Logs every send to `data/sent_emails_log.json`.

```json
// request
{ "to": ["x@org.org"], "subject": "...", "body": "...", "confirmed": true }
// response
{ "success": true, "message": "Email sent to x@org.org." }
```

Guards:
- `confirmed !== true` → `400` "Sending requires explicit confirmation".
- Missing `to`/`subject`/`body` → `400`.
- Missing SMTP creds → `500`.

---

## Error model
Endpoints return `200` with an `error` field for soft failures (e.g. AI unavailable), and standard `4xx/5xx` for hard failures (missing fields, not found). AI endpoints degrade gracefully — if both Bedrock and OpenAI fail, the copilot returns an apologetic message rather than crashing.
