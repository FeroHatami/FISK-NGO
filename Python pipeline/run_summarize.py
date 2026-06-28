"""Run news + email summarization (standalone script, safe to call as subprocess)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from app import load_articles, run_summarization, load_email_articles, run_email_summarization

articles = load_articles()
if articles:
    run_summarization(articles)
else:
    print("[INFO] No articles found.")

email_articles = load_email_articles()
if email_articles:
    run_email_summarization(email_articles)
else:
    print("[INFO] No email articles found.")
