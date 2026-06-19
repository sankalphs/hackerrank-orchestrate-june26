"""Unit tests for history.py risk-flag mapping (no API calls)."""

from history import map_history_risk_flags


def test_high_frequency_user():
    history = {
        "user_X": {
            "user_id": "user_X",
            "past_claim_count": "7",
            "accept_claim": "2",
            "manual_review_claim": "2",
            "rejected_claim": "3",
            "last_90_days_claim_count": "4",
            "history_flags": "user_history_risk",
            "history_summary": "Several exaggerated claims",
        }
    }
    flags, summary = map_history_risk_flags("user_X", history)
    assert "user_history_risk" in flags
    assert "manual_review_required" in flags
    assert "exaggerated" in summary


def test_low_risk_user():
    history = {
        "user_Y": {
            "user_id": "user_Y",
            "past_claim_count": "2",
            "accept_claim": "2",
            "manual_review_claim": "0",
            "rejected_claim": "0",
            "last_90_days_claim_count": "1",
            "history_flags": "none",
            "history_summary": "Low-risk user",
        }
    }
    flags, summary = map_history_risk_flags("user_Y", history)
    assert flags == []
    assert "Low-risk" in summary


def test_unknown_user():
    flags, summary = map_history_risk_flags("nobody", {})
    assert flags == []
    assert "No prior" in summary


def test_rejected_only():
    history = {
        "user_Z": {
            "user_id": "user_Z",
            "past_claim_count": "3",
            "accept_claim": "0",
            "manual_review_claim": "0",
            "rejected_claim": "3",
            "last_90_days_claim_count": "0",
            "history_flags": "none",
            "history_summary": "Many rejections",
        }
    }
    flags, _ = map_history_risk_flags("user_Z", history)
    assert "user_history_risk" in flags
    assert "manual_review_required" not in flags
