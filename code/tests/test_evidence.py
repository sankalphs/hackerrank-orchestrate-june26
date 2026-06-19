"""Unit tests for evidence.py (no API calls)."""

from evidence import _issue_family, evaluate_evidence_standard, find_applicable_requirements

REQUIREMENTS = [
    {
        "requirement_id": "REQ_GENERAL_OBJECT_PART",
        "claim_object": "all",
        "applies_to": "general claim review",
        "minimum_image_evidence": "The claimed object and relevant part should be visible clearly enough to inspect the claimed condition.",
    },
    {
        "requirement_id": "REQ_CAR_BODY_PANEL",
        "claim_object": "car",
        "applies_to": "dent or scratch",
        "minimum_image_evidence": "The claimed car panel or bumper should be visible from an angle where surface marks or deformation can be assessed.",
    },
    {
        "requirement_id": "REQ_PACKAGE_EXTERIOR",
        "claim_object": "package",
        "applies_to": "crushed, torn, or seal damage",
        "minimum_image_evidence": "The package exterior and claimed side, corner, flap, or seal should be visible clearly enough to inspect packaging damage.",
    },
]


def test_issue_family():
    assert _issue_family("car", "dent") == "dent or scratch"
    assert _issue_family("car", "crack") == "crack, broken, or missing part"
    assert _issue_family("package", "torn_packaging") == "crushed, torn, or seal damage"
    assert _issue_family("laptop", "stain") == "water, stain, or label damage"
    assert _issue_family("car", "unknown") == "general"


def test_find_applicable():
    car_dent = find_applicable_requirements("car", "dent", REQUIREMENTS)
    ids = [r["requirement_id"] for r in car_dent]
    assert "REQ_GENERAL_OBJECT_PART" in ids
    assert "REQ_CAR_BODY_PANEL" in ids

    pkg_torn = find_applicable_requirements("package", "torn_packaging", REQUIREMENTS)
    ids = [r["requirement_id"] for r in pkg_torn]
    assert "REQ_PACKAGE_EXTERIOR" in ids


def test_evidence_met():
    met, reason = evaluate_evidence_standard("car", "dent", 2, True, REQUIREMENTS)
    assert met is True
    assert "met" in reason.lower() or "visible" in reason.lower()


def test_evidence_no_usable_images():
    met, reason = evaluate_evidence_standard("car", "dent", 0, False, REQUIREMENTS)
    assert met is False
    assert "no usable" in reason.lower() or "insufficient" in reason.lower()


def test_evidence_part_not_visible():
    met, reason = evaluate_evidence_standard("car", "dent", 1, False, REQUIREMENTS)
    assert met is False
    assert "part" in reason.lower() or "not" in reason.lower()
