"""NetworkX adapter for connectivity/path queries over serialized geography state."""

from uuid import UUID

import networkx as nx  # type: ignore[import-untyped]

from cliova.simulation.types import EntityId, GeographyState


def as_graph(geography: GeographyState) -> nx.Graph:
    """Build a disposable graph view; NetworkX objects are never authoritative state."""
    graph = nx.Graph()
    for region in geography.regions:
        graph.add_node(region.id.value)
    for connection in geography.connections:
        graph.add_edge(
            connection.a.value,
            connection.b.value,
            travel_cost=connection.travel_cost,
        )
    return graph


def is_connected(geography: GeographyState) -> bool:
    """Return whether every serialized region is mutually reachable."""
    graph = as_graph(geography)
    return bool(graph) and nx.is_connected(graph)


def shortest_path(
    geography: GeographyState, start: EntityId, end: EntityId
) -> tuple[EntityId, ...]:
    """Return the minimum-travel-cost region path using NetworkX's public API."""
    region_ids = _region_ids(geography)
    _require_region(region_ids, start)
    _require_region(region_ids, end)
    try:
        path = nx.shortest_path(
            as_graph(geography), source=start.value, target=end.value, weight="travel_cost"
        )
    except nx.NetworkXNoPath as exc:
        raise ValueError("regions are not connected") from exc
    return tuple(region_ids[node] for node in path)


def shortest_travel_cost(geography: GeographyState, start: EntityId, end: EntityId) -> float:
    """Return weighted shortest-path cost without exposing NetworkX graph state."""
    region_ids = _region_ids(geography)
    _require_region(region_ids, start)
    _require_region(region_ids, end)
    try:
        return float(
            nx.shortest_path_length(
                as_graph(geography), source=start.value, target=end.value, weight="travel_cost"
            )
        )
    except nx.NetworkXNoPath as exc:
        raise ValueError("regions are not connected") from exc


def _region_ids(geography: GeographyState) -> dict[UUID, EntityId]:
    return {region.id.value: region.id for region in geography.regions}


def _require_region(region_ids: dict[UUID, EntityId], region_id: EntityId) -> None:
    if region_id.kind != "region" or region_id.value not in region_ids:
        raise ValueError("region ID is not part of this geography")
