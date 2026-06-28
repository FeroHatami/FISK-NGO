#!/usr/bin/env python3
"""Summarize scraped articles using an LLM (OpenAI-compatible API).

Reads articles.csv (output of ingest_inbox.py or ingest.py), sends each row's
full_text through a structured-extraction prompt, and writes summaries.csv.

Caches by `link` — re-running skips already-summarized articles so you never
pay twice. Rows with empty full_text are skipped (scrape failed).

Usage:
    python3 summarize.py                        # summarize all unsummarized articles
    python3 summarize.py --limit 5              # only process 5 new articles (cost control)
    python3 summarize.py --input articles.csv   # explicit input path
    python3 summarize.py --language German       # output language (default: German)

Requires: OPENAI_API_KEY in .env (or environment).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from bedrock_llm import llm_chat

HERE = Path(__file__).resolve().parent

# The 9-value category taxonomy from ARCHITECTURE.md §6
CATEGORIES = [
    "Mobile Veterinary Support",
    "Stray Population Infrastructure",
    "Wildlife Trade Defenses",
    "Emergency Relief Hub",
    "Bildung",
    "Gesundheit",
    "Kinder- und Frauenrechte",
    "Kommunale Entwicklung und Umweltschutz",
    "Uncategorized",
]

INPUT_FIELDS = ["source", "title", "link", "published_date", "summary", "full_text", "alert_topic"]
OUTPUT_FIELDS = [
    "source", "title", "link", "published_date", "alert_topic",
    "gist", "key_points", "locations", "category", "urgency", "urgency_reason",
]

SYSTEM_PROMPT = """You are an expert intelligence analyst working for two German NGOs:
- Welttierschutzgesellschaft (WTG): animal welfare, wildlife trade, veterinary support, stray animals.
- Burundikids e.V.: education, health, children's/women's rights, community development in Burundi.

Your task: read the article text and produce a structured JSON extraction. Be concise and factual.
Do NOT hallucinate information not present in the text.

Output JSON with exactly these fields:
{{
  "gist": "1-2 sentence summary in {language}. Translate if the source is in another language.",
  "key_points": ["up to 3 bullet points, in {language}"],
  "locations": ["all specific places/countries/regions mentioned"],
  "category": "exactly one of: {categories}",
  "urgency": "high | medium | low",
  "urgency_reason": "one short sentence in {language} explaining urgency level"
}}

Urgency guidelines (judge from CONTENT, not recency):
- high: active security threats, disease outbreaks, wildlife trafficking busts, natural disasters,
  violence, urgent humanitarian situations.
- medium: policy changes, elections, new programs, regional developments worth monitoring.
- low: routine reports, cultural stories, general information, stable situations.

Category guidelines:
- Mobile Veterinary Support: working animals (donkeys, horses), vet clinics, animal health.
- Stray Population Infrastructure: stray dogs/cats, spay/neuter, rabies vaccination programs.
- Wildlife Trade Defenses: poaching, trafficking, smuggling, seizures, wildlife crime.
- Emergency Relief Hub: disasters, floods, conflict displacement, emergency funding, Ebola/epidemics.
- Bildung: education, schools, training, literacy, youth programs.
- Gesundheit: health (human), hospitals, disease (non-emergency), maternal health.
- Kinder- und Frauenrechte: children's rights, women's rights, GBV, shelters.
- Kommunale Entwicklung und Umweltschutz: infrastructure, environment, water, sanitation, agriculture.
- Uncategorized: does not clearly fit any of the above.
"""


def build_user_prompt(title: str, full_text: str, source: str, alert_topic: str) -> str:
    # Truncate very long articles to stay within token limits
    max_chars = 6000
    text = full_text[:max_chars] + ("..." if len(full_text) > max_chars else "")
    return (
        f"Source: {source}\n"
        f"Alert topic: {alert_topic}\n"
        f"Title: {title}\n\n"
        f"Article text:\n{text}"
    )


def summarize_one(client, model: str, row: dict, language: str) -> dict | None:
    """Call AWS Bedrock (Nova) for one article. Returns parsed JSON dict or None on failure."""
    system = SYSTEM_PROMPT.format(
        language=language,
        categories=" | ".join(CATEGORIES),
    )
    user = build_user_prompt(row["title"], row["full_text"], row["source"], row.get("alert_topic", ""))

    try:
        content = llm_chat(
            system_prompt=system,
            user_prompt=user,
            temperature=0.1,
            max_tokens=500,
            json_mode=True,
        )
        if not content:
            return None
        data = json.loads(content)
        # Validate category
        if data.get("category") not in CATEGORIES:
            data["category"] = "Uncategorized"
        # Normalize urgency
        if data.get("urgency") not in ("high", "medium", "low"):
            data["urgency"] = "low"
        return data
    except Exception as exc:
        print(f"  ERROR summarizing {row['link']}: {exc}", file=sys.stderr)
        return None


def load_existing_cache(path: Path) -> dict[str, dict]:
    """Load already-summarized rows keyed by link."""
    cache = {}
    if path.exists():
        with path.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                cache[row["link"]] = row
    return cache


def main() -> int:
    ap = argparse.ArgumentParser(description="Summarize articles via LLM")
    ap.add_argument("--input", type=Path, default=HERE / "articles.csv")
    ap.add_argument("--output", type=Path, default=HERE / "summaries.csv")
    ap.add_argument("--limit", type=int, default=0, help="max new articles to summarize (0=all)")
    ap.add_argument("--language", default="German", help="output language (default: German)")
    args = ap.parse_args()

    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    # Note: We now use AWS Bedrock as primary. OpenAI is fallback only.
    # No API key check needed since Bedrock uses AWS credentials from environment.

    # Load input articles
    if not args.input.exists():
        print(f"ERROR: {args.input} not found. Run ingest_inbox.py first.", file=sys.stderr)
        return 1
    with args.input.open(encoding="utf-8") as f:
        articles = list(csv.DictReader(f))

    # Load cache of already-summarized articles
    cache = load_existing_cache(args.output)
    print(f"Loaded {len(articles)} articles, {len(cache)} already summarized (cached).")

    # Filter to only unsummarized articles with non-empty full_text
    to_process = [
        a for a in articles
        if a["link"] not in cache and a.get("full_text", "").strip()
    ]
    if args.limit > 0:
        to_process = to_process[:args.limit]

    print(f"Processing {len(to_process)} new article(s)...")

    # Summarize
    new_summaries = []
    for i, art in enumerate(to_process, 1):
        print(f"  [{i}/{len(to_process)}] {art['title'][:60]}...")
        result = summarize_one(None, None, art, args.language)
        if result:
            row = {
                "source": art["source"],
                "title": art["title"],
                "link": art["link"],
                "published_date": art["published_date"],
                "alert_topic": art.get("alert_topic", ""),
                "gist": result.get("gist", ""),
                "key_points": json.dumps(result.get("key_points", []), ensure_ascii=False),
                "locations": json.dumps(result.get("locations", []), ensure_ascii=False),
                "category": result.get("category", "Uncategorized"),
                "urgency": result.get("urgency", "low"),
                "urgency_reason": result.get("urgency_reason", ""),
            }
            new_summaries.append(row)
            cache[art["link"]] = row
        # Small delay to be polite to the API
        time.sleep(0.2)

    # Write all summaries (cached + new) to output
    all_rows = list(cache.values())
    with args.output.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS)
        w.writeheader()
        for row in all_rows:
            w.writerow({k: row.get(k, "") for k in OUTPUT_FIELDS})

    print(f"\nDone. {len(new_summaries)} new + {len(cache) - len(new_summaries)} cached = {len(all_rows)} total in {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
