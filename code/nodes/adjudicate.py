"""Node D: Adjudication (Minimax M3 via Token Router).

Receives ONLY Node C's deterministic facts and drafts a concise, image-grounded
claim_status_justification. It must not override the status or invent image IDs.
"""

from __future__ import annotations

import logging
from typing import Any

from config import ADJUDICATION_MAX_TOKENS, ADJUDICATION_TEMPERATURE, TEXT_MODEL
from llm_clients import call_token_router
from prompts import ADJUDICATION_SYSTEM, ADJUDICATION_USER
from state import ClaimState

logger = logging.getLogger(__name__)


def adjudicate_node(state: ClaimState) -> dict[str, Any]:
    """Draft the human-readable justification from Node C facts only."""
    strategy = state.get("strategy", "m3_only")
    supporting_ids = state.get("supporting_image_ids", [])

    messages = [
        {"role": "system", "content": ADJUDICATION_SYSTEM},
        {
            "role": "user",
            "content": ADJUDICATION_USER.format(
                claim_object=state.get("claim_object", ""),
                claimed_parts=state.get("claimed_parts", []),
                claimed_issue_type=state.get("claimed_issue_type", "unknown"),
                evidence_standard_met=state.get("evidence_standard_met", False),
                evidence_standard_met_reason=state.get("evidence_standard_met_reason", ""),
                contradiction_flag=state.get("contradiction_flag", False),
                contradiction_reasons=state.get("contradiction_reasons", []),
                aggregated_issue_type=state.get("aggregated_issue_type", "unknown"),
                aggregated_object_part=state.get("aggregated_object_part", "unknown"),
                aggregated_severity=state.get("aggregated_severity", "unknown"),
                base_claim_status=state.get("base_claim_status", "unknown"),
                risk_flags=state.get("risk_flags", []),
                history_summary=state.get("history_summary", ""),
                supporting_image_ids=supporting_ids,
            ),
        },
    ]

    justification = ""
    try:
        _, parsed = call_token_router(
            messages,
            model=TEXT_MODEL,
            max_tokens=ADJUDICATION_MAX_TOKENS,
            temperature=ADJUDICATION_TEMPERATURE,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            node="adjudicate",
            strategy=strategy,
        )
        if parsed and isinstance(parsed, dict):
            justification = (parsed.get("claim_status_justification") or "").strip()
        if not justification:
            justification = _fallback_justification(state)
    except Exception as e:
        logger.warning("Adjudication LLM failed for user %s: %s", state.get("user_id"), e)
        justification = _fallback_justification(state)

    return {"claim_status_justification": justification}


def _fallback_justification(state: ClaimState) -> str:
    """Deterministic fallback if the LLM call fails."""
    base = state.get("base_claim_status", "unknown")
    part = state.get("aggregated_object_part", "unknown")
    issue = state.get("aggregated_issue_type", "unknown")
    supporting = state.get("supporting_image_ids", [])

    if base == "supported":
        ref = f" Images {', '.join(supporting)} support this claim." if supporting else ""
        return f"The images show {issue} on the {part}, supporting the claim.{ref}"
    if base == "contradicted":
        reasons = state.get("contradiction_reasons", [])
        reason_text = reasons[0] if reasons else "the visual evidence does not match the claim"
        return f"The claim is contradicted because {reason_text}."
    return f"There is not enough information to evaluate the {part} claim."
