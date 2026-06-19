"""LangGraph shared state schema."""

from __future__ import annotations

from typing import TypedDict


class VisionRecord(TypedDict):
    image_id: str
    image_path: str
    vision_detected_object: str
    vision_detected_parts: list[str]
    normalized_parts: list[str]
    damage_type: str
    visible_severity: str
    is_usable_image: bool
    quality_flags: list[str]
    raw_error: str | None


class ClaimState(TypedDict, total=False):
    user_id: str
    image_paths: list[str]
    user_claim: str
    claim_object: str
    strategy: str

    claimed_parts: list[str]
    claimed_issue_type: str
    history_risk_flags: list[str]
    history_summary: str

    vision_records: list[VisionRecord]

    evidence_standard_met: bool
    evidence_standard_met_reason: str
    contradiction_flag: bool
    contradiction_reasons: list[str]
    aggregated_issue_type: str
    aggregated_object_part: str
    aggregated_severity: str
    supporting_image_ids: list[str]
    valid_image: bool
    risk_flags: list[str]
    base_claim_status: str

    claim_status_justification: str

    final_claim_status: str
    issue_type: str
    object_part: str
    severity: str
