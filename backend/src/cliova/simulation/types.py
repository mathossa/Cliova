"""Serializable primitives shared by authoritative simulation domains."""

import json
from typing import Annotated, Final, Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

NonNegativeInt = Annotated[int, Field(strict=True, ge=0)]
NonEmptyString = Annotated[str, Field(strict=True, min_length=1)]
EntityKind = Literal["world", "region", "society", "polity", "individual"]
RNG_ALGORITHM: Final = "pcg64-sha256-v1"


class SimulationModel(BaseModel):
    """Only immutable fields belong here; nested domain state must follow suit."""

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


class EntityId(SimulationModel):
    """A kind-qualified UUID; display names are never identities."""

    kind: EntityKind
    value: UUID


def entity_id(world_id: EntityId, kind: EntityKind, key: str) -> EntityId:
    """Derive an ID from a stable domain key, without consuming simulation RNG."""
    if world_id.kind != "world":
        raise ValueError("world_id must identify a world")
    if kind == "world" or not key:
        raise ValueError("use a non-world entity kind and a non-empty stable key")
    name = json.dumps([kind, key], ensure_ascii=True, separators=(",", ":"))
    return EntityId(kind=kind, value=uuid5(world_id.value, name))


class SimulationTime(SimulationModel):
    """Completed tick count and world year; phase is reserved for sub-year work."""

    year: Annotated[int, Field(strict=True)] = 0
    tick: NonNegativeInt = 0
    phase: NonEmptyString | None = None

    def next_year(self) -> "SimulationTime":
        if self.phase is not None:
            raise ValueError("yearly stepping does not support sub-year phases")
        return SimulationTime(year=self.year + 1, tick=self.tick + 1)


class WorldMetadata(SimulationModel):
    """Required snapshot header. Unsupported versions require an explicit migration."""

    schema_version: Literal[1]
    simulation_version: Literal[1]
    rng_algorithm: Literal["pcg64-sha256-v1"]

    @field_validator("schema_version", "simulation_version", mode="before")
    @classmethod
    def validate_version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("version must be an integer")
        return value


class WorldState(SimulationModel):
    """Minimal aggregate; domain-owned state is added when its rules are introduced."""

    id: EntityId
    seed: Annotated[int, Field(strict=True)]
    metadata: WorldMetadata
    time: SimulationTime

    @model_validator(mode="after")
    def check_world_id(self) -> "WorldState":
        if self.id.kind != "world":
            raise ValueError("WorldState.id must identify a world")
        return self

    @property
    def year(self) -> int:
        """Read-only convenience for the existing headless CLI."""
        return self.time.year

    @classmethod
    def create(cls, *, seed: int, world_key: str = "default") -> "WorldState":
        """Identical seed/key pairs identify the same reproducible initial world."""
        if type(seed) is not int:
            raise ValueError("seed must be an integer")
        if not isinstance(world_key, str) or not world_key:
            raise ValueError("world_key must be a non-empty string")
        name = json.dumps(
            ["cliova.world.v1", seed, world_key], ensure_ascii=True, separators=(",", ":")
        )
        return cls(
            id=EntityId(kind="world", value=uuid5(NAMESPACE_URL, name)),
            seed=seed,
            metadata=WorldMetadata(
                schema_version=1, simulation_version=1, rng_algorithm=RNG_ALGORITHM
            ),
            time=SimulationTime(),
        )


class SimulationChange(SimulationModel):
    """A proposed numeric change; interpretation/application belongs to its owner."""

    source: NonEmptyString
    key: NonEmptyString
    delta: float
    reason: NonEmptyString
    target: EntityId | None = None
    cause_event_ids: tuple[UUID, ...] = ()


class SimulationEvent(SimulationModel):
    """Immutable event envelope, with ordered changes and explicit causal references."""

    id: UUID
    time: SimulationTime
    source: NonEmptyString
    kind: NonEmptyString
    reason: NonEmptyString
    subjects: tuple[EntityId, ...] = ()
    cause_event_ids: tuple[UUID, ...] = ()
    changes: tuple[SimulationChange, ...] = ()
