"""Unit tests for llm_clients JSON extraction + think-tag stripping (no API calls)."""

from llm_clients import _strip_think, extract_json


def test_strip_think_basic():
    raw = '<think>reasoning here</think>\n{"a": 1}'
    assert _strip_think(raw) == '{"a": 1}'


def test_strip_think_multiline():
    raw = (
        '<think>\nThe user wants...\nLet me check.\n</think>\n\n{"claimed_parts": ["front_bumper"]}'
    )
    cleaned = _strip_think(raw)
    assert cleaned.startswith("{")


def test_strip_think_no_closing():
    raw = "<think>partial reasoning that got cut off"
    cleaned = _strip_think(raw)
    assert cleaned == raw


def test_strip_think_empty():
    assert _strip_think("") == ""
    assert _strip_think(None or "") == ""


def test_extract_json_raw():
    result = extract_json('{"image_id": "img_1", "damage_type": "dent"}')
    assert result is not None
    assert result["image_id"] == "img_1"
    assert result["damage_type"] == "dent"


def test_extract_json_fenced():
    result = extract_json('```json\n{"image_id": "img_1"}\n```')
    assert result is not None
    assert result["image_id"] == "img_1"


def test_extract_json_with_think():
    raw = '<think>\nI see a car with rear damage.\n</think>\n```json\n{"damage_type": "dent"}\n```'
    result = extract_json(raw)
    assert result is not None
    assert result["damage_type"] == "dent"


def test_extract_json_trailing_prose():
    raw = '{"a": 1}\n\nThat is my answer.'
    result = extract_json(raw)
    assert result is not None
    assert result["a"] == 1


def test_extract_json_invalid():
    assert extract_json("not json at all") is None
    assert extract_json("") is None


def test_extract_json_partial_repair():
    result = extract_json('{"image_id": "img_1", "damage_type":')
    assert result is not None
    assert result.get("image_id") == "img_1"
