"""Storey derivation and member→storey assignment for steel IFC export.

``build_steel`` groups members into building storeys. A steel/Revit model
supplies occupied-floor storeys (from its levels), but foundation members —
spread-footing pads and the below-grade foundation-column extensions — belong
on a dedicated below-grade "Foundations" storey that the model's levels don't
include. This module synthesizes that storey when needed and resolves every
member to a storey:

  - foundation members → the Foundations storey
  - others             → by ``floor_id`` when it matches a supplied storey,
                         else the nearest storey by elevation.
"""
from typing import Dict, List, Optional, Tuple

FOUNDATIONS_STOREY_ID = "__foundations__"
FOUNDATIONS_STOREY_NAME = "Foundations"

# Foundation-member signals (see 3d-modeling-service pipeline._generate_foundations):
#   pads     → kind "steel_foundation_pad" / id "foundation_pad_*" / footing dims
#   fnd cols → id "col_ext_*" / element_type "steel_column" (vs "steel_w_column")
_FOUNDATION_KINDS = {"steel_foundation_pad", "steel_column"}


def is_foundation_member(member: dict) -> bool:
    """True if a member belongs on the below-grade Foundations storey."""
    kind = member.get("kind") or member.get("type") or ""
    if kind in _FOUNDATION_KINDS:
        return True
    if member.get("footing"):
        return True
    mid = member.get("id") or ""
    return mid.startswith("col_ext_") or mid.startswith("foundation_pad_")


def member_elevation_ft(member: dict) -> Optional[float]:
    """Member base elevation from the transform translation Z, if available."""
    t = member.get("transform")
    if t and len(t) >= 12:
        return float(t[11])
    return None


def _existing_foundations_storey(storeys: List[dict]) -> Optional[dict]:
    for s in storeys:
        if (s.get("name") or "").strip().lower() == FOUNDATIONS_STOREY_NAME.lower():
            return s
        if s.get("id") in (FOUNDATIONS_STOREY_ID, "FND"):
            return s
    return None


def normalize_storeys_and_assign(
    storeys: List[dict],
    members: List[dict],
) -> Tuple[List[dict], Dict[str, str]]:
    """Return ``(storeys_out, assignment)`` mapping member id → storey id.

    Synthesizes a below-grade Foundations storey when foundation members are
    present and none was supplied. Foundation members are assigned to it; other
    members by ``floor_id``, falling back to the nearest storey by elevation.
    """
    storeys_out = list(storeys)
    storey_by_id = {s["id"]: s for s in storeys_out}

    foundation_members = [m for m in members if is_foundation_member(m)]

    foundations = _existing_foundations_storey(storeys_out)
    if foundations is None and foundation_members:
        # Place it below the lowest supplied storey / lowest footing.
        fnd_elevs = [e for e in (member_elevation_ft(m) for m in foundation_members) if e is not None]
        base = min([s.get("elevation", 0.0) for s in storeys_out], default=0.0)
        elev = min(fnd_elevs) if fnd_elevs else (base - 4.0)
        foundations = {"id": FOUNDATIONS_STOREY_ID, "name": FOUNDATIONS_STOREY_NAME, "elevation": elev}
        storeys_out.append(foundations)
        storey_by_id[foundations["id"]] = foundations

    # Real (non-foundation) storeys for the nearest-by-elevation fallback.
    real_storeys = [s for s in storeys_out if foundations is None or s["id"] != foundations["id"]]
    if not real_storeys:
        real_storeys = storeys_out

    def nearest(elev: Optional[float]) -> Optional[str]:
        if not real_storeys:
            return None
        if elev is None:
            return real_storeys[0]["id"]
        return min(real_storeys, key=lambda s: abs(s.get("elevation", 0.0) - elev))["id"]

    assignment: Dict[str, str] = {}
    for m in members:
        mid = m.get("id")
        if foundations is not None and is_foundation_member(m):
            assignment[mid] = foundations["id"]
        elif m.get("floor_id") in storey_by_id:
            assignment[mid] = m["floor_id"]
        else:
            nid = nearest(member_elevation_ft(m))
            if nid is not None:
                assignment[mid] = nid

    return storeys_out, assignment
