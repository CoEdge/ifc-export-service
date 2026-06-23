"""Tests for steel storey derivation + member→storey assignment."""
from app.services.steel_storeys import (
    is_foundation_member,
    member_elevation_ft,
    normalize_storeys_and_assign,
    FOUNDATIONS_STOREY_ID,
)


class TestIsFoundationMember:
    def test_pad_kind(self):
        assert is_foundation_member({"id": "p", "kind": "steel_foundation_pad"})

    def test_footing_dims(self):
        assert is_foundation_member({"id": "p", "kind": "x", "footing": {"width_ft": 6}})

    def test_col_ext_id(self):
        assert is_foundation_member({"id": "col_ext_ab12", "kind": "steel_column"})

    def test_foundation_pad_id(self):
        assert is_foundation_member({"id": "foundation_pad_x", "kind": "steel_foundation_pad"})

    def test_regular_beam_is_not(self):
        assert not is_foundation_member({"id": "beam_1", "kind": "steel_w_beam"})

    def test_regular_column_is_not(self):
        assert not is_foundation_member({"id": "col_1", "kind": "steel_w_column"})


def test_member_elevation_from_transform():
    m = {"id": "x", "transform": [0, 0, 1, 1, 0, -1, 0, 2, 1, 0, 0, -4]}
    assert member_elevation_ft(m) == -4.0
    assert member_elevation_ft({"id": "y"}) is None


class TestNormalizeAndAssign:
    def test_synthesizes_foundations_storey(self):
        storeys = [{"id": "L1", "name": "Level 1", "elevation": 0.0}]
        members = [
            {"id": "beam_1", "kind": "steel_w_beam", "floor_id": "L1"},
            {"id": "col_ext_1", "kind": "steel_column",
             "transform": [0, 0, 1, 0, 0, -1, 0, 0, 1, 0, 0, -4]},
            {"id": "pad_1", "kind": "steel_foundation_pad",
             "footing": {"width_ft": 6, "depth_ft": 6, "thickness_ft": 2},
             "transform": [0, 0, 1, 0, 0, -1, 0, 0, 1, 0, 0, -6]},
        ]
        storeys_out, assignment = normalize_storeys_and_assign(storeys, members)

        fnd = [s for s in storeys_out if s["id"] == FOUNDATIONS_STOREY_ID]
        assert len(fnd) == 1
        assert fnd[0]["elevation"] == -6.0  # lowest footing elevation
        assert assignment["beam_1"] == "L1"
        assert assignment["col_ext_1"] == FOUNDATIONS_STOREY_ID
        assert assignment["pad_1"] == FOUNDATIONS_STOREY_ID

    def test_reuses_supplied_foundations_storey(self):
        storeys = [
            {"id": "L1", "name": "Level 1", "elevation": 0.0},
            {"id": "FND", "name": "Foundations", "elevation": -4.0},
        ]
        members = [{"id": "pad_1", "kind": "steel_foundation_pad", "floor_id": "FND"}]
        storeys_out, assignment = normalize_storeys_and_assign(storeys, members)
        # No extra synthesized storey.
        assert len(storeys_out) == 2
        assert assignment["pad_1"] == "FND"

    def test_no_foundation_members_no_synthesis(self):
        storeys = [{"id": "L1", "name": "Level 1", "elevation": 0.0}]
        members = [{"id": "beam_1", "kind": "steel_w_beam", "floor_id": "L1"}]
        storeys_out, assignment = normalize_storeys_and_assign(storeys, members)
        assert len(storeys_out) == 1
        assert assignment["beam_1"] == "L1"

    def test_unresolved_floor_id_uses_nearest_elevation(self):
        storeys = [
            {"id": "L1", "name": "Level 1", "elevation": 0.0},
            {"id": "L2", "name": "Level 2", "elevation": 12.0},
        ]
        # floor_id "ghost" doesn't exist; elevation 11 → nearest is L2.
        members = [{
            "id": "beam_x", "kind": "steel_w_beam", "floor_id": "ghost",
            "transform": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 11.0],
        }]
        _, assignment = normalize_storeys_and_assign(storeys, members)
        assert assignment["beam_x"] == "L2"
