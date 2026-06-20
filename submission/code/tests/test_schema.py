"""Deterministic unit tests for schema normalization/clamp logic (no API calls)."""

from schema import (
    clamp_enum,
    clamp_risk_flags,
    max_severity,
    normalize_part,
)


def test_normalize_part_car():
    assert normalize_part("rear bumper", "car") == "rear_bumper"
    assert normalize_part("Front Bumper", "car") == "front_bumper"
    assert normalize_part("side mirror", "car") == "side_mirror"
    assert normalize_part("trunk", "car") == "body"
    assert normalize_part("nonsense", "car") == "unknown"
    assert normalize_part("", "car") == "unknown"


def test_normalize_part_laptop():
    assert normalize_part("screen", "laptop") == "screen"
    assert normalize_part("display", "laptop") == "screen"
    assert normalize_part("trackpad", "laptop") == "trackpad"
    assert normalize_part("front bumper", "laptop") == "unknown"


def test_normalize_part_package():
    assert normalize_part("package corner", "package") == "package_corner"
    assert normalize_part("seal", "package") == "seal"
    assert normalize_part("box", "package") == "box"


def test_clamp_enum():
    assert clamp_enum("dent", {"dent", "scratch"}) == "dent"
    assert clamp_enum("Scratch", {"dent", "scratch"}) == "scratch"
    assert clamp_enum("glass shatter", {"glass_shatter"}) == "glass_shatter"
    assert clamp_enum("bogus", {"dent"}, default="unknown") == "unknown"
    assert clamp_enum(None, {"dent"}, default="unknown") == "unknown"


def test_max_severity():
    assert max_severity(["low", "high", "medium"]) == "high"
    assert max_severity(["unknown", "low"]) == "low"
    assert max_severity(["unknown"]) == "unknown"
    assert max_severity([]) == "unknown"
    assert max_severity(["none", "low"]) == "low"


def test_clamp_risk_flags():
    flags = clamp_risk_flags(["blurry_image", "Blurry Image", "bogus", "user_history_risk", ""])
    assert flags == ["blurry_image", "user_history_risk"]
    assert clamp_risk_flags([]) == []
