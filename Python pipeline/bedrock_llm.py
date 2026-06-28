"""
AWS Bedrock LLM client for the Python ingestion/summarization pipeline.

Provides a drop-in replacement for OpenAI calls using Amazon Nova models
via AWS Bedrock, with automatic fallback to OpenAI if Bedrock fails.

Usage:
    from bedrock_llm import llm_chat

    result = llm_chat(
        system_prompt="You are an analyst...",
        user_prompt="Summarize this article...",
        json_mode=True,
        temperature=0.3,
    )
    # result is a string (the model's text response)
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# Load .env
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).resolve().parent / ".env"
    if _env_path.exists():
        load_dotenv(_env_path, override=True)
except ImportError:
    pass

# --- Configuration ---
AWS_REGION = os.environ.get("AWS_DEFAULT_REGION", "us-west-2")
BEDROCK_MODEL_LITE = os.environ.get("BEDROCK_MODEL_LITE", "us.amazon.nova-lite-v1:0")
BEDROCK_MODEL_MICRO = os.environ.get("BEDROCK_MODEL_MICRO", "us.amazon.nova-micro-v1:0")

# For summarization we use Nova Lite (good balance of speed and quality)
DEFAULT_MODEL = BEDROCK_MODEL_LITE


def _get_bedrock_client():
    """Create a Bedrock runtime client."""
    import boto3
    return boto3.client("bedrock-runtime", region_name=AWS_REGION)


def llm_chat(
    system_prompt: str,
    user_prompt: str,
    model_id: str | None = None,
    temperature: float = 0.3,
    max_tokens: int = 1024,
    json_mode: bool = False,
) -> str | None:
    """
    Call Bedrock (Nova) with fallback to OpenAI.

    Args:
        system_prompt: System instructions
        user_prompt: User content
        model_id: Override Bedrock model (default: Nova Lite)
        temperature: Sampling temperature
        max_tokens: Max response tokens
        json_mode: If True, instruct model to return JSON only

    Returns:
        Model response text, or None if both providers fail
    """
    model = model_id or DEFAULT_MODEL

    # Try Bedrock first
    result = _call_bedrock(system_prompt, user_prompt, model, temperature, max_tokens, json_mode)
    if result is not None:
        return result

    # Fallback to OpenAI
    result = _call_openai(system_prompt, user_prompt, temperature, max_tokens, json_mode)
    if result is not None:
        return result

    logger.error("Both Bedrock and OpenAI failed.")
    return None


def _call_bedrock(
    system_prompt: str,
    user_prompt: str,
    model_id: str,
    temperature: float,
    max_tokens: int,
    json_mode: bool,
) -> str | None:
    """Call AWS Bedrock with Amazon Nova format."""
    try:
        client = _get_bedrock_client()

        system_text = system_prompt
        if json_mode:
            system_text += "\n\nIMPORTANT: Respond with ONLY a valid JSON object. No markdown fences, no explanation outside JSON."

        body = {
            "messages": [
                {"role": "user", "content": [{"text": user_prompt}]}
            ],
            "system": [{"text": system_text}],
            "inferenceConfig": {
                "maxTokens": max_tokens,
                "temperature": temperature,
            }
        }

        response = client.invoke_model(
            modelId=model_id,
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json",
        )

        result = json.loads(response["body"].read())
        text = result["output"]["message"]["content"][0]["text"]

        # Strip markdown fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        return text

    except Exception as e:
        logger.warning(f"Bedrock call failed ({model_id}): {e}")
        return None


def _call_openai(
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    max_tokens: int,
    json_mode: bool,
) -> str | None:
    """Fallback to OpenAI."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)

        kwargs = {
            "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = client.chat.completions.create(**kwargs)
        text = response.choices[0].message.content.strip()

        # Strip markdown fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        return text

    except Exception as e:
        logger.warning(f"OpenAI fallback failed: {e}")
        return None
