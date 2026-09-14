from cliova.simulation.engine import SimulationEngine
from cliova.simulation.types import WorldState


def test_engine_advances_requested_years() -> None:
    world = WorldState(seed=42)
    world, changes = SimulationEngine().run(world, years=100)

    assert world.year == 100
    assert changes == []


def test_engine_rejects_negative_years() -> None:
    world = WorldState(seed=42)

    try:
        SimulationEngine().run(world, years=-1)
    except ValueError as exc:
        assert str(exc) == "years must be non-negative"
    else:
        raise AssertionError("negative years must fail")
