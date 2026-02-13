"""Create a blank IFC4 file with standard header, units, and representation contexts."""
import ifcopenshell

from app.ifc.placement import create_axis2_placement_3d


def create_ifc4_file(
    project_name: str = "BIM Model",
    author: str = "",
    organization: str = "",
):
    """Create a new IFC4 file with project, units, and 3-D representation context.

    Returns:
        (ifc_file, ifc_project, body_context) tuple.
    """
    ifc = ifcopenshell.file(schema="IFC4")

    # --- Units ----------------------------------------------------------
    length_unit = ifc.createIfcSIUnit(
        UnitType="LENGTHUNIT",
        Name="METRE",
    )
    area_unit = ifc.createIfcSIUnit(
        UnitType="AREAUNIT",
        Name="SQUARE_METRE",
    )
    volume_unit = ifc.createIfcSIUnit(
        UnitType="VOLUMEUNIT",
        Name="CUBIC_METRE",
    )
    plane_angle_unit = ifc.createIfcSIUnit(
        UnitType="PLANEANGLEUNIT",
        Name="RADIAN",
    )
    unit_assignment = ifc.createIfcUnitAssignment(
        Units=[length_unit, area_unit, volume_unit, plane_angle_unit],
    )

    # --- Representation context -----------------------------------------
    origin = create_axis2_placement_3d(ifc)

    context_3d = ifc.createIfcGeometricRepresentationContext(
        ContextIdentifier="Model",
        ContextType="Model",
        CoordinateSpaceDimension=3,
        Precision=1e-5,
        WorldCoordinateSystem=origin,
    )

    body_context = ifc.createIfcGeometricRepresentationSubContext(
        ContextIdentifier="Body",
        ContextType="Model",
        ParentContext=context_3d,
        TargetView="MODEL_VIEW",
    )

    # --- Project --------------------------------------------------------
    project = ifc.createIfcProject(
        GlobalId=ifcopenshell.guid.new(),
        Name=project_name,
        UnitsInContext=unit_assignment,
        RepresentationContexts=[context_3d],
    )

    return ifc, project, body_context
