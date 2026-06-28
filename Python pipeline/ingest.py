"""
ingest.py – Fetch recent articles from RSS feeds and scrape full text.
Run with: python ingest.py
"""

import csv
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse

import feedparser
import requests
from bs4 import BeautifulSoup

_HERE = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Feed list: add more (source_name, feed_url) tuples as needed.
# ---------------------------------------------------------------------------
FEEDS = [
    ("Iwacu English News", "https://www.iwacu-burundi.org/englishnews/feed/"),
    ("Radio Isanganiro", "https://isanganiro.org/feed/"),
    ("Burundi-Eco", "https://burundi-eco.com/feed/"),
    ("Burundi Forum", "https://burundi-forum.org/feed"),
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

REQUEST_TIMEOUT = 30  # seconds
SCRAPE_WORKERS = 5
POLITENESS_DELAY = 0.7  # seconds between requests to the same domain


def fetch_feed(source_name: str, feed_url: str) -> list[dict]:
    """Parse an RSS feed and return a list of entry dicts."""
    entries = []
    try:
        feed = feedparser.parse(feed_url)
        if feed.bozo and not feed.entries:
            print(f"[WARNING] Could not parse feed for {source_name}: {feed.bozo_exception}")
            return entries
    except Exception as e:
        print(f"[WARNING] Error fetching feed for {source_name}: {e}")
        return entries

    for entry in feed.entries:
        title = entry.get("title", "")
        link = entry.get("link", "")
        published = entry.get("published", entry.get("updated", ""))
        summary = entry.get("summary", entry.get("description", ""))
        # Strip HTML tags from summary
        if summary:
            summary = BeautifulSoup(summary, "html.parser").get_text(separator=" ", strip=True)

        entries.append({
            "source": source_name,
            "title": title,
            "link": link,
            "published_date": published,
            "summary": summary,
            "full_text": "",
        })

    print(f"[INFO] {source_name}: found {len(entries)} entries")
    return entries


def scrape_full_text(url: str) -> str:
    """Follow a URL and attempt to extract the full article text."""
    if not url:
        return ""

    try:
        response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except Exception as e:
        print(f"[WARNING] Failed to fetch {url}: {e}")
        return ""

    soup = BeautifulSoup(response.content, "html.parser")

    # Try common content selectors in order of specificity
    selectors = [
        "article .entry-content",
        "div.entry-content",
        "div.post-content",
        "div.article-content",
        "div.content",
        "article",
        "div.post",
        "main",
    ]

    for selector in selectors:
        container = soup.select_one(selector)
        if container:
            paragraphs = container.find_all("p")
            text = "\n".join(
                p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)
            )
            if text:
                return text

    # Fallback: grab all <p> tags in the body
    body = soup.find("body")
    if body:
        paragraphs = body.find_all("p")
        text = "\n".join(
            p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)
        )
        if text:
            return text

    return ""


def main():
    all_entries = []

    # Step 1: Fetch all feeds (sequential — fast, only 4 feeds)
    for source_name, feed_url in FEEDS:
        entries = fetch_feed(source_name, feed_url)
        all_entries.extend(entries)
        time.sleep(1)

    print(f"\n[INFO] Total entries collected: {len(all_entries)}")
    print(f"[INFO] Scraping full article text with {SCRAPE_WORKERS} workers...\n")

    # Step 2: Scrape full text in parallel with per-domain politeness
    domain_locks = {}  # domain -> Lock
    domain_last_request = {}  # domain -> timestamp
    global_lock = threading.Lock()

    def get_domain(url):
        try:
            return urlparse(url).netloc
        except Exception:
            return ""

    def scrape_with_politeness(url: str) -> tuple[str, str]:
        """Scrape a URL with per-domain rate limiting. Returns (url, full_text)."""
        if not url:
            return (url, "")

        domain = get_domain(url)

        # Get or create a per-domain lock
        with global_lock:
            if domain not in domain_locks:
                domain_locks[domain] = threading.Lock()
                domain_last_request[domain] = 0.0

        # Enforce politeness delay per domain
        with domain_locks[domain]:
            elapsed = time.time() - domain_last_request[domain]
            if elapsed < POLITENESS_DELAY:
                time.sleep(POLITENESS_DELAY - elapsed)
            domain_last_request[domain] = time.time()

        text = scrape_full_text(url)
        return (url, text)

    # Map link -> entry index for result assignment
    link_to_indices = {}
    for i, entry in enumerate(all_entries):
        link = entry.get("link", "")
        if link not in link_to_indices:
            link_to_indices[link] = []
        link_to_indices[link].append(i)

    completed = 0
    total = len(all_entries)

    with ThreadPoolExecutor(max_workers=SCRAPE_WORKERS) as executor:
        futures = {}
        for entry in all_entries:
            link = entry.get("link", "")
            if link and link not in futures.values():
                future = executor.submit(scrape_with_politeness, link)
                futures[future] = link

        for future in as_completed(futures):
            link = futures[future]
            completed += 1
            try:
                _, full_text = future.result()
                # Assign to all entries with this link
                for idx in link_to_indices.get(link, []):
                    all_entries[idx]["full_text"] = full_text
                title = all_entries[link_to_indices[link][0]]["title"][:50] if link_to_indices.get(link) else ""
                print(f"  [{completed}/{total}] {title}...")
            except Exception as e:
                print(f"  [{completed}/{total}] ERROR {link[:50]}: {e}")

    # Step 3: Write to CSV
    output_file = str(_HERE / "articles.csv")
    fieldnames = ["source", "title", "link", "published_date", "summary", "full_text"]

    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_entries)

    print(f"\n[INFO] Done. Wrote {len(all_entries)} articles to {output_file}")


if __name__ == "__main__":
    main()
