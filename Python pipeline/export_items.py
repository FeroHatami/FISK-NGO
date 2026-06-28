"""
export_items.py – Export all pipeline data as JSON for the Lovable frontend.
Run with: python export_items.py
"""

import csv, json, os, sys
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from app import (
    CATEGORIES, build_display_data, build_email_cards, load_articles,
    load_email_articles, load_email_summaries_cache, load_funding_data,
    load_summaries_cache, merge_email_into_grouped, merge_funding_into_grouped,
)

OUTPUT_DIR = Path(__file__).parent.parent / "Loveable pipeline" / "data"
OUTPUT_FILE = OUTPUT_DIR / "items.json"

# CSV paths (same as app.py)
ARTICLES_CSV = Path(__file__).parent / "articles.csv"
EMAIL_ARTICLES_CSV = Path(__file__).parent / "alert_articles.csv"
FUNDING_CSV = Path(__file__).parent / "funding_opportunities.csv"

EAST_AFRICA = {
    "kenya","rwanda","tanzania","uganda","ethiopia","south sudan",
    "sudan","somalia","djibouti","eritrea","drc","dr congo","congo",
    "democratic republic of the congo",
}
BURUNDI_LOCS = {
    "burundi","bujumbura","gitega","ngozi","rumonge","makamba","muyinga",
    "kayanza","cibitoke","bubanza","kirundo","muramvya","rutana","ruyigi",
    "cankuzo","karuzi","mwaro","bururi",
}
GERMANY_LOCS = {"germany","berlin","bonn","munich","hamburg","frankfurt"}
INDIA_LOCS = {"india","mumbai","delhi","new delhi","kolkata","chennai","bangalore","hyderabad"}
THAILAND_LOCS = {"thailand","bangkok","chiang mai","phuket"}
MALAWI_LOCS = {"malawi","lilongwe","blantyre"}
INDONESIA_LOCS = {"indonesia","jakarta","bali","sumatra","borneo","java","sulawesi"}

def bucket_region(location):
    loc = location.strip().lower()
    if loc in BURUNDI_LOCS: return "Burundi"
    if loc in GERMANY_LOCS: return "Germany"
    if loc in EAST_AFRICA: return "East Africa"
    if loc in INDIA_LOCS: return "India"
    if loc in THAILAND_LOCS: return "Thailand"
    if loc in MALAWI_LOCS: return "Malawi"
    if loc in INDONESIA_LOCS: return "Indonesia"
    return "Global"

def regions_from_locations(locations):
    return sorted(set(bucket_region(l) for l in locations)) if locations else ["Global"]

def map_priority(urgency):
    if urgency == "high": return "high"
    if urgency == "medium": return "med"
    return "low"

# ---------------------------------------------------------------------------
# Robust date parsing
# ---------------------------------------------------------------------------

def _parse_date_string(date_str):
    """Try to parse a date string using multiple strategies.
    Returns a timezone-aware datetime or None if all attempts fail.
    """
    if not date_str or not date_str.strip():
        return None
    s = date_str.strip()

    # Strategy 1: RFC 2822 (e.g. "Wed, 02 Nov 2022 10:57:56 +0000")
    try:
        dt = parsedate_to_datetime(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        pass

    # Strategy 2: Plain ISO date "YYYY-MM-DD"
    try:
        d = datetime.strptime(s, "%Y-%m-%d")
        return d.replace(tzinfo=timezone.utc)
    except ValueError:
        pass

    # Strategy 3: ISO datetime (various forms)
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        pass

    # All parsing failed
    print(f"[WARNING] Could not parse date: '{s}'")
    return None


def funding_urgency_bucket(deadline_str):
    """Bucket funding items by days until deadline."""
    dt = _parse_date_string(deadline_str)
    if dt is None:
        return "later"
    dl = dt.date() if hasattr(dt, 'date') else dt
    days = (dl - date.today()).days
    if days <= 3: return "now"
    if days <= 14: return "today"
    if days <= 30: return "this week"
    return "later"


def news_urgency_bucket(published_date_str):
    """Bucket news/email items by how recently they were published."""
    dt = _parse_date_string(published_date_str)
    if dt is None:
        return "later"
    now = datetime.now(timezone.utc)
    hours = (now - dt).total_seconds() / 3600
    if hours < 24: return "now"
    if hours < 48: return "today"
    if hours < 168: return "this week"
    return "later"


def parse_iso_date(date_str):
    """Parse a date string into ISO format for the output JSON."""
    dt = _parse_date_string(date_str)
    if dt is None:
        return datetime.now(timezone.utc).isoformat()
    return dt.isoformat()


# ---------------------------------------------------------------------------
# Source-text lookups (for the "original" field)
# ---------------------------------------------------------------------------

def _load_full_text_lookup():
    """Load full_text from articles.csv keyed by link."""
    lookup = {}
    if ARTICLES_CSV.exists():
        with open(ARTICLES_CSV, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                link = row.get("link", "")
                text = row.get("full_text", "")
                if link and text:
                    lookup[link] = text
    return lookup


def _load_email_full_text_lookup():
    """Load full_text from alert_articles.csv keyed by link."""
    lookup = {}
    if EMAIL_ARTICLES_CSV.exists():
        with open(EMAIL_ARTICLES_CSV, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                link = row.get("link", "")
                text = row.get("full_text", "")
                if link and text:
                    lookup[link] = text
    return lookup


def _load_funding_raw_text_lookup():
    """Load raw_text from funding_opportunities.csv keyed by link."""
    lookup = {}
    if FUNDING_CSV.exists():
        with open(FUNDING_CSV, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                link = row.get("link", "")
                text = row.get("raw_text", "")
                if link and text:
                    lookup[link] = text
    return lookup


# ---------------------------------------------------------------------------
# Item builders
# ---------------------------------------------------------------------------

def build_news_item(card, idx, full_text_lookup):
    link = card.get("link", "")
    original_text = full_text_lookup.get(link, "") or ""
    return {
        "id": f"news-{idx}",
        "priority": map_priority(card.get("urgency","")),
        "urgency": news_urgency_bucket(card.get("published_date","")),
        "timeEstimate": "5 min",
        "type": "news",
        "title": card.get("title_en","") or card.get("title",""),
        "title_de": card.get("title_de","") or card.get("title",""),
        "title_original": card.get("title",""),
        "source": card.get("source",""),
        "link": link,
        "date": parse_iso_date(card.get("published_date","")),
        "topic": [card.get("category","Uncategorized")],
        "region": regions_from_locations(card.get("locations",[])),
        "summary": card.get("gist_en",""),
        "suggestedAction": "Monitor",
        "original": original_text[:500],
        "translation": card.get("gist_en",""),
        "translation_de": card.get("gist_de",""),
        "contact_email": card.get("contact_email") or None,
        "contact_phone": card.get("contact_phone") or None,
        "originalLanguage": card.get("detected_language") or None,
    }

def build_email_item(card, idx, email_full_text_lookup):
    link = card.get("link", "")
    original_text = email_full_text_lookup.get(link, "") or ""
    return {
        "id": f"email-{idx}",
        "priority": map_priority(card.get("urgency","")),
        "urgency": news_urgency_bucket(card.get("published_date","")),
        "timeEstimate": "15 min",
        "type": "email",
        "title": card.get("title_en","") or card.get("title",""),
        "title_de": card.get("title_de","") or card.get("title",""),
        "title_original": card.get("title",""),
        "source": card.get("source",""),
        "link": link,
        "date": parse_iso_date(card.get("published_date","")),
        "topic": [card.get("category","Uncategorized")],
        "region": regions_from_locations(card.get("locations",[])),
        "summary": card.get("gist_en",""),
        "suggestedAction": "Reply",
        "original": original_text[:500],
        "translation": card.get("gist_en",""),
        "translation_de": card.get("gist_de",""),
        "contact_email": card.get("contact_email") or None,
        "contact_phone": card.get("contact_phone") or None,
        "originalLanguage": card.get("detected_language") or None,
        "sender": "Google Alert",
    }

def build_funding_item(card, idx, funding_raw_text_lookup):
    link = card.get("link", "")
    original_text = funding_raw_text_lookup.get(link, "") or ""
    elig = card.get("eligibility_en", [])
    if isinstance(elig, list):
        elig_str = "; ".join(elig)
    else:
        elig_str = str(elig)
    return {
        "id": f"funding-{idx}",
        "priority": map_priority(card.get("urgency","")),
        "urgency": funding_urgency_bucket(card.get("deadline","")),
        "timeEstimate": "2h",
        "type": "funding",
        "title": card.get("title_en","") or card.get("title",""),
        "title_de": card.get("title_de","") or card.get("title",""),
        "title_original": card.get("title",""),
        "source": card.get("source",""),
        "link": link,
        "date": parse_iso_date(card.get("deadline","") or ""),
        "topic": [card.get("category","Uncategorized")],
        "region": regions_from_locations(card.get("locations",[])),
        "summary": card.get("summary_en",""),
        "suggestedAction": "Apply",
        "original": original_text[:500],
        "translation": card.get("summary_en",""),
        "translation_de": card.get("summary_de",""),
        "contact_email": card.get("contact_email") or None,
        "contact_phone": card.get("contact_phone") or None,
        "deadline": card.get("deadline") or None,
        "amount": card.get("amount") or None,
        "eligibility": elig_str or None,
        "fundingOrg": card.get("source",""),
    }

def main():
    # Load source text lookups for the "original" field
    full_text_lookup = _load_full_text_lookup()
    email_full_text_lookup = _load_email_full_text_lookup()
    funding_raw_text_lookup = _load_funding_raw_text_lookup()

    # Load all data using app.py's existing functions
    articles = load_articles()
    summaries = load_summaries_cache()
    grouped = build_display_data(articles, summaries)

    funding_cards = load_funding_data()
    merge_funding_into_grouped(grouped, funding_cards)

    email_articles = load_email_articles()
    email_summaries = load_email_summaries_cache()
    email_news, email_funding = build_email_cards(email_articles, email_summaries)
    merge_email_into_grouped(grouped, email_news, email_funding)

    # Collect all items
    items = []
    news_idx = 0
    email_idx = 0
    funding_idx = 0

    for cat in CATEGORIES:
        # News articles
        for card in grouped[cat]["news"]["articles"]:
            items.append(build_news_item(card, news_idx, full_text_lookup))
            news_idx += 1
        # News from email
        for card in grouped[cat]["news"]["email"]:
            items.append(build_email_item(card, email_idx, email_full_text_lookup))
            email_idx += 1
        # Funding scraped
        for card in grouped[cat]["funding"]["scraped"]:
            items.append(build_funding_item(card, funding_idx, funding_raw_text_lookup))
            funding_idx += 1
        # Funding from email
        for card in grouped[cat]["funding"]["email"]:
            items.append(build_funding_item(card, funding_idx, funding_raw_text_lookup))
            funding_idx += 1

    # Write output
    OUTPUT_DIR.mkdir(exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

    # Print summary with urgency distribution
    print(f"[INFO] Exported {len(items)} items to {OUTPUT_FILE}")
    print(f"       News: {news_idx}, Email: {email_idx}, Funding: {funding_idx}")

    # Show urgency distribution for verification
    urgency_counts = {"now": 0, "today": 0, "this week": 0, "later": 0}
    for item in items:
        bucket = item.get("urgency", "later")
        urgency_counts[bucket] = urgency_counts.get(bucket, 0) + 1
    print(f"       Urgency distribution: {urgency_counts}")


if __name__ == "__main__":
    main()
