"""
app.py – Flask web app that reads articles.csv, summarizes each article via
OpenAI, caches results in summaries.csv, and displays a categorized dashboard.
Also integrates funding opportunities from funding_opportunities.csv and
funding_summaries.csv.

Run with: python app.py
Requires: OPENAI_API_KEY environment variable set.
"""

import csv
import json
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from flask import Flask, render_template

from bedrock_llm import llm_chat

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent

ARTICLES_CSV = str(_HERE / "articles.csv")
SUMMARIES_CSV = str(_HERE / "summaries.csv")
EMAIL_ARTICLES_CSV = str(_HERE / "alert_articles.csv")
EMAIL_SUMMARIES_CSV = str(_HERE / "email_summaries.csv")
FUNDING_CSV = str(_HERE / "funding_opportunities.csv")
FUNDING_SUMMARIES_CSV = str(_HERE / "funding_summaries.csv")

SYSTEM_PROMPT = """You are a press review assistant for two NGOs working in Burundi and on global animal welfare (WTG).
You will be given the full text of one article. Some articles are in French, some in English.
Analyze the article and respond with ONLY a JSON object in this exact structure, no other text:
{
  "title_en": "the article title translated into English",
  "title_de": "the article title translated into German",
  "gist_en": "1-2 sentence summary in English, regardless of the article's original language",
  "gist_de": "1-2 sentence summary in German, regardless of the article's original language",
  "key_points_en": ["point 1 in English", "point 2 in English", "point 3 in English"],
  "key_points_de": ["point 1 in German", "point 2 in German", "point 3 in German"],
  "locations": ["list of all specific places mentioned, e.g. cities, regions, or countries"],
  "category": "one of the following exact strings",
  "urgency": "high | medium | low",
  "urgency_reason": "one short sentence explaining why",
  "contact_email": "a specific contact email address if literally stated in the text, or null",
  "contact_phone": "a specific contact phone number if literally stated in the text, or null",
  "detected_language": "the original language of the article, e.g. French, English, German, Kirundi"
}

Valid values for "category" (pick exactly one):
- "Mobile Veterinary Support"
- "Stray Population Infrastructure"
- "Wildlife Trade Defenses"
- "Emergency Relief Hub"
- "Bildung"
- "Gesundheit"
- "Kinder- und Frauenrechte"
- "Kommunale Entwicklung und Umweltschutz"
- "Uncategorized"

Urgency rules:
- Default to "low" unless there's a clear, specific reason to escalate.
- "high": reserved for active, acute crises ONLY — ongoing disasters, outbreaks currently happening, immediate funding deadlines, or urgent safety/conflict situations explicitly described as current and severe in the article text.
- "medium": meaningful developments, policy changes, notable progress or setbacks that matter but are not crises (e.g. new legislation, program launches, diplomatic shifts).
- "low": the default for routine coverage, general updates, profiles, ceremonial news, background reporting, or anything without explicit urgency signals in the text.
- Most articles should be "low" or "medium". Reserve "high" for genuinely acute situations only.

Contact extraction rules:
- Only populate contact_email or contact_phone if a specific email address or phone number is LITERALLY stated in the source text.
- Never infer or guess. If not explicitly given, use null.

If the article doesn't clearly fit any category, use "Uncategorized". If no specific location is named beyond the country, list the country itself."""

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

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_articles() -> list[dict]:
    """Load articles from CSV."""
    articles = []
    if not os.path.exists(ARTICLES_CSV):
        print(f"[WARNING] {ARTICLES_CSV} not found. Run ingest.py first.")
        return articles
    with open(ARTICLES_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            articles.append(row)
    return articles


def load_summaries_cache() -> dict:
    """Load existing summaries keyed by article link."""
    cache = {}
    if not os.path.exists(SUMMARIES_CSV):
        return cache
    with open(SUMMARIES_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cache[row["link"]] = row
    return cache


def save_summaries_cache(cache: dict):
    """Write the full summaries cache back to CSV."""
    if not cache:
        return
    fieldnames = [
        "link", "title_en", "title_de", "gist_en", "gist_de", "key_points_en", "key_points_de",
        "locations", "category", "urgency", "urgency_reason",
        "contact_email", "contact_phone", "detected_language",
    ]
    with open(SUMMARIES_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in cache.values():
            writer.writerow(row)


def summarize_article(client, full_text: str) -> dict | None:
    """Call AWS Bedrock (Nova) to summarize a single article. Returns parsed JSON or None."""
    if not full_text or not full_text.strip():
        return None

    try:
        content = llm_chat(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=full_text[:12000],
            temperature=0.3,
            max_tokens=1024,
            json_mode=True,
        )
        if not content:
            return None

        result = json.loads(content)
        # Validate urgency field
        valid_urgencies = {"high", "medium", "low"}
        urgency = result.get("urgency", "").strip().lower()
        result["urgency"] = urgency if urgency in valid_urgencies else "low"
        return result
    except json.JSONDecodeError as e:
        print(f"[WARNING] Failed to parse LLM response as JSON: {e}")
        return None
    except Exception as e:
        print(f"[WARNING] LLM call failed: {e}")
        return None


def run_summarization(articles: list[dict]) -> dict:
    """Summarize all articles in parallel using AWS Bedrock (Nova), with cache."""
    cache = load_summaries_cache()

    # Filter to articles not yet in cache
    to_process = []
    for article in articles:
        link = article.get("link", "")
        if link in cache:
            continue
        full_text = article.get("full_text", "")
        if not full_text.strip():
            continue
        to_process.append(article)

    print(f"[INFO] Articles total: {len(articles)}, cached: {len(cache)}, to process: {len(to_process)}")

    if not to_process:
        print("[INFO] All articles already summarized.")
        return cache

    new_calls = 0
    lock = threading.Lock()

    print(f"[INFO] Summarizing {len(to_process)} articles with 10 parallel workers (AWS Bedrock)...")

    def process_one_news(article: dict) -> tuple[str, dict | None]:
        link = article.get("link", "")
        full_text = article.get("full_text", "")
        result = summarize_article(None, full_text)
        if result:
            row = {
                "link": link,
                "title_en": result.get("title_en", ""),
                "title_de": result.get("title_de", ""),
                "gist_en": result.get("gist_en", ""),
                "gist_de": result.get("gist_de", ""),
                "key_points_en": json.dumps(result.get("key_points_en", [])),
                "key_points_de": json.dumps(result.get("key_points_de", [])),
                "locations": json.dumps(result.get("locations", [])),
                "category": result.get("category", "Uncategorized"),
                "urgency": result.get("urgency", "low"),
                "urgency_reason": result.get("urgency_reason", ""),
                "contact_email": result.get("contact_email") or "",
                "contact_phone": result.get("contact_phone") or "",
                "detected_language": result.get("detected_language") or "",
            }
            return (link, row)
        return (link, None)

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {}
        for article in to_process:
            future = executor.submit(process_one_news, article)
            futures[future] = article.get("title", "")[:50]

        for future in as_completed(futures):
            title = futures[future]
            try:
                link, row = future.result()
                if row:
                    with lock:
                        cache[link] = row
                        new_calls += 1
                    print(f"  [OK] {title}")
                else:
                    print(f"  [SKIP] {title} (no result)")
            except Exception as e:
                print(f"  [ERROR] {title}: {e}")

    # Write full cache once at the end
    save_summaries_cache(cache)

    print(f"[INFO] Summarization complete. New API calls: {new_calls}, Total cached: {len(cache)}")
    return cache


def build_display_data(articles: list[dict], summaries: dict) -> dict:
    """Merge articles with their summaries and group by category.
    Returns dict[category] = {"news": {"articles": [...], "email": [...]},
                              "funding": {"scraped": [...], "email": []}}
    """
    grouped = {cat: {"news": {"articles": [], "email": []}, "funding": {"scraped": [], "email": []}} for cat in CATEGORIES}

    for article in articles:
        link = article.get("link", "")
        summary = summaries.get(link)
        if not summary:
            continue

        try:
            key_points_en = json.loads(summary.get("key_points_en", "[]"))
        except (json.JSONDecodeError, TypeError):
            key_points_en = []

        try:
            key_points_de = json.loads(summary.get("key_points_de", "[]"))
        except (json.JSONDecodeError, TypeError):
            key_points_de = []

        try:
            locations = json.loads(summary.get("locations", "[]"))
        except (json.JSONDecodeError, TypeError):
            locations = []

        valid_urgencies = {"high", "medium", "low"}
        raw_urgency = summary.get("urgency", "").strip().lower()
        urgency = raw_urgency if raw_urgency in valid_urgencies else "low"

        card = {
            "content_type": "news",
            "title": article.get("title", ""),
            "title_en": summary.get("title_en", "") or article.get("title", ""),
            "title_de": summary.get("title_de", "") or article.get("title", ""),
            "link": link,
            "source": article.get("source", ""),
            "published_date": article.get("published_date", ""),
            "gist_en": summary.get("gist_en", ""),
            "gist_de": summary.get("gist_de", ""),
            "key_points_en": key_points_en,
            "key_points_de": key_points_de,
            "locations": locations,
            "category": summary.get("category", "Uncategorized"),
            "urgency": urgency,
            "urgency_reason": summary.get("urgency_reason", ""),
            "contact_email": summary.get("contact_email", ""),
            "contact_phone": summary.get("contact_phone", ""),
            "detected_language": summary.get("detected_language", ""),
            "sub_tab": "articles",
        }

        category = card["category"]
        if category not in grouped:
            category = "Uncategorized"
        grouped[category]["news"]["articles"].append(card)

    return grouped


# ---------------------------------------------------------------------------
# Email ingestion & summarization
# ---------------------------------------------------------------------------

def load_email_articles() -> list[dict]:
    """Load email-sourced articles from alert_articles.csv."""
    articles = []
    if not os.path.exists(EMAIL_ARTICLES_CSV):
        return articles
    with open(EMAIL_ARTICLES_CSV, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            articles.append(row)
    return articles


def load_email_summaries_cache() -> dict:
    """Load existing email summaries keyed by link."""
    cache = {}
    if not os.path.exists(EMAIL_SUMMARIES_CSV):
        return cache
    with open(EMAIL_SUMMARIES_CSV, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            cache[row["link"]] = row
    return cache


def save_email_summaries_cache(cache: dict):
    """Write the email summaries cache to CSV."""
    if not cache:
        return
    fieldnames = [
        "link", "classified_type", "title_en", "title_de",
        "gist_en", "gist_de", "key_points_en", "key_points_de",
        "locations", "category", "urgency", "urgency_reason",
        "contact_email", "contact_phone", "detected_language",
        "summary_en", "summary_de", "deadline", "amount",
        "eligibility_en", "eligibility_de",
    ]
    with open(EMAIL_SUMMARIES_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in cache.values():
            writer.writerow({k: row.get(k, "") for k in fieldnames})


EMAIL_SYSTEM_PROMPT = """You are a press review assistant for two NGOs (WTG for animal welfare, Burundikids for Burundi development).
You will be given the full text of one article sourced from an email alert. It may be news or a funding opportunity.
First, classify it as "news" or "funding". Then extract the appropriate fields.

Respond with ONLY a JSON object in this exact structure, no other text:
{
  "content_type": "news or funding",
  "title_en": "the article title translated into English",
  "title_de": "the article title translated into German",
  "gist_en": "1-2 sentence English summary (always provided regardless of type)",
  "gist_de": "1-2 sentence German summary (always provided regardless of type)",
  "key_points_en": ["point 1", "point 2", "point 3"],
  "key_points_de": ["Punkt 1", "Punkt 2", "Punkt 3"],
  "locations": ["places mentioned"],
  "category": "one of the valid category strings",
  "urgency": "high | medium | low",
  "urgency_reason": "one short sentence",
  "contact_email": "a specific contact email if literally stated, or null",
  "contact_phone": "a specific contact phone if literally stated, or null",
  "detected_language": "the original language of the article, e.g. French, English, German",
  "deadline": "YYYY-MM-DD if this is a funding opportunity with a deadline, or null",
  "amount": "funding amount if stated, or null",
  "summary_en": "1-2 sentence English summary of what funding supports (only for funding type, null for news)",
  "summary_de": "1-2 sentence German summary of what funding supports (only for funding type, null for news)",
  "eligibility_en": ["eligibility bullet 1", "bullet 2"],
  "eligibility_de": ["Förderfähigkeit Punkt 1", "Punkt 2"]
}

Classification rules:
- "funding": the article describes a grant, fellowship, award, funding call, or financial opportunity that organizations could apply for.
- "news": everything else (reports, events, crises, policy changes, general coverage).

Valid categories: "Mobile Veterinary Support", "Stray Population Infrastructure", "Wildlife Trade Defenses", "Emergency Relief Hub", "Bildung", "Gesundheit", "Kinder- und Frauenrechte", "Kommunale Entwicklung und Umweltschutz", "Uncategorized"

Urgency rules: Default to "low". "high" only for active acute crises. "medium" for meaningful developments. Most should be "low" or "medium".

Contact extraction: Only populate contact_email/contact_phone if literally stated in text. Never infer. Use null if not given.

For news-type articles: deadline, amount, summary_en, summary_de, eligibility_en, eligibility_de should all be null/empty.
For funding-type articles: fill in deadline, amount, summary_en/de, eligibility_en/de as available."""


def run_email_summarization(articles: list[dict]) -> dict:
    """Summarize email articles in parallel using AWS Bedrock (Nova)."""
    cache = load_email_summaries_cache()

    to_process = []
    for article in articles:
        link = article.get("link", "")
        if link in cache:
            continue
        full_text = article.get("full_text", "")
        if not full_text.strip():
            continue
        to_process.append(article)

    print(f"[INFO] Email articles total: {len(articles)}, cached: {len(cache)}, to process: {len(to_process)}")

    if not to_process:
        print("[INFO] All email articles already summarized.")
        return cache

    def process_one_email(article: dict) -> tuple[str, dict | None]:
        link = article.get("link", "")
        full_text = article.get("full_text", "")
        if not full_text or not full_text.strip():
            return (link, None)
        try:
            content = llm_chat(
                system_prompt=EMAIL_SYSTEM_PROMPT,
                user_prompt=full_text[:12000],
                temperature=0.3,
                max_tokens=1024,
                json_mode=True,
            )
            if not content:
                return (link, None)
            result = json.loads(content)
        except Exception as e:
            print(f"[WARNING] LLM call failed for {link[:50]}: {e}")
            return (link, None)

        # Validate
        valid_urgencies = {"high", "medium", "low"}
        urgency = result.get("urgency", "").strip().lower()
        urgency = urgency if urgency in valid_urgencies else "low"

        classified = result.get("content_type", "news").strip().lower()
        if classified not in ("news", "funding"):
            classified = "news"

        row = {
            "link": link,
            "classified_type": classified,
            "title_en": result.get("title_en", ""),
            "title_de": result.get("title_de", ""),
            "gist_en": result.get("gist_en", ""),
            "gist_de": result.get("gist_de", ""),
            "key_points_en": json.dumps(result.get("key_points_en", [])),
            "key_points_de": json.dumps(result.get("key_points_de", [])),
            "locations": json.dumps(result.get("locations", [])),
            "category": result.get("category", "Uncategorized"),
            "urgency": urgency,
            "urgency_reason": result.get("urgency_reason", ""),
            "contact_email": result.get("contact_email") or "",
            "contact_phone": result.get("contact_phone") or "",
            "detected_language": result.get("detected_language") or "",
            "summary_en": result.get("summary_en") or "",
            "summary_de": result.get("summary_de") or "",
            "deadline": result.get("deadline") or "",
            "amount": result.get("amount") or "",
            "eligibility_en": json.dumps(result.get("eligibility_en", [])),
            "eligibility_de": json.dumps(result.get("eligibility_de", [])),
        }
        return (link, row)

    new_calls = 0
    lock = threading.Lock()

    print(f"[INFO] Summarizing {len(to_process)} email articles with 10 parallel workers (AWS Bedrock)...")

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {}
        for article in to_process:
            future = executor.submit(process_one_email, article)
            futures[future] = article.get("title", "")[:50]

        for future in as_completed(futures):
            title = futures[future]
            try:
                link, row = future.result()
                if row:
                    with lock:
                        cache[link] = row
                        new_calls += 1
                    print(f"  [OK] {title}")
                else:
                    print(f"  [SKIP] {title} (no result)")
            except Exception as e:
                print(f"  [ERROR] {title}: {e}")

    save_email_summaries_cache(cache)
    print(f"[INFO] Email summarization complete. New: {new_calls}, Total cached: {len(cache)}")
    return cache


def build_email_cards(email_articles: list[dict], email_summaries: dict) -> tuple[list[dict], list[dict]]:
    """Build display cards for email-sourced articles.
    Returns (news_cards, funding_cards) split by classified_type.
    """
    news_cards = []
    funding_cards = []

    for article in email_articles:
        link = article.get("link", "")
        summary = email_summaries.get(link)
        if not summary:
            continue

        try:
            key_points_en = json.loads(summary.get("key_points_en", "[]"))
        except (json.JSONDecodeError, TypeError):
            key_points_en = []
        try:
            key_points_de = json.loads(summary.get("key_points_de", "[]"))
        except (json.JSONDecodeError, TypeError):
            key_points_de = []
        try:
            locations = json.loads(summary.get("locations", "[]"))
        except (json.JSONDecodeError, TypeError):
            locations = []

        valid_urgencies = {"high", "medium", "low"}
        raw_urgency = summary.get("urgency", "").strip().lower()
        urgency = raw_urgency if raw_urgency in valid_urgencies else "low"

        classified = summary.get("classified_type", "news").strip().lower()

        if classified == "funding":
            try:
                eligibility_en = json.loads(summary.get("eligibility_en", "[]"))
            except (json.JSONDecodeError, TypeError):
                eligibility_en = []
            try:
                eligibility_de = json.loads(summary.get("eligibility_de", "[]"))
            except (json.JSONDecodeError, TypeError):
                eligibility_de = []

            card = {
                "content_type": "funding",
                "title": article.get("title", ""),
                "title_en": summary.get("title_en", "") or article.get("title", ""),
                "title_de": summary.get("title_de", "") or article.get("title", ""),
                "link": link,
                "source": article.get("source", ""),
                "alert_topic": article.get("alert_topic", ""),
                "summary_en": summary.get("summary_en", "") or summary.get("gist_en", ""),
                "summary_de": summary.get("summary_de", "") or summary.get("gist_de", ""),
                "deadline": summary.get("deadline", ""),
                "amount": summary.get("amount", ""),
                "eligibility_en": eligibility_en,
                "eligibility_de": eligibility_de,
                "locations": locations,
                "category": summary.get("category", "Uncategorized"),
                "urgency": urgency,
                "contact_email": summary.get("contact_email", ""),
                "contact_phone": summary.get("contact_phone", ""),
                "sub_tab": "email",
            }
            funding_cards.append(card)
        else:
            card = {
                "content_type": "email",
                "title": article.get("title", ""),
                "title_en": summary.get("title_en", "") or article.get("title", ""),
                "title_de": summary.get("title_de", "") or article.get("title", ""),
                "link": link,
                "source": article.get("source", ""),
                "alert_topic": article.get("alert_topic", ""),
                "published_date": article.get("published_date", ""),
                "gist_en": summary.get("gist_en", ""),
                "gist_de": summary.get("gist_de", ""),
                "key_points_en": key_points_en,
                "key_points_de": key_points_de,
                "locations": locations,
                "category": summary.get("category", "Uncategorized"),
                "urgency": urgency,
                "urgency_reason": summary.get("urgency_reason", ""),
                "contact_email": summary.get("contact_email", ""),
                "contact_phone": summary.get("contact_phone", ""),
                "detected_language": summary.get("detected_language", ""),
                "sub_tab": "email",
            }
            news_cards.append(card)

    return news_cards, funding_cards


def merge_email_into_grouped(grouped: dict, email_news_cards: list[dict], email_funding_cards: list[dict]):
    """Add email cards into the appropriate grouped sub-lists."""
    for card in email_news_cards:
        category = card.get("category", "Uncategorized")
        if category not in grouped:
            category = "Uncategorized"
        grouped[category]["news"]["email"].append(card)

    for card in email_funding_cards:
        category = card.get("category", "Uncategorized")
        if category not in grouped:
            category = "Uncategorized"
        grouped[category]["funding"]["email"].append(card)


def load_funding_data() -> list[dict]:
    """Load funding opportunities and their summaries, join by link.
    Returns a list of funding card dicts ready for display.
    """
    # Load funding opportunities (source, title, link, raw_text)
    opportunities = {}
    if os.path.exists(FUNDING_CSV):
        with open(FUNDING_CSV, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                opportunities[row.get("link", "")] = row

    # Load funding summaries (link, summary, deadline, amount, eligibility, category, locations, urgency)
    summaries = {}
    if os.path.exists(FUNDING_SUMMARIES_CSV):
        with open(FUNDING_SUMMARIES_CSV, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                summaries[row.get("link", "")] = row

    cards = []
    for link, summary in summaries.items():
        urgency = summary.get("urgency", "undefined").strip().lower()

        # Filter out expired funding
        if urgency == "expired":
            continue

        opp = opportunities.get(link, {})

        try:
            eligibility_en = json.loads(summary.get("eligibility_en", "[]"))
        except (json.JSONDecodeError, TypeError):
            eligibility_en = []

        try:
            eligibility_de = json.loads(summary.get("eligibility_de", "[]"))
        except (json.JSONDecodeError, TypeError):
            eligibility_de = []

        try:
            locations = json.loads(summary.get("locations", "[]"))
        except (json.JSONDecodeError, TypeError):
            locations = []

        card = {
            "content_type": "funding",
            "title": opp.get("title", "") or summary.get("link", ""),
            "link": link,
            "source": opp.get("source", ""),
            "summary_en": summary.get("summary_en", ""),
            "summary_de": summary.get("summary_de", ""),
            "deadline": summary.get("deadline", ""),
            "amount": summary.get("amount", ""),
            "eligibility_en": eligibility_en,
            "eligibility_de": eligibility_de,
            "locations": locations,
            "category": summary.get("category", "Uncategorized"),
            "urgency": urgency,
            "contact_email": summary.get("contact_email", ""),
            "contact_phone": summary.get("contact_phone", ""),
            "sub_tab": "scraped",
        }
        cards.append(card)

    return cards


def _parse_amount_for_sort(amount_str: str) -> float:
    """Extract the largest numeric value from an amount string for sorting.
    Returns 0.0 if unparseable.
    """
    if not amount_str:
        return 0.0
    # Find all numbers (with optional dots/commas as thousands/decimal separators)
    numbers = re.findall(r"[\d.,]+", amount_str)
    max_val = 0.0
    for num_str in numbers:
        # Normalize: remove thousands separators, handle comma as decimal
        cleaned = num_str.replace(".", "").replace(",", ".")
        try:
            val = float(cleaned)
            if val > max_val:
                max_val = val
        except ValueError:
            continue
    return max_val


def sort_funding_cards(cards: list[dict]) -> list[dict]:
    """Sort funding cards: primary by urgency tier, secondary by amount descending."""
    urgency_order = {"high": 0, "medium": 1, "low": 2, "undefined": 3}

    def sort_key(card):
        tier = urgency_order.get(card.get("urgency", "undefined"), 3)
        amount = _parse_amount_for_sort(card.get("amount", ""))
        # Negate amount for descending sort; unparseable (0.0) sorts last within tier
        return (tier, -amount if amount > 0 else float("inf"))

    return sorted(cards, key=sort_key)


def merge_funding_into_grouped(grouped: dict, funding_cards: list[dict]):
    """Add funding cards into the grouped structure, sorted appropriately."""
    for card in funding_cards:
        category = card.get("category", "Uncategorized")
        if category not in grouped:
            category = "Uncategorized"
        grouped[category]["funding"]["scraped"].append(card)

    # Sort funding within each category
    for cat in grouped:
        grouped[cat]["funding"]["scraped"] = sort_funding_cards(grouped[cat]["funding"]["scraped"])


def build_map_markers(grouped: dict) -> list[dict]:
    """Build a list of unique locations with their max urgency for the map."""

    # -----------------------------------------------------------------------
    # Country centroids (~195 countries) — lowercase name → [lat, lng]
    # -----------------------------------------------------------------------
    COUNTRY_CENTROIDS = {
        "afghanistan": [33.94, 67.71], "albania": [41.15, 20.17],
        "algeria": [28.03, 1.66], "andorra": [42.55, 1.60],
        "angola": [-11.20, 17.87], "antigua and barbuda": [17.06, -61.80],
        "argentina": [-38.42, -63.62], "armenia": [40.07, 45.04],
        "australia": [-25.27, 133.78], "austria": [47.52, 14.55],
        "azerbaijan": [40.14, 47.58], "bahamas": [25.03, -77.40],
        "bahrain": [26.07, 50.56], "bangladesh": [23.68, 90.36],
        "barbados": [13.19, -59.54], "belarus": [53.71, 27.95],
        "belgium": [50.50, 4.47], "belize": [17.19, -88.50],
        "benin": [9.31, 2.32], "bhutan": [27.51, 90.43],
        "bolivia": [-16.29, -63.59], "bosnia and herzegovina": [43.92, 17.68],
        "botswana": [-22.33, 24.68], "brazil": [-14.24, -51.93],
        "brunei": [4.54, 114.73], "bulgaria": [42.73, 25.49],
        "burkina faso": [12.24, -1.56], "burundi": [-3.37, 29.92],
        "cabo verde": [16.00, -24.01], "cambodia": [12.57, 104.99],
        "cameroon": [7.37, 12.35], "canada": [56.13, -106.35],
        "central african republic": [6.61, 20.94],
        "chad": [15.45, 18.73], "chile": [-35.68, -71.54],
        "china": [35.86, 104.20], "colombia": [4.57, -74.30],
        "comoros": [-11.88, 43.87], "congo": [-0.23, 15.83],
        "republic of the congo": [-0.23, 15.83],
        "costa rica": [9.75, -83.75], "croatia": [45.10, 15.20],
        "cuba": [21.52, -77.78], "cyprus": [35.13, 33.43],
        "czech republic": [49.82, 15.47], "czechia": [49.82, 15.47],
        "democratic republic of the congo": [-4.04, 21.76],
        "drc": [-4.04, 21.76], "dr congo": [-4.04, 21.76],
        "denmark": [56.26, 9.50], "djibouti": [11.83, 42.59],
        "dominica": [15.41, -61.37], "dominican republic": [18.74, -70.16],
        "ecuador": [-1.83, -78.18], "egypt": [26.82, 30.80],
        "el salvador": [13.79, -88.90], "equatorial guinea": [1.65, 10.27],
        "eritrea": [15.18, 39.78], "estonia": [58.60, 25.01],
        "eswatini": [-26.52, 31.47], "ethiopia": [9.15, 40.49],
        "fiji": [-17.71, 178.07], "finland": [61.92, 25.75],
        "france": [46.23, 2.21], "gabon": [-0.80, 11.61],
        "gambia": [13.44, -15.31], "georgia": [42.32, 43.36],
        "germany": [51.17, 10.45], "ghana": [7.95, -1.02],
        "greece": [39.07, 21.82], "grenada": [12.12, -61.68],
        "guatemala": [15.78, -90.23], "guinea": [9.95, -9.70],
        "guinea-bissau": [11.80, -15.18], "guyana": [4.86, -58.93],
        "haiti": [18.97, -72.29], "honduras": [15.20, -86.24],
        "hungary": [47.16, 19.50], "iceland": [64.96, -19.02],
        "india": [20.59, 78.96], "indonesia": [-0.79, 113.92],
        "iran": [32.43, 53.69], "iraq": [33.22, 43.68],
        "ireland": [53.14, -7.69], "israel": [31.05, 34.85],
        "italy": [41.87, 12.57], "ivory coast": [7.54, -5.55],
        "cote d'ivoire": [7.54, -5.55],
        "jamaica": [18.11, -77.30], "japan": [36.20, 138.25],
        "jordan": [30.59, 36.24], "kazakhstan": [48.02, 66.92],
        "kenya": [-0.02, 37.91], "kiribati": [-3.37, -168.73],
        "kosovo": [42.60, 20.90], "kuwait": [29.31, 47.48],
        "kyrgyzstan": [41.20, 74.77], "laos": [19.86, 102.50],
        "latvia": [56.88, 24.60], "lebanon": [33.85, 35.86],
        "lesotho": [-29.61, 28.23], "liberia": [6.43, -9.43],
        "libya": [26.34, 17.23], "liechtenstein": [47.17, 9.56],
        "lithuania": [55.17, 23.88], "luxembourg": [49.82, 6.13],
        "madagascar": [-18.77, 46.87], "malawi": [-13.25, 34.30],
        "malaysia": [4.21, 101.98], "maldives": [3.20, 73.22],
        "mali": [17.57, -4.00], "malta": [35.94, 14.38],
        "marshall islands": [7.13, 171.18], "mauritania": [21.01, -10.94],
        "mauritius": [-20.35, 57.55], "mexico": [23.63, -102.55],
        "micronesia": [7.43, 150.55], "moldova": [47.41, 28.37],
        "monaco": [43.75, 7.41], "mongolia": [46.86, 103.85],
        "montenegro": [42.71, 19.37], "morocco": [31.79, -7.09],
        "mozambique": [-18.67, 35.53], "myanmar": [21.91, 95.96],
        "namibia": [-22.96, 18.49], "nauru": [-0.52, 166.93],
        "nepal": [28.39, 84.12], "netherlands": [52.13, 5.29],
        "new zealand": [-40.90, 174.89], "nicaragua": [12.87, -85.21],
        "niger": [17.61, 8.08], "nigeria": [9.08, 8.68],
        "north korea": [40.34, 127.51], "north macedonia": [41.51, 21.75],
        "norway": [60.47, 8.47], "oman": [21.47, 55.98],
        "pakistan": [30.38, 69.35], "palau": [7.51, 134.58],
        "palestine": [31.95, 35.23], "panama": [8.54, -80.78],
        "papua new guinea": [-6.31, 143.96], "paraguay": [-23.44, -58.44],
        "peru": [-9.19, -75.02], "philippines": [12.88, 121.77],
        "poland": [51.92, 19.15], "portugal": [39.40, -8.22],
        "qatar": [25.35, 51.18], "romania": [45.94, 24.97],
        "russia": [61.52, 105.32], "rwanda": [-1.94, 29.87],
        "saint kitts and nevis": [17.36, -62.78],
        "saint lucia": [13.91, -60.98],
        "saint vincent and the grenadines": [12.98, -61.29],
        "samoa": [-13.76, -172.10], "san marino": [43.94, 12.46],
        "sao tome and principe": [0.19, 6.61],
        "saudi arabia": [23.89, 45.08], "senegal": [14.50, -14.45],
        "serbia": [44.02, 21.01], "seychelles": [-4.68, 55.49],
        "sierra leone": [8.46, -11.78], "singapore": [1.35, 103.82],
        "slovakia": [48.67, 19.70], "slovenia": [46.15, 14.99],
        "solomon islands": [-9.65, 160.16], "somalia": [5.15, 46.20],
        "south africa": [-30.56, 22.94], "south korea": [35.91, 127.77],
        "south sudan": [6.88, 31.31], "spain": [40.46, -3.75],
        "sri lanka": [7.87, 80.77], "sudan": [12.86, 30.22],
        "suriname": [3.92, -56.03], "sweden": [60.13, 18.64],
        "switzerland": [46.82, 8.23], "syria": [34.80, 38.99],
        "taiwan": [23.70, 120.96], "tajikistan": [38.86, 71.28],
        "tanzania": [-6.37, 34.89], "thailand": [15.87, 100.99],
        "timor-leste": [-8.87, 125.73], "togo": [8.62, 1.21],
        "tonga": [-21.18, -175.20], "trinidad and tobago": [10.69, -61.22],
        "tunisia": [33.89, 9.54], "turkey": [38.96, 35.24],
        "turkmenistan": [38.97, 59.56], "tuvalu": [-7.11, 177.65],
        "uganda": [1.37, 32.29], "ukraine": [48.38, 31.17],
        "united arab emirates": [23.42, 53.85], "uae": [23.42, 53.85],
        "united kingdom": [55.38, -3.44], "uk": [55.38, -3.44],
        "united states": [37.09, -95.71], "usa": [37.09, -95.71],
        "us": [37.09, -95.71],
        "uruguay": [-32.52, -55.77], "uzbekistan": [41.38, 64.59],
        "vanuatu": [-15.38, 166.96], "vatican city": [41.90, 12.45],
        "venezuela": [6.42, -66.59], "vietnam": [14.06, 108.28],
        "yemen": [15.55, 48.52], "zambia": [-13.13, 27.85],
        "zimbabwe": [-19.02, 29.15],
        # Continent-level fallbacks
        "africa": [0.0, 20.0], "europe": [54.53, 15.26],
        "asia": [34.05, 100.62], "south america": [-8.78, -55.49],
        "north america": [54.53, -105.26],
    }

    # Burundi provinces and major cities — higher precision overrides
    BURUNDI_OVERRIDES = {
        "bujumbura": [-3.3614, 29.3599],
        "gitega": [-3.4264, 29.9246],
        "ngozi": [-2.9075, 29.8306],
        "rumonge": [-3.9736, 29.4386],
        "makamba": [-4.1347, 29.8040],
        "muyinga": [-2.8453, 30.3414],
        "kayanza": [-2.9222, 29.6286],
        "cibitoke": [-2.8869, 29.1242],
        "bubanza": [-3.0784, 29.3917],
        "kirundo": [-2.5847, 30.0958],
        "muramvya": [-3.2681, 29.6078],
        "rutana": [-3.9281, 29.9919],
        "ruyigi": [-3.4764, 30.2486],
        "cankuzo": [-3.2194, 30.5528],
        "karuzi": [-3.1042, 29.9833],
        "mwaro": [-3.5167, 29.7000],
        "bururi": [-3.9489, 29.6244],
        "bujumbura mairie": [-3.3614, 29.3599],
        "bujumbura rural": [-3.3300, 29.4600],
    }

    # Other well-known cities for common matches
    CITY_OVERRIDES = {
        "nairobi": [-1.2921, 36.8219],
        "kigali": [-1.9403, 29.8739],
        "kinshasa": [-4.4419, 15.2663],
        "dar es salaam": [-6.7924, 39.2083],
        "kampala": [0.3476, 32.5825],
        "addis ababa": [9.0250, 38.7469],
        "johannesburg": [-26.2041, 28.0473],
        "cape town": [-33.9249, 18.4241],
        "lagos": [6.5244, 3.3792],
        "accra": [5.6037, -0.1870],
        "dakar": [14.7167, -17.4677],
        "abuja": [9.0579, 7.4951],
        "cairo": [30.0444, 31.2357],
        "tunis": [36.8065, 10.1815],
        "algiers": [36.7538, 3.0588],
        "rabat": [34.0209, -6.8416],
        "lusaka": [-15.3875, 28.3228],
        "harare": [-17.8252, 31.0335],
        "maputo": [-25.9692, 32.5732],
        "lilongwe": [-13.9626, 33.7741],
        "mogadishu": [2.0469, 45.3182],
        "berlin": [52.5200, 13.4050],
        "paris": [48.8566, 2.3522],
        "london": [51.5074, -0.1278],
        "brussels": [50.8503, 4.3517],
        "geneva": [46.2044, 6.1432],
        "new york": [40.7128, -74.0060],
        "washington": [38.9072, -77.0369],
        "bonn": [50.7374, 7.0982],
    }

    # Merge into one lookup: overrides take priority
    LOCATION_COORDS = {**COUNTRY_CENTROIDS, **CITY_OVERRIDES, **BURUNDI_OVERRIDES}

    urgency_rank = {"high": 3, "medium": 2, "low": 1}
    location_data = {}  # location_name -> {"urgency": str, "cards": [...]}

    for category, sections in grouped.items():
        # Collect all cards from the nested structure
        all_cards = (
            sections.get("news", {}).get("articles", []) +
            sections.get("news", {}).get("email", []) +
            sections.get("funding", {}).get("scraped", []) +
            sections.get("funding", {}).get("email", [])
        )
        for card in all_cards:
            for loc in card.get("locations", []):
                loc_lower = loc.lower().strip()
                if loc_lower not in location_data:
                    location_data[loc_lower] = {"urgency": "low", "cards": []}

                # Update max urgency
                current = location_data[loc_lower]["urgency"]
                if urgency_rank.get(card.get("urgency", ""), 0) > urgency_rank.get(current, 0):
                    location_data[loc_lower]["urgency"] = card["urgency"]

                # Add card reference for popup
                gist = card.get("gist_en") or card.get("summary_en") or ""
                location_data[loc_lower]["cards"].append({
                    "title": card.get("title", "")[:80],
                    "gist": gist[:120],
                    "category": card.get("category", ""),
                    "content_type": card.get("content_type", ""),
                    "urgency": card.get("urgency", "low"),
                    "dom_id": card.get("dom_id", ""),
                    "sub_tab": card.get("sub_tab", "articles"),
                })

    markers = []
    for loc, data in location_data.items():
        coords = LOCATION_COORDS.get(loc)
        if not coords:
            # Try partial match
            for key, val in LOCATION_COORDS.items():
                if key in loc or loc in key:
                    coords = val
                    break
        if coords:
            # Sort cards by urgency descending
            sorted_cards = sorted(
                data["cards"],
                key=lambda c: urgency_rank.get(c["urgency"], 0),
                reverse=True,
            )
            markers.append({
                "name": loc.title(),
                "lat": coords[0],
                "lng": coords[1],
                "urgency": data["urgency"],
                "cards": sorted_cards[:10],  # Cap at 10 to keep JSON manageable
            })

    return markers


# ---------------------------------------------------------------------------
# Flask App
# ---------------------------------------------------------------------------
app = Flask(__name__, template_folder=str(_HERE / "templates"))


@app.route("/")
def index():
    articles = load_articles()
    summaries = load_summaries_cache()
    grouped = build_display_data(articles, summaries)

    # Load and merge funding data
    funding_cards = load_funding_data()
    merge_funding_into_grouped(grouped, funding_cards)

    # Load and merge email data
    email_articles = load_email_articles()
    email_summaries = load_email_summaries_cache()
    email_news_cards, email_funding_cards = build_email_cards(email_articles, email_summaries)
    merge_email_into_grouped(grouped, email_news_cards, email_funding_cards)

    # Assign stable dom_id to every card for JS navigation
    for cat_idx, cat in enumerate(CATEGORIES):
        for i, card in enumerate(grouped[cat]["news"]["articles"]):
            card["dom_id"] = f"card-news-{cat_idx}-{i}"
        for i, card in enumerate(grouped[cat]["news"]["email"]):
            card["dom_id"] = f"card-email-{cat_idx}-{i}"
        for i, card in enumerate(grouped[cat]["funding"]["scraped"]):
            card["dom_id"] = f"card-funding-{cat_idx}-{i}"
        for i, card in enumerate(grouped[cat]["funding"]["email"]):
            card["dom_id"] = f"card-fundemail-{cat_idx}-{i}"

    markers = build_map_markers(grouped)

    # Compute counts per category for each sub-section
    news_article_counts = {cat: len(grouped[cat]["news"]["articles"]) for cat in CATEGORIES}
    news_email_counts = {cat: len(grouped[cat]["news"]["email"]) for cat in CATEGORIES}
    funding_scraped_counts = {cat: len(grouped[cat]["funding"]["scraped"]) for cat in CATEGORIES}
    funding_email_counts = {cat: len(grouped[cat]["funding"]["email"]) for cat in CATEGORIES}

    return render_template(
        "index.html",
        grouped=grouped,
        categories=CATEGORIES,
        markers=markers,
        news_article_counts=news_article_counts,
        news_email_counts=news_email_counts,
        funding_scraped_counts=funding_scraped_counts,
        funding_email_counts=funding_email_counts,
    )


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("[INFO] Loading articles and running summarization...")
    articles = load_articles()
    if articles:
        run_summarization(articles)
    else:
        print("[INFO] No articles found. Run ingest.py first to populate articles.csv.")

    # Email summarization
    email_articles = load_email_articles()
    if email_articles:
        print("[INFO] Running email article summarization...")
        run_email_summarization(email_articles)
    else:
        print("[INFO] No email articles found (alert_articles.csv missing or empty).")

    print("[INFO] Starting Flask server on http://127.0.0.1:5000")
    app.run(debug=True, host="127.0.0.1", port=5000)
