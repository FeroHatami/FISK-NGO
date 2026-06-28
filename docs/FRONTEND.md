# Frontend

A React 19 SPA built on TanStack Router + TanStack Start, Vite, and Tailwind CSS v4. Bilingual (EN/DE).

---

## Routes (`src/routes/`)

| Route file | Path | Purpose |
|------------|------|---------|
| `__root.tsx` | — | Root layout, error boundaries, providers |
| `index.tsx` | `/` | Landing/redirect |
| `app.tsx` | `/app` | App shell: sidebar, top bar, global search, AI copilot |
| `app.index.tsx` | `/app/` | **Dashboard** — map, daily briefing, Action required / Important updates |
| `app.inbox.tsx` | `/app/inbox` | **Smart Inbox** — all items sorted by priority, detail view |
| `app.funding.tsx` | `/app/funding` | **Funding finder** — AI project-to-grant matching |
| `app.opportunities.tsx` | `/app/opportunities` | **Opportunity finder** — AI partnership insights |

---

## Key components (`src/components/lumen/`)

| Component | Role |
|-----------|------|
| `africa-map.tsx` | Leaflet map: urgency-colored markers, hover tooltips, click-to-filter by region |
| `copilot.tsx` | Floating "Ask AI" chat widget → `/api/copilot` and `/api/copilot/draft-email` |
| `daily-briefing.tsx` | Prioritized briefing card |
| `badges.tsx` | Priority dots, type badges |
| `logo.tsx` | Brand mark |

UI primitives (buttons, dialogs, dropdowns, etc.) live in `src/components/ui/` (Radix-based).

---

## Library (`src/lib/`)

| File | Purpose |
|------|---------|
| `api.ts` | Typed API client; base URL from `VITE_API_BASE` (defaults to `http://localhost:5000`) |
| `use-items.ts` | TanStack Query hooks (`useItems`, `useMarkers`, …) with caching |
| `i18n.ts` | EN/DE string table + `t()` helper + `useLang()` |
| `sort-items.ts` | Priority sorting + language-aware titles |
| `mock-data.ts` | The `Item` TypeScript type + dev sample data |
| `utils.ts` | `cn()` class merge helper |

---

## Data fetching

TanStack Query handles fetching, caching, and revalidation. The dashboard reads `/api/items` and `/api/markers`; the copilot and funding/opportunity pages call the AI endpoints on demand. The `apiFetch` wrapper always includes credentials for session continuity.

---

## Internationalization

Every user-facing string flows through `t(key, lang)` with an `EN`/`DE` table in `i18n.ts`. Items themselves are bilingual end-to-end (`title`/`title_de`, `translation`/`translation_de`), so switching language swaps both the UI chrome and the content.

---

## UI behavior notes

- **Show more / show less:** the dashboard's "Action required" and "Important updates" sections show 5 items by default with an expand/collapse toggle, keeping the page short.
- **Map layering:** the map is an isolated stacking context so its Leaflet panes don't overlap the search dropdown or copilot panel (both `z-[100]`).
- **Map tooltips:** hovering a marker shows a compact card (location, count, top items); the tooltip auto-flips to stay on-screen.

---

## Running the frontend

```bash
cd "Loveable pipeline"
npm install
VITE_API_BASE="http://localhost:5001" npm run dev   # http://localhost:5173
```

Build a standalone static SPA (servable from any static host or Flask):

```bash
npx vite build --config vite.spa.config.ts   # outputs dist-spa/
```
