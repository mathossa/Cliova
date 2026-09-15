"""Small generic catalog for authoritative gameplay-relevant structures.

Definitions describe identity and integration seams only. Numerical effects remain owned by
other simulation domains such as economy, governance, logistics, trade, and warfare.
"""

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class StructureDefinition:
    """A reusable strategic structure definition, separate from authoritative instances."""

    key: str
    display_name: str
    effect_domains: tuple[str, ...] = ()
    required_capabilities: tuple[str, ...] = ()


STRUCTURE_DEFINITIONS: Final[tuple[StructureDefinition, ...]] = (
    StructureDefinition("storage", "Storage", ("economy",)),
    StructureDefinition("workshop", "Workshop", ("economy", "knowledge")),
    StructureDefinition("market", "Trading Place", ("economy", "trade")),
    StructureDefinition("ritual_structure", "Ritual Structure", ("spirituality",)),
    StructureDefinition("water_infrastructure", "Water Infrastructure", ("population", "economy")),
    StructureDefinition("livestock_enclosure", "Livestock Enclosure", ("economy",)),
    StructureDefinition("fortification", "Fortification", ("warfare",)),
    StructureDefinition("harbour_infrastructure", "Harbour Infrastructure", ("logistics", "trade")),
    StructureDefinition("transport_infrastructure", "Transport Infrastructure", ("logistics",)),
    StructureDefinition("administrative_structure", "Administrative Structure", ("governance",)),
)
_STRUCTURE_BY_KEY: Final[dict[str, StructureDefinition]] = {
    definition.key: definition for definition in STRUCTURE_DEFINITIONS
}


def structure_definition(key: str) -> StructureDefinition:
    """Resolve a known strategic structure definition by stable key."""

    try:
        return _STRUCTURE_BY_KEY[key]
    except KeyError as exc:
        raise ValueError(f"unknown authoritative structure definition: {key}") from exc
