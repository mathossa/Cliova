"""Authoritative settlements, camps, and gameplay-relevant constructed structures."""

from cliova.simulation.domains.settlements.catalog import (
    STRUCTURE_DEFINITIONS,
    StructureDefinition,
    structure_definition,
)
from cliova.simulation.domains.settlements.domain import (
    SettlementDomain,
    establish_settlement_input,
    establish_structure_input,
    initialize_settlements,
    settlement_status_input,
    structure_status_input,
)
from cliova.simulation.domains.settlements.fixtures import starter_settlement_inputs

__all__ = [
    "STRUCTURE_DEFINITIONS",
    "SettlementDomain",
    "StructureDefinition",
    "establish_settlement_input",
    "establish_structure_input",
    "initialize_settlements",
    "settlement_status_input",
    "starter_settlement_inputs",
    "structure_definition",
    "structure_status_input",
]
