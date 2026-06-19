"""Node B: Visual Inspection Loop.

Loops through image_paths, making a separate VLM API call per image to
preserve high-resolution detail. Strategy 1 uses M3 (Token Router); Strategy 2
uses Nemotron Omni (NVIDIA NIM). Includes:
- asyncio.Semaphore(1) + sleep for NIM rate limiting
- tenacity retry on 429/5xx (in llm_clients)
- sha256-keyed caching
- token metering via cache.log_call
- hard-case escape hatch: re-call with thinking enabled when damage_type=unknown
"""

from __future__ import annotations

import asyncio
import base64
import logging
from pathlib import Path
from typing import Any

import cache
from config import (
    DATASET_DIR,
    NIM_SEMAPHORE,
    NIM_SLEEP_SECONDS,
    STRATEGY1,
    VISION_MAX_TOKENS,
    VISION_MODEL_STRATEGY1,
    VISION_MODEL_STRATEGY2,
    VISION_TEMPERATURE,
)
from llm_clients import call_nvidia, call_token_router
from prompts import VISION_SYSTEM, VISION_USER
from schema import ISSUE_TYPES, SEVERITIES, clamp_enum, normalize_part
from state import ClaimState, VisionRecord

logger = logging.getLogger(__name__)

_NIM_SEMAPHORE: asyncio.Semaphore | None = None


def _get_nim_semaphore() -> asyncio.Semaphore:
    global _NIM_SEMAPHORE
    if _NIM_SEMAPHORE is None:
        _NIM_SEMAPHORE = asyncio.Semaphore(NIM_SEMAPHORE)
    return _NIM_SEMAPHORE


def _image_to_data_url(path: str) -> str:
    full = Path(path)
    if not full.is_absolute():
        full = DATASET_DIR / path
    with full.open("rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:image/jpeg;base64,{b64}"


def _image_id_from_path(path: str) -> str:
    return Path(path).stem


def _build_vision_messages(image_path: str, image_id: str) -> list[dict]:
    data_url = _image_to_data_url(image_path)
    return [
        {"role": "system", "content": VISION_SYSTEM},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": VISION_USER.format(image_id=image_id)},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        },
    ]


def _normalize_vision_record(
    raw: dict, image_id: str, image_path: str, claim_object: str
) -> VisionRecord:
    """Clamp a raw VLM JSON response into a schema-valid VisionRecord."""
    parts_raw = raw.get("vision_detected_parts", [])
    if not isinstance(parts_raw, list):
        parts_raw = [parts_raw] if parts_raw else []
    normalized = [normalize_part(p, claim_object) for p in parts_raw if isinstance(p, str)]
    normalized = list(dict.fromkeys(normalized))

    return VisionRecord(
        image_id=image_id,
        image_path=image_path,
        vision_detected_object=raw.get("vision_detected_object", "unknown"),
        vision_detected_parts=[p for p in parts_raw if isinstance(p, str)],
        normalized_parts=normalized,
        damage_type=clamp_enum(raw.get("damage_type"), ISSUE_TYPES, "unknown"),
        visible_severity=clamp_enum(raw.get("visible_severity"), SEVERITIES, "unknown"),
        is_usable_image=bool(raw.get("is_usable_image", True)),
        quality_flags=[
            f for f in (raw.get("quality_flags") or []) if isinstance(f, str) and f.strip()
        ],
        raw_error=None,
    )


async def _call_vision_single(image_path: str, strategy: str, claim_object: str) -> VisionRecord:
    """Call the vision model for one image, with caching + retry + escape hatch."""
    image_id = _image_id_from_path(image_path)

    cached = cache.get_cached_vision(image_path)
    if cached is not None:
        cache.log_call(
            node="vision",
            model=(VISION_MODEL_STRATEGY1 if strategy == STRATEGY1 else VISION_MODEL_STRATEGY2),
            strategy=strategy,
            image_id=image_id,
            cached=True,
        )
        return _normalize_vision_record(cached, image_id, image_path, claim_object)

    messages = _build_vision_messages(image_path, image_id)

    if strategy == STRATEGY1:
        model = VISION_MODEL_STRATEGY1
        _, parsed = await asyncio.to_thread(
            call_token_router,
            messages,
            model=model,
            max_tokens=VISION_MAX_TOKENS,
            temperature=VISION_TEMPERATURE,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            node="vision",
            strategy=strategy,
            image_id=image_id,
        )
    else:
        model = VISION_MODEL_STRATEGY2
        sem = _get_nim_semaphore()
        async with sem:
            await asyncio.sleep(NIM_SLEEP_SECONDS)
            _, parsed = await asyncio.to_thread(
                call_nvidia,
                messages,
                model=model,
                max_tokens=VISION_MAX_TOKENS,
                temperature=VISION_TEMPERATURE,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}, "top_k": 1},
                node="vision",
                strategy=strategy,
                image_id=image_id,
            )

    if not parsed or not isinstance(parsed, dict):
        record: VisionRecord = VisionRecord(
            image_id=image_id,
            image_path=image_path,
            vision_detected_object="unknown",
            vision_detected_parts=[],
            normalized_parts=[],
            damage_type="unknown",
            visible_severity="unknown",
            is_usable_image=False,
            quality_flags=[],
            raw_error="VLM returned unparseable JSON",
        )
        return record

    record = _normalize_vision_record(parsed, image_id, image_path, claim_object)

    if record["is_usable_image"] and record["damage_type"] == "unknown":
        record = await _escape_hatch(image_path, image_id, strategy, claim_object, record)

    cache.set_cached_vision(image_path, dict(record))
    return record


async def _escape_hatch(
    image_path: str, image_id: str, strategy: str, claim_object: str, base_record: VisionRecord
) -> VisionRecord:
    """Re-call the image with thinking enabled when damage_type is unknown."""
    logger.info("Escape hatch triggered for %s (unknown damage)", image_id)
    messages = _build_vision_messages(image_path, image_id)
    try:
        if strategy == STRATEGY1:
            _, parsed = await asyncio.to_thread(
                call_token_router,
                messages,
                model=VISION_MODEL_STRATEGY1,
                max_tokens=4000,
                temperature=VISION_TEMPERATURE,
                extra_body={"chat_template_kwargs": {"enable_thinking": True}},
                node="vision_escape",
                strategy=strategy,
                image_id=image_id,
            )
        else:
            sem = _get_nim_semaphore()
            async with sem:
                await asyncio.sleep(NIM_SLEEP_SECONDS)
                _, parsed = await asyncio.to_thread(
                    call_nvidia,
                    messages,
                    model=VISION_MODEL_STRATEGY2,
                    max_tokens=4000,
                    temperature=VISION_TEMPERATURE,
                    extra_body={
                        "chat_template_kwargs": {"enable_thinking": True, "reasoning_budget": 2048},
                    },
                    node="vision_escape",
                    strategy=strategy,
                    image_id=image_id,
                )
        if parsed and isinstance(parsed, dict):
            return _normalize_vision_record(parsed, image_id, image_path, claim_object)
    except Exception as e:
        logger.warning("Escape hatch failed for %s: %s", image_id, e)
    return base_record


async def _vision_loop_async(
    image_paths: list[str], strategy: str, claim_object: str
) -> list[VisionRecord]:
    tasks = [_call_vision_single(p, strategy, claim_object) for p in image_paths]
    return await asyncio.gather(*tasks)


def vision_node(state: ClaimState) -> dict[str, Any]:
    """LangGraph node: run the vision loop synchronously (wraps async)."""
    image_paths = state.get("image_paths", [])
    strategy = state.get("strategy", STRATEGY1)
    claim_object = state.get("claim_object", "")

    if not image_paths:
        return {"vision_records": []}

    records = asyncio.run(_vision_loop_async(image_paths, strategy, claim_object))
    return {"vision_records": records}
