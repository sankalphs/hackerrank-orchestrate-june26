"""OpenAI-compatible LLM clients for Token Router (M3) and NVIDIA NIM (Nemotron).

Both clients share the `openai` SDK pointed at different base URLs. Includes
robust JSON extraction (strips <think> tags that M3 always emits), per-call
token metering via cache.log_call, and rate-limit retry via tenacity.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

import cache
from config import (
    NVIDIA_API_KEY,
    NVIDIA_BASE_URL,
    TOKEN_ROUTER_API_KEY,
    TOKEN_ROUTER_BASE_URL,
)
from json_repair import repair_json
from openai import OpenAI
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


class TransientAPIError(Exception):
    """Raised for 429 / 5xx to trigger tenacity retry."""


def _strip_think(text: str) -> str:
    """Remove <think>...</think> blocks that M3 always emits inline."""
    if not text:
        return ""
    cleaned = _THINK_RE.sub("", text).strip()
    if not cleaned and text:
        if "</think>" in text:
            cleaned = text.split("</think>", 1)[1].strip()
        else:
            cleaned = text
    return cleaned


def extract_json(text: str) -> Any:
    """Best-effort JSON extraction from an LLM response.

    Handles: raw JSON, ```json fenced blocks, leading <think> tags, trailing
    prose. Uses json-repair for partial JSON.
    """
    if not text:
        return None
    cleaned = _strip_think(text)
    if not cleaned:
        cleaned = text
    fence = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1)
    else:
        brace = re.search(r"\{.*\}|\[.*\]", cleaned, re.DOTALL)
        if brace:
            cleaned = brace.group(0)
    try:
        result = json.loads(cleaned)
        return result if isinstance(result, (dict, list)) else None
    except json.JSONDecodeError:
        try:
            result = repair_json(cleaned, return_objects=True)
            return result if isinstance(result, (dict, list)) else None
        except Exception:
            return None


def _make_client(api_key: str, base_url: str) -> OpenAI:
    return OpenAI(api_key=api_key, base_url=base_url, timeout=120.0)


_token_router_client: OpenAI | None = None
_nvidia_client: OpenAI | None = None


def token_router_client() -> OpenAI:
    global _token_router_client
    if _token_router_client is None:
        _token_router_client = _make_client(TOKEN_ROUTER_API_KEY, TOKEN_ROUTER_BASE_URL)
    return _token_router_client


def nvidia_client() -> OpenAI:
    global _nvidia_client
    if _nvidia_client is None:
        _nvidia_client = _make_client(NVIDIA_API_KEY, NVIDIA_BASE_URL)
    return _nvidia_client


def _do_chat(
    client: OpenAI,
    model: str,
    messages: list[dict],
    max_tokens: int,
    temperature: float,
    extra_body: dict | None = None,
) -> tuple[str, int, int]:
    """Execute a chat completion, returning (content, prompt_tokens, completion_tokens).

    Raises TransientAPIError on 429/5xx so tenacity can retry.
    """
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            extra_body=extra_body or {},
        )
        content = resp.choices[0].message.content or ""
        usage = resp.usage
        pt = getattr(usage, "prompt_tokens", 0) or 0
        ct = getattr(usage, "completion_tokens", 0) or 0
        return content, pt, ct
    except Exception as e:
        msg = str(e).lower()
        if (
            "429" in msg
            or "rate" in msg
            or "502" in msg
            or "503" in msg
            or "504" in msg
            or "timeout" in msg
        ):
            raise TransientAPIError(str(e)) from e
        raise


@retry(
    retry=retry_if_exception_type(TransientAPIError),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    stop=stop_after_attempt(5),
    reraise=True,
)
def call_token_router(
    messages: list[dict],
    *,
    model: str,
    max_tokens: int,
    temperature: float,
    extra_body: dict | None = None,
    node: str = "unknown",
    strategy: str = "unknown",
    image_id: str | None = None,
) -> tuple[str, dict | None]:
    """Call Token Router (M3). Returns (raw_content, parsed_json_or_None).

    M3 always emits <think> tags inline regardless of enable_thinking=False, so
    we strip them before JSON parsing.
    """
    start = time.time()
    try:
        content, pt, ct = _do_chat(
            token_router_client(), model, messages, max_tokens, temperature, extra_body
        )
        elapsed = int((time.time() - start) * 1000)
        cache.log_call(
            node=node,
            model=model,
            strategy=strategy,
            image_id=image_id,
            prompt_tokens=pt,
            completion_tokens=ct,
            elapsed_ms=elapsed,
        )
        parsed = extract_json(content)
        return content, parsed
    except TransientAPIError:
        raise
    except Exception as e:
        elapsed = int((time.time() - start) * 1000)
        cache.log_call(
            node=node,
            model=model,
            strategy=strategy,
            image_id=image_id,
            elapsed_ms=elapsed,
            error=f"{type(e).__name__}: {str(e)[:200]}",
        )
        raise


@retry(
    retry=retry_if_exception_type(TransientAPIError),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    stop=stop_after_attempt(5),
    reraise=True,
)
def call_nvidia(
    messages: list[dict],
    *,
    model: str,
    max_tokens: int,
    temperature: float,
    extra_body: dict | None = None,
    node: str = "unknown",
    strategy: str = "unknown",
    image_id: str | None = None,
) -> tuple[str, dict | None]:
    """Call NVIDIA NIM. Returns (raw_content, parsed_json_or_None)."""
    start = time.time()
    try:
        content, pt, ct = _do_chat(
            nvidia_client(), model, messages, max_tokens, temperature, extra_body
        )
        elapsed = int((time.time() - start) * 1000)
        cache.log_call(
            node=node,
            model=model,
            strategy=strategy,
            image_id=image_id,
            prompt_tokens=pt,
            completion_tokens=ct,
            elapsed_ms=elapsed,
        )
        parsed = extract_json(content)
        return content, parsed
    except TransientAPIError:
        raise
    except Exception as e:
        elapsed = int((time.time() - start) * 1000)
        cache.log_call(
            node=node,
            model=model,
            strategy=strategy,
            image_id=image_id,
            elapsed_ms=elapsed,
            error=f"{type(e).__name__}: {str(e)[:200]}",
        )
        raise
