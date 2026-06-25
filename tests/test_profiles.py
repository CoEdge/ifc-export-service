"""Tests for the vendored AISC W-shape profile loader."""
import pytest

from app.ifc.profiles import get_profile, has_profile, _load_profiles


def test_loads_full_table():
    profiles = _load_profiles()
    assert len(profiles) == 171


def test_known_designation_has_ishape_dims():
    p = get_profile("W24x68")
    assert p is not None
    # All four I-shape parameters needed for IfcIShapeProfileDef are present.
    for key in ("d", "bf", "tw", "tf"):
        assert key in p and isinstance(p[key], (int, float))
    assert p["designation"] == "W24x68"


def test_lookup_is_case_insensitive():
    lower = get_profile("W16x26")
    upper = get_profile("W16X26")
    assert lower is not None
    assert upper is lower  # same cached record


def test_designation_with_decimal_weight():
    p = get_profile("W6x8.5")
    assert p is not None
    assert p["d"] > 0 and p["bf"] > 0


def test_unknown_designation_returns_none():
    assert get_profile("W99x999") is None
    assert get_profile("") is None
    assert get_profile(None) is None


def test_has_profile():
    assert has_profile("W24x68") is True
    assert has_profile("HSS6x6") is False
    assert has_profile(None) is False


@pytest.mark.parametrize("designation", ["W44x335", "W6x8.5", "W16x26"])
def test_dimensions_positive(designation):
    p = get_profile(designation)
    assert p is not None
    assert p["d"] > 0 and p["bf"] > 0 and p["tw"] > 0 and p["tf"] > 0
