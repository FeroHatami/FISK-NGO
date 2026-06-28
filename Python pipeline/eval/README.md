# Evaluation & Reliability Harness

Measures how accurate the pipeline is, so reliability is a number instead of an assertion.
See `../../ARCHITECTURE.md` §7 for the rationale.

## Files

| File | Purpose |
|---|---|
| `golden_dataset.json` | Hand-labeled news + funding cases with expected outputs. `as_of` fixes the date so deterministic funding urgency is reproducible. |
| `scorecard.py` | Runs the checks and prints a pass/fail scorecard. Exit code gates CI. |
| `predictions.sample.json` | Recorded model outputs so the scorecard runs with no API key (replay mode). |

## Run it

```bash
# Replay mode (default) - no API key needed, runs instantly
python3 scorecard.py

# Replay against your own dumped predictions
python3 scorecard.py --predictions my_predictions.json

# Live mode - calls the real summarizer (needs OPENAI_API_KEY and the pipeline built)
python3 scorecard.py --live

# Live + save predictions so you can replay later without paying for tokens
python3 scorecard.py --live --dump predictions.latest.json
```

## What it checks

- **Deterministic layer** — `compute_funding_urgency(deadline, as_of)`. Must be 100%. The pipeline's
  `summarize_funding.py` should import this exact function so the test and production share one implementation.
- **Model layer** — category accuracy (against the 9-value taxonomy), news-urgency accuracy, funding
  deadline/amount correctness, and location recall. Passes when the aggregate meets the dataset `threshold`.

The sample predictions contain a few intentional misses so you can see the diagnostics work. The default run
should report a model score around 85% and an overall PASS, with the wrong cases listed under "Diagnostics".

## Wiring live mode to the pipeline

`scorecard.py --live` imports `summarize_article(input)` from `summarize.py` and `summarize_funding(input)`
from `summarize_funding.py`. Each must return a dict matching the schemas in `ARCHITECTURE.md` (§4 / §5).
Until those exist, live mode exits with a clear message and replay mode is used for the scorecard.

## Growing the dataset

Add real labeled examples from actual scraped feeds/listings. Aim for coverage across all 9 categories and
all urgency bands. The bigger and more representative the golden set, the more trustworthy the score.
