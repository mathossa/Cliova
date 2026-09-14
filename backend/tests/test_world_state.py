import json
from uuid import uuid5

import pytest
from pydantic import ValidationError

from cliova.simulation.types import (
    EntityId,
    SimulationChange,
    SimulationEvent,
    SimulationTime,
    WorldState,
    entity_id,
)


def test_world_creation_is_reproducible_and_requires_seed() -> None:
    first = WorldState.create(seed=42)
    second = WorldState.create(seed=42)
    assert first == second
    assert first.model_dump_json() == second.model_dump_json()
    assert first != WorldState.create(seed=43)
    assert first.id != WorldState.create(seed=42, world_key="second").id
    assert first.time == SimulationTime(year=0, tick=0)
    with pytest.raises(TypeError):
        WorldState.create()  # type: ignore[call-arg]


@pytest.mark.parametrize("seed", [0, -1, 2**128])
def test_integer_seeds_round_trip(seed: int) -> None:
    world = WorldState.create(seed=seed)
    assert WorldState.model_validate_json(world.model_dump_json()) == world


def test_stable_entity_and_event_ids_survive_json() -> None:
    world = WorldState.create(seed=42)
    region = entity_id(world.id, "region", "initial:0")
    society = entity_id(world.id, "society", "initial:0")
    polity = entity_id(world.id, "polity", "initial:0")
    individual = entity_id(world.id, "individual", "notable:0")
    assert len({region.value, society.value, polity.value, individual.value}) == 4
    assert region == entity_id(world.id, "region", "initial:0")
    assert region != entity_id(WorldState.create(seed=43).id, "region", "initial:0")
    restored = WorldState.model_validate_json(world.model_dump_json())
    assert region == entity_id(restored.id, "region", "initial:0")
    cause_id = uuid5(world.id.value, "event:cause")
    change = SimulationChange(
        source="population", key="count", delta=1, reason="growth",
        target=society, cause_event_ids=(cause_id,),
    )
    event = SimulationEvent(
        id=uuid5(world.id.value, "event:1"), time=SimulationTime(year=1, tick=1),
        source="population", kind="growth", reason="test cause",
        subjects=(region, society, polity, individual), cause_event_ids=(cause_id,),
        changes=(change,),
    )
    assert SimulationEvent.model_validate_json(event.model_dump_json()) == event


def test_snapshot_header_is_explicit() -> None:
    world = WorldState.create(seed=42)
    data = json.loads(world.model_dump_json())
    assert data["metadata"] == {
        "schema_version": 1,
        "simulation_version": 1,
        "rng_algorithm": "pcg64-sha256-v1",
    }
    del data["metadata"]
    with pytest.raises(ValidationError):
        WorldState.model_validate(data)


@pytest.mark.parametrize("field", ["schema_version", "simulation_version", "rng_algorithm"])
def test_missing_metadata_is_not_silently_defaulted(field: str) -> None:
    data = json.loads(WorldState.create(seed=42).model_dump_json())
    del data["metadata"][field]
    with pytest.raises(ValidationError):
        WorldState.model_validate(data)


@pytest.mark.parametrize("field,value", [
    ("schema_version", 2), ("simulation_version", 2), ("rng_algorithm", "unknown"),
    ("schema_version", True), ("simulation_version", 1.0),
])
def test_unsupported_metadata_requires_migration(field: str, value: object) -> None:
    data = json.loads(WorldState.create(seed=42).model_dump_json())
    data["metadata"][field] = value
    with pytest.raises(ValidationError):
        WorldState.model_validate(data)


def test_invalid_state_is_rejected() -> None:
    data = json.loads(WorldState.create(seed=42).model_dump_json())
    data["seed"] = True
    with pytest.raises(ValidationError):
        WorldState.model_validate(data)
    data["seed"] = 42
    data["id"]["kind"] = "region"
    with pytest.raises(ValidationError):
        WorldState.model_validate(data)
    with pytest.raises(ValidationError):
        SimulationTime(tick=-1)
    with pytest.raises(ValidationError):
        SimulationTime(tick=True)
    with pytest.raises(ValidationError):
        SimulationChange(source="test", key="metric", delta=float("nan"), reason="test")


def test_state_and_nested_time_are_immutable() -> None:
    world = WorldState.create(seed=42)
    with pytest.raises(ValidationError):
        world.seed = 9
    with pytest.raises(ValidationError):
        world.time.year = 9
    with pytest.raises(ValidationError):
        world.id.kind = "region"


def test_identity_keys_and_phases_are_validated() -> None:
    world = WorldState.create(seed=42)
    with pytest.raises(ValueError):
        WorldState.create(seed=42, world_key="")
    with pytest.raises(ValueError):
        entity_id(world.id, "region", "")
    with pytest.raises(ValueError):
        entity_id(EntityId(kind="region", value=world.id.value), "society", "0")
    with pytest.raises(ValueError, match="sub-year"):
        SimulationTime(phase="spring").next_year()
    # Negative calendar years are legitimate; elapsed ticks remain non-negative.
    assert SimulationTime(year=-2).next_year() == SimulationTime(year=-1, tick=1)
