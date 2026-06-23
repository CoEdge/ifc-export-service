"""IFC Builder — orchestrates construction of a complete IFC4 file from the intermediate format."""
import logging
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

from app.ifc.templates import create_ifc4_file
from app.ifc.hierarchy import create_spatial_hierarchy
from app.services.element_mapper import create_ifc_element, create_ifc_steel_element
from app.services.property_mapper import create_property_sets
from app.services.steel_storeys import normalize_storeys_and_assign
from app.models.schemas import IFCExportRequest, SteelExportRequest

import ifcopenshell

logger = logging.getLogger(__name__)


class IFCBuilder:
    """Build a complete IFC4 file from the intermediate mesh format."""

    def build(self, request: IFCExportRequest) -> bytes:
        """Convert an ``IFCExportRequest`` into IFC4 file bytes (STEP Physical File).

        Args:
            request: Validated Pydantic model with project info, storeys, and elements.

        Returns:
            Raw ``.ifc`` file content as ``bytes``.
        """
        project_data = request.project
        source_units = request.source_units

        # 1. Create IFC4 file with template
        ifc, project, body_context = create_ifc4_file(
            project_name=project_data.name if project_data else "BIM Model",
        )

        # 2. Create spatial hierarchy
        storeys_raw = [s.model_dump() for s in (request.storeys or [])]
        site, building, storey_map = create_spatial_hierarchy(
            ifc,
            project,
            storeys_raw,
            source_units=source_units,
            site_name=(request.site.name if request.site else "Default Site"),
            building_name=(request.building.name if request.building else "Default Building"),
        )

        # 3. Create elements and group by storey
        elements_by_storey: Dict[int, List] = defaultdict(list)

        for elem in request.elements:
            elem_dict = elem.model_dump()

            # Resolve storey
            floor_id = elem.floor_id
            storey = storey_map.get(floor_id) if floor_id else None
            if storey is None:
                # Fall back to first available storey
                storey = next(iter(storey_map.values()))

            # Create IFC element with geometry
            ifc_element = create_ifc_element(
                ifc, elem_dict, body_context, source_units,
            )

            # Attach property sets
            create_property_sets(
                ifc, ifc_element, elem_dict.get("properties"), source_units,
            )

            elements_by_storey[id(storey)].append(ifc_element)

        # 4. Assign elements to storeys
        for storey_id_str, storey_entity in storey_map.items():
            storey_elements = elements_by_storey.get(id(storey_entity), [])
            if storey_elements:
                ifc.createIfcRelContainedInSpatialStructure(
                    GlobalId=ifcopenshell.guid.new(),
                    RelatingStructure=storey_entity,
                    RelatedElements=storey_elements,
                )

        # 5. Serialize to STEP Physical File
        return self._serialize(ifc)

    def build_steel(self, request: SteelExportRequest) -> bytes:
        """Convert a ``SteelExportRequest`` into IFC4 file bytes.

        Builds parametric steel members (IfcColumn/IfcBeam/IfcFooting with
        extruded I-shape / rectangle solids) into a Project→Site→Building→Storey
        hierarchy, attaching property sets and grouping members by storey.

        Args:
            request: Validated steel export request (project info, storeys, members).

        Returns:
            Raw ``.ifc`` file content as ``bytes``.
        """
        project_data = request.project
        source_units = request.source_units

        ifc, project, body_context = create_ifc4_file(
            project_name=project_data.name if project_data else "Steel Structure",
        )

        # Derive storeys (synthesizing a below-grade Foundations storey for
        # footings / foundation columns) and resolve each member to a storey.
        storeys_raw = [s.model_dump() for s in (request.storeys or [])]
        members_raw = [m.model_dump() for m in request.members]
        storeys_norm, assignment = normalize_storeys_and_assign(storeys_raw, members_raw)

        site, building, storey_map = create_spatial_hierarchy(
            ifc,
            project,
            storeys_norm,
            source_units=source_units,
            site_name=(request.site.name if request.site else "Default Site"),
            building_name=(request.building.name if request.building else "Default Building"),
        )

        elements_by_storey: Dict[int, List] = defaultdict(list)

        for member_dict in members_raw:
            storey_id = assignment.get(member_dict["id"])
            storey = storey_map.get(storey_id) if storey_id else None
            if storey is None:
                storey = next(iter(storey_map.values()))

            ifc_element = create_ifc_steel_element(
                ifc, member_dict, body_context, source_units,
            )
            create_property_sets(
                ifc, ifc_element, member_dict.get("properties"), source_units,
            )
            elements_by_storey[id(storey)].append(ifc_element)

        for storey_entity in storey_map.values():
            storey_elements = elements_by_storey.get(id(storey_entity), [])
            if storey_elements:
                ifc.createIfcRelContainedInSpatialStructure(
                    GlobalId=ifcopenshell.guid.new(),
                    RelatingStructure=storey_entity,
                    RelatedElements=storey_elements,
                )

        return self._serialize(ifc)

    @staticmethod
    def _serialize(ifc: ifcopenshell.file) -> bytes:
        """Write IFC file to a temp file and read back as bytes."""
        with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False) as tmp:
            tmp_path = tmp.name

        ifc.write(tmp_path)
        data = Path(tmp_path).read_bytes()

        # Clean up
        try:
            Path(tmp_path).unlink()
        except OSError:
            pass

        return data
