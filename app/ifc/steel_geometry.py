"""Parametric IFC geometry for steel members.

Steel members reach the exporter as a section ``designation`` (→ I-shape
dimensions, see :mod:`app.ifc.profiles`), a ``length`` and a 3×4 ``transform``.
This builds the matching IFC geometry: an ``IfcExtrudedAreaSolid`` swept from an
``IfcIShapeProfileDef`` (or an ``IfcRectangleProfileDef`` for footings) placed by
the member's transform.

Local-frame convention (must match ``steel_member.py`` in 3d-modeling-service):

    transform = [ up | lateral | direction | position ]   (3×4, column-wise)
      local X = up        (the profile DEPTH axis)
      local Y = lateral   (the profile FLANGE-WIDTH axis)
      local Z = direction (the extrusion / member-length axis)

``IfcIShapeProfileDef`` defines OverallDepth along the profile's *Y* axis and
OverallWidth along *X*. To put depth on local X and width on local Y, the
extruded-solid ``Position`` is rotated 90° (Axis = +Z, RefDirection = +Y) so the
profile X→local Y and profile Y→local X. The member ``ObjectPlacement`` then maps
local→world with Axis = direction and RefDirection = up — reproducing the
``steel_member`` transform exactly.
"""
import logging

import ifcopenshell

from app.services.unit_converter import FEET_TO_METERS, INCH_TO_METERS

logger = logging.getLogger(__name__)


def _dir(ifc: ifcopenshell.file, vec):
    return ifc.createIfcDirection(tuple(float(c) for c in vec))


def _pt(ifc: ifcopenshell.file, vec):
    return ifc.createIfcCartesianPoint(tuple(float(c) for c in vec))


def _len(value: float, source_units: str) -> float:
    return value * FEET_TO_METERS if source_units == "feet" else value


def ishape_profile(ifc: ifcopenshell.file, dims: dict, name: str = None):
    """Create an IfcIShapeProfileDef (metres) from AISC dimensions (inches)."""
    return ifc.createIfcIShapeProfileDef(
        ProfileType="AREA",
        ProfileName=name,
        OverallWidth=dims["bf"] * INCH_TO_METERS,
        OverallDepth=dims["d"] * INCH_TO_METERS,
        WebThickness=dims["tw"] * INCH_TO_METERS,
        FlangeThickness=dims["tf"] * INCH_TO_METERS,
    )


def ishape_extrusion(
    ifc: ifcopenshell.file,
    dims: dict,
    length_ft: float,
    source_units: str = "feet",
    name: str = None,
):
    """Extrude an I-shape profile along local +Z by ``length`` (member axis).

    The solid ``Position`` rotates the profile 90° so depth lands on local X
    (up) and flange width on local Y (lateral), matching ``steel_member.py``.
    """
    profile = ishape_profile(ifc, dims, name)
    position = ifc.createIfcAxis2Placement3D(
        Location=_pt(ifc, (0.0, 0.0, 0.0)),
        Axis=_dir(ifc, (0.0, 0.0, 1.0)),
        RefDirection=_dir(ifc, (0.0, 1.0, 0.0)),
    )
    return ifc.createIfcExtrudedAreaSolid(
        SweptArea=profile,
        Position=position,
        ExtrudedDirection=_dir(ifc, (0.0, 0.0, 1.0)),
        Depth=_len(length_ft, source_units),
    )


def box_extrusion(
    ifc: ifcopenshell.file,
    width_ft: float,
    depth_ft: float,
    thickness_ft: float,
    source_units: str = "feet",
):
    """Extrude a centered rectangle (width×depth) up by ``thickness`` — footings."""
    profile = ifc.createIfcRectangleProfileDef(
        ProfileType="AREA",
        XDim=_len(width_ft, source_units),
        YDim=_len(depth_ft, source_units),
    )
    position = ifc.createIfcAxis2Placement3D(Location=_pt(ifc, (0.0, 0.0, 0.0)))
    return ifc.createIfcExtrudedAreaSolid(
        SweptArea=profile,
        Position=position,
        ExtrudedDirection=_dir(ifc, (0.0, 0.0, 1.0)),
        Depth=_len(thickness_ft, source_units),
    )


def placement_from_transform(
    ifc: ifcopenshell.file,
    transform,
    source_units: str = "feet",
    relative_to=None,
):
    """Build an IfcLocalPlacement from a 3×4 row-major ``[up|lat|dir|pos]`` matrix.

    ``transform`` is the member's ``world_transform_3x4``:
    ``[r00,r01,r02,tx, r10,r11,r12,ty, r20,r21,r22,tz]``. The placement Axis is
    the member direction (col 2) and RefDirection is up (col 0).
    """
    t = transform
    location = (_len(t[3], source_units), _len(t[7], source_units), _len(t[11], source_units))
    direction = (t[2], t[6], t[10])   # local Z = member axis
    up = (t[0], t[4], t[8])           # local X = up / depth axis
    a2p = ifc.createIfcAxis2Placement3D(
        Location=_pt(ifc, location),
        Axis=_dir(ifc, direction),
        RefDirection=_dir(ifc, up),
    )
    return ifc.createIfcLocalPlacement(PlacementRelTo=relative_to, RelativePlacement=a2p)


def swept_representation(ifc: ifcopenshell.file, body_context, solid):
    """Wrap a swept solid in an IfcProductDefinitionShape (RepresentationType SweptSolid)."""
    rep = ifc.createIfcShapeRepresentation(
        ContextOfItems=body_context,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )
    return ifc.createIfcProductDefinitionShape(Representations=[rep])


def get_material(ifc: ifcopenshell.file, name: str):
    """Find or create an IfcMaterial by name (deduplicated per file)."""
    for mat in ifc.by_type("IfcMaterial"):
        if mat.Name == name:
            return mat
    return ifc.createIfcMaterial(Name=name)


def associate_material(ifc: ifcopenshell.file, element, material):
    """Associate a material with an element, reusing the material's relationship."""
    for rel in ifc.by_type("IfcRelAssociatesMaterial"):
        if rel.RelatingMaterial == material:
            rel.RelatedObjects = list(rel.RelatedObjects) + [element]
            return rel
    return ifc.createIfcRelAssociatesMaterial(
        GlobalId=ifcopenshell.guid.new(),
        RelatedObjects=[element],
        RelatingMaterial=material,
    )
