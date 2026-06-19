"""Main entry point: read claims.csv, run the LangGraph pipeline, write output.csv.

Usage:
    python -m code.main                          # run on dataset/claims.csv
    python -m code.main --strategy m3_only       # Strategy 1 (default)
    python -m code.main --strategy m3_text_nemotron_vision  # Strategy 2
    python -m code.main --sample                 # run on sample_claims.csv
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
from pathlib import Path

from config import CLAIMS_CSV, DATASET_DIR, OUTPUT_CSV, SAMPLE_CLAIMS_CSV, STRATEGY1
from graph import build_graph
from schema import OUTPUT_COLUMNS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _split_image_paths_raw(raw: str) -> list[str]:
    """Split semicolon-separated image paths without resolving."""
    if not raw:
        return []
    return [p.strip() for p in raw.split(";") if p.strip()]


def _split_image_paths(raw: str) -> list[str]:
    """Split semicolon-separated image paths, resolving relative paths against dataset dir."""
    if not raw:
        return []
    paths = [p.strip() for p in raw.split(";") if p.strip()]
    resolved: list[str] = []
    for p in paths:
        pp = Path(p)
        if not pp.is_absolute():
            resolved.append(str(DATASET_DIR / p))
        else:
            resolved.append(p)
    return resolved


def _format_output_row(state: dict) -> dict:
    """Convert final state to an output.csv row with exact column order."""
    risk_flags = state.get("risk_flags", [])
    risk_str = ";".join(risk_flags) if risk_flags else "none"

    supporting = state.get("supporting_image_ids", [])
    supporting_str = ";".join(supporting) if supporting else "none"

    image_paths_out = state.get("image_paths_original") or state.get("image_paths", [])

    return {
        "user_id": state.get("user_id", ""),
        "image_paths": ";".join(image_paths_out),
        "user_claim": state.get("user_claim", ""),
        "claim_object": state.get("claim_object", ""),
        "evidence_standard_met": "true" if state.get("evidence_standard_met", False) else "false",
        "evidence_standard_met_reason": state.get("evidence_standard_met_reason", ""),
        "risk_flags": risk_str,
        "issue_type": state.get("issue_type", "unknown"),
        "object_part": state.get("object_part", "unknown"),
        "claim_status": state.get("final_claim_status", "not_enough_information"),
        "claim_status_justification": state.get("claim_status_justification", ""),
        "supporting_image_ids": supporting_str,
        "valid_image": "true" if state.get("valid_image", False) else "false",
        "severity": state.get("severity", "unknown"),
    }


def run_pipeline(
    input_csv: Path,
    output_csv: Path,
    strategy: str = STRATEGY1,
    limit: int | None = None,
) -> int:
    """Run the full pipeline on input_csv and write results to output_csv.

    Returns the number of rows processed.
    """
    app = build_graph()

    with input_csv.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if limit:
        rows = rows[:limit]

    output_rows: list[dict] = []
    for i, row in enumerate(rows):
        user_id = row.get("user_id", f"row_{i}")
        original_image_paths = _split_image_paths_raw(row.get("image_paths", ""))
        image_paths = _split_image_paths(row.get("image_paths", ""))
        logger.info(
            "[%d/%d] Processing %s (%d images, %s)",
            i + 1,
            len(rows),
            user_id,
            len(image_paths),
            row.get("claim_object", ""),
        )

        initial_state = {
            "user_id": user_id,
            "image_paths": image_paths,
            "image_paths_original": original_image_paths,
            "user_claim": row.get("user_claim", ""),
            "claim_object": row.get("claim_object", ""),
            "strategy": strategy,
        }

        try:
            final_state = app.invoke(initial_state)
            output_row = _format_output_row(final_state)
        except Exception as e:
            logger.error("Failed on %s: %s", user_id, e)
            output_row = _format_output_row(
                {
                    **initial_state,
                    "image_paths": original_image_paths,
                    "final_claim_status": "not_enough_information",
                }
            )
            output_row["claim_status_justification"] = f"Processing error: {type(e).__name__}"

        output_rows.append(output_row)

    with output_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(output_rows)

    logger.info("Wrote %d rows to %s", len(output_rows), output_csv)
    return len(output_rows)


def main():
    parser = argparse.ArgumentParser(description="Run the damage-claim verification pipeline")
    parser.add_argument(
        "--strategy", default=STRATEGY1, help="Strategy: m3_only or m3_text_nemotron_vision"
    )
    parser.add_argument(
        "--sample", action="store_true", help="Run on sample_claims.csv instead of claims.csv"
    )
    parser.add_argument("--limit", type=int, default=None, help="Max rows to process (for testing)")
    parser.add_argument("--output", default=None, help="Output CSV path (default: output.csv)")
    args = parser.parse_args()

    input_csv = SAMPLE_CLAIMS_CSV if args.sample else CLAIMS_CSV
    output_csv = Path(args.output) if args.output else OUTPUT_CSV

    if not input_csv.exists():
        logger.error("Input CSV not found: %s", input_csv)
        sys.exit(1)

    count = run_pipeline(input_csv, output_csv, args.strategy, args.limit)
    logger.info("Done. %d rows processed.", count)


if __name__ == "__main__":
    main()
