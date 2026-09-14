from uuid import UUID, uuid5

import pytest

from cliova.simulation.engine import SimulationEngine, TickContext, TickPhase
from cliova.simulation.history import EventHistory
from cliova.simulation.randomness import RandomSource
from cliova.simulation.types import (
    DomainResult,
    EventProposal,
    SimulationEvent,
    SimulationTime,
    WorldState,
    entity_id,
)


def _event_id(world: WorldState, key: str) -> UUID:
    return uuid5(world.id.value, f"history-test:{key}")


def _event(
    world: WorldState,
    key: str,
    *,
    year: int,
    source: str,
    kind: str,
    reason: str,
    subjects=(),
    causes=(),
) -> SimulationEvent:
    return SimulationEvent(
        id=_event_id(world, key),
        time=SimulationTime(year=year, tick=year),
        source=source,
        kind=kind,
        reason=reason,
        subjects=subjects,
        cause_event_ids=causes,
    )


def test_history_filters_by_year_subject_and_event_type_in_canonical_order() -> None:
    world = WorldState.create(seed=17, world_key="history-filter")
    north = entity_id(world.id, "region", "north")
    south = entity_id(world.id, "region", "south")
    northern_society = entity_id(world.id, "society", "northern-society")

    first = _event(
        world,
        "first",
        year=1,
        source="population",
        kind="migration",
        reason="Families moved north",
        subjects=(north, northern_society),
    )
    second = _event(
        world,
        "second",
        year=2,
        source="economy",
        kind="food-security",
        reason="Food security fell",
        subjects=(north, northern_society),
    )
    third = _event(
        world,
        "third",
        year=3,
        source="governance",
        kind="directive-outcome",
        reason="Rationing was extended",
        subjects=(south,),
    )

    history = EventHistory((third, first, second))

    assert history.query(start_year=1, end_year=2) == (first, second)
    assert history.query(subject=north) == (first, second)
    assert history.query(subject=northern_society, event_type="food-security") == (second,)
    assert history.query(year=3, source="governance") == (third,)


def test_query_rejects_ambiguous_or_inverted_time_filters() -> None:
    history = EventHistory()

    with pytest.raises(ValueError, match="year cannot be combined"):
        history.query(year=2, start_year=1)
    with pytest.raises(ValueError, match="start_year"):
        history.query(start_year=3, end_year=2)


def test_why_handles_multi_cause_chain_across_multiple_ticks() -> None:
    world = WorldState.create(seed=23, world_key="history-causes")
    society = entity_id(world.id, "society", "river-society")

    dry_season = _event(
        world,
        "dry-season",
        year=1,
        source="world",
        kind="dry-season",
        reason="Rainfall stayed below normal",
        subjects=(society,),
    )
    harvest = _event(
        world,
        "harvest",
        year=2,
        source="economy",
        kind="poor-harvest",
        reason="The harvest was poor",
        subjects=(society,),
        causes=(dry_season.id,),
    )
    trade = _event(
        world,
        "trade",
        year=2,
        source="economy",
        kind="trade-disruption",
        reason="Imported grain declined",
        subjects=(society,),
        causes=(dry_season.id,),
    )
    food_security = _event(
        world,
        "food-security",
        year=3,
        source="population",
        kind="food-security",
        reason="Food security fell",
        subjects=(society,),
        causes=(harvest.id, trade.id),
    )

    history = EventHistory((food_security, trade, dry_season, harvest))

    assert history.causal_chain(food_security.id) == (
        dry_season,
        harvest,
        trade,
        food_security,
    )
    assert history.causal_chain(food_security.id, include_target=False) == (
        dry_season,
        harvest,
        trade,
    )

    explanations = history.why(food_security.id)
    assert [explanation.event_id for explanation in explanations] == [
        dry_season.id,
        harvest.id,
        trade.id,
        food_security.id,
    ]
    assert explanations[-1].message == "Food security fell"
    assert explanations[-1].cause_event_ids == (harvest.id, trade.id)


def test_causal_chain_rejects_missing_causes_and_cycles() -> None:
    world = WorldState.create(seed=29, world_key="history-invalid")
    missing_id = _event_id(world, "missing")
    incomplete = _event(
        world,
        "incomplete",
        year=2,
        source="economy",
        kind="shortage",
        reason="A shortage occurred",
        causes=(missing_id,),
    )

    with pytest.raises(KeyError, match="missing causal event"):
        EventHistory((incomplete,)).causal_chain(incomplete.id)

    first_id = _event_id(world, "cycle-first")
    second_id = _event_id(world, "cycle-second")
    first = SimulationEvent(
        id=first_id,
        time=SimulationTime(year=1, tick=1),
        source="population",
        kind="cycle-a",
        reason="Cycle A",
        cause_event_ids=(second_id,),
    )
    second = SimulationEvent(
        id=second_id,
        time=SimulationTime(year=2, tick=2),
        source="economy",
        kind="cycle-b",
        reason="Cycle B",
        cause_event_ids=(first_id,),
    )

    with pytest.raises(ValueError, match="causal cycle"):
        EventHistory((first, second)).causal_chain(second.id)


def test_chronology_is_generated_from_event_fields_without_becoming_state() -> None:
    world = WorldState.create(seed=31, world_key="history-chronology")
    event = _event(
        world,
        "directive",
        year=4,
        source="governance",
        kind="directive-outcome",
        reason="Emergency grain reserves were opened",
    )
    history = EventHistory((event,))

    assert history.chronology() == (
        "Year 4: Emergency grain reserves were opened (directive-outcome, governance)",
    )
    assert history.events == (event,)


def test_replay_produces_equivalent_history_ids_and_content() -> None:
    class HistoryDomain:
        name = "economy"
        phase = TickPhase.ECONOMY

        def step(
            self, world: WorldState, context: TickContext, rng: RandomSource
        ) -> DomainResult:
            return DomainResult(
                events=(
                    EventProposal(
                        kind="market-shift",
                        reason=f"Market conditions changed in year {context.time.year}",
                    ),
                )
            )

        def apply_change(self, world: WorldState, change) -> WorldState:
            return world

    first = SimulationEngine((HistoryDomain(),)).run(
        WorldState.create(seed=37, world_key="history-replay"), years=2
    )
    second = SimulationEngine((HistoryDomain(),)).run(
        WorldState.create(seed=37, world_key="history-replay"), years=2
    )

    first_events = EventHistory.from_run(first).events
    second_events = EventHistory.from_run(second).events

    assert first_events == second_events
    assert tuple(event.model_dump_json() for event in first_events) == tuple(
        event.model_dump_json() for event in second_events
    )
