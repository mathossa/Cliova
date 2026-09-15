from uuid import UUID

import pytest

from cliova.simulation.domains.economy import EconomyDomain, initialize_economy
from cliova.simulation.domains.knowledge import KnowledgeDomain, initialize_knowledge
from cliova.simulation.domains.knowledge.catalog import CAPABILITIES
from cliova.simulation.domains.knowledge.graph import validate_catalog
from cliova.simulation.domains.knowledge.types import (
    CapabilityRequirement,
    ExperienceGain,
    InnovationPressureSignal,
    RegionalLearningInput,
    ResourcePotentialRequirement,
)
from cliova.simulation.domains.population import initialize_population
from cliova.simulation.domains.world.fixtures import create_starter_world
from cliova.simulation.engine import SimulationEngine, TickContext, TickPhase
from cliova.simulation.history import EventHistory
from cliova.simulation.randomness import random_for
from cliova.simulation.types import (
    CapabilityProgress,
    ExperienceTrack,
    KnowledgeDomainState,
    SimulationChange,
    SimulationEvent,
    SocietyKnowledgeState,
    WorldState,
    entity_id,
)


def setup_world(region="fertile-lowlands", practice=5.0, proficiency=0.0):
    world = initialize_economy(initialize_population(create_starter_world(seed=11)))
    society = SocietyKnowledgeState(
        society_id=entity_id(world.id, "society", "travellers"),
        region_ids=(world.geography.region(region).id,),
        capabilities=(
            CapabilityProgress(
                capability_key="cultivation_efficiency",
                proficiency=proficiency,
            ),
        ),
        experience=(
            ExperienceTrack(key="cultivation", amount=practice),
            ExperienceTrack(key="extraction", amount=practice),
        ),
    )
    return initialize_knowledge(world, (society,))


def learning(world, pressure=1.0, amount=0.0, causes=()):
    society = world.knowledge.societies[0]
    return tuple(
        RegionalLearningInput(
            society_id=society.society_id,
            region_id=region,
            pressures=tuple(
                InnovationPressureSignal(
                    key=key,
                    magnitude=pressure,
                    reason="Relevant regional need",
                    cause_event_ids=causes,
                )
                for key in ("food", "metal_ore")
            ),
            experience=tuple(
                ExperienceGain(track=key, amount=amount, cause_event_ids=causes)
                for key in ("cultivation", "extraction")
            ),
        )
        for region in society.region_ids
    )


def run_learning(world, pressure=1.0, amount=0.0, years=1):
    domain = KnowledgeDomain(learning_adapter=lambda w, c: learning(w, pressure, amount))
    return SimulationEngine((domain,)).run(world, years)


def test_capability_catalog_is_acyclic():
    assert len(validate_catalog(CAPABILITIES)) == 4
    first = CAPABILITIES[0]
    bad = first.model_copy(
        update={
            "requirements": (CapabilityRequirement(capability_key="missing", min_proficiency=0.1),)
        }
    )
    with pytest.raises(ValueError, match="missing"):
        validate_catalog((bad,))
    cyclic = first.model_copy(
        update={
            "requirements": (CapabilityRequirement(capability_key=first.key, min_proficiency=0.1),)
        }
    )
    with pytest.raises(ValueError, match="acyclic"):
        validate_catalog((cyclic,))
    with pytest.raises(ValueError, match="duplicate"):
        validate_catalog((first, first))


@pytest.mark.parametrize(
    "region,practice,pressure,blocked",
    [
        ("fertile-lowlands", 5, 1, "soil_management"),
        ("fertile-lowlands", 5, 1, "ore_extraction"),
        ("fertile-lowlands", 0, 1, "cultivation_efficiency"),
        ("fertile-lowlands", 5, 0, "cultivation_efficiency"),
    ],
)
def test_missing_prerequisites_and_pressure_block_advancement(region, practice, pressure, blocked):
    result = run_learning(setup_world(region, practice), pressure)
    assert result.world.knowledge.societies[0].proficiency(blocked) == 0


def test_starting_geography_creates_different_paths():
    fertile = run_learning(setup_world(), years=3).world.knowledge.societies[0]
    highland = run_learning(setup_world("mineral-highlands"), years=3).world.knowledge.societies[0]
    assert fertile.proficiency("cultivation_efficiency") == 0.3
    assert fertile.proficiency("ore_extraction") == 0
    assert highland.proficiency("ore_extraction") == 0.3
    assert highland.proficiency("cultivation_efficiency") == 0


def test_replay_serialization_and_stable_parallel_order():
    world = setup_world("river-forest", proficiency=0.4)
    first = run_learning(world, amount=0.5, years=6)
    second = run_learning(
        WorldState.model_validate_json(world.model_dump_json()), amount=0.5, years=6
    )
    assert first.model_dump_json() == second.model_dump_json()
    assert WorldState.model_validate_json(first.world.model_dump_json()) == first.world
    keys = [c.key for c in first.ticks[0].changes if ".proficiency." in c.key]
    assert keys == sorted(keys)
    normal = KnowledgeDomain(learning_adapter=lambda w, c: learning(w))
    reversed_domain = KnowledgeDomain(
        reversed(CAPABILITIES), learning_adapter=lambda w, c: learning(w)
    )
    assert SimulationEngine((normal,)).step(world) == SimulationEngine((reversed_domain,)).step(
        world
    )


def test_effect_is_pure_scales_and_improves_actual_economy():
    world = setup_world(proficiency=0.8)
    before = world.model_dump_json()
    knowledge = KnowledgeDomain()
    region = world.knowledge.societies[0].region_ids[0]
    assert knowledge.capability_modifier(world, region, "food") == 1.2
    assert knowledge.capability_modifier(world, region, "stone") == 1
    assert world.model_dump_json() == before
    base = SimulationEngine((EconomyDomain(),)).step(world).world.economy.region(region)
    improved = SimulationEngine((EconomyDomain(knowledge.capability_modifier),)).step(world)
    assert improved.world.economy.region(region).resource("food").production == pytest.approx(
        base.resource("food").production * 1.2,
    )
    emerging = setup_world(proficiency=0.19)
    assert knowledge.capability_modifier(emerging, region, "food") == 1


def test_discovery_occurs_once_and_preserves_causal_history():
    world = setup_world(proficiency=0.15)
    society = world.knowledge.societies[0]
    parent = SimulationEvent(
        id=UUID("00000000-0000-0000-0000-000000000011"),
        time=world.time,
        source="economy",
        kind="economy.shortage",
        reason="Food shortage",
        subjects=society.region_ids,
    )
    domain = KnowledgeDomain(learning_adapter=lambda w, c: learning(w, causes=(parent.id,)))
    run = SimulationEngine((domain,)).run(world, 3)
    events = [
        e
        for t in run.ticks
        for e in t.events
        if any("cultivation_efficiency" in c.key for c in e.changes)
    ]
    assert len(events) == 1
    event = events[0]
    assert event.kind == "knowledge.capability_discovered"
    assert event.subjects == (society.society_id, *society.region_ids)
    assert event.cause_event_ids == (parent.id,)
    history = EventHistory((parent, event))
    assert parent in history.causal_chain(event.id)
    assert history.why(event.id)


def test_multitick_experience_and_no_same_tick_prerequisite_chain():
    run = run_learning(setup_world(practice=0), amount=1, years=12)
    assert run.ticks[0].world.knowledge.societies[0].practice("cultivation") == 1
    assert run.ticks[0].world.knowledge.societies[0].proficiency("cultivation_efficiency") == 0
    assert run.world.knowledge.societies[0].proficiency("cultivation_efficiency") > 0.2
    world = setup_world(proficiency=0.3)
    first = run_learning(world).world.knowledge.societies[0]
    assert first.proficiency("cultivation_efficiency") == 0.4
    assert first.proficiency("soil_management") == 0


def test_economy_adapter_accumulates_practice_and_preserves_region_causes():
    world = setup_world("dry-basin")
    domain = KnowledgeDomain()
    engine = SimulationEngine((EconomyDomain(domain.capability_modifier), domain))
    first = engine.step(world)
    region = world.knowledge.societies[0].region_ids[0]
    gain = next(c for c in first.changes if c.key == "knowledge.experience.cultivation")
    assert 0 < gain.delta < 1
    assert gain.cause_event_ids
    assert all(
        region in event.subjects for event in first.events if event.id in gain.cause_event_ids
    )
    assert engine.run(world, 5).model_dump_json() == engine.run(world, 5).model_dump_json()


def test_knowledge_survives_changed_participation_and_bonus_moves():
    world = setup_world(proficiency=0.8)
    society = world.knowledge.societies[0]
    old_region = society.region_ids[0]
    new_region = world.geography.region("river-forest").id
    moved = society.model_copy(update={"region_ids": (new_region,)})
    world = WorldState.model_validate(
        {
            **world.model_dump(),
            "knowledge": KnowledgeDomainState(societies=(moved,)),
        }
    )
    assert moved.society_id == society.society_id
    assert moved.capabilities == society.capabilities
    assert KnowledgeDomain().capability_modifier(world, old_region, "food") == 1
    assert KnowledgeDomain().capability_modifier(world, new_region, "food") == 1.2


def test_prerequisites_must_coexist_in_one_region():
    world = setup_world()
    society = world.knowledge.societies[0]
    society = society.model_copy(
        update={
            "region_ids": (
                *society.region_ids,
                world.geography.region("mineral-highlands").id,
            )
        }
    )
    world = world.model_copy(update={"knowledge": KnowledgeDomainState(societies=(society,))})
    rule = CAPABILITIES[0].model_copy(
        update={
            "requirements": (
                ResourcePotentialRequirement(resource="arable_land", min_potential=0.9),
                ResourcePotentialRequirement(resource="metal_ores", min_potential=0.9),
            )
        }
    )
    domain = KnowledgeDomain((rule,), learning_adapter=lambda w, c: learning(w))
    result = SimulationEngine((domain,)).step(world)
    assert result.world.knowledge == world.knowledge


def test_invalid_participation_and_reducer_changes_fail():
    world = setup_world()
    society = world.knowledge.societies[0]
    other = society.model_copy(update={"society_id": entity_id(world.id, "society", "other")})
    with pytest.raises(ValueError, match="unambiguous"):
        KnowledgeDomainState(societies=(society, other))
    invalid = society.model_copy(update={"region_ids": (entity_id(world.id, "region", "absent"),)})
    with pytest.raises(ValueError, match="geography"):
        WorldState.model_validate({**world.model_dump(), "knowledge": {"societies": (invalid,)}})
    for key, delta in (
        ("knowledge.proficiency.cultivation_efficiency", 2),
        ("knowledge.experience.cultivation", -10),
        ("knowledge.proficiency.missing", 0.1),
    ):
        with pytest.raises(ValueError):
            KnowledgeDomain().apply_change(
                world,
                SimulationChange(
                    source="knowledge",
                    key=key,
                    delta=delta,
                    reason="Invalid",
                    target=society.society_id,
                ),
            )


def test_zero_economy_no_presence_and_proficiency_bounds():
    world = setup_world(proficiency=0.99)
    context = TickContext(world.time.next_year(), TickPhase.KNOWLEDGE_SCENARIOS, (), ())
    result = KnowledgeDomain().step(world, context, random_for(11, 1, "knowledge"))
    assert not result.changes
    bounded = run_learning(world, years=5).world.knowledge.societies[0]
    assert bounded.proficiency("cultivation_efficiency") == 1
    absent = world.knowledge.societies[0].model_copy(update={"region_ids": ()})
    world = world.model_copy(update={"knowledge": KnowledgeDomainState(societies=(absent,))})
    assert run_learning(world).world.knowledge == world.knowledge
