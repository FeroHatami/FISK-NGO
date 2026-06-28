"""
AWS Bedrock AI client for the NGO Intelligence Hub.

Provides a unified interface for calling Amazon Bedrock (Nova models)
with automatic fallback to OpenAI if Bedrock is unavailable.

Model routing:
  - Nova Pro:   Complex reasoning (copilot, insights, funding matching)
  - Nova Lite:  Standard tasks (summarization, email drafting)
  - Nova Micro: Fast/simple tasks (briefings, keyword extraction)
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Load .env once
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).parent.parent / "Python pipeline" / ".env"
    if _env_path.exists():
        load_dotenv(_env_path, override=True)
except ImportError:
    pass

# --- Configuration ---
AWS_REGION = os.environ.get("AWS_DEFAULT_REGION", "us-west-2")
BEDROCK_MODEL_PRO = os.environ.get("BEDROCK_MODEL_PRO", "us.amazon.nova-pro-v1:0")
BEDROCK_MODEL_LITE = os.environ.get("BEDROCK_MODEL_LITE", "us.amazon.nova-lite-v1:0")
BEDROCK_MODEL_MICRO = os.environ.get("BEDROCK_MODEL_MICRO", "us.amazon.nova-micro-v1:0")

# Model tier selection
MODELS = {
    "pro": BEDROCK_MODEL_PRO,
    "lite": BEDROCK_MODEL_LITE,
    "micro": BEDROCK_MODEL_MICRO,
}


def _get_bedrock_client():
    """Lazily create a Bedrock runtime client."""
    import boto3
    return boto3.client("bedrock-runtime", region_name=AWS_REGION)


def _call_bedrock(messages: list[dict], model_id: str, temperature: float = 0.4,
                  max_tokens: int = 2048, json_mode: bool = False) -> str:
    """
    Call AWS Bedrock with Amazon Nova's Converse-compatible format.

    Args:
        messages: List of {"role": "user"|"assistant", "content": "..."}
                  First message can have role "system" — it will be extracted.
        model_id: Bedrock model ID (e.g. us.amazon.nova-pro-v1:0)
        temperature: Sampling temperature
        max_tokens: Max tokens in response
        json_mode: If True, instruct the model to return valid JSON

    Returns:
        The text content of the model's response.
    """
    client = _get_bedrock_client()

    # Separate system message from conversation
    system_content = None
    converse_messages = []

    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        if role == "system":
            system_content = content
        else:
            # Nova uses "content" as a list of content blocks
            converse_messages.append({
                "role": role,
                "content": [{"text": content}]
            })

    # If json_mode, append instruction to system prompt
    if json_mode and system_content:
        system_content += "\n\nIMPORTANT: You MUST respond with valid JSON only. No markdown, no explanation outside the JSON."
    elif json_mode:
        system_content = "You MUST respond with valid JSON only. No markdown, no explanation outside the JSON."

    # Build the request body for Nova's native format
    body = {
        "messages": converse_messages,
        "inferenceConfig": {
            "maxTokens": max_tokens,
            "temperature": temperature,
        }
    }

    if system_content:
        body["system"] = [{"text": system_content}]

    response = client.invoke_model(
        modelId=model_id,
        body=json.dumps(body),
        contentType="application/json",
        accept="application/json",
    )

    result = json.loads(response["body"].read())
    text = result["output"]["message"]["content"][0]["text"]
    return _strip_fences(text) if json_mode else text


def _strip_fences(text: str) -> str:
    """Strip markdown code fences (```json ... ```) that models sometimes add around JSON."""
    if not text:
        return text
    text = text.strip()
    if text.startswith("```"):
        # Drop the opening fence line (``` or ```json)
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    return text.strip()


def _call_openai_fallback(messages: list[dict], temperature: float = 0.4,
                          max_tokens: int = 2048, json_mode: bool = False) -> Optional[str]:
    """Fallback to OpenAI if Bedrock fails."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)

        kwargs = {
            "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = client.chat.completions.create(**kwargs)
        text = response.choices[0].message.content.strip()
        return _strip_fences(text) if json_mode else text
    except Exception as e:
        logger.warning(f"OpenAI fallback also failed: {e}")
        return None


def chat(messages: list[dict], tier: str = "pro", temperature: float = 0.4,
         max_tokens: int = 2048, json_mode: bool = False) -> str:
    """
    Primary AI interface. Uses Bedrock (Nova) with OpenAI fallback.

    Args:
        messages: OpenAI-style message list [{"role": ..., "content": ...}]
        tier: "pro" | "lite" | "micro" — selects the Nova model
        temperature: Sampling temperature
        max_tokens: Max response tokens
        json_mode: Whether to request JSON output

    Returns:
        Model response text

    Raises:
        RuntimeError if both Bedrock and OpenAI fail
    """
    model_id = MODELS.get(tier, BEDROCK_MODEL_PRO)

    # Try Bedrock first
    try:
        result = _call_bedrock(messages, model_id, temperature, max_tokens, json_mode)
        logger.info(f"Bedrock ({model_id}) responded successfully")
        return result
    except Exception as e:
        logger.warning(f"Bedrock failed ({model_id}): {e}")

    # Fallback to OpenAI
    fallback = _call_openai_fallback(messages, temperature, max_tokens, json_mode)
    if fallback:
        logger.info("OpenAI fallback responded successfully")
        return fallback

    raise RuntimeError(
        f"Both AWS Bedrock ({model_id}) and OpenAI fallback failed. "
        "Check AWS credentials and/or OPENAI_API_KEY."
    )
