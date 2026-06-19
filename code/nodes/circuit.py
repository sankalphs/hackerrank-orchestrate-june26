"""Node C: Deterministic Circuit Breaker (pure Python, NO LLM).

Aggregates Node A and Node B outputs using only if/else logic:
- Per-part union matching (not majority vote)
- Evidence standard check against evidence_requirements.csv
- Contradiction detection (object, part, issue type, severity)
- valid_image computation
- supporting_image_ids (deterministic)
- severity aggregation
- base_claim_status decision
"""

from __future__ import annotations

from typing import Any

from evidence import evaluate_evidence_standard, load_evidence_requirements
from schema import (
    RISK_FLAGS,
    clamp_enum,
    clamp_risk_flags,
    max_severity,
)
from state import ClaimState, VisionRecord

OBJECT_MAP = {"car": "car", "laptop": "laptop", "package": "package"}


def _usable_images(records: list[VisionRecord]) -> list[VisionRecord]:
    return [r for r in records if r.get("is_usable_image", True)]


def _part_matches(claimed_part: str, vision_parts: list[str]) -> bool:
    """Check if a claimed part appears in the vision-detected parts."""
    if claimed_part in ("unknown",):
        return True
    for vp in vision_parts:
        if vp == claimed_part:
            return True
    return False


def _issue_mismatch(claimed_issue: str, vision_damage: str, claim_object: str) -> bool:
    """Check if the claimed issue type conflicts with the vision damage type."""
    if claimed_issue in ("unknown", "none") or vision_damage in ("unknown", "none"):
        return False
    if claimed_issue == vision_damage:
        return False
    if claim_object == "package":
        pkg_issues = {"torn_packaging", "crushed_packaging", "water_damage", "stain"}
        if claimed_issue in pkg_issues and vision_damage in pkg_issues:
            return False
    if claim_object in ("car", "laptop"):
        hard_issues = {"crack", "glass_shatter", "broken_part", "missing_part"}
        if claimed_issue in hard_issues and vision_damage in hard_issues:
            return False
    return True


def _severity_exaggeration(claimed_issue: str, vision_severities: list[str]) -> bool:
    """Detect if the claim implies high severity but vision shows low/none."""
    if claimed_issue in ("unknown", "none"):
        return False
    if not vision_severities:
        return False
    max_vis = max_severity(vision_severities)
    if max_vis in ("none", "low") and claimed_issue in {
        "glass_shatter",
        "broken_part",
        "missing_part",
    }:
        return True
    return False


def circuit_node(state: ClaimState) -> dict[str, Any]:
    """The supreme logic gate. Pure Python — no LLM calls."""
    claim_object = state.get("claim_object", "")
    claimed_parts = state.get("claimed_parts", ["unknown"])
    claimed_issue_type = state.get("claimed_issue_type", "unknown")
    vision_records: list[VisionRecord] = state.get("vision_records", [])
    history_risk_flags = state.get("history_risk_flags", [])

    usable = _usable_images(vision_records)
    usable_count = len(usable)

    supported_parts: list[str] = []
    unsupported_parts: list[str] = []
    for cp in claimed_parts:
        found = any(_part_matches(cp, r.get("normalized_parts", [])) for r in usable)
        if found:
            supported_parts.append(cp)
        else:
            unsupported_parts.append(cp)

    claimed_part_visible = len(supported_parts) > 0

    requirements = load_evidence_requirements()
    evidence_met, evidence_reason = evaluate_evidence_standard(
        claim_object, claimed_issue_type, usable_count, claimed_part_visible, requirements
    )

    contradiction_reasons: list[str] = []
    risk_flags: list[str] = []
    wrong_object_detected = False

    for r in vision_records:
        vobj = (r.get("vision_detected_object") or "").lower().strip()
        if vobj not in ("", "unknown") and vobj != claim_object and vobj in OBJECT_MAP:
            wrong_object_detected = True
            if "wrong_object" not in risk_flags:
                risk_flags.append("wrong_object")
            if "object mismatch" not in contradiction_reasons:
                contradiction_reasons.append(
                    f"Image {r['image_id']} shows {vobj} but claim is {claim_object}"
                )

    if wrong_object_detected and usable_count > 0:
        evidence_met = True
        evidence_reason = "Usable images were provided and are sufficient to evaluate the claim (they show a different object)."

    if unsupported_parts and claimed_part_visible:
        for up in unsupported_parts:
            flag = "wrong_object_part" if up != "unknown" else "damage_not_visible"
            if flag not in risk_flags:
                risk_flags.append(flag)

    if not claimed_part_visible and usable_count > 0:
        if "damage_not_visible" not in risk_flags:
            risk_flags.append("damage_not_visible")
        if "claimed part not visible" not in contradiction_reasons:
            contradiction_reasons.append(
                f"None of the usable images show the claimed part(s): {', '.join(claimed_parts)}"
            )

    vision_damage_types = [r.get("damage_type", "unknown") for r in usable]
    if claimed_issue_type not in ("unknown", "none") and vision_damage_types:
        from collections import Counter

        damage_counts = Counter(d for d in vision_damage_types if d not in ("unknown", "none"))
        if damage_counts:
            majority_damage = damage_counts.most_common(1)[0][0]
            if _issue_mismatch(claimed_issue_type, majority_damage, claim_object):
                if "claim_mismatch" not in risk_flags:
                    risk_flags.append("claim_mismatch")
                contradiction_reasons.append(
                    f"Claimed issue '{claimed_issue_type}' but vision shows '{majority_damage}'"
                )

    vision_severities = [r.get("visible_severity", "unknown") for r in usable]
    if _severity_exaggeration(claimed_issue_type, vision_severities):
        if "claim_mismatch" not in risk_flags:
            risk_flags.append("claim_mismatch")
        contradiction_reasons.append(
            f"Claim implies severe damage but vision shows only {max_severity(vision_severities)}"
        )

    for r in vision_records:
        for qf in r.get("quality_flags", []):
            flag = clamp_enum(qf, RISK_FLAGS, "")
            if flag and flag not in risk_flags:
                risk_flags.append(flag)

    for hf in history_risk_flags:
        if hf not in risk_flags:
            risk_flags.append(hf)

    risk_flags = clamp_risk_flags(risk_flags)

    supporting: list[str] = []
    for r in usable:
        parts = r.get("normalized_parts", [])
        damage = r.get("damage_type", "unknown")
        if any(_part_matches(cp, parts) for cp in claimed_parts) and damage not in (
            "none",
            "unknown",
        ):
            if r["image_id"] not in supporting:
                supporting.append(r["image_id"])
    if not supporting and claimed_part_visible:
        for r in usable:
            if any(_part_matches(cp, r.get("normalized_parts", [])) for cp in claimed_parts):
                if r["image_id"] not in supporting:
                    supporting.append(r["image_id"])

    valid_image = True
    for r in vision_records:
        qf = r.get("quality_flags", [])
        if "non_original_image" in qf or "possible_manipulation" in qf:
            valid_image = False
            break
    if usable_count == 0 and len(vision_records) > 0:
        valid_image = False

    aggregated_severity = max_severity(vision_severities) if vision_severities else "unknown"

    primary_part = claimed_parts[0] if claimed_parts else "unknown"
    aggregated_object_part = primary_part

    aggregated_issue_type = claimed_issue_type
    if vision_damage_types:
        from collections import Counter

        damage_counts = Counter(d for d in vision_damage_types if d not in ("unknown", "none"))
        if damage_counts:
            aggregated_issue_type = damage_counts.most_common(1)[0][0]

    contradiction_flag = len(contradiction_reasons) > 0

    if not evidence_met:
        base_status = "not_enough_information"
    elif contradiction_flag:
        base_status = "contradicted"
    else:
        base_status = "supported"

    return {
        "evidence_standard_met": evidence_met,
        "evidence_standard_met_reason": evidence_reason,
        "contradiction_flag": contradiction_flag,
        "contradiction_reasons": contradiction_reasons,
        "aggregated_issue_type": aggregated_issue_type,
        "aggregated_object_part": aggregated_object_part,
        "aggregated_severity": aggregated_severity,
        "supporting_image_ids": supporting,
        "valid_image": valid_image,
        "risk_flags": risk_flags,
        "base_claim_status": base_status,
    }
