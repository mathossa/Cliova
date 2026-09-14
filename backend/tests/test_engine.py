import pytest

from cliova.simulation.engine import SimulationEngine
from cliova.simulation.randomness import RandomSource
from cliova.simulation.types import SimulationChange, WorldState


class SampleDomain:
    name = "sample"

    def step(
        self, world: WorldState, year: int, rng: RandomSource
    ) -> list[SimulationChange]:
        assert year == world.year + 1
        return [SimulationChange(
            source=self.name, key="sample", delta=rng.random(), reason="seeded sample"
        )]


def test_engine_advances_requested_years() -> None:
    initial = WorldState.create(seed=42)
    world, changes = SimulationEngine().run(initial, years=3)
    assert world.year == 3
    assert world.time.tick == 3
    assert world.id == initial.id
    assert world.metadata == initial.metadata
    assert initial.year == 0
    assert changes == []


def test_engine_rejects_negative_years() -> None:
    with pytest.raises(ValueError, match="years must be non-negative"):
        SimulationEngine().run(WorldState.create(seed=42), years=-1)


def test_zero_ticks_returns_same_state() -> None:
    world = WorldState.create(seed=42)
    result, changes = SimulationEngine().run(world, years=0)
    assert result is world
    assert changes == []


def test_seeded_multi_tick_replay_and_snapshot_resume() -> None:
    initial = WorldState.create(seed=42)
    engine = SimulationEngine([SampleDomain()])
    expected = engine.run(initial, years=3)
    assert engine.run(WorldState.create(seed=42), years=3) == expected
    midway, first_changes = engine.run(initial, years=1)
    restored = WorldState.model_validate_json(midway.model_dump_json())
    final, later_changes = SimulationEngine([SampleDomain()]).run(restored, years=2)
    assert (final, first_changes + later_changes) == expected
    assert initial.time.tick == 0


def test_failure_does_not_advance_input_and_retry_replays() -> None:
    class FailingDomain(SampleDomain):
        def step(
            self, world: WorldState, year: int, rng: RandomSource
        ) -> list[SimulationChange]:
            rng.random()
            raise RuntimeError("domain failed")

    initial = WorldState.create(seed=42)
    snapshot = initial.model_dump_json()
    with pytest.raises(RuntimeError, match="domain failed"):
        SimulationEngine([FailingDomain()]).step(initial)
    assert initial.model_dump_json() == snapshot
    engine = SimulationEngine([SampleDomain()])
    assert engine.step(initial) == engine.step(WorldState.model_validate_json(snapshot))


def test_rng_dependency_can_be_injected() -> None:
    calls: list[tuple[int, int, str]] = []

    class FixedRandom:
        def random(self) -> float:
            return 0.25

    def factory(seed: int, tick: int, domain: str) -> RandomSource:
        calls.append((seed, tick, domain))
        return FixedRandom()

    _, changes = SimulationEngine([SampleDomain()], rng_factory=factory).run(
        WorldState.create(seed=7), years=2
    )
    assert calls == [(7, 1, "sample"), (7, 2, "sample")]
    assert [change.delta for change in changes] == [0.25, 0.25]


def test_domain_order_is_explicit_and_streams_are_independent() -> None:
    first = SampleDomain()
    second = SampleDomain()
    second.name = "second"
    initial = WorldState.create(seed=42)
    _, forward = SimulationEngine([first, second]).step(initial)
    _, reverse = SimulationEngine([second, first]).step(initial)
    assert [change.source for change in forward] == ["sample", "second"]
    assert forward == list(reversed(reverse))


def test_duplicate_domain_names_are_rejected() -> None:
    with pytest.raises(ValueError, match="unique"):
        SimulationEngine([SampleDomain(), SampleDomain()])
