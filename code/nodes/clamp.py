"""Node E: Enum-Clamp Layer (pure Python, NO LLM).

Intercepts the final status before writing to output.csv and forces all values
into the exact HackerRank schema strings.
"""

from __future__ import annotations

from typing import Any

from schema import (
    CLAIM_STATUS,
    ISSUE_TYPES,
    OBJECT_PARTS,
    SEVERITIES,
    clamp_enum,
    clamp_risk_flags,
)
from state import ClaimState


def clamp_node(state: ClaimState) -> dict[str, Any]:
    """Force every output field into the allowed enum set."""
    contradiction_flag = state.get("contradiction_flag", False)
    evidence_met = state.get("evidence_standard_met", True)
    base_status = state.get("base_claim_status", "not_enough_information")

    if contradiction_flag:
        final_status = "contradicted"
    elif not evidence_met:
        final_status = "not_enough_information"
    else:
        final_status = clamp_enum(base_status, CLAIM_STATUS, "not_enough_information")

    claim_object = state.get("claim_object", "")
    allowed_parts = OBJECT_PARTS.get(claim_object, set())

    issue_type = clamp_enum(state.get("aggregated_issue_type"), ISSUE_TYPES, "unknown")
    object_part = clamp_enum(state.get("aggregated_object_part"), allowed_parts, "unknown")
    severity = clamp_enum(state.get("aggregated_severity"), SEVERITIES, "unknown")

    risk_flags = clamp_risk_flags(state.get("risk_flags", []))

    supporting = state.get("supporting_image_ids", [])
    if not isinstance(supporting, list):
        supporting = [supporting] if supporting else []
    supporting = [s for s in supporting if isinstance(s, str) and s.strip()]

    return {
        "final_claim_status": final_status,
        "issue_type": issue_type,
        "object_part": object_part,
        "severity": severity,
        "risk_flags": risk_flags,
        "supporting_image_ids": supporting,
    }
