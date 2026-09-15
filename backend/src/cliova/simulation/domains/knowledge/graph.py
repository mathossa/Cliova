"""Disposable NetworkX validation adapter; graph objects never enter world state."""

from collections.abc import Iterable

import networkx as nx  # type: ignore[import-untyped]

from cliova.simulation.domains.knowledge.types import CapabilityDefinition, CapabilityRequirement


def validate_catalog(
    definitions: Iterable[CapabilityDefinition],
) -> tuple[CapabilityDefinition, ...]:
    catalog = tuple(sorted(definitions, key=lambda item: item.key))
    by_key = {item.key: item for item in catalog}
    if len(by_key) != len(catalog):
        raise ValueError("duplicate capability keys")
    graph = nx.DiGraph()
    graph.add_nodes_from(by_key)
    for definition in catalog:
        if not 0 < definition.activation_threshold <= 1:
            raise ValueError("activation threshold must be in (0, 1]")
        for requirement in definition.requirements:
            if isinstance(requirement, CapabilityRequirement):
                if requirement.capability_key not in by_key:
                    raise ValueError("missing capability prerequisite")
                graph.add_edge(requirement.capability_key, definition.key)
    if not nx.is_directed_acyclic_graph(graph):
        raise ValueError("capability prerequisites must be acyclic")
    # Evaluation uses the same pre-step proficiency snapshot, so key order is
    # sufficient and prevents traversal order from creating same-tick unlock chains.
    return catalog
