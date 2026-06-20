"""Node A: Text Parsing & Risk Ingestion.

Uses Minimax M3 (via Token Router) to extract claimed_parts and
claimed_issue_type from the chat transcript, then maps user_history.csv to
deterministic risk flags via Python.
"""

from __future__ import annotations

import logging
from typing import Any

from config import STRATEGY1, TEXT_MODEL, TEXT_PARSE_MAX_TOKENS, TEXT_TEMPERATURE
from history import load_user_history, map_history_risk_flags
from llm_clients import call_token_router
from prompts import PARSE_SYSTEM, PARSE_USER
from schema import ISSUE_TYPES, clamp_enum, normalize_part
from state import ClaimState

logger = logging.getLogger(__name__)


def parse_node(state: ClaimState) -> dict[str, Any]:
    """Extract claimed parts + issue type from the transcript and ingest user history."""
    strategy = state.get("strategy", STRATEGY1)
    transcript = state.get("user_claim", "")
    claim_object = state.get("claim_object", "")

    messages = [
        {"role": "system", "content": PARSE_SYSTEM},
        {"role": "user", "content": PARSE_USER.format(transcript=transcript)},
    ]

    claimed_parts: list[str] = []
    claimed_issue_type = "unknown"

    try:
        _, parsed = call_token_router(
            messages,
            model=TEXT_MODEL,
            max_tokens=TEXT_PARSE_MAX_TOKENS,
            temperature=TEXT_TEMPERATURE,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            node="parse",
            strategy=strategy,
        )
        if parsed and isinstance(parsed, dict):
            raw_parts = parsed.get("claimed_parts", [])
            if isinstance(raw_parts, list):
                claimed_parts = [
                    normalize_part(p, claim_object)
                    for p in raw_parts
                    if isinstance(p, str) and p.strip()
                ]
                claimed_parts = [p for p in claimed_parts if p != "unknown"] or claimed_parts
            raw_issue = parsed.get("claimed_issue_type")
            claimed_issue_type = clamp_enum(raw_issue, ISSUE_TYPES, "unknown")
    except Exception as e:
        logger.warning("Parse node LLM failed for user %s: %s", state.get("user_id"), e)

    if not claimed_parts:
        claimed_parts = ["unknown"]

    history = load_user_history()
    risk_flags, history_summary = map_history_risk_flags(state.get("user_id", ""), history)

    return {
        "claimed_parts": claimed_parts,
        "claimed_issue_type": claimed_issue_type,
        "history_risk_flags": risk_flags,
        "history_summary": history_summary,
    }
