"""
summarize_funding.py – Read funding_opportunities.csv, extract structured info
via OpenAI (parallel), compute urgency in Python, and write to funding_summaries.csv.

Run with: python summarize_funding.py
Requires: OPENAI_API_KEY in a .env file.
"""

import csv
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv

from bedrock_llm import llm_chat

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
load_dotenv(_HERE / ".env")

INPUT_CSV = str(_HERE / "funding_opportunities.csv")
OUTPUT_CSV = str(_HERE / "funding_summaries.csv")
MAX_WORKERS = 25

SYSTEM_PROMPT = """You are extracting structured information from a funding opportunity listing for two NGOs (WTG, focused on animal welfare, and Burundikids, focused on Burundi development).
Respond with ONLY a JSON object in this exact structure, no other text:
{
  "summary_en": "1-2 sentence summary in English of what this funding supports and who it's for",
  "summary_de": "1-2 sentence summary in German of what this funding supports and who it's for",
  "deadline": "YYYY-MM-DD format, or null if the opportunity is rolling/ongoing or no deadline is mentioned",
  "amount": "the funding amount with currency as stated, e.g. '€50,000' or 'up to €120,000', or null if not specified",
  "eligibility_en": ["short bullet point 1 in English", "short bullet point 2 in English", "..."],
  "eligibility_de": ["short bullet point 1 in German", "short bullet point 2 in German", "..."],
  "category": "one of the following exact strings",
  "locations": ["list of relevant countries or regions this funding applies to"],
  "contact_email": "a specific contact email address if literally stated in the text, or null",
  "contact_phone": "a specific contact phone number if literally stated in the text, or null"
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

If the deadline is ambiguous (e.g. "end of summer"), make a reasonable best estimate and convert to YYYY-MM-DD. Only use null when there is genuinely no deadline concept (rolling applications) or it's not mentioned at all.

Contact extraction: Only populate contact_email or contact_phone if a specific email address or phone number is LITERALLY stated in the source text. Never infer or guess. If not explicitly given, use null."""

VALID_CATEGORIES = {
    "Mobile Veterinary Support",
    "Stray Population Infrastructure",
    "Wildlife Trade Defenses",
    "Emergency Relief Hub",
    "Bildung",
    "Gesundheit",
    "Kinder- und Frauenrechte",
    "Kommunale Entwicklung und Umweltschutz",
    "Uncategorized",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_input() -> list[dict]:
    """Load funding opportunities from CSV."""
    if not os.path.exists(INPUT_CSV):
        print(f"[ERROR] {INPUT_CSV} not found.")
        return []
    with open(INPUT_CSV, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_cache() -> dict:
    """Load existing summaries keyed by link."""
    cache = {}
    if not os.path.exists(OUTPUT_CSV):
        return cache
    with open(OUTPUT_CSV, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            cache[row["link"]] = row
    return cache


def save_cache(cache: dict):
    """Write the full cache back to CSV."""
    if not cache:
        return
    fieldnames = ["link", "summary_en", "summary_de", "deadline", "amount", "eligibility_en", "eligibility_de", "category", "locations", "urgency"]
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in cache.values():
            writer.writerow(row)


def compute_urgency(deadline_str: str | None) -> str:
    """Compute urgency based on days until deadline."""
    if not deadline_str or deadline_str.strip().lower() == "null":
        return "undefined"

    try:
        deadline_date = datetime.strptime(deadline_str.strip(), "%Y-%m-%d").date()
    except ValueError:
        return "undefined"

    days_remaining = (deadline_date - date.today()).days

    if days_remaining < 0:
        return "expired"
    elif days_remaining <= 30:
        return "high"
    elif days_remaining <= 60:
        return "medium"
    else:
        return "low"


def extract_funding_info(client, raw_text: str) -> dict | None:
    """Call AWS Bedrock (Nova) to extract structured funding info. Returns parsed dict or None."""
    if not raw_text or not raw_text.strip():
        return None

    try:
        content = llm_chat(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=raw_text[:12000],
            temperature=0.2,
            max_tokens=1024,
            json_mode=True,
        )
        if not content:
            return None
        result = json.loads(content)
        return result
    except json.JSONDecodeError as e:
        print(f"[WARNING] Failed to parse LLM response as JSON: {e}")
        return None
    except Exception as e:
        print(f"[WARNING] LLM call failed: {e}")
        return None


def process_one(client, link: str, raw_text: str, title: str) -> tuple[str, dict | None]:
    """
    Process a single funding opportunity: call Bedrock, parse result, compute urgency.
    Returns (link, result_dict) or (link, None) on failure.
    """
    result = extract_funding_info(client, raw_text)
    if not result:
        return (link, None)

    # Validate category
    category = result.get("category", "Uncategorized")
    if category not in VALID_CATEGORIES:
        category = "Uncategorized"

    # Handle deadline — normalize null
    deadline = result.get("deadline")
    if deadline is None or str(deadline).strip().lower() == "null":
        deadline = ""

    # Compute urgency in Python
    urgency = compute_urgency(deadline if deadline else None)

    row = {
        "link": link,
        "summary_en": result.get("summary_en", ""),
        "summary_de": result.get("summary_de", ""),
        "deadline": deadline,
        "amount": result.get("amount") or "",
        "eligibility_en": json.dumps(result.get("eligibility_en", [])),
        "eligibility_de": json.dumps(result.get("eligibility_de", [])),
        "category": category,
        "locations": json.dumps(result.get("locations", [])),
        "urgency": urgency,
    }
    return (link, row)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    listings = load_input()
    if not listings:
        print("[INFO] No listings to process.")
        return

    cache = load_cache()

    # Step 1: Recompute urgency for all existing cached rows (deadline drift)
    recomputed = 0
    for link, row in cache.items():
        deadline = row.get("deadline", "")
        new_urgency = compute_urgency(deadline if deadline else None)
        if row.get("urgency") != new_urgency:
            row["urgency"] = new_urgency
            recomputed += 1

    if recomputed:
        print(f"[INFO] Recomputed urgency for {recomputed} cached rows.")
        save_cache(cache)

    # Step 2: Filter to items not yet in cache
    to_process = []
    for row in listings:
        link = row.get("link", "")
        if link in cache:
            continue
        raw_text = row.get("raw_text", "")
        if not raw_text.strip():
            continue
        to_process.append(row)

    print(f"[INFO] Total listings: {len(listings)}")
    print(f"[INFO] Already cached: {len(cache)}")
    print(f"[INFO] To process: {len(to_process)}")

    if not to_process:
        print("[INFO] Nothing new to process. Done.")
        return

    # Step 3: Process new items in parallel
    print(f"[INFO] Running {MAX_WORKERS} parallel workers (AWS Bedrock)...\n")
    new_calls = 0
    lock = threading.Lock()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {}
        for row in to_process:
            link = row.get("link", "")
            raw_text = row.get("raw_text", "")
            title = row.get("title", "")
            future = executor.submit(process_one, None, link, raw_text, title)
            futures[future] = title

        for future in as_completed(futures):
            title = futures[future]
            try:
                link, result_row = future.result()
                if result_row:
                    with lock:
                        cache[link] = result_row
                        new_calls += 1
                    print(f"  [OK] {title[:60]}")
                else:
                    print(f"  [SKIP] {title[:60]} (no result)")
            except Exception as e:
                print(f"  [ERROR] {title[:60]}: {e}")

    # Step 4: Write final cache to CSV
    save_cache(cache)

    print(f"\n[INFO] Done. New API calls: {new_calls}, Total cached: {len(cache)}")
    print(f"[INFO] Results written to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
