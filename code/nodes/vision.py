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
from collections import Counter
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
    VISION_VOTE_ROUNDS,
    VISION_VOTE_TEMPERATURE,
)
from llm_clients import call_nvidia, call_token_router
from prompts import VISION_SYSTEM, VISION_USER
from schema import ISSUE_TYPES, SEVERITIES, clamp_enum, normalize_part
from state import ClaimState, VisionRecord

logger = logging.getLogger(__name__)


def _majority_vote(values: list[str]) -> str:
    """Return the most common value; ties broken by first occurrence."""
    if not values:
        return "unknown"
    counts: Counter = Counter(values)
    return counts.most_common(1)[0][0]


def _vote_severity(severities: list[str]) -> str:
    """Majority vote on severity; if all differ, take the median (conservative)."""
    if not severities:
        return "unknown"
    counts: Counter = Counter(severities)
    if counts.most_common(1)[0][1] >= 2:
        return counts.most_common(1)[0][0]
    rank = {"none": 0, "low": 1, "medium": 2, "high": 3, "unknown": -1}
    known = [s for s in severities if s in rank and s != "unknown"]
    if not known:
        return "unknown"
    known.sort(key=lambda s: rank[s])
    return known[len(known) // 2]


def _vote_quality_flags(all_flags: list[list[str]]) -> list[str]:
    """Flags that appear in majority of runs (>= half)."""
    if not all_flags:
        return []
    threshold = len(all_flags) / 2.0
    counts: Counter = Counter()
    for flags in all_flags:
        for f in set(flags):
            counts[f] += 1
    return [f for f, c in counts.items() if c >= threshold]


def _vote_parts(all_parts: list[list[str]], fallback_all: list[list[str]]) -> list[str]:
    """Parts that appear in majority of runs; if none, fall back to union."""
    if not all_parts:
        return []
    threshold = len(all_parts) / 2.0
    counts: Counter = Counter()
    for parts in all_parts:
        for p in set(parts):
            counts[p] += 1
    voted = [p for p, c in counts.items() if c >= threshold]
    if not voted:
        voted = list(set(p for parts in fallback_all for p in parts))
    return voted


def _vote_records(records: list[VisionRecord], claim_object: str) -> VisionRecord:
    """Combine N vision records via majority voting into a single consensus record."""
    if len(records) == 1:
        return records[0]
    image_id = records[0]["image_id"]
    image_path = records[0]["image_path"]

    objects = [r.get("vision_detected_object", "unknown") for r in records]
    damage_types = [r.get("damage_type", "unknown") for r in records]
    severities = [r.get("visible_severity", "unknown") for r in records]
    usable = [r.get("is_usable_image", True) for r in records]
    all_quality = [r.get("quality_flags", []) for r in records]
    all_parts_raw = [r.get("vision_detected_parts", []) for r in records]
    all_parts_norm = [r.get("normalized_parts", []) for r in records]

    voted_object = _majority_vote(objects)
    voted_damage = _majority_vote(damage_types)
    voted_severity = _vote_severity(severities)
    voted_usable = any(usable)
    voted_quality = _vote_quality_flags(all_quality)
    voted_parts_raw = _vote_parts(all_parts_raw, all_parts_raw)
    voted_parts_norm = _vote_parts(all_parts_norm, all_parts_norm)

    return VisionRecord(
        image_id=image_id,
        image_path=image_path,
        vision_detected_object=voted_object,
        vision_detected_parts=voted_parts_raw,
        normalized_parts=voted_parts_norm,
        damage_type=voted_damage,
        visible_severity=voted_severity,
        is_usable_image=voted_usable,
        quality_flags=voted_quality,
        raw_error=None,
    )


def _get_nim_semaphore() -> asyncio.Semaphore:
    """Create or return the NIM semaphore for the current event loop."""
    try:
        current_loop = asyncio.get_running_loop()
        if getattr(_get_nim_semaphore, "_loop", None) is not current_loop:
            _get_nim_semaphore._sem = asyncio.Semaphore(NIM_SEMAPHORE)
            _get_nim_semaphore._loop = current_loop
        return _get_nim_semaphore._sem
    except RuntimeError:
        sem = asyncio.Semaphore(NIM_SEMAPHORE)
        return sem


def _image_to_data_url(path: str) -> str:
    full = Path(path)
    if not full.is_absolute():
        full = DATASET_DIR / path
    raw = full.read_bytes()

    header = raw[:20]
    is_avif = b"ftypavif" in header or b"ftypavis" in header
    if is_avif:
        from io import BytesIO

        try:
            from PIL import Image
        except ImportError:
            Image = None
        if Image is not None:
            try:
                img = Image.open(BytesIO(raw))
                if img.mode in ("RGBA", "LA", "P"):
                    img = img.convert("RGB")
                buf = BytesIO()
                img.save(buf, format="JPEG", quality=90)
                raw = buf.getvalue()
            except Exception as e:
                logger.warning("AVIF conversion failed for %s: %s", path, e)
                raise

    b64 = base64.b64encode(raw).decode("utf-8")
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


async def _call_vision_single(
    image_path: str, strategy: str, claim_object: str, vote_idx: int = 0
) -> VisionRecord:
    """Call the vision model for one image, with caching + retry + escape hatch.

    vote_idx > 0 enables self-consistency voting (higher temperature for diversity).
    """
    image_id = _image_id_from_path(image_path)
    model = VISION_MODEL_STRATEGY1 if strategy == STRATEGY1 else VISION_MODEL_STRATEGY2

    cached = cache.get_cached_vision(image_path, model=model, vote_idx=vote_idx)
    if cached is not None:
        cache.log_call(
            node="vision",
            model=model,
            strategy=strategy,
            image_id=image_id,
            cached=True,
        )
        return _normalize_vision_record(cached, image_id, image_path, claim_object)

    try:
        messages = _build_vision_messages(image_path, image_id)
    except Exception as e:
        logger.warning("Image build failed for %s: %s", image_id, e)
        cache.log_call(
            node="vision",
            model=model,
            strategy=strategy,
            image_id=image_id,
            error=f"image_build_failed: {type(e).__name__}: {str(e)[:100]}",
        )
        return VisionRecord(
            image_id=image_id,
            image_path=image_path,
            vision_detected_object="unknown",
            vision_detected_parts=[],
            normalized_parts=[],
            damage_type="unknown",
            visible_severity="unknown",
            is_usable_image=False,
            quality_flags=[],
            raw_error=f"image_build_failed: {type(e).__name__}",
        )

    temp = VISION_VOTE_TEMPERATURE if vote_idx > 0 else VISION_TEMPERATURE
    parsed = None
    api_error = None
    if strategy == STRATEGY1:
        try:
            _, parsed = await asyncio.to_thread(
                call_token_router,
                messages,
                model=model,
                max_tokens=VISION_MAX_TOKENS,
                temperature=temp,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
                node="vision",
                strategy=strategy,
                image_id=image_id,
            )
        except Exception as e:
            api_error = f"{type(e).__name__}: {str(e)[:200]}"
            logger.warning("Vision API failed for %s: %s", image_id, api_error)
    else:
        sem = _get_nim_semaphore()
        async with sem:
            await asyncio.sleep(NIM_SLEEP_SECONDS)
            try:
                _, parsed = await asyncio.to_thread(
                    call_nvidia,
                    messages,
                    model=model,
                    max_tokens=VISION_MAX_TOKENS,
                    temperature=temp,
                    extra_body={"chat_template_kwargs": {"enable_thinking": False}, "top_k": 1},
                    node="vision",
                    strategy=strategy,
                    image_id=image_id,
                )
            except Exception as e:
                api_error = f"{type(e).__name__}: {str(e)[:200]}"
                logger.warning("Vision API failed for %s: %s", image_id, api_error)

    if api_error and parsed is None:
        return VisionRecord(
            image_id=image_id,
            image_path=image_path,
            vision_detected_object="unknown",
            vision_detected_parts=[],
            normalized_parts=[],
            damage_type="unknown",
            visible_severity="unknown",
            is_usable_image=False,
            quality_flags=[],
            raw_error=api_error,
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

    if record["is_usable_image"] and record["damage_type"] == "unknown" and vote_idx == 0:
        record = await _escape_hatch(image_path, image_id, strategy, claim_object, record)

    cache.set_cached_vision(image_path, dict(record), model=model, vote_idx=vote_idx)
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
    """Run N=VISION_VOTE_ROUNDS calls per image in parallel, then majority-vote."""
    tasks = []
    for p in image_paths:
        for vote_idx in range(VISION_VOTE_ROUNDS):
            tasks.append(_call_vision_single(p, strategy, claim_object, vote_idx))
    flat = await asyncio.gather(*tasks)

    records: list[VisionRecord] = []
    for i, p in enumerate(image_paths):
        per_image = flat[i * VISION_VOTE_ROUNDS:(i + 1) * VISION_VOTE_ROUNDS]
        non_error = [r for r in per_image if not r.get("raw_error")]
        if not non_error:
            records.append(per_image[0])
            continue
        records.append(_vote_records(non_error, claim_object))
    return records


def vision_node(state: ClaimState) -> dict[str, Any]:
    """LangGraph node: run the vision loop synchronously (wraps async)."""
    image_paths = state.get("image_paths", [])
    strategy = state.get("strategy", STRATEGY1)
    claim_object = state.get("claim_object", "")

    if not image_paths:
        return {"vision_records": []}

    records = asyncio.run(_vision_loop_async(image_paths, strategy, claim_object))
    return {"vision_records": records}
