"""AISC W-shape section profiles for parametric steel IFC geometry.

Steel members reach the exporter as a section ``designation`` (e.g. ``"W24x68"``)
plus a length and transform. To emit parametric IFC (``IfcIShapeProfileDef`` +
``IfcExtrudedAreaSolid``) we need the I-shape cross-section dimensions, which are
looked up here from a vendored copy of the AISC shapes table.

The data file ``app/data/aisc/w_shapes.json`` is a verbatim copy of
``3d-modeling-service/app/bim/data/aisc/w_shapes.json`` (AISC Shapes Database
v15.0 — W-shapes subset). Keep the two in sync; the 3d-modeling-service file is
the source of truth. Designations use a lowercase ``x`` separator, matching the
member sizing / element-metadata output.

Per-shape dimensions (inches): ``d`` (overall depth), ``bf`` (flange width),
``tw`` (web thickness), ``tf`` (flange thickness); plus section properties
(``A``, ``Ix``, ``Sx``, ``Zx`` …) and ``weight`` (plf).
"""
import json
import logging
import os
from typing import Dict, Optional

logger = logging.getLogger(__name__)

_DATA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "aisc", "w_shapes.json"
)

_profile_cache: Optional[Dict[str, dict]] = None


def _normalize(designation: str) -> str:
    """Canonicalize a designation for case-insensitive lookup.

    Sizing emits a lowercase ``x`` (``"W16x26"``) but config libraries elsewhere
    use uppercase (``"W16X26"``); normalize both to the same key.
    """
    return designation.strip().upper().replace("X", "x")


def _load_profiles() -> Dict[str, dict]:
    """Load and cache the W-shape table keyed by normalized designation."""
    global _profile_cache
    if _profile_cache is None:
        with open(_DATA_PATH) as f:
            data = json.load(f)
        _profile_cache = {_normalize(s["designation"]): s for s in data["shapes"]}
        logger.debug("Loaded %d AISC W-shapes from %s", len(_profile_cache), _DATA_PATH)
    return _profile_cache


def get_profile(designation: Optional[str]) -> Optional[dict]:
    """Return the W-shape record for a designation, or ``None`` if unknown.

    Lookup is case-insensitive on the ``x``/``X`` separator. Callers should
    fall back to mesh/bounding-box geometry when this returns ``None``.
    """
    if not designation:
        return None
    return _load_profiles().get(_normalize(designation))


def has_profile(designation: Optional[str]) -> bool:
    """True if a parametric profile is available for the designation."""
    return get_profile(designation) is not None
