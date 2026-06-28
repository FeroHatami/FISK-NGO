# AI Prompts & Reasoning Design

The system uses purpose-built prompts at each stage. All run on **AWS Bedrock (Amazon Nova)**. This document explains each prompt's job; the full text lives in the source files referenced.

---

## 1. News extraction prompt
**Where:** `Python pipeline/app.py` (`SYSTEM_PROMPT`), also `summarize.py`
**Model:** Nova Lite · JSON mode

Instructs the model to act as a press-review analyst for the two NGOs and return a strict JSON object with: `title_en`, `title_de`, `gist_en`, `gist_de`, `key_points_en/de`, `locations[]`, `category`, `urgency`, `urgency_reason`, `contact_email`, `contact_phone`, `detected_language`.

Key design choices:
- **Urgency is conservative by default** — "high" is reserved for active, acute crises explicitly described as current; most items should be low/medium. This prevents alert fatigue.
- **No hallucinated contacts** — emails/phones only if literally in the text.
- **Always translate** — output is bilingual regardless of source language (French/English/Kirundi).

## 2. Email classification + extraction prompt
**Where:** `Python pipeline/app.py` (`EMAIL_SYSTEM_PROMPT`)
**Model:** Nova Lite · JSON mode

First classifies an email-sourced article as `news` or `funding`, then extracts the appropriate fields. Funding emails additionally yield `deadline`, `amount`, `summary_en/de`, `eligibility_en/de`.

## 3. Funding extraction prompt
**Where:** `Python pipeline/summarize_funding.py` (`SYSTEM_PROMPT`)
**Model:** Nova Lite · JSON mode

Extracts structured grant data: bilingual summary, `deadline` (normalized to `YYYY-MM-DD`, or null for rolling), `amount`, bilingual `eligibility[]`, `category`, `locations[]`, contacts. Ambiguous deadlines are best-estimated to a concrete date; urgency itself is then computed in Python from the deadline.

## 4. Copilot prompt
**Where:** `Loveable pipeline/app.py` (`/api/copilot`)
**Model:** Nova Pro

System prompt frames the model as the "Lumen" assistant and **constrains it to answer only from the provided items** — if the answer isn't in context, it must say so rather than guess. Retrieved items are injected as JSON context (up to ~16k chars). Conversation history is threaded for follow-ups.

**Retrieval (`select_relevant_items`)** combines three signals before the prompt:
1. **Intent detection** — keywords map to item types (e.g. "deadline/grant/apply" → funding) so the right item type is surfaced even when the literal word isn't in any item.
2. **Keyword scoring** — overlap with title/summary/topic/region.
3. **Diverse fallback** — a high-priority mix so the model is never starved of context.

## 5. Insights prompt
**Where:** `Loveable pipeline/app.py` (`/api/insights`)
**Model:** Nova Pro · JSON mode

Asks the model to find **genuine** partnership/synergy opportunities across items (shared funders, overlapping geography, complementary campaigns, aligned timing) — explicitly told to return an empty array rather than invent weak links. Bilingual output, capped at 5, cached 1h.

## 6. Funding-match prompt
**Where:** `Loveable pipeline/app.py` (`/api/funding/search`)
**Model:** Nova Pro · JSON mode

Given a free-text project description and the funding list, returns ranked matches with a one-sentence justification each; told to return few or zero if nothing genuinely fits.

## 7. Email-draft prompt
**Where:** `Loveable pipeline/app.py` (`/api/copilot/draft-email`)
**Model:** Nova Lite · JSON mode

Drafts subject/body in the requested language, constrained to suggest **only** contact emails present in the data. Returns a `contact_note` when relevant items lack contacts, so the user knows coverage is partial.

---

## Cross-cutting prompt engineering

- **Strict JSON mode** with a reinforced "JSON only" instruction, plus markdown-fence stripping on the client to survive stray formatting.
- **Validation after generation** (category/urgency coercion) rather than trusting the model blindly.
- **Deterministic logic stays in code** — time-sensitive funding urgency is computed in Python, not by the LLM.
- **Grounding over generation** — the copilot and insights are constrained to the actual data to minimize hallucination.
