# AWS Bedrock Integration — Technical Deep-Dive

This document explains exactly how FISK uses **Amazon Bedrock** as its core intelligence layer, how model routing and fallback work, and how to operate it.

---

## 1. Summary

Every AI inference in FISK is a call to **Amazon Bedrock** (Amazon Nova model family) through the AWS SDK (`boto3` → `bedrock-runtime.invoke_model`). OpenAI is wired in **only** as an automatic fallback that activates if a Bedrock call raises an exception. Under normal operation, **100% of inferences run on AWS.**

There are two Bedrock clients, one per subsystem, both implementing the same primary→fallback contract:

| Client | File | Subsystem | Default tier |
|--------|------|-----------|--------------|
| `llm_chat()` | `Python pipeline/bedrock_llm.py` | Ingestion / summarization | Nova Lite |
| `chat()` | `Loveable pipeline/bedrock_client.py` | Live Flask API | Nova Pro (tiered) |

---

## 2. Models & region

- **Region:** `us-west-2`
- **Access pattern:** cross-region **inference profiles** (the `us.` prefix). The hackathon/workshop account policy explicitly denies direct on-demand foundation-model IDs (e.g. `anthropic.claude-3-haiku-...` and bare `amazon.nova-pro-v1:0`), so calls must target the inference-profile IDs below.

| Tier | Inference profile ID | Role |
|------|----------------------|------|
| Pro | `us.amazon.nova-pro-v1:0` | Multi-step reasoning: copilot, insights, funding matching |
| Lite | `us.amazon.nova-lite-v1:0` | High-volume structured extraction: summarization, translation, classification, email drafting |
| Micro | `us.amazon.nova-micro-v1:0` | Lightweight/fast tasks |

All three are configurable via environment variables (`BEDROCK_MODEL_PRO/LITE/MICRO`), so swapping models requires no code change.

---

## 3. Request format (Amazon Nova native schema)

Nova on Bedrock uses a structured body. The clients build it like this:

```python
body = {
    "messages": [
        {"role": "user", "content": [{"text": user_prompt}]}
    ],
    "system": [{"text": system_prompt}],
    "inferenceConfig": {
        "maxTokens": max_tokens,
        "temperature": temperature,
    },
}

response = client.invoke_model(
    modelId="us.amazon.nova-pro-v1:0",
    body=json.dumps(body),
    contentType="application/json",
    accept="application/json",
)
text = json.loads(response["body"].read())["output"]["message"]["content"][0]["text"]
```

Key details:
- The **system prompt** is a separate top-level `system` block (not a message role).
- Message **content is a list of blocks** (`[{"text": ...}]`), not a bare string.
- The API client converts OpenAI-style `[{role, content}]` message lists into this format automatically, so the rest of the codebase stays provider-agnostic.

---

## 4. Model routing (tiered inference)

`bedrock_client.py` selects the model by a `tier` argument so cost/latency track task complexity:

```python
MODELS = {
    "pro":   "us.amazon.nova-pro-v1:0",
    "lite":  "us.amazon.nova-lite-v1:0",
    "micro": "us.amazon.nova-micro-v1:0",
}

chat(messages, tier="pro")    # copilot, insights, funding matching
chat(messages, tier="lite")   # email drafting
```

| Endpoint / task | Tier | Why |
|-----------------|------|-----|
| `/api/copilot` | Pro | Open-ended reasoning over retrieved context |
| `/api/insights` | Pro | Cross-item synthesis, structured JSON |
| `/api/funding/search` | Pro | Relevance judgement + justification |
| `/api/copilot/draft-email` | Lite | Templated generation, lower cost |
| Pipeline summarization | Lite | High volume (hundreds of items), structured extraction |

---

## 5. Fallback strategy (cross-cloud resiliency)

Each call attempts Bedrock first. Only if Bedrock raises does the client try OpenAI `gpt-4o-mini`. If both fail, the API surfaces a clear error.

```
chat() ──► Bedrock (Nova)  ──success──► return
              │
              └─ exception ─► OpenAI gpt-4o-mini ──success──► return
                                  │
                                  └─ none/exception ─► RuntimeError
```

OpenAI is optional: if `OPENAI_API_KEY` is blank, the system runs **Bedrock-only** and simply errors if Bedrock is down. This keeps AWS unambiguously the primary path.

---

## 6. JSON-mode hardening

Several features need machine-parseable JSON (insights, funding matches, email drafts). When `json_mode=True`:

1. The system prompt is augmented with a strict "return JSON only" instruction.
2. Responses are passed through `_strip_fences()`, which removes ```` ```json … ``` ```` wrappers that Nova (especially Lite) sometimes adds, so downstream `json.loads()` doesn't fail.

This was a real bug we hit and fixed: Nova Lite intermittently wrapped email-draft JSON in markdown fences, breaking the parse. Fence-stripping made it robust.

---

## 7. Credentials & configuration

Loaded from `Python pipeline/.env` with `override=True` (so `.env` is the single source of truth, even over stale shell exports):

```env
AWS_DEFAULT_REGION=us-west-2
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_SESSION_TOKEN=...            # required for temporary/workshop creds
BEDROCK_MODEL_PRO=us.amazon.nova-pro-v1:0
BEDROCK_MODEL_LITE=us.amazon.nova-lite-v1:0
BEDROCK_MODEL_MICRO=us.amazon.nova-micro-v1:0
OPENAI_API_KEY=                  # optional fallback
```

`boto3` reads the AWS variables from the environment; the clients call `load_dotenv(..., override=True)` at import so both the pipeline and the API pick them up.

> **Temporary credentials expire.** When using workshop/STS credentials, refresh `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and `AWS_SESSION_TOKEN` in `.env` and restart the backend.

---

## 8. Verifying Bedrock connectivity

Quick check that credentials reach Bedrock and a model responds:

```python
import boto3, json
c = boto3.client("bedrock-runtime", region_name="us-west-2")
body = json.dumps({
    "messages": [{"role": "user", "content": [{"text": "Say hello in one word"}]}],
    "inferenceConfig": {"maxTokens": 20},
})
r = c.invoke_model(modelId="us.amazon.nova-lite-v1:0", body=body,
                   contentType="application/json", accept="application/json")
print(json.loads(r["body"].read())["output"]["message"]["content"][0]["text"])
```

To list models the account can see:

```python
import boto3
b = boto3.client("bedrock", region_name="us-west-2")
for m in b.list_foundation_models()["modelSummaries"]:
    print(m["modelId"])
```

---

## 9. Common errors

| Error | Cause | Fix |
|-------|-------|-----|
| `AccessDeniedException ... explicit deny` | Used a direct model ID instead of the `us.` inference profile | Use `us.amazon.nova-*` IDs |
| `ValidationException ... on-demand throughput isn't supported` | Same as above for Nova | Use the inference-profile ID |
| `ExpiredTokenException` / `UnrecognizedClientException` | Temporary AWS creds expired | Refresh the three AWS values in `.env`, restart |
| `Both AWS Bedrock and OpenAI fallback failed` | Bedrock errored and no/!invalid `OPENAI_API_KEY` | Fix AWS creds, or set a valid OpenAI key |

---

## 10. Why this counts as "Best use of AWS"

- AWS Bedrock is the **default and primary** engine for **every** AI capability — not an optional add-on.
- **Three Nova tiers** are used deliberately, with routing matched to task complexity.
- Uses Bedrock's **native Nova API** and **cross-region inference profiles** correctly under a restrictive IAM policy.
- Implements production concerns: **provider failover**, **JSON-mode robustness**, **caching to minimize spend**, and **env-driven model configuration**.
- The entire ingestion-to-insight pipeline — translation, classification, urgency, summarization, conversational RAG, partnership detection, funding matching, and outreach drafting — is powered by Amazon Bedrock.
