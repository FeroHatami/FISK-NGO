"""
ingest_funding.py – Scrape funding opportunity listings from two sources
and write them to funding_opportunities.csv.

Source 1: Förderdatenbank Entwicklungsländer (JSON embedded in HTML attribute)
Source 2: Förderkompass (structured bullet lists with German labels)

Run with: python ingest_funding.py
"""

import csv
import json
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

_HERE = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Source list: add more (source_name, url) tuples as needed.
# ---------------------------------------------------------------------------
SOURCES = [
    ("Förderdatenbank Entwicklungsländer", "https://wirtschaft-entwicklung.de/digitale-services/foerderdatenbank-entwicklungslaender"),
    ("Förderkompass", "https://www.zerowasteagentur.de/foerderkompass.html"),
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

REQUEST_TIMEOUT = 30  # seconds
DELAY_BETWEEN_REQUESTS = 1  # seconds
OUTPUT_CSV = str(_HERE / "funding_opportunities.csv")


def fetch_page(url: str) -> BeautifulSoup | None:
    """Fetch a URL and return a BeautifulSoup object, or None on failure."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return BeautifulSoup(response.content, "html.parser")
    except Exception as e:
        print(f"[WARNING] Failed to fetch {url}: {e}")
        return None


# ---------------------------------------------------------------------------
# Source 1: Förderdatenbank Entwicklungsländer
# ---------------------------------------------------------------------------

def scrape_foerderdatenbank(source_name: str, url: str) -> list[dict]:
    """
    The page embeds its full dataset as JSON inside the data-projects
    attribute of a <div class="awedb-database"> element.
    """
    listings = []
    soup = fetch_page(url)
    if not soup:
        return listings

    # Find the div with embedded JSON data
    db_div = soup.find("div", class_="awedb-database")
    if not db_div:
        print(f"[WARNING] {source_name}: could not find div.awedb-database")
        return listings

    data_attr = db_div.get("data-projects", "")
    if not data_attr:
        print(f"[WARNING] {source_name}: data-projects attribute is empty")
        return listings

    try:
        projects = json.loads(data_attr)
    except json.JSONDecodeError as e:
        print(f"[WARNING] {source_name}: failed to parse data-projects JSON: {e}")
        return listings

    if not isinstance(projects, list):
        print(f"[WARNING] {source_name}: data-projects is not a list")
        return listings

    for item in projects:
        name = item.get("name", "").strip()
        if not name:
            continue

        # Build full URL from relative uri
        uri = item.get("uri", "")
        link = urljoin("https://wirtschaft-entwicklung.de", uri) if uri else ""

        # Build raw_text with all available info, clearly labeled
        parts = []

        intro = item.get("intro", "").strip()
        if intro:
            # Strip HTML tags from intro
            intro_clean = BeautifulSoup(intro, "html.parser").get_text(separator=" ", strip=True)
            parts.append(f"Intro: {intro_clean}")

        description = item.get("description", "").strip()
        if description:
            # Strip HTML tags from description
            desc_clean = BeautifulSoup(description, "html.parser").get_text(separator=" ", strip=True)
            parts.append(f"Description: {desc_clean}")

        # Funding amount
        funding_sum = item.get("sum", "")
        sum_max = item.get("sumMax", "")
        sum_notice = item.get("sumNotice", "")
        amount_parts = []
        if funding_sum:
            amount_parts.append(str(funding_sum))
        if sum_max:
            amount_parts.append(f"max {sum_max}")
        if sum_notice:
            amount_parts.append(f"({sum_notice})")
        if amount_parts:
            parts.append(f"Funding amount: {' '.join(amount_parts)}")

        # Duration
        duration = item.get("duration", "")
        duration_max = item.get("durationMax", "")
        duration_unit = item.get("durationUnit", "")
        duration_parts = []
        if duration:
            duration_parts.append(str(duration))
        if duration_max:
            duration_parts.append(f"- {duration_max}")
        if duration_unit:
            duration_parts.append(duration_unit)
        if duration_parts:
            parts.append(f"Duration: {' '.join(duration_parts)}")

        # Countries
        countries = item.get("countries", [])
        if countries:
            if isinstance(countries, list):
                country_names = []
                for c in countries:
                    if isinstance(c, dict):
                        country_names.append(c.get("name", str(c)))
                    else:
                        country_names.append(str(c))
                parts.append(f"Countries: {', '.join(country_names)}")
            else:
                parts.append(f"Countries: {countries}")

        # Sectors/keywords
        keywords = item.get("keywords", [])
        if keywords:
            if isinstance(keywords, list):
                kw_names = []
                for k in keywords:
                    if isinstance(k, dict):
                        kw_names.append(k.get("name", str(k)))
                    else:
                        kw_names.append(str(k))
                parts.append(f"Sectors: {', '.join(kw_names)}")
            else:
                parts.append(f"Sectors: {keywords}")

        raw_text = "\n".join(parts)

        listings.append({
            "source": source_name,
            "title": name,
            "link": link,
            "raw_text": raw_text,
        })

    print(f"[INFO] {source_name}: found {len(listings)} listings")
    return listings


# ---------------------------------------------------------------------------
# Source 2: Förderkompass
# ---------------------------------------------------------------------------


def scrape_foerderkompass(source_name: str, url: str) -> list[dict]:
    """
    Scrape the Förderkompass page.

    The page uses an accordion layout: each listing is a card with:
    - <div class="card-header"> containing a <button class="accordion-toggle">
      with the program name as title.
    - <div class="card-body"> containing <li> items with labeled data
      (Förderart, Antragsberechtigt, Bewerbungsfrist, Mehr Informationen, etc.)

    The link is extracted from the "Mehr Informationen" <li>'s <a> tag.
    """
    listings = []
    soup = fetch_page(url)
    if not soup:
        return listings

    # Find all accordion card headers
    card_headers = soup.find_all("div", class_="card-header")

    for header in card_headers:
        # Extract program name from the toggle button
        btn = header.find("button", class_="accordion-toggle")
        if not btn:
            continue
        title = btn.get_text(strip=True)
        if not title:
            continue

        # Find the card body (sibling or within the same parent card)
        parent_card = header.parent
        body = parent_card.find("div", class_="card-body") if parent_card else None
        if not body:
            # Try next sibling
            body = header.find_next_sibling("div", class_="card-body")

        # Extract all text content from the body
        raw_lines = []
        link = ""

        if body:
            # Get all <li> items in the body
            lis = body.find_all("li")
            for li in lis:
                li_text = li.get_text(strip=True)
                if li_text:
                    raw_lines.append(li_text)

                # Extract link from "Mehr Informationen" bullet
                if li_text.startswith("Mehr Informationen") and not link:
                    link_tag = li.find("a", href=True)
                    if link_tag:
                        href = link_tag["href"]
                        if href.startswith("http"):
                            link = href
                        elif href.startswith("/"):
                            link = urljoin(url, href)

            # Also grab any paragraph/span text in the body not in <li>
            # (some cards have descriptive text outside the bullet list)
            for p in body.find_all(["p", "span"], recursive=False):
                p_text = p.get_text(strip=True)
                if p_text and p_text not in raw_lines:
                    raw_lines.insert(0, p_text)

        raw_text = "\n".join(raw_lines)

        listings.append({
            "source": source_name,
            "title": title,
            "link": link,
            "raw_text": raw_text,
        })

    print(f"[INFO] {source_name}: found {len(listings)} listings")
    return listings


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    all_listings = []

    for source_name, url in SOURCES:
        print(f"\n[INFO] Scraping: {source_name}")
        try:
            if "wirtschaft-entwicklung.de" in url:
                listings = scrape_foerderdatenbank(source_name, url)
            elif "zerowasteagentur.de" in url:
                listings = scrape_foerderkompass(source_name, url)
            else:
                print(f"[WARNING] No scraper defined for {url}, skipping.")
                listings = []
        except Exception as e:
            print(f"[WARNING] {source_name} failed entirely: {e}")
            listings = []

        all_listings.extend(listings)
        time.sleep(DELAY_BETWEEN_REQUESTS)

    # Write to CSV
    fieldnames = ["source", "title", "link", "raw_text"]
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_listings)

    print(f"\n[INFO] Done. Wrote {len(all_listings)} total listings to {OUTPUT_CSV}")

    # Spot-check
    if all_listings:
        print("\n--- Spot-check (first 3 rows) ---")
        for row in all_listings[:3]:
            print(f"  Source: {row['source']}")
            print(f"  Title:  {row['title'][:80]}")
            print(f"  Link:   {row['link'][:80]}")
            print(f"  Text:   {row['raw_text'][:120]}...")
            print()


if __name__ == "__main__":
    main()
