#!/usr/bin/env python3
"""Ingest Google Alert emails from a Gmail inbox over IMAP, extract + unwrap the
result links, scrape the linked pages, and write a shared articles.csv.

Live mode (needs a Gmail App Password in .env or the environment):
    python3 ingest_inbox.py

Offline mode (parse a saved .eml, no network/credentials):
    python3 ingest_inbox.py --eml sample_alert.eml --no-scrape

CSV schema (matches ingest.py, plus an alert_topic column for provenance):
    source, title, link, published_date, summary, full_text, alert_topic
"""

from __future__ import annotations

import argparse
import csv
import email
import email.utils
import imaplib
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from email.header import decode_header, make_header
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from bs4 import BeautifulSoup

# Optional: load GMAIL_* vars from a .env file if python-dotenv is installed.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

HERE = Path(__file__).resolve().parent
FIELDNAMES = ["source", "title", "link", "published_date", "summary", "full_text", "alert_topic"]
_HEADERS = {"User-Agent": "Mozilla/5.0 (AI4Good press-monitor; +https://example.org)"}
_CONTENT_SELECTORS = [
    "article", "main", "div.article-content",
    "div.entry-content", "div.post-content", "div#content",
]


# --------------------------------------------------------------------------- #
# URL helpers
# --------------------------------------------------------------------------- #
def unwrap_google_url(href: str) -> str:
    """`https://www.google.com/url?...&url=REAL` -> REAL (decoded).
    Unchanged if it isn't a Google redirect."""
    try:
        p = urlparse(href)
    except ValueError:
        return href
    if p.netloc.endswith("google.com") and p.path in ("/url", "/aclk"):
        qs = parse_qs(p.query)
        for key in ("url", "q"):
            if qs.get(key):
                return qs[key][0]
    return href


def domain_of(url: str) -> str:
    try:
        return urlparse(url).netloc.replace("www.", "")
    except ValueError:
        return ""


def is_google_host(url: str) -> bool:
    """True for google.com control links (manage alerts, unsubscribe, RSS, support)."""
    try:
        return urlparse(url).netloc.endswith("google.com")
    except ValueError:
        return False


# --------------------------------------------------------------------------- #
# Scraping
# --------------------------------------------------------------------------- #
def fetch_full_text(url: str, timeout: int = 15) -> str:
    """Follow a URL, return its main text. Tries common content containers,
    falls back to concatenating <p> tags. Raises on network/HTTP errors."""
    import requests  # imported lazily so --no-scrape works without requests installed

    resp = requests.get(url, headers=_HEADERS, timeout=timeout)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for selector in _CONTENT_SELECTORS:
        node = soup.select_one(selector)
        if node:
            text = node.get_text(" ", strip=True)
            if len(text) > 200:
                return text
    paras = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
    return " ".join(t for t in paras if t)


# --------------------------------------------------------------------------- #
# Email parsing
# --------------------------------------------------------------------------- #
def decode_subject(raw: str) -> str:
    try:
        return str(make_header(decode_header(raw or "")))
    except Exception:
        return raw or ""


def topic_from_subject(subject: str) -> str:
    """Google Alert subjects look like: 'Google Alert - <query>'"""
    return subject.split(" - ", 1)[1].strip() if " - " in subject else subject.strip()


def get_html_part(msg) -> str:
    for wanted in ("text/html", "text/plain"):
        for part in (msg.walk() if msg.is_multipart() else [msg]):
            if part.get_content_type() == wanted:
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode(part.get_content_charset() or "utf-8", "replace")
    return ""


def extract_alert_links(html: str) -> list[dict]:
    """Pull real article links out of a Google Alert HTML body."""
    soup = BeautifulSoup(html, "html.parser")
    out, seen = [], set()
    for a in soup.find_all("a", href=True):
        real = unwrap_google_url(a["href"])
        if not real.startswith(("http://", "https://")):
            continue
        if is_google_host(real):          # manage-alerts / unsubscribe / RSS / support
            continue
        if real in seen:                   # de-dup within one email
            continue
        title = a.get_text(" ", strip=True)
        if not title:
            continue
        seen.add(real)
        out.append({"title": title, "link": real, "source": domain_of(real)})
    return out


def message_to_articles(msg) -> list[dict]:
    topic = topic_from_subject(decode_subject(msg.get("Subject", "")))
    published = ""
    try:
        dt = email.utils.parsedate_to_datetime(msg.get("Date"))
        published = dt.date().isoformat() if dt else ""
    except Exception:
        pass
    arts = extract_alert_links(get_html_part(msg))
    for a in arts:
        a.update(published_date=published, alert_topic=topic, summary="", full_text="")
    return arts


# --------------------------------------------------------------------------- #
# IMAP
# --------------------------------------------------------------------------- #
def fetch_from_imap(host: str, user: str, password: str, sender: str, since_days: int) -> list:
    M = imaplib.IMAP4_SSL(host)
    try:
        M.login(user, password)
        M.select("INBOX", readonly=True)  # read-only: never modifies the inbox
        since = (date.today() - timedelta(days=since_days)).strftime("%d-%b-%Y")
        typ, data = M.search(None, f'(FROM "{sender}" SINCE "{since}")')
        msgs = []
        if typ == "OK" and data and data[0]:
            for num in data[0].split():
                t2, md = M.fetch(num, "(RFC822)")
                if t2 == "OK" and md and md[0]:
                    msgs.append(email.message_from_bytes(md[0][1]))
        return msgs
    finally:
        try:
            M.logout()
        except Exception:
            pass


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description="Ingest Google Alert emails into articles.csv")
    ap.add_argument("--eml", type=Path, help="parse a saved .eml file instead of IMAP (offline test)")
    ap.add_argument("--no-scrape", action="store_true", help="skip following links (full_text stays empty)")
    ap.add_argument("--out", type=Path, default=HERE / "alert_articles.csv")
    ap.add_argument("--since", type=int, default=int(os.getenv("ALERT_SINCE_DAYS", "7")),
                    help="how many days back to search (default: 7, or ALERT_SINCE_DAYS env)")
    args = ap.parse_args()

    if args.eml:
        messages = [email.message_from_bytes(args.eml.read_bytes())]
    else:
        user = os.getenv("GMAIL_IMAP_USER")
        pw = os.getenv("GMAIL_APP_PASSWORD")
        if not user or not pw:
            print("WARNING: GMAIL_IMAP_USER and GMAIL_APP_PASSWORD not set. "
                  "Writing empty alert_articles.csv. "
                  "Set credentials in .env, or use --eml to parse a saved alert offline.",
                  file=sys.stderr)
            # Write empty CSV so downstream scripts have a file to read
            with args.out.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=FIELDNAMES)
                w.writeheader()
            print(f"Wrote 0 row(s) to {args.out}")
            return 0
        host = os.getenv("IMAP_HOST", "imap.gmail.com")
        sender = os.getenv("ALERT_SENDER", "googlealerts-noreply@google.com")
        messages = fetch_from_imap(host, user, pw, sender, args.since)

    articles, seen = [], set()
    for m in messages:
        for a in message_to_articles(m):
            if a["link"] not in seen:
                seen.add(a["link"])
                articles.append(a)
    print(f"Found {len(articles)} unique article link(s) across {len(messages)} message(s).")

    if not args.no_scrape:
        SCRAPE_WORKERS = 6
        POLITENESS_DELAY = 0.7  # seconds between requests to same domain

        domain_locks: dict[str, threading.Lock] = {}
        domain_last: dict[str, float] = {}
        global_lock = threading.Lock()

        def _get_domain(url: str) -> str:
            try:
                return urlparse(url).netloc
            except Exception:
                return ""

        def _scrape_one(url: str) -> tuple[str, str]:
            """Scrape with per-domain politeness. Returns (url, full_text)."""
            domain = _get_domain(url)
            with global_lock:
                if domain not in domain_locks:
                    domain_locks[domain] = threading.Lock()
                    domain_last[domain] = 0.0

            with domain_locks[domain]:
                elapsed = time.time() - domain_last[domain]
                if elapsed < POLITENESS_DELAY:
                    time.sleep(POLITENESS_DELAY - elapsed)
                domain_last[domain] = time.time()

            return (url, fetch_full_text(url))

        print(f"  Scraping {len(articles)} articles with {SCRAPE_WORKERS} workers...")
        link_to_indices: dict[str, list[int]] = {}
        for i, a in enumerate(articles):
            link_to_indices.setdefault(a["link"], []).append(i)

        completed = 0
        with ThreadPoolExecutor(max_workers=SCRAPE_WORKERS) as executor:
            futures = {}
            for a in articles:
                if a["link"] not in futures.values():
                    future = executor.submit(_scrape_one, a["link"])
                    futures[future] = a["link"]

            for future in as_completed(futures):
                link = futures[future]
                completed += 1
                try:
                    _, text = future.result()
                    for idx in link_to_indices.get(link, []):
                        articles[idx]["full_text"] = text
                    print(f"  scraped: {link}")
                except Exception as exc:
                    print(f"  WARN failed to scrape {link}: {exc}", file=sys.stderr)

    with args.out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES)
        w.writeheader()
        for a in articles:
            w.writerow({k: a.get(k, "") for k in FIELDNAMES})
    print(f"Wrote {len(articles)} row(s) to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
