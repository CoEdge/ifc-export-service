"""IFC spatial hierarchy: IfcProject -> IfcSite -> IfcBuilding -> IfcBuildingStorey."""
import logging
from typing import Dict, List, Optional

import ifcopenshell

from app.ifc.placement import create_local_placement
from app.services.unit_converter import convert_elevation

logger = logging.getLogger(__name__)


def create_spatial_hierarchy(
    ifc: ifcopenshell.file,
    project,
    storeys_data: List[dict],
    source_units: str = "feet",
    site_name: str = "Default Site",
    building_name: str = "Default Building",
):
    """Build IfcSite -> IfcBuilding -> IfcBuildingStorey[] and attach to project.

    Args:
        ifc: The IFC file being constructed.
        project: The IfcProject entity.
        storeys_data: List of dicts with keys ``id``, ``name``, ``elevation``.
        source_units: Unit system of the elevations ("feet" or "meters").
        site_name: Display name for the site.
        building_name: Display name for the building.

    Returns:
        (site, building, storey_map) where storey_map maps storey id -> IfcBuildingStorey.
    """
    # --- Site -----------------------------------------------------------
    site_placement = create_local_placement(ifc)
    site = ifc.createIfcSite(
        GlobalId=ifcopenshell.guid.new(),
        Name=site_name,
        ObjectPlacement=site_placement,
    )
    ifc.createIfcRelAggregates(
        GlobalId=ifcopenshell.guid.new(),
        RelatingObject=project,
        RelatedObjects=[site],
    )

    # --- Building -------------------------------------------------------
    building_placement = create_local_placement(ifc, relative_to=site_placement)
    building = ifc.createIfcBuilding(
        GlobalId=ifcopenshell.guid.new(),
        Name=building_name,
        ObjectPlacement=building_placement,
    )
    ifc.createIfcRelAggregates(
        GlobalId=ifcopenshell.guid.new(),
        RelatingObject=site,
        RelatedObjects=[building],
    )

    # --- Storeys --------------------------------------------------------
    storey_map: Dict[str, object] = {}

    sorted_storeys = sorted(storeys_data, key=lambda s: s.get("elevation", 0.0))
    for sd in sorted_storeys:
        elev_m = convert_elevation(sd["elevation"], source_units)
        storey_placement = create_local_placement(
            ifc, z=elev_m, relative_to=building_placement,
        )
        storey = ifc.createIfcBuildingStorey(
            GlobalId=ifcopenshell.guid.new(),
            Name=sd.get("name") or sd["id"],
            Elevation=elev_m,
            ObjectPlacement=storey_placement,
        )
        storey_map[sd["id"]] = storey

    # Ensure at least one storey exists
    if not storey_map:
        default_placement = create_local_placement(ifc, relative_to=building_placement)
        default_storey = ifc.createIfcBuildingStorey(
            GlobalId=ifcopenshell.guid.new(),
            Name="Default Storey",
            Elevation=0.0,
            ObjectPlacement=default_placement,
        )
        storey_map["__default__"] = default_storey

    # Aggregate storeys into building
    ifc.createIfcRelAggregates(
        GlobalId=ifcopenshell.guid.new(),
        RelatingObject=building,
        RelatedObjects=list(storey_map.values()),
    )

    return site, building, storey_map
