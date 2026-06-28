# Data Model

The unified item schema in `items.json`, the category taxonomy, and the controlled vocabularies.

---

## Item schema

Every item (news, email, funding, report, alert) shares one schema (TypeScript type in `src/lib/mock-data.ts`):

```ts
interface Item {
  id: string;                 // e.g. "news-0", "funding-12", "email-5"
  priority: "high" | "med" | "low";
  type: "funding" | "news" | "email" | "report" | "alert";
  title: string;              // English title
  title_de?: string;          // German title
  title_original?: string;    // original-language title
  source: string;
  date: string;               // ISO 8601
  topic: string[];            // category taxonomy values
  region: string[];           // bucketed regions
  summary: string;
  suggestedAction: "Apply" | "Reply" | "Read" | "Monitor";
  urgency: "now" | "today" | "this week" | "later";
  timeEstimate: "2 min" | "5 min" | "15 min" | "30 min" | "1h" | "2h";

  translation?: string;       // English summary
  translation_de?: string;    // German summary
  original?: string;          // original source text (truncated)
  originalLanguage?: string;  // e.g. "French"

  // funding-only
  deadline?: string;          // ISO date
  amount?: string;            // e.g. "€15,000 – €80,000"
  eligibility?: string;
  requirements?: string;
  fundingOrg?: string;

  // email-only
  sender?: string;

  // contacts (only if literally present in source)
  contact_email?: string;
  contact_phone?: string;

  link?: string;
}
```

---

## Category taxonomy (9 values)

Tailored to the two partner NGOs (WTG — animal welfare; Burundikids — Burundi development):

| Category | Domain |
|----------|--------|
| Mobile Veterinary Support | Working-animal health, vet clinics |
| Stray Population Infrastructure | Stray dogs/cats, spay/neuter, rabies |
| Wildlife Trade Defenses | Poaching, trafficking, seizures |
| Emergency Relief Hub | Disasters, outbreaks, conflict displacement |
| Bildung | Education, schools, training, youth |
| Gesundheit | Human health, hospitals, maternal health |
| Kinder- und Frauenrechte | Children's & women's rights, GBV |
| Kommunale Entwicklung und Umweltschutz | Infrastructure, environment, water, agriculture |
| Uncategorized | Fallback when nothing fits |

The model must return exactly one of these; any other value is coerced to `Uncategorized`.

---

## Regions (8 buckets)

Free-text locations from the model are bucketed into: **Burundi, East Africa, Germany, India, Thailand, Malawi, Indonesia, Global.**

`export_items.py` maps specific places (e.g. Bujumbura → Burundi; Nairobi → East Africa; Berlin → Germany) into these buckets.

---

## Priority vs. urgency

Two distinct axes:

- **`priority`** (`high/med/low`) — derived from the model's content-based urgency judgement. Drives the "Action required" vs. "Important updates" split on the dashboard.
- **`urgency`** (`now/today/this week/later`) — a time bucket:
  - **News/email:** by recency (`< 24h` = now, `< 48h` = today, `< 168h` = this week, else later).
  - **Funding:** by deadline proximity (`≤ 3d` = now, `≤ 14d` = today, `≤ 30d` = this week, else later).

This lets the UI distinguish "important" from "time-sensitive" — a low-priority grant with a tomorrow deadline still surfaces as urgent.

---

## Contact-extraction policy

`contact_email` / `contact_phone` are populated **only when literally present** in the source text. The prompts explicitly forbid inference. This is enforced again at the email-drafting layer, which will only suggest recipients that actually exist in the data — preventing the system from inventing addresses.
