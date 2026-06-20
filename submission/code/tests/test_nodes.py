"""Unit tests for Node C (circuit breaker) and Node E (enum-clamp) — pure Python, no API."""

from nodes.circuit import circuit_node
from nodes.clamp import clamp_node


def _state(**kw):
    base = {
        "user_id": "u1",
        "image_paths": ["img_1.jpg"],
        "user_claim": "dent on rear bumper",
        "claim_object": "car",
        "strategy": "m3_only",
        "claimed_parts": ["rear_bumper"],
        "claimed_issue_type": "dent",
        "history_risk_flags": [],
        "history_summary": "low risk",
    }
    base.update(kw)
    return base


def test_circuit_supported():
    state = _state(
        vision_records=[
            {
                "image_id": "img_1",
                "image_path": "img_1.jpg",
                "vision_detected_object": "car",
                "vision_detected_parts": ["rear bumper"],
                "normalized_parts": ["rear_bumper"],
                "damage_type": "dent",
                "visible_severity": "medium",
                "is_usable_image": True,
                "quality_flags": [],
                "raw_error": None,
            }
        ]
    )
    result = circuit_node(state)
    assert result["base_claim_status"] == "supported"
    assert result["evidence_standard_met"] is True
    assert result["contradiction_flag"] is False
    assert result["aggregated_severity"] == "medium"
    assert "img_1" in result["supporting_image_ids"]


def test_circuit_wrong_object():
    state = _state(
        claim_object="car",
        claimed_parts=["rear_bumper"],
        claimed_issue_type="dent",
        vision_records=[
            {
                "image_id": "img_1",
                "image_path": "img_1.jpg",
                "vision_detected_object": "laptop",
                "vision_detected_parts": ["screen"],
                "normalized_parts": ["screen"],
                "damage_type": "crack",
                "visible_severity": "high",
                "is_usable_image": True,
                "quality_flags": [],
                "raw_error": None,
            }
        ],
    )
    result = circuit_node(state)
    assert result["contradiction_flag"] is True
    assert result["base_claim_status"] == "contradicted"
    assert "wrong_object" in result["risk_flags"]


def test_circuit_no_usable_images():
    state = _state(
        vision_records=[
            {
                "image_id": "img_1",
                "image_path": "img_1.jpg",
                "vision_detected_object": "car",
                "vision_detected_parts": ["rear bumper"],
                "normalized_parts": ["rear_bumper"],
                "damage_type": "unknown",
                "visible_severity": "unknown",
                "is_usable_image": False,
                "quality_flags": ["blurry_image"],
                "raw_error": None,
            }
        ],
    )
    result = circuit_node(state)
    assert result["evidence_standard_met"] is False
    assert result["base_claim_status"] == "not_enough_information"


def test_circuit_issue_mismatch():
    state = _state(
        claimed_issue_type="glass_shatter",
        claimed_parts=["windshield"],
        vision_records=[
            {
                "image_id": "img_1",
                "image_path": "img_1.jpg",
                "vision_detected_object": "car",
                "vision_detected_parts": ["windshield"],
                "normalized_parts": ["windshield"],
                "damage_type": "scratch",
                "visible_severity": "low",
                "is_usable_image": True,
                "quality_flags": [],
                "raw_error": None,
            }
        ],
    )
    result = circuit_node(state)
    assert result["contradiction_flag"] is True
    assert "claim_mismatch" in result["risk_flags"]


def test_circuit_non_original_image():
    state = _state(
        vision_records=[
            {
                "image_id": "img_1",
                "image_path": "img_1.jpg",
                "vision_detected_object": "car",
                "vision_detected_parts": ["rear bumper"],
                "normalized_parts": ["rear_bumper"],
                "damage_type": "dent",
                "visible_severity": "medium",
                "is_usable_image": True,
                "quality_flags": ["non_original_image"],
                "raw_error": None,
            }
        ],
    )
    result = circuit_node(state)
    assert result["valid_image"] is False


def test_circuit_history_risk_merged():
    state = _state(
        history_risk_flags=["user_history_risk", "manual_review_required"],
        vision_records=[
            {
                "image_id": "img_1",
                "image_path": "img_1.jpg",
                "vision_detected_object": "car",
                "vision_detected_parts": ["rear bumper"],
                "normalized_parts": ["rear_bumper"],
                "damage_type": "dent",
                "visible_severity": "medium",
                "is_usable_image": True,
                "quality_flags": [],
                "raw_error": None,
            }
        ],
    )
    result = circuit_node(state)
    assert result["contradiction_flag"] is False
    assert result["base_claim_status"] == "supported"


def test_clamp_supported():
    state = {
        "contradiction_flag": False,
        "evidence_standard_met": True,
        "base_claim_status": "supported",
        "claim_object": "car",
        "aggregated_issue_type": "dent",
        "aggregated_object_part": "rear_bumper",
        "aggregated_severity": "medium",
        "risk_flags": ["blurry_image"],
        "supporting_image_ids": ["img_1"],
    }
    result = clamp_node(state)
    assert result["final_claim_status"] == "supported"
    assert result["issue_type"] == "dent"
    assert result["object_part"] == "rear_bumper"
    assert result["severity"] == "medium"
    assert result["risk_flags"] == ["blurry_image"]


def test_clamp_contradiction_overrides():
    state = {
        "contradiction_flag": True,
        "evidence_standard_met": True,
        "base_claim_status": "supported",
        "claim_object": "car",
        "aggregated_issue_type": "bogus_type",
        "aggregated_object_part": "nonsense",
        "aggregated_severity": "super_high",
        "risk_flags": [],
        "supporting_image_ids": [],
    }
    result = clamp_node(state)
    assert result["final_claim_status"] == "contradicted"
    assert result["issue_type"] == "unknown"
    assert result["object_part"] == "unknown"
    assert result["severity"] == "unknown"


def test_clamp_evidence_fail_overrides():
    state = {
        "contradiction_flag": False,
        "evidence_standard_met": False,
        "base_claim_status": "supported",
        "claim_object": "laptop",
        "aggregated_issue_type": "crack",
        "aggregated_object_part": "screen",
        "aggregated_severity": "unknown",
        "risk_flags": [],
        "supporting_image_ids": [],
    }
    result = clamp_node(state)
    assert result["final_claim_status"] == "not_enough_information"
