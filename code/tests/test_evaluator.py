"""Unit tests for evaluation/evaluator.py (no API calls)."""

from evaluation.evaluator import evaluate_predictions


def test_perfect_match():
    gt = [
        {
            "user_id": "u1",
            "claim_status": "supported",
            "issue_type": "dent",
            "object_part": "rear_bumper",
            "severity": "medium",
            "evidence_standard_met": "true",
            "valid_image": "true",
            "risk_flags": "none",
            "supporting_image_ids": "img_1",
        },
    ]
    pred = [
        {
            "user_id": "u1",
            "claim_status": "supported",
            "issue_type": "dent",
            "object_part": "rear_bumper",
            "severity": "medium",
            "evidence_standard_met": "true",
            "valid_image": "true",
            "risk_flags": "none",
            "supporting_image_ids": "img_1",
        },
    ]
    result = evaluate_predictions(pred, gt)
    assert result["matched_rows"] == 1
    assert result["per_column_accuracy"]["claim_status"] == 1.0
    assert result["weighted_score"] == 1.0


def test_claim_status_mismatch():
    gt = [
        {
            "user_id": "u1",
            "claim_status": "supported",
            "issue_type": "dent",
            "object_part": "rear_bumper",
            "severity": "medium",
            "evidence_standard_met": "true",
            "valid_image": "true",
            "risk_flags": "none",
            "supporting_image_ids": "img_1",
        }
    ]
    pred = [
        {
            "user_id": "u1",
            "claim_status": "contradicted",
            "issue_type": "dent",
            "object_part": "rear_bumper",
            "severity": "medium",
            "evidence_standard_met": "true",
            "valid_image": "true",
            "risk_flags": "none",
            "supporting_image_ids": "img_1",
        }
    ]
    result = evaluate_predictions(pred, gt)
    assert result["per_column_accuracy"]["claim_status"] == 0.0
    assert result["weighted_score"] < 1.0
    assert result["confusion_matrix"]["supported"]["contradicted"] == 1


def test_set_field_matching():
    gt = [
        {
            "user_id": "u1",
            "claim_status": "supported",
            "issue_type": "dent",
            "object_part": "door",
            "severity": "low",
            "evidence_standard_met": "true",
            "valid_image": "true",
            "risk_flags": "blurry_image;user_history_risk",
            "supporting_image_ids": "img_1;img_2",
        }
    ]
    pred = [
        {
            "user_id": "u1",
            "claim_status": "supported",
            "issue_type": "dent",
            "object_part": "door",
            "severity": "low",
            "evidence_standard_met": "true",
            "valid_image": "true",
            "risk_flags": "user_history_risk;blurry_image",
            "supporting_image_ids": "img_2;img_1",
        }
    ]
    result = evaluate_predictions(pred, gt)
    assert result["per_column_accuracy"]["risk_flags"] == 1.0
    assert result["per_column_accuracy"]["supporting_image_ids"] == 1.0


def test_boolean_field_matching():
    gt = [
        {
            "user_id": "u1",
            "claim_status": "supported",
            "issue_type": "dent",
            "object_part": "door",
            "severity": "low",
            "evidence_standard_met": "false",
            "valid_image": "true",
            "risk_flags": "none",
            "supporting_image_ids": "none",
        }
    ]
    pred = [
        {
            "user_id": "u1",
            "claim_status": "supported",
            "issue_type": "dent",
            "object_part": "door",
            "severity": "low",
            "evidence_standard_met": "false",
            "valid_image": "true",
            "risk_flags": "none",
            "supporting_image_ids": "none",
        }
    ]
    result = evaluate_predictions(pred, gt)
    assert result["per_column_accuracy"]["evidence_standard_met"] == 1.0


def test_no_matches():
    gt = [
        {
            "user_id": "u1",
            "claim_status": "supported",
            "issue_type": "dent",
            "object_part": "door",
            "severity": "low",
            "evidence_standard_met": "true",
            "valid_image": "true",
            "risk_flags": "none",
            "supporting_image_ids": "none",
        }
    ]
    pred = [
        {
            "user_id": "u2",
            "claim_status": "supported",
            "issue_type": "dent",
            "object_part": "door",
            "severity": "low",
            "evidence_standard_met": "true",
            "valid_image": "true",
            "risk_flags": "none",
            "supporting_image_ids": "none",
        }
    ]
    result = evaluate_predictions(pred, gt)
    assert result["matched_rows"] == 0
    assert result["weighted_score"] == 0.0
