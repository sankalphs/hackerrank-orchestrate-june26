"""Load user_history.csv and map historical claim patterns to risk flags.

This module is pure Python and deterministic — no LLM calls.
"""

from __future__ import annotations

import csv
from pathlib import Path

from config import (
    HISTORY_MANUAL_REVIEW_THRESHOLD,
    HISTORY_REJECTED_THRESHOLD,
    HISTORY_RISK_90D_THRESHOLD,
    USER_HISTORY_CSV,
)


def load_user_history(csv_path: Path = USER_HISTORY_CSV) -> dict[str, dict]:
    """Return {user_id: row_dict} from user_history.csv."""
    history: dict[str, dict] = {}
    if not csv_path.exists():
        return history
    with csv_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            uid = (row.get("user_id") or "").strip()
            if uid:
                history[uid] = row
    return history


def _safe_int(value: str | None, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return default


def map_history_risk_flags(
    user_id: str,
    history: dict[str, dict] | None = None,
) -> tuple[list[str], str]:
    """Map a user's historical claim record to deterministic risk flags.

    Returns (risk_flags, history_summary). risk_flags may contain:
    user_history_risk, manual_review_required. Empty list if low-risk.

    Rules (from AGENTS.md plan + sample analysis):
    - last_90_days_claim_count >= 3  -> user_history_risk
    - rejected_claim >= 2            -> user_history_risk
    - manual_review_claim >= 2       -> manual_review_required
    - history_flags contains 'user_history_risk' -> user_history_risk (carry-through)
    """
    if history is None:
        history = load_user_history()
    row = history.get(user_id)
    if not row:
        return [], "No prior claim history"

    flags: list[str] = []
    last_90 = _safe_int(row.get("last_90_days_claim_count"))
    rejected = _safe_int(row.get("rejected_claim"))
    manual_review = _safe_int(row.get("manual_review_claim"))
    raw_flags = (row.get("history_flags") or "").strip().lower()

    if last_90 >= HISTORY_RISK_90D_THRESHOLD:
        flags.append("user_history_risk")
    if rejected >= HISTORY_REJECTED_THRESHOLD:
        if "user_history_risk" not in flags:
            flags.append("user_history_risk")
    if manual_review >= HISTORY_MANUAL_REVIEW_THRESHOLD:
        flags.append("manual_review_required")
    if "user_history_risk" in raw_flags and "user_history_risk" not in flags:
        flags.append("user_history_risk")

    summary = (row.get("history_summary") or "").strip()
    return flags, summary
