"""Allowed enum values, normalization maps, and clamp helpers.

These are the single source of truth for the allowed output values defined in
problem_statement.md. Node C (circuit breaker) and Node E (enum-clamp) use these
to force LLM/vision output into schema-valid strings.
"""

from __future__ import annotations

CLAIM_STATUS = {"supported", "contradicted", "not_enough_information"}

ISSUE_TYPES = {
    "dent",
    "scratch",
    "crack",
    "glass_shatter",
    "broken_part",
    "missing_part",
    "torn_packaging",
    "crushed_packaging",
    "water_damage",
    "stain",
    "none",
    "unknown",
}

CAR_PARTS = {
    "front_bumper",
    "rear_bumper",
    "door",
    "hood",
    "windshield",
    "side_mirror",
    "headlight",
    "taillight",
    "fender",
    "quarter_panel",
    "body",
    "unknown",
}

LAPTOP_PARTS = {
    "screen",
    "keyboard",
    "trackpad",
    "hinge",
    "lid",
    "corner",
    "port",
    "base",
    "body",
    "unknown",
}

PACKAGE_PARTS = {
    "box",
    "package_corner",
    "package_side",
    "seal",
    "label",
    "contents",
    "item",
    "unknown",
}

RISK_FLAGS = {
    "none",
    "blurry_image",
    "cropped_or_obstructed",
    "low_light_or_glare",
    "wrong_angle",
    "wrong_object",
    "wrong_object_part",
    "damage_not_visible",
    "claim_mismatch",
    "possible_manipulation",
    "non_original_image",
    "text_instruction_present",
    "user_history_risk",
    "manual_review_required",
}

SEVERITIES = {"none", "low", "medium", "high", "unknown"}

SEVERITY_RANK = {"none": 0, "low": 1, "medium": 2, "high": 3, "unknown": -1}

OBJECT_PARTS = {
    "car": CAR_PARTS,
    "laptop": LAPTOP_PARTS,
    "package": PACKAGE_PARTS,
}

PART_NORMALIZE = {
    "front bumper": "front_bumper",
    "rear bumper": "rear_bumper",
    "back bumper": "rear_bumper",
    "side mirror": "side_mirror",
    "quarter panel": "quarter_panel",
    "package corner": "package_corner",
    "package side": "package_side",
    "rear light": "taillight",
    "tail light": "taillight",
    "taillight": "taillight",
    "tail_light": "taillight",
    "head light": "headlight",
    "front light": "headlight",
    "wind shield": "windshield",
    "front glass": "windshield",
    "trunk": "body",
    "trunk lid": "body",
    "trunk_lid": "body",
    "rear panel": "body",
    "rear body panel": "body",
    "rear windshield": "windshield",
    "rear window": "windshield",
    "license plate": "body",
    "license plate area": "body",
    "exhaust": "body",
    "exhaust pipe": "body",
    "undercarriage": "body",
    "tire": "body",
    "wheel": "body",
    "door panel": "door",
    "screen": "screen",
    "display": "screen",
    "keyboard": "keyboard",
    "trackpad": "trackpad",
    "hinge": "hinge",
    "lid": "lid",
    "corner": "corner",
    "port": "port",
    "base": "base",
    "body": "body",
    "box": "box",
    "seal": "seal",
    "label": "label",
    "contents": "contents",
    "item": "item",
}


def normalize_part(raw: str, claim_object: str) -> str:
    """Normalize a free-text part name to an allowed enum for the object."""
    if not raw:
        return "unknown"
    key = raw.strip().lower().replace("-", " ").replace("_", " ")
    mapped = PART_NORMALIZE.get(key)
    if mapped:
        allowed = OBJECT_PARTS.get(claim_object, set())
        if mapped in allowed:
            return mapped
        return "unknown"
    direct = raw.strip().lower().replace(" ", "_")
    allowed = OBJECT_PARTS.get(claim_object, set())
    if direct in allowed:
        return direct
    if direct in PART_NORMALIZE.values():
        return "unknown"
    return "unknown"


def clamp_enum(value: str | None, allowed: set[str], default: str = "unknown") -> str:
    """Force a value into the allowed enum set, else default."""
    if value is None:
        return default
    v = value.strip().lower()
    if v in allowed:
        return v
    v_underscore = v.replace(" ", "_")
    if v_underscore in allowed:
        return v_underscore
    return default


def max_severity(severities: list[str]) -> str:
    """Return the highest severity, treating unknown conservatively."""
    if not severities:
        return "unknown"
    known = [s for s in severities if s in SEVERITY_RANK and s != "unknown"]
    if not known:
        return "unknown"
    return max(known, key=lambda s: SEVERITY_RANK[s])


def clamp_risk_flags(flags: list[str]) -> list[str]:
    """Filter to allowed risk flags, de-dup, drop empty; empty -> []."""
    seen: list[str] = []
    for f in flags:
        if not f:
            continue
        v = f.strip().lower()
        if v in RISK_FLAGS and v not in seen:
            seen.append(v)
        else:
            v_us = v.replace(" ", "_").replace("-", "_")
            if v_us in RISK_FLAGS and v_us not in seen:
                seen.append(v_us)
    return seen


OUTPUT_COLUMNS = [
    "user_id",
    "image_paths",
    "user_claim",
    "claim_object",
    "evidence_standard_met",
    "evidence_standard_met_reason",
    "risk_flags",
    "issue_type",
    "object_part",
    "claim_status",
    "claim_status_justification",
    "supporting_image_ids",
    "valid_image",
    "severity",
]
