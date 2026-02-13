import pytest
from app.services.unit_converter import (
    FEET_TO_METERS,
    ft_to_m,
    convert_positions,
    convert_elevation,
    convert_dimension,
)


class TestFtToM:
    def test_zero(self):
        assert ft_to_m(0.0) == 0.0

    def test_one_foot(self):
        assert ft_to_m(1.0) == pytest.approx(0.3048)

    def test_ten_feet(self):
        assert ft_to_m(10.0) == pytest.approx(3.048)

    def test_negative(self):
        assert ft_to_m(-5.0) == pytest.approx(-5.0 * FEET_TO_METERS)


class TestConvertPositions:
    def test_feet_to_meters(self):
        positions = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
        result = convert_positions(positions, "feet")
        assert len(result) == 6
        assert result[0] == pytest.approx(1.0 * FEET_TO_METERS)
        assert result[5] == pytest.approx(6.0 * FEET_TO_METERS)

    def test_meters_passthrough(self):
        positions = [1.0, 2.0, 3.0]
        result = convert_positions(positions, "meters")
        assert result == positions

    def test_empty(self):
        assert convert_positions([], "feet") == []


class TestConvertElevation:
    def test_feet(self):
        assert convert_elevation(10.0, "feet") == pytest.approx(10.0 * FEET_TO_METERS)

    def test_meters_passthrough(self):
        assert convert_elevation(10.0, "meters") == 10.0


class TestConvertDimension:
    def test_feet(self):
        assert convert_dimension(0.5, "feet") == pytest.approx(0.5 * FEET_TO_METERS)

    def test_meters_passthrough(self):
        assert convert_dimension(0.5, "meters") == 0.5
