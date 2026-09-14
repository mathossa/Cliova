from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from math import isfinite
from statistics import median
from time import perf_counter_ns
from typing import Any

from pydantic import BaseModel

from cliova.simulation.engine import SimulationEngine
from cliova.simulation.history import EventHistory
from cliova.simulation.types import (
    EntityId,
    SimulationInput,
    SimulationRunResult,
    TickResult,
    WorldState,
)


class SimulationQualityError(AssertionError):
    """Invariant/replay failure with reproducible simulation context."""


@dataclass(frozen=True, slots=True)
class HeadlessTrace:
    initial_world: WorldState
    run: SimulationRunResult

    @property
    def seed(self) -> int:
        return self.initial_world.seed


@dataclass(frozen=True, slots=True)
class TickTiming:
    durations_ns: tuple[int, ...]

    @property
    def median_ns(self) -> float:
        return median(self.durations_ns)

    @property
    def median_ms(self) -> float:
        return self.median_ns / 1_000_000


def run_headless(
    world_factory: Callable[[], WorldState],
    engine_factory: Callable[[], SimulationEngine],
    *,
    years: int,
    inputs: Sequence[Sequence[SimulationInput]] = (),
) -> HeadlessTrace:
    """Run existing engine ticks one-by-one so failures retain exact tick context."""
    if type(years) is not int or years < 0:
        raise ValueError("years must be non-negative")

    input_batches = tuple(tuple(batch) for batch in inputs)
    if len(input_batches) > years:
        raise ValueError("input batches cannot exceed requested years")

    initial_world = world_factory()
    engine = engine_factory()
    world = initial_world
    ticks: list[TickResult] = []
    for index in range(years):
        tick = engine.step(world, inputs=input_batches[index] if index < len(input_batches) else ())
        ticks.append(tick)
        world = tick.world

    return HeadlessTrace(
        initial_world=initial_world,
        run=SimulationRunResult(world=world, ticks=tuple(ticks)),
    )


def assert_core_invariants(trace: HeadlessTrace) -> None:
    """Check only dependency-independent invariants valid for every simulation domain."""
    assert_monotonic_ticks(trace)
    assert_unique_event_ids(trace)
    assert_stable_entity_ids(trace.initial_world, seed=trace.seed, tick=trace.initial_world.time.tick)
    assert_finite_values(trace.initial_world, seed=trace.seed, tick=trace.initial_world.time.tick)

    expected_world_id = trace.initial_world.id
    for tick_result in trace.run.ticks:
        tick = tick_result.world.time.tick
        if tick_result.world.id != expected_world_id:
            _fail(
                "stable-world-id",
                seed=trace.seed,
                tick=tick,
                detail=f"expected={expected_world_id.value} actual={tick_result.world.id.value}",
            )
        assert_stable_entity_ids(tick_result.world, seed=trace.seed, tick=tick)
        assert_finite_values(tick_result, seed=trace.seed, tick=tick)


def assert_replay_equivalent(
    world_factory: Callable[[], WorldState],
    engine_factory: Callable[[], SimulationEngine],
    *,
    years: int,
    inputs: Sequence[Sequence[SimulationInput]] = (),
) -> tuple[HeadlessTrace, HeadlessTrace]:
    """Replay a case from fresh state/engine instances and compare state plus history."""
    input_batches = tuple(tuple(batch) for batch in inputs)
    first = run_headless(world_factory, engine_factory, years=years, inputs=input_batches)
    second = run_headless(world_factory, engine_factory, years=years, inputs=input_batches)
    assert_core_invariants(first)
    assert_core_invariants(second)

    if first.initial_world != second.initial_world:
        difference = _first_difference(first.initial_world, second.initial_world)
        _fail(
            "replay-initial-state",
            seed=first.seed,
            tick=first.initial_world.time.tick,
            detail=_format_difference(difference),
        )

    for first_tick, second_tick in zip(first.run.ticks, second.run.ticks, strict=True):
        tick = first_tick.world.time.tick
        if first_tick.world != second_tick.world:
            difference = _first_difference(first_tick.world, second_tick.world)
            _fail(
                "replay-world-state",
                seed=first.seed,
                tick=tick,
                detail=_format_difference(difference),
            )
        if first_tick.events != second_tick.events:
            difference = _first_difference(first_tick.events, second_tick.events)
            _fail(
                "replay-history",
                seed=first.seed,
                tick=tick,
                detail=_format_difference(difference),
            )

    first_history = EventHistory.from_run(first.run).events
    second_history = EventHistory.from_run(second.run).events
    if first.run.world != second.run.world:
        difference = _first_difference(first.run.world, second.run.world)
        _fail(
            "replay-final-state",
            seed=first.seed,
            tick=first.run.world.time.tick,
            detail=_format_difference(difference),
        )
    if first_history != second_history:
        difference = _first_difference(first_history, second_history)
        _fail(
            "replay-final-history",
            seed=first.seed,
            tick=first.run.world.time.tick,
            detail=_format_difference(difference),
        )

    return first, second


def assert_monotonic_ticks(trace: HeadlessTrace) -> None:
    expected = trace.initial_world.time.tick
    for tick_result in trace.run.ticks:
        expected += 1
        actual = tick_result.world.time.tick
        if actual != expected:
            _fail(
                "monotonic-ticks",
                seed=trace.seed,
                tick=actual,
                detail=f"expected tick {expected}, got {actual}",
            )
        for event in tick_result.events:
            if event.time.tick != actual:
                _fail(
                    "event-tick-alignment",
                    seed=trace.seed,
                    tick=actual,
                    detail=f"event={event.id} has tick {event.time.tick}",
                )


def assert_unique_event_ids(trace: HeadlessTrace) -> None:
    seen: dict[object, int] = {}
    for tick_result in trace.run.ticks:
        tick = tick_result.world.time.tick
        for event in tick_result.events:
            first_tick = seen.get(event.id)
            if first_tick is not None:
                _fail(
                    "unique-event-ids",
                    seed=trace.seed,
                    tick=tick,
                    detail=f"event={event.id} first_seen_tick={first_tick}",
                )
            seen[event.id] = tick


def assert_stable_entity_ids(world: WorldState, *, seed: int, tick: int) -> None:
    """Ensure every currently materialized entity ID survives authoritative JSON round-trip."""
    restored = WorldState.model_validate_json(world.model_dump_json())
    before = tuple(_iter_entity_ids(world))
    after = tuple(_iter_entity_ids(restored))
    if before != after:
        difference = _first_difference(before, after)
        _fail(
            "stable-entity-ids",
            seed=seed,
            tick=tick,
            detail=_format_difference(difference),
        )


def assert_finite_values(value: object, *, seed: int, tick: int) -> None:
    """Reject NaN/infinite floats anywhere in a nested authoritative/test payload."""
    for path, candidate in _iter_floats(value):
        if not isfinite(candidate):
            _fail(
                "finite-values",
                seed=seed,
                tick=tick,
                detail=f"path={path} value={candidate!r}",
            )


def measure_tick_runtime(
    world_factory: Callable[[], WorldState],
    engine_factory: Callable[[], SimulationEngine],
    *,
    repeats: int = 5,
) -> TickTiming:
    """Measure one fresh headless tick repeatedly; report only, never enforce a threshold."""
    if type(repeats) is not int or repeats <= 0:
        raise ValueError("repeats must be a positive integer")

    # One untimed warm-up avoids making import/cache setup part of the reported samples.
    engine_factory().step(world_factory())

    durations: list[int] = []
    for _ in range(repeats):
        world = world_factory()
        engine = engine_factory()
        started = perf_counter_ns()
        engine.step(world)
        durations.append(perf_counter_ns() - started)
    return TickTiming(durations_ns=tuple(durations))


def _iter_entity_ids(value: object, path: str = "world"):
    if isinstance(value, EntityId):
        yield path, value
        return
    if isinstance(value, BaseModel):
        for field_name in type(value).model_fields:
            yield from _iter_entity_ids(getattr(value, field_name), f"{path}.{field_name}")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            yield from _iter_entity_ids(item, f"{path}[{key!r}]")
        return
    if isinstance(value, (tuple, list)):
        for index, item in enumerate(value):
            yield from _iter_entity_ids(item, f"{path}[{index}]")


def _iter_floats(value: object, path: str = "root"):
    if isinstance(value, float):
        yield path, value
        return
    if isinstance(value, BaseModel):
        for field_name in type(value).model_fields:
            yield from _iter_floats(getattr(value, field_name), f"{path}.{field_name}")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            yield from _iter_floats(item, f"{path}[{key!r}]")
        return
    if isinstance(value, (tuple, list)):
        for index, item in enumerate(value):
            yield from _iter_floats(item, f"{path}[{index}]")


def _first_difference(left: object, right: object, path: str = "root") -> tuple[str, object, object] | None:
    if isinstance(left, BaseModel) and isinstance(right, BaseModel):
        return _first_difference(
            left.model_dump(mode="python"), right.model_dump(mode="python"), path
        )
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        left_keys = tuple(left.keys())
        right_keys = tuple(right.keys())
        if left_keys != right_keys:
            return path, left_keys, right_keys
        for key in left_keys:
            difference = _first_difference(left[key], right[key], f"{path}.{key}")
            if difference is not None:
                return difference
        return None
    if isinstance(left, (tuple, list)) and isinstance(right, (tuple, list)):
        if len(left) != len(right):
            return f"{path}.length", len(left), len(right)
        for index, (left_item, right_item) in enumerate(zip(left, right, strict=True)):
            difference = _first_difference(left_item, right_item, f"{path}[{index}]")
            if difference is not None:
                return difference
        return None
    if left != right:
        return path, left, right
    return None


def _format_difference(difference: tuple[str, object, object] | None) -> str:
    if difference is None:
        return "values differ without a discoverable structural path"
    path, left, right = difference
    return f"path={path} first={left!r} replay={right!r}"


def _fail(invariant: str, *, seed: int, tick: int, detail: str) -> None:
    raise SimulationQualityError(f"{invariant} failed: seed={seed} tick={tick}; {detail}")
