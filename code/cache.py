"""Persistent cache for vision API calls + structured call-log for the ops report."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from threading import Lock

from config import CACHE_DIR, CALL_LOG, PROMPT_VERSION, VISION_CACHE

_CACHE_LOCK = Lock()
_LOG_LOCK = Lock()


def _ensure_dirs() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def vision_cache_key(
    image_path: str,
    prompt_version: str = PROMPT_VERSION,
    model: str = "",
    vote_idx: int | None = None,
) -> str:
    """Stable hash key for a vision call: file content hash + prompt version + model + vote round."""
    p = Path(image_path)
    h = hashlib.sha256()
    if p.exists():
        h.update(p.read_bytes())
    else:
        h.update(image_path.encode("utf-8"))
    h.update(prompt_version.encode("utf-8"))
    h.update(model.encode("utf-8"))
    if vote_idx is not None:
        h.update(f"vote{vote_idx}".encode("utf-8"))
    return h.hexdigest()


def load_vision_cache() -> dict[str, dict]:
    _ensure_dirs()
    if VISION_CACHE.exists():
        try:
            return json.loads(VISION_CACHE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_vision_cache(cache: dict[str, dict]) -> None:
    _ensure_dirs()
    tmp = VISION_CACHE.with_suffix(".tmp")
    tmp.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
    tmp.replace(VISION_CACHE)


def get_cached_vision(image_path: str, model: str = "", vote_idx: int | None = None) -> dict | None:
    key = vision_cache_key(image_path, model=model, vote_idx=vote_idx)
    with _CACHE_LOCK:
        cache = load_vision_cache()
        return cache.get(key)


def set_cached_vision(image_path: str, record: dict, model: str = "", vote_idx: int | None = None) -> None:
    key = vision_cache_key(image_path, model=model, vote_idx=vote_idx)
    with _CACHE_LOCK:
        cache = load_vision_cache()
        cache[key] = record
        save_vision_cache(cache)


def log_call(
    *,
    node: str,
    model: str,
    strategy: str,
    image_id: str | None = None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    elapsed_ms: int = 0,
    cached: bool = False,
    error: str | None = None,
) -> None:
    _ensure_dirs()
    entry = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "node": node,
        "model": model,
        "strategy": strategy,
        "image_id": image_id,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "elapsed_ms": elapsed_ms,
        "cached": cached,
        "error": error,
    }
    with _LOG_LOCK:
        with CALL_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_call_log() -> list[dict]:
    if not CALL_LOG.exists():
        return []
    out: list[dict] = []
    for line in CALL_LOG.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def reset_call_log() -> None:
    _ensure_dirs()
    CALL_LOG.write_text("", encoding="utf-8")
