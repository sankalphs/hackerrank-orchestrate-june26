"""Evaluation entry point: run both strategies on sample_claims.csv,
compare accuracy, and generate evaluation_report.md.
"""

from __future__ import annotations

import argparse
import csv
import logging
from pathlib import Path

import cache
from config import (
    REPO_ROOT,
    SAMPLE_CLAIMS_CSV,
    STRATEGY1,
    STRATEGY2,
)
from graph import build_graph
from main import _format_output_row, _split_image_paths, _split_image_paths_raw
from schema import OUTPUT_COLUMNS

from evaluation.evaluator import evaluate_predictions
from evaluation.report import build_report

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

EVAL_DIR = REPO_ROOT / "evaluation"
EVAL_OUTPUT_DIR = EVAL_DIR
REPORT_PATH = EVAL_DIR / "evaluation_report.md"


def _load_ground_truth(csv_path: Path) -> list[dict]:
    rows: list[dict] = []
    with csv_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def _run_strategy(strategy: str, ground_truth: list[dict], limit: int | None = None) -> list[dict]:
    """Run the pipeline on a strategy and return output rows matching ground_truth order."""
    app = build_graph()
    gt_by_id = {row.get("user_id", ""): row for row in ground_truth}
    ids = list(gt_by_id.keys())
    if limit:
        ids = ids[:limit]

    output_rows: list[dict] = []
    for uid in ids:
        gt_row = gt_by_id[uid]
        original_paths = _split_image_paths_raw(gt_row.get("image_paths", ""))
        resolved_paths = _split_image_paths(gt_row.get("image_paths", ""))

        initial_state = {
            "user_id": uid,
            "image_paths": resolved_paths,
            "image_paths_original": original_paths,
            "user_claim": gt_row.get("user_claim", ""),
            "claim_object": gt_row.get("claim_object", ""),
            "strategy": strategy,
        }

        try:
            final_state = app.invoke(initial_state)
            output_rows.append(_format_output_row(final_state))
        except Exception as e:
            logger.error("Strategy %s failed on %s: %s", strategy, uid, e)
            output_rows.append(
                _format_output_row(
                    {**initial_state, "final_claim_status": "not_enough_information"}
                )
            )

    return output_rows


def _write_predictions(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description="Evaluate the damage-claim pipeline")
    parser.add_argument(
        "--limit", type=int, default=None, help="Max rows to evaluate (for testing)"
    )
    parser.add_argument(
        "--reset-cache",
        action="store_true",
        help="Clear call log and vision cache before evaluation",
    )
    parser.add_argument("--strategy1-only", action="store_true", help="Run only Strategy 1")
    parser.add_argument("--strategy2-only", action="store_true", help="Run only Strategy 2")
    args = parser.parse_args()

    if args.reset_cache:
        cache.reset_call_log()
        cache.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        if cache.VISION_CACHE.exists():
            cache.VISION_CACHE.unlink()

    ground_truth = _load_ground_truth(SAMPLE_CLAIMS_CSV)
    logger.info("Loaded %d ground-truth rows from %s", len(ground_truth), SAMPLE_CLAIMS_CSV)

    results: dict = {}

    if not args.strategy2_only:
        logger.info("=== Running Strategy 1: %s ===", STRATEGY1)
        s1_rows = _run_strategy(STRATEGY1, ground_truth, args.limit)
        _write_predictions(s1_rows, EVAL_OUTPUT_DIR / f"predictions_{STRATEGY1}.csv")
        results["strategy1"] = evaluate_predictions(s1_rows, ground_truth)

    if not args.strategy1_only:
        logger.info("=== Running Strategy 2: %s ===", STRATEGY2)
        s2_rows = _run_strategy(STRATEGY2, ground_truth, args.limit)
        _write_predictions(s2_rows, EVAL_OUTPUT_DIR / f"predictions_{STRATEGY2}.csv")
        results["strategy2"] = evaluate_predictions(s2_rows, ground_truth)

    report = build_report(
        results.get(
            "strategy1",
            {
                "matched_rows": 0,
                "per_column_accuracy": {},
                "per_column_correct": {},
                "per_column_total": {},
                "confusion_matrix": {},
                "weighted_score": 0.0,
            },
        ),
        results.get(
            "strategy2",
            {
                "matched_rows": 0,
                "per_column_accuracy": {},
                "per_column_correct": {},
                "per_column_total": {},
                "confusion_matrix": {},
                "weighted_score": 0.0,
            },
        ),
    )
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")
    logger.info("Report written to %s", REPORT_PATH)


if __name__ == "__main__":
    main()
