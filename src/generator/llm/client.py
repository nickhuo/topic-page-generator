"""OpenRouter client wrapper.

Direct httpx calls (not the openai SDK) so respx can mock the full surface in
tests. OpenAI's chat-completions request shape is well-documented and
OpenRouter is wire-compatible. Using httpx also avoids the openai SDK's
internal http client lifecycle.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from generator.llm.trace_buffer import push as _push_trace
from generator.schema import LLMCall

_T = TypeVar("_T", bound=BaseModel)

_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
_TRANSIENT = (httpx.TimeoutException, httpx.NetworkError)

_STAGE_FALLBACK_MODELS = {
    "triage": "anthropic/claude-haiku-4-5",
    "disambiguate": "anthropic/claude-sonnet-4-6",
    "aesthetic": "anthropic/claude-haiku-4-5",
    "extract": "anthropic/claude-haiku-4-5",
    "consistency": "anthropic/claude-haiku-4-5",
}


def get_default_model(stage: str) -> str:
    """Resolve the per-stage model at call time so .env loaded later is respected."""
    env_key = f"MODEL_{stage.upper()}"
    return os.getenv(env_key) or _STAGE_FALLBACK_MODELS[stage]


# Per-million-token pricing snapshot (USD). Used only for the trace; not load-bearing.
# Keys are model identifiers as passed to OpenRouter.
_PRICING_USD_PER_1M = {
    "anthropic/claude-haiku-4-5": {"input": 1.00, "output": 5.00},
    "anthropic/claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
}


class LLMConfigError(RuntimeError):
    """Raised when required LLM configuration is missing (e.g. no API key)."""


class LLMOutputError(RuntimeError):
    """Raised when the LLM returns output that fails Pydantic validation twice."""


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    rates = _PRICING_USD_PER_1M.get(model)
    if not rates:
        return 0.0
    return round(
        (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000,
        6,
    )


def _strip_provider_unsupported_keywords(schema: Any) -> Any:
    """Remove JSON Schema keywords that some OpenRouter providers reject.

    Amazon Bedrock's Converse API rejects `minimum`/`maximum` on number types
    and `minItems`/`maxItems` on array types, even when `strict: false`.
    Pydantic emits these from `Field(ge=, le=)` and `Field(min_length=, max_length=)`
    bounds. We strip them here and rely on the `_clamp_confidences` walker plus
    the validation-retry loop to enforce bounds.
    """
    UNSUPPORTED = {
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "minItems",
        "maxItems",
    }
    if isinstance(schema, dict):
        return {
            k: _strip_provider_unsupported_keywords(v)
            for k, v in schema.items()
            if k not in UNSUPPORTED
        }
    if isinstance(schema, list):
        return [_strip_provider_unsupported_keywords(item) for item in schema]
    return schema


def _clamp_confidences(obj: Any) -> Any:
    """Walk parsed JSON and clamp confidence-like floats to [0, 1].

    Names taken from schema.md: confidence, preset_confidence, overall,
    cross_source_agreement. Recursively applied so nested signals objects
    are also corrected.
    """
    KEYS = {"confidence", "preset_confidence", "overall", "cross_source_agreement"}
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in KEYS and isinstance(v, (int, float)):
                obj[k] = max(0.0, min(1.0, float(v)))
            else:
                _clamp_confidences(v)
    elif isinstance(obj, list):
        for item in obj:
            _clamp_confidences(item)
    return obj


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, max=4),
    retry=retry_if_exception_type(_TRANSIENT),
)
async def _post(client: httpx.AsyncClient, body: dict) -> httpx.Response:
    resp = await client.post(_ENDPOINT, json=body)
    if resp.status_code in (429, 500, 502, 503, 504):
        raise httpx.NetworkError(f"transient {resp.status_code}")
    return resp


async def call_structured(
    model: str,
    messages: list[dict],
    response_model: type[_T],
    *,
    max_validation_retries: int = 1,
) -> _T:
    """One LLM call → validated Pydantic instance. Records cost/tokens/duration."""
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise LLMConfigError("OPENROUTER_API_KEY is not set; cannot call OpenRouter.")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/nickhuo/topic-page-generator",
        "X-Title": "topic-page-generator",
    }
    body = {
        "model": model,
        "messages": list(messages),
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": response_model.__name__,
                "schema": _strip_provider_unsupported_keywords(
                    response_model.model_json_schema()
                ),
                # `strict: True` is OFF: Pydantic's anyOf-for-Optional shape
                # is rejected by some OpenRouter-routed providers (Bedrock).
                # The validation-retry loop below provides correctness.
                "strict": False,
            },
        },
        "temperature": 0.0,
        # Cap output tokens — routing-brain outputs are small (~500-800 tokens)
        # and uncapped requests trigger OpenRouter's per-request credit-budget
        # rejection for keys with low limits.
        "max_tokens": 4096,
    }

    attempts = 0
    last_error: Exception | None = None
    async with httpx.AsyncClient(headers=headers, timeout=60.0) as client:
        while attempts <= max_validation_retries:
            attempts += 1
            t0 = time.perf_counter()
            resp = await _post(client, body)
            duration_ms = int((time.perf_counter() - t0) * 1000)

            if resp.status_code != 200:
                raise LLMOutputError(
                    f"OpenRouter returned status {resp.status_code}: {resp.text[:300]}"
                )

            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            in_tok = int(usage.get("prompt_tokens", 0))
            out_tok = int(usage.get("completion_tokens", 0))

            _push_trace(
                LLMCall(
                    model=model,
                    input_tokens=in_tok,
                    output_tokens=out_tok,
                    cost_usd=_estimate_cost(model, in_tok, out_tok),
                    duration_ms=duration_ms,
                )
            )

            try:
                parsed = json.loads(content)
            except json.JSONDecodeError as exc:
                last_error = exc
                body["messages"].append(
                    {
                        "role": "user",
                        "content": f"Your previous reply was not valid JSON ({exc}). Reply with the corrected JSON object only.",
                    }
                )
                continue

            _clamp_confidences(parsed)

            try:
                return response_model.model_validate(parsed)
            except ValidationError as exc:
                last_error = exc
                body["messages"].append(
                    {
                        "role": "user",
                        "content": (
                            f"Your previous JSON failed schema validation: {exc.json()}. "
                            "Reply with corrected JSON conforming to the same schema. Do not include any prose."
                        ),
                    }
                )

    raise LLMOutputError(
        f"LLM output failed validation after {attempts} attempts: {last_error}"
    )
