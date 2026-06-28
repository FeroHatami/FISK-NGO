#!/usr/bin/env python3
"""Reliability scorecard for the Press Review & Funding Monitor.

Measures pipeline accuracy against a hand-labeled golden set (`golden_dataset.json`).
It has two layers:

  1. Deterministic checks  - funding urgency derived from a deadline. No model needed;
     should always be 100%. This is the shared logic the pipeline must reuse.
  2. Model-output checks    - category / news-urgency / deadline / amount / locations.
     By default these run in REPLAY mode against recorded predictions
     (`predictions.sample.json`). Use `--live` to call the real summarizer instead.

Usage:
    python3 scorecard.py                         # replay against predictions.sample.json
    python3 scorecard.py --predictions my.json   # replay against your own dump
    python3 scorecard.py --live                  # call the real pipeline (needs OPENAI_API_KEY)
    python3 scorecard.py --live --dump out.json  # run live and save predictions for replay

Exit code is 0 when deterministic checks are perfect AND the model score meets the
dataset threshold; otherwise 1 (so it can gate CI / a build step).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATASET_PATH = HERE / "golden_dataset.json"
DEFAULT_PREDICTIONS = HERE / "predictions.sample.json"

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


# --------------------------------------------------------------------------------------
# Deterministic layer (the pipeline's summarize_funding.py MUST import this exact logic)
# --------------------------------------------------------------------------------------
def compute_funding_urgency(deadline: str | None, as_of: str) -> str:
    """Map a funding deadline to an urgency band, relative to `as_of` (YYYY-MM-DD)."""
    if not deadline:
        return "undefined"
    d = date.fromisoformat(deadline)
    today = date.fromisoformat(as_of)
    days = (d - today).days
    if days <= 30:
        return "high"
    if days <= 60:
        return "medium"
    return "low"


# --------------------------------------------------------------------------------------
# Prediction sources
# --------------------------------------------------------------------------------------
def load_replay_predictions(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("predictions", data)


def run_live(cases: list[dict]) -> dict:
    """Call the real pipeline. Wrapped so a missing pipeline degrades gracefully."""
    try:
        from summarize import summarize_article  # type: ignore
        from summarize_funding import summarize_funding  # type: ignore
    except ImportError as exc:  # pipeline not wired yet
        print(
            "  [--live] Real summarizer not importable yet "
            f"({exc}). Build summarize.py / summarize_funding.py, then re-run.",
            file=sys.stderr,
        )
        sys.exit(2)

    preds: dict = {}
    for c in cases:
        if c["content_type"] == "news":
            preds[c["id"]] = summarize_article(c["input"])
        else:
            preds[c["id"]] = summarize_funding(c["input"])
    return preds


# --------------------------------------------------------------------------------------
# Metric helpers
# --------------------------------------------------------------------------------------
def pct(num: int, den: int) -> str:
    return f"{(100 * num / den):.0f}%" if den else "n/a"


def leader(label: str, num: int, den: int) -> str:
    dots = "." * max(3, 40 - len(label))
    return f"  {label} {dots} {num}/{den}  ({pct(num, den)})"


def locations_recall(expected: list[str], predicted: list[str]) -> float:
    if not expected:
        return 1.0
    exp = {e.strip().lower() for e in expected}
    pred = {p.strip().lower() for p in predicted}
    return len(exp & pred) / len(exp)


# --------------------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="Reliability scorecard")
    ap.add_argument("--live", action="store_true", help="call the real summarizer")
    ap.add_argument("--predictions", type=Path, default=DEFAULT_PREDICTIONS)
    ap.add_argument("--dump", type=Path, help="with --live, save predictions to this path")
    args = ap.parse_args()

    dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    as_of = dataset["as_of"]
    threshold = dataset.get("threshold", 0.8)
    cases = dataset["cases"]

    news = [c for c in cases if c["content_type"] == "news"]
    funding = [c for c in cases if c["content_type"] == "funding"]

    source_label = "live pipeline" if args.live else args.predictions.name
    preds = run_live(cases) if args.live else load_replay_predictions(args.predictions)
    if args.live and args.dump:
        args.dump.write_text(json.dumps({"predictions": preds}, indent=2), encoding="utf-8")

    print("=" * 70)
    print("Press Review & Funding Monitor - Reliability Scorecard")
    print("=" * 70)
    print(f"As-of date : {as_of}")
    print(f"Cases      : {len(cases)} (news: {len(news)}, funding: {len(funding)})")
    print(f"Predictions: {source_label}")
    print()

    # ---- Deterministic layer ----------------------------------------------------------
    det_ok = sum(
        1 for c in funding if compute_funding_urgency(c["expected"]["deadline"], as_of) == c["expected"]["urgency"]
    )
    print("Deterministic checks (no model needed):")
    print(leader("Funding urgency from deadline", det_ok, len(funding)))
    print()

    # ---- Model layer ------------------------------------------------------------------
    cat_ok = cat_n = 0
    urg_ok = urg_n = 0
    dl_ok = dl_n = 0
    amt_ok = amt_n = 0
    recall_sum = 0.0
    failures: list[str] = []

    for c in cases:
        cid = c["id"]
        exp = c["expected"]
        p = preds.get(cid, {})

        # category (all cases)
        cat_n += 1
        pred_cat = p.get("category")
        if pred_cat not in VALID_CATEGORIES:
            failures.append(f"{cid}: category '{pred_cat}' is not in the 9-value taxonomy")
        elif pred_cat == exp["category"]:
            cat_ok += 1
        else:
            failures.append(f"{cid}: category expected '{exp['category']}', got '{pred_cat}'")

        # urgency (news only - funding urgency is deterministic, checked above)
        if c["content_type"] == "news":
            urg_n += 1
            if p.get("urgency") == exp["urgency"]:
                urg_ok += 1
            else:
                failures.append(f"{cid}: urgency expected '{exp['urgency']}', got '{p.get('urgency')}'")

        # deadline + amount (funding only)
        if c["content_type"] == "funding":
            dl_n += 1
            if p.get("deadline") == exp["deadline"]:
                dl_ok += 1
            else:
                failures.append(f"{cid}: deadline expected {exp['deadline']!r}, got {p.get('deadline')!r}")
            amt_n += 1
            if p.get("amount") == exp["amount"]:
                amt_ok += 1
            else:
                failures.append(f"{cid}: amount expected {exp['amount']!r}, got {p.get('amount')!r}")

        recall_sum += locations_recall(exp.get("locations", []), p.get("locations", []))

    print(f"Model-output checks (source: {source_label}):")
    print(leader("Category accuracy", cat_ok, cat_n))
    print(leader("Urgency accuracy (news)", urg_ok, urg_n))
    print(leader("Deadline correctness (funding)", dl_ok, dl_n))
    print(leader("Amount correctness (funding)", amt_ok, amt_n))
    print(f"  {'Locations recall (avg)':.<40} {recall_sum / len(cases):.0%}")
    print()

    model_ok = cat_ok + urg_ok + dl_ok + amt_ok
    model_n = cat_n + urg_n + dl_n + amt_n
    model_score = model_ok / model_n if model_n else 0.0
    det_perfect = det_ok == len(funding)
    passed = det_perfect and model_score >= threshold

    print("-" * 70)
    print(f"Deterministic layer : {'PASS' if det_perfect else 'FAIL'} ({det_ok}/{len(funding)})")
    print(f"Model score         : {model_ok}/{model_n} ({model_score:.0%})  threshold {threshold:.0%}")
    print(f"OVERALL             : {'PASS' if passed else 'FAIL'}")
    print("-" * 70)

    if failures:
        print("\nDiagnostics (what to fix):")
        for f in failures:
            print(f"  - {f}")

    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
