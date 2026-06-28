"""
run_all.py – Run the full FISK + Loveable pipeline end-to-end.

Usage:
    python run_all.py              # full pipeline
    python run_all.py --skip-ingest  # skip scraping, jump to summarize + export + serve

Steps:
    1. ingest.py          — news RSS ingestion
    2. ingest_funding.py  — funding listings ingestion
    3. ingest_inbox.py    — Google Alert email ingestion (skipped if no Gmail creds)
    4. summarize_funding.py — funding extraction/summarization
    5. News + email summarization (from app.py startup logic)
    6. export_items.py    — unified JSON export to Loveable pipeline
    7. Start Loveable pipeline Flask server (stays running)
"""

import argparse
import csv
import os
import subprocess
import sys
from pathlib import Path

# Resolve paths relative to this script's location
HERE = Path(__file__).resolve().parent
PYTHON_PIPELINE = HERE / "Python pipeline"
LOVEABLE_PIPELINE = HERE / "Loveable pipeline"

# Try loading .env for credential checks
try:
    sys.path.insert(0, str(PYTHON_PIPELINE))
    from dotenv import load_dotenv
    load_dotenv(PYTHON_PIPELINE / ".env")
except ImportError:
    pass


def count_csv_rows(path: Path) -> int:
    if not path.exists():
        return 0
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader, None)
        return sum(1 for _ in reader)


def run_step(label: str, command: list[str], cwd: Path) -> bool:
    print(f"\n{'='*60}")
    print(f"  STEP: {label}")
    print(f"{'='*60}\n")
    result = subprocess.run(command, cwd=str(cwd))
    if result.returncode != 0:
        print(f"\n[ERROR] Step failed: {label} (exit code {result.returncode})")
        return False
    return True


def main():
    parser = argparse.ArgumentParser(description="Run the full FISK + Loveable pipeline.")
    parser.add_argument("--skip-ingest", action="store_true",
                        help="Skip ingestion steps 1-3, jump to summarization + export + serve")
    args = parser.parse_args()

    python = sys.executable

    # ------------------------------------------------------------------
    # Ingestion (skippable)
    # ------------------------------------------------------------------
    if not args.skip_ingest:
        if not run_step("News RSS ingestion (ingest.py)", [python, "ingest.py"], PYTHON_PIPELINE):
            print("[FATAL] Pipeline stopped.")
            return 1

        if not run_step("Funding listings ingestion (ingest_funding.py)", [python, "ingest_funding.py"], PYTHON_PIPELINE):
            print("[FATAL] Pipeline stopped.")
            return 1

        # Email ingestion — skip gracefully if no creds
        gmail_user = os.environ.get("GMAIL_IMAP_USER")
        gmail_pass = os.environ.get("GMAIL_APP_PASSWORD")
        if gmail_user and gmail_pass:
            if not run_step("Google Alert email ingestion (ingest_inbox.py)", [python, "ingest_inbox.py"], PYTHON_PIPELINE):
                print("[FATAL] Pipeline stopped.")
                return 1
        else:
            print(f"\n{'='*60}")
            print("  STEP: Google Alert email ingestion (ingest_inbox.py)")
            print(f"{'='*60}")
            print("\n[WARNING] Skipping — GMAIL_IMAP_USER/GMAIL_APP_PASSWORD not set.\n")
    else:
        print("\n[INFO] --skip-ingest: skipping ingestion steps 1-3.\n")

    # ------------------------------------------------------------------
    # Summarization
    # ------------------------------------------------------------------
    if not run_step("Funding summarization (summarize_funding.py)", [python, "summarize_funding.py"], PYTHON_PIPELINE):
        print("[FATAL] Pipeline stopped.")
        return 1

    # News + email summarization
    if not run_step("News + email summarization (run_summarize.py)", [python, "run_summarize.py"], PYTHON_PIPELINE):
        print("[FATAL] News/email summarization failed.")
        return 1

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------
    if not run_step("Export items.json (export_items.py)", [python, "export_items.py"], PYTHON_PIPELINE):
        print("[FATAL] Pipeline stopped.")
        return 1

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    articles_count = count_csv_rows(PYTHON_PIPELINE / "articles.csv")
    funding_count = count_csv_rows(PYTHON_PIPELINE / "funding_opportunities.csv")
    email_count = count_csv_rows(PYTHON_PIPELINE / "alert_articles.csv")

    print(f"\n{'='*60}")
    print("  PIPELINE COMPLETE")
    print(f"{'='*60}")
    print(f"  News articles:          {articles_count}")
    print(f"  Funding opportunities:  {funding_count}")
    print(f"  Email-sourced items:    {email_count}")
    print(f"{'='*60}\n")

    # ------------------------------------------------------------------
    # Start Loveable Flask server (long-running)
    # ------------------------------------------------------------------
    print(f"\n{'='*60}")
    print("  STEP: Starting Loveable Flask server (app.py)")
    print(f"{'='*60}")
    print(f"\n[INFO] Server will be at http://127.0.0.1:5000")
    print("[INFO] Press Ctrl+C to stop.\n")

    try:
        # Use subprocess instead of execv — handles paths with spaces correctly on Windows
        subprocess.run([python, str(LOVEABLE_PIPELINE / "app.py")], cwd=str(LOVEABLE_PIPELINE))
    except KeyboardInterrupt:
        pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
