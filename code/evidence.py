"""Load evidence_requirements.csv and determine whether a claim meets its
minimum image-evidence standard.

The minimum_image_evidence column is free-text, not a clean integer. We parse
it heuristically: the default rule is that at least one usable image showing
the claimed part must be present.
"""

from __future__ import annotations

import csv
from pathlib import Path

from config import EVIDENCE_REQUIREMENTS_CSV


def load_evidence_requirements(
    csv_path: Path = EVIDENCE_REQUIREMENTS_CSV,
) -> list[dict]:
    """Return list of requirement rows."""
    rows: list[dict] = []
    if not csv_path.exists():
        return rows
    with csv_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def _issue_family(claim_object: str, issue_type: str) -> str:
    """Classify the issue into a family that maps to evidence requirements."""
    issue = (issue_type or "").strip().lower()
    obj = (claim_object or "").strip().lower()

    if issue in {"dent", "scratch"}:
        return "dent or scratch"
    if issue in {"crack", "glass_shatter", "broken_part", "missing_part"}:
        if obj == "car":
            return "crack, broken, or missing part"
        return "broken"
    if issue in {"torn_packaging", "crushed_packaging"}:
        return "crushed, torn, or seal damage"
    if issue in {"water_damage", "stain"}:
        return "water, stain, or label damage"
    if issue in {"none", "unknown"}:
        return "general"
    return "general"


def find_applicable_requirements(
    claim_object: str,
    issue_type: str,
    requirements: list[dict] | None = None,
) -> list[dict]:
    """Return the subset of evidence requirements that apply to this claim."""
    if requirements is None:
        requirements = load_evidence_requirements()
    family = _issue_family(claim_object, issue_type)
    applicable: list[dict] = []
    for req in requirements:
        req_obj = (req.get("claim_object") or "").strip().lower()
        req_family = (req.get("applies_to") or "").strip().lower()
        if req_obj == "all":
            applicable.append(req)
        elif req_obj == claim_object and (req_family == family or not req_family):
            applicable.append(req)
        elif req_obj == claim_object and family in req_family:
            applicable.append(req)
    return applicable


def evaluate_evidence_standard(
    claim_object: str,
    issue_type: str,
    usable_image_count: int,
    claimed_part_visible: bool,
    requirements: list[dict] | None = None,
) -> tuple[bool, str]:
    """Determine whether the evidence standard is met.

    Returns (met: bool, reason: str). Default rule: at least one usable image
    showing the claimed part must be present.
    """
    applicable = find_applicable_requirements(claim_object, issue_type, requirements)

    if usable_image_count < 1:
        reason = "No usable images were submitted for review."
        if applicable:
            req_text = applicable[0].get("minimum_image_evidence", "")
            if req_text:
                reason = f"Insufficient usable images. Requirement: {req_text}"
        return False, reason

    if not claimed_part_visible:
        reason = "The submitted images do not clearly show the claimed object or part."
        return False, reason

    req_texts = [
        r.get("minimum_image_evidence", "") for r in applicable if r.get("minimum_image_evidence")
    ]
    if req_texts:
        reason = f"Evidence standard met. Requirement: {req_texts[0]}"
    else:
        reason = "The claimed object and relevant part are visible clearly enough to inspect."
    return True, reason
