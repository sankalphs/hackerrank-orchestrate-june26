"""Evaluation: compare predictions against ground truth, per-column accuracy,
claim_status confusion matrix, and operational metrics.
"""

from __future__ import annotations

from collections import Counter

from schema import OUTPUT_COLUMNS


def _normalize_set_field(actual: str | None, expected: str | None) -> tuple[set[str], set[str]]:
    """Normalize semicolon-separated fields to sets for comparison."""
    a = set()
    e = set()
    if actual:
        a = {x.strip() for x in str(actual).split(";") if x.strip() and x.strip().lower() != "none"}
    if expected:
        e = {
            x.strip() for x in str(expected).split(";") if x.strip() and x.strip().lower() != "none"
        }
    return a, e


def _field_match(actual: str | None, expected: str | None, field: str) -> bool:
    """Compare two field values, with set-aware logic for semicolon fields."""
    a = "" if actual is None else str(actual).strip()
    e = "" if expected is None else str(expected).strip()

    set_fields = {"risk_flags", "supporting_image_ids"}
    if field in set_fields:
        a_set, e_set = _normalize_set_field(a, e)
        return a_set == e_set

    bool_fields = {"evidence_standard_met", "valid_image"}
    if field in bool_fields:
        a_bool = a.lower() in ("true", "1", "yes")
        e_bool = e.lower() in ("true", "1", "yes")
        return a_bool == e_bool

    return a == e


def evaluate_predictions(predicted: list[dict], ground_truth: list[dict]) -> dict:
    """Compute per-column accuracy, claim_status confusion matrix, and overall score.

    Both inputs are lists of dicts keyed by output column names. Rows are matched
    by user_id (assumed to be the first column and unique within the set).
    """
    gt_by_id = {row.get("user_id", ""): row for row in ground_truth}
    pred_by_id = {row.get("user_id", ""): row for row in predicted}

    matched_ids = sorted(set(gt_by_id.keys()) & set(pred_by_id.keys()))

    per_column_correct: dict[str, int] = {col: 0 for col in OUTPUT_COLUMNS}
    per_column_total: dict[str, int] = {col: 0 for col in OUTPUT_COLUMNS}
    confusion: dict[str, Counter] = {}

    total_score = 0.0
    max_score = 0.0

    for uid in matched_ids:
        gt = gt_by_id[uid]
        pred = pred_by_id[uid]

        for col in OUTPUT_COLUMNS:
            if col in {"user_id", "image_paths", "user_claim", "claim_object"}:
                continue
            gt_val = gt.get(col, "")
            pred_val = pred.get(col, "")
            per_column_total[col] += 1
            if _field_match(pred_val, gt_val, col):
                per_column_correct[col] += 1

        gt_status = (gt.get("claim_status") or "").strip().lower()
        pred_status = (pred.get("claim_status") or "").strip().lower()
        confusion.setdefault(gt_status, Counter())[pred_status] += 1

        claim_status_weight = 3.0
        issue_part_weight = 1.0
        other_weight = 0.5

        weighted_correct = 0.0
        weighted_total = 0.0
        if _field_match(pred.get("claim_status"), gt.get("claim_status"), "claim_status"):
            weighted_correct += claim_status_weight
        weighted_total += claim_status_weight

        for col in ("issue_type", "object_part"):
            if _field_match(pred.get(col), gt.get(col), col):
                weighted_correct += issue_part_weight
            weighted_total += issue_part_weight

        for col in ("evidence_standard_met", "severity", "valid_image"):
            if _field_match(pred.get(col), gt.get(col), col):
                weighted_correct += other_weight
            weighted_total += other_weight

        total_score += weighted_correct
        max_score += weighted_total

    per_column_accuracy = {
        col: (per_column_correct[col] / per_column_total[col]) if per_column_total[col] > 0 else 0.0
        for col in OUTPUT_COLUMNS
    }

    return {
        "matched_rows": len(matched_ids),
        "per_column_accuracy": per_column_accuracy,
        "per_column_correct": per_column_correct,
        "per_column_total": per_column_total,
        "confusion_matrix": {k: dict(v) for k, v in confusion.items()},
        "weighted_score": total_score / max_score if max_score > 0 else 0.0,
    }
