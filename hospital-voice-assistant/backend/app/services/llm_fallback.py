"""Groq LLM fallback for low-confidence intents (structured JSON output)."""
from __future__ import annotations

import json
from typing import Any

from groq import AsyncGroq
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings
from app.core.logging import logger


_client = AsyncGroq(api_key=settings.GROQ_API_KEY)


SYSTEM_PROMPT = """You are the intent classifier for a hospital voice assistant.

Given a patient utterance (already translated to English) and a catalog of
available hospital services, pick the SINGLE best-matching service or return
null if no service applies.

You MUST respond with a JSON object of shape:
{
  "service_code": "<code from catalog OR null>",
  "confidence": <float between 0 and 1>,
  "slots": {"<slot_name>": "<value>", ...},
  "reason": "<one short sentence>"
}

Never invent a service_code that isn't in the provided catalog.
Never include prose outside the JSON object.
"""


def _catalog_to_prompt(catalog: list[dict[str, Any]]) -> str:
    return "\n".join(
        f"- code={c['code']} | name={c['name']} | keywords={','.join(c.get('keywords', []))}"
        for c in catalog
    )


@retry(reraise=True, stop=stop_after_attempt(2), wait=wait_exponential(min=0.5, max=3))
async def classify_with_llm(
    transcript_en: str,
    catalog: list[dict[str, Any]],
) -> dict[str, Any]:
    user_prompt = (
        f"Utterance (English): {transcript_en}\n\n"
        f"Available services:\n{_catalog_to_prompt(catalog)}\n\n"
        "Return the JSON object now."
    )

    resp = await _client.chat.completions.create(
        model=settings.GROQ_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
        max_tokens=400,
    )
    raw = resp.choices[0].message.content or "{}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("llm.fallback.parse_error", raw=raw)
        data = {}

    return {
        "service_code": data.get("service_code"),
        "confidence": float(data.get("confidence", 0.0)),
        "slots": data.get("slots") or {},
        "reason": data.get("reason", ""),
    }


async def translate_to_english(transcript: str, source_language: str | None) -> str:
    """Ask Groq to normalize/translate the utterance to English (idempotent)."""
    if not transcript.strip():
        return transcript
    if source_language and source_language.lower().startswith("en"):
        return transcript

    resp = await _client.chat.completions.create(
        model=settings.GROQ_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "Translate the user's utterance to natural English. "
                    "Return ONLY the translated sentence, nothing else."
                ),
            },
            {"role": "user", "content": transcript},
        ],
        temperature=0.0,
        max_tokens=200,
    )
    return (resp.choices[0].message.content or transcript).strip()
