"""Node C: Deterministic Circuit Breaker (pure Python, NO LLM).

Aggregates Node A and Node B outputs using only if/else logic:
- Per-part union matching (not majority vote)
- Evidence standard check against evidence_requirements.csv
- Contradiction detection (object, part, issue type, severity)
- valid_image computation
- supporting_image_ids (deterministic)
- severity aggregation (with damage-type-implied caps)
- base_claim_status decision
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from evidence import evaluate_evidence_standard, load_evidence_requirements
from schema import (
    RISK_FLAGS,
    SEVERITY_RANK,
    clamp_enum,
    clamp_risk_flags,
    max_severity,
)
from state import ClaimState, VisionRecord

OBJECT_MAP = {"car": "car", "laptop": "laptop", "package": "package"}

DAMAGE_TYPE_SEVERITY_CAP = {
    "scratch": "low",
    "stain": "low",
    "dent": "medium",
    "crack": "medium",
    "torn_packaging": "medium",
    "crushed_packaging": "medium",
    "water_damage": "medium",
    "glass_shatter": "medium",
    "broken_part": "medium",
    "missing_part": "high",
}

PART_SEVERITY_FLOOR = {}

_SEVERITY_ORDER = {"none": 0, "low": 1, "medium": 2, "high": 3, "unknown": -1}


def _clamp_severity_with_part(severity, damage_type, part):
    """Apply damage-type cap + part-aware floor."""
    if severity in ("none", "unknown") or not damage_type:
        return severity
    cap = DAMAGE_TYPE_SEVERITY_CAP.get(damage_type)
    if cap:
        cap_rank = _SEVERITY_ORDER.get(cap, 3)
        sev_rank = _SEVERITY_ORDER.get(severity, 1)
        if sev_rank > cap_rank:
            severity = cap
    floor = PART_SEVERITY_FLOOR.get((damage_type, part))
    if floor:
        floor_rank = _SEVERITY_ORDER.get(floor, 1)
        sev_rank = _SEVERITY_ORDER.get(severity, 1)
        if sev_rank < floor_rank:
            severity = floor
    return severity


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


def _cap_severity_by_damage(severity: str, damage_type: str) -> str:
    """Cap severity based on damage type. E.g. scratch is never above 'low'."""
    if damage_type not in DAMAGE_TYPE_SEVERITY_CAP:
        return severity
    cap = DAMAGE_TYPE_SEVERITY_CAP[damage_type]
    if severity in ("none", "unknown"):
        return severity
    if SEVERITY_RANK.get(severity, 0) > SEVERITY_RANK.get(cap, 3):
        return cap
    return severity


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


def _refine_damage_type(
    damage_type: str, severity: str, claim_object: str, parts: list[str]
) -> str:
    """Post-process the vision model's damage_type based on severity + part context.

    If the vision model says 'glass_shatter' but the severity is only 'medium'
    or lower, it's almost certainly a 'crack' (true shattering would be high
    severity). Only applies to glass parts (windshield).
    """
    if damage_type == "glass_shatter" and severity in ("medium", "low", "none"):
        if "windshield" in parts or claim_object == "laptop":
            return "crack"
    if damage_type == "water_damage" and severity in ("none", "low"):
        return "stain"
    return damage_type


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

    cropped_or_blurry_count = sum(
        1
        for r in vision_records
        if any(qf in r.get("quality_flags", []) for qf in ("cropped_or_obstructed", "blurry_image"))
    )
    if len(vision_records) > 0 and cropped_or_blurry_count == len(vision_records):
        evidence_met = False
        evidence_reason = (
            "All submitted images are cropped or blurry and cannot be used to evaluate the claim."
        )

    contradiction_reasons: list[str] = []
    risk_flags: list[str] = []
    wrong_object_detected = False

    other_count = 0
    specific_count = 0
    for r in vision_records:
        vobj = (r.get("vision_detected_object") or "").lower().strip()
        if vobj == "other":
            other_count += 1
        elif vobj in OBJECT_MAP:
            specific_count += 1

    for r in vision_records:
        vobj = (r.get("vision_detected_object") or "").lower().strip()
        if (
            vobj == "other"
            and claim_object in ("car", "laptop", "package")
            and other_count > specific_count
        ):
            wrong_object_detected = True
            if "wrong_object" not in risk_flags:
                risk_flags.append("wrong_object")
            if "object mismatch" not in contradiction_reasons:
                contradiction_reasons.append(
                    f"Image {r['image_id']} does not show a {claim_object}"
                )
        elif vobj not in ("", "unknown") and vobj != claim_object and vobj in OBJECT_MAP:
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

    part_not_visible_but_images_exist = (
        not claimed_part_visible and usable_count > 0 and not wrong_object_detected
    )

    if part_not_visible_but_images_exist:
        if "damage_not_visible" not in risk_flags:
            risk_flags.append("damage_not_visible")

    vision_damage_types = [r.get("damage_type", "unknown") for r in usable]
    vision_damage_on_claimed_parts: list[str] = []
    if claimed_part_visible:
        for r in usable:
            r_parts = r.get("normalized_parts", [])
            if any(_part_matches(cp, r_parts) for cp in claimed_parts):
                vision_damage_on_claimed_parts.append(r.get("damage_type", "unknown"))

    if claimed_issue_type not in ("unknown", "none") and vision_damage_on_claimed_parts:
        damage_counts = Counter(
            d for d in vision_damage_on_claimed_parts if d not in ("unknown", "none")
        )
        if damage_counts:
            majority_damage, majority_count = damage_counts.most_common(1)[0]
            total_non_unknown = sum(damage_counts.values())
            if majority_count >= max(2, total_non_unknown * 0.6):
                if _issue_mismatch(claimed_issue_type, majority_damage, claim_object):
                    if "claim_mismatch" not in risk_flags:
                        risk_flags.append("claim_mismatch")
                    contradiction_reasons.append(
                        f"Claimed issue '{claimed_issue_type}' but vision shows '{majority_damage}' on the claimed part"
                    )
        elif claimed_part_visible and claimed_issue_type not in ("unknown", "none"):
            no_damage_visible_on_part = all(
                d in ("none", "unknown") for d in vision_damage_on_claimed_parts
            )
            contents_claim_with_no_visible_damage = (
                "contents" in claimed_parts
                and claimed_issue_type in ("missing_part",)
                and no_damage_visible_on_part
            )
            if contents_claim_with_no_visible_damage:
                if "damage_not_visible" not in risk_flags:
                    risk_flags.append("damage_not_visible")
            elif no_damage_visible_on_part and claimed_issue_type not in ("missing_part",):
                if "damage_not_visible" not in risk_flags:
                    risk_flags.append("damage_not_visible")

    vision_severities = [r.get("visible_severity", "unknown") for r in usable]
    vision_severities_on_claimed: list[str] = []
    if claimed_part_visible:
        for r in usable:
            r_parts = r.get("normalized_parts", [])
            if any(_part_matches(cp, r_parts) for cp in claimed_parts):
                vision_severities_on_claimed.append(r.get("visible_severity", "unknown"))

    sev_check = vision_severities_on_claimed or vision_severities
    if _severity_exaggeration(claimed_issue_type, sev_check):
        if "claim_mismatch" not in risk_flags:
            risk_flags.append("claim_mismatch")
        contradiction_reasons.append(
            f"Claim implies severe damage but vision shows only {max_severity(sev_check)}"
        )

    transcript = state.get("user_claim", "") or ""
    transcript_lower = transcript.lower()
    severity_words = [
        "bad",
        "pretty bad",
        "very bad",
        "extremely",
        "severe",
        "severely",
        "heavy",
        "heavily",
        "completely",
        "totally",
        "destroyed",
        "shattered",
        "major",
        "massive",
        "huge",
        "terrible",
    ]
    transcript_severity_exaggeration = any(w in transcript_lower for w in severity_words)
    if (
        transcript_severity_exaggeration
        and sev_check
        and max_severity(sev_check) in ("none", "low")
        and claimed_issue_type not in ("unknown", "none")
    ):
        if "claim_mismatch" not in risk_flags:
            risk_flags.append("claim_mismatch")
        if not any(
            "severity" in r.lower() or "exaggerat" in r.lower() for r in contradiction_reasons
        ):
            contradiction_reasons.append(
                "User describes severe damage but images show only minor issues"
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

    if wrong_object_detected:
        aggregated_issue_type = "unknown"
        aggregated_severity = "unknown"
    elif claimed_part_visible and vision_damage_on_claimed_parts:
        refined_damages = []
        for r in usable:
            r_parts = r.get("normalized_parts", [])
            if any(_part_matches(cp, r_parts) for cp in claimed_parts):
                dmg = r.get("damage_type", "unknown")
                sev = _cap_severity_by_damage(r.get("visible_severity", "unknown"), dmg)
                refined_damages.append(_refine_damage_type(dmg, sev, claim_object, r_parts))
        damage_counts = Counter(d for d in refined_damages if d not in ("unknown", "none"))
        if damage_counts:
            aggregated_issue_type = damage_counts.most_common(1)[0][0]
        else:
            aggregated_issue_type = claimed_issue_type
        capped_severities: list[str] = []
        for r in usable:
            r_parts = r.get("normalized_parts", [])
            if any(_part_matches(cp, r_parts) for cp in claimed_parts):
                sev = r.get("visible_severity", "unknown")
                dmg = r.get("damage_type", "unknown")
                refined_dmg = _refine_damage_type(dmg, sev, claim_object, r_parts)
                matched_part = next(
                    (cp for cp in claimed_parts if any(_part_matches(cp, p) for p in r_parts)),
                    claimed_parts[0],
                )
                clamped = _cap_severity_by_damage(sev, refined_dmg)
                clamped = _clamp_severity_with_part(clamped, refined_dmg, matched_part)
                capped_severities.append(clamped)
        aggregated_severity = max_severity(capped_severities) if capped_severities else "unknown"
    else:
        refined_all = []
        for r, dmg, sev in zip(usable, vision_damage_types, vision_severities, strict=False):
            r_parts = r.get("normalized_parts", [])
            refined_all.append(_refine_damage_type(dmg, sev, claim_object, r_parts))
        damage_counts = Counter(d for d in refined_all if d not in ("unknown", "none"))
        if damage_counts:
            aggregated_issue_type = damage_counts.most_common(1)[0][0]
        else:
            aggregated_issue_type = "unknown"
        if not vision_severities:
            aggregated_severity = "unknown"
        else:
            capped_severities = []
            for s, t in zip(vision_severities, vision_damage_types, strict=False):
                refined_t = _refine_damage_type(t, s, claim_object, [])
                clamped = _cap_severity_by_damage(s, refined_t)
                clamped = _clamp_severity_with_part(clamped, refined_t, claimed_parts[0])
                capped_severities.append(clamped)
            aggregated_severity = max_severity(capped_severities)

    primary_part = claimed_parts[0] if claimed_parts else "unknown"
    aggregated_object_part = "unknown" if wrong_object_detected else primary_part

    contradiction_flag = len(contradiction_reasons) > 0

    if wrong_object_detected:
        base_status = "contradicted"
    elif part_not_visible_but_images_exist:
        base_status = "not_enough_information"
    elif not evidence_met:
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
