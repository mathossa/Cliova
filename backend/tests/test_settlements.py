from simulation_quality import assert_replay_equivalent

from cliova.simulation.domains.knowledge import initialize_knowledge
from cliova.simulation.domains.knowledge.catalog import MOBILE_PASTORALISM_KEY
from cliova.simulation.domains.population import (
    SeasonalSubsistenceAccessDomain,
    initialize_population,
    initialize_society_region_relationships,
)
from cliova.simulation.domains.settlements import (
    STRUCTURE_DEFINITIONS,
    SettlementDomain,
    settlement_status_input,
    starter_settlement_inputs,
    structure_status_input,
)
from cliova.simulation.engine import SimulationEngine
from cliova.simulation.history import EventHistory
from cliova.simulation.types import (
    CapabilityProgress,
    GeographyState,
    KnowledgeDomainState,
    RegionConnection,
    RegionState,
    ResourcePotential,
    SettlementDomainState,
    SocietyKnowledgeState,
    SocietyRegionRelationshipState,
    WorldState,
    entity_id,
)


def _region(world: WorldState, key: str, *, grazing: float) -> RegionState:
    return RegionState(
        id=entity_id(world.id, "region", key),
        key=key,
        terrain="plain",
        biome="temperate",
        habitability=0.7,
        water_access=0.5,
        climate_pressure=0.2,
        resources=(
            ResourcePotential(resource="arable_land", potential=0.3),
            ResourcePotential(resource="grazing", potential=grazing),
            ResourcePotential(resource="wild_food", potential=0.2),
            ResourcePotential(resource="aquatic_food", potential=0.1),
        ),
    )


def _world(*, seed: int = 601, mobile: bool = True) -> tuple[WorldState, dict[str, object]]:
    world = WorldState.create(seed=seed, world_key="settlement-domain")
    core = _region(world, "core", grazing=0.1)
    seasonal = _region(world, "seasonal", grazing=1.0)
    world = world.model_copy(
        update={
            "geography": GeographyState(
                regions=(core, seasonal),
                connections=(RegionConnection(a=core.id, b=seasonal.id, travel_cost=1.0),),
            )
        }
    )
    world = initialize_population(world, total_per_region=500)
    society_id = entity_id(world.id, "society", "mobile-society")
    capabilities = (
        (CapabilityProgress(capability_key=MOBILE_PASTORALISM_KEY, proficiency=0.8),)
        if mobile
        else ()
    )
    world = initialize_knowledge(
        world,
        societies=(
            SocietyKnowledgeState(
                society_id=society_id,
                region_ids=(core.id,),
                capabilities=capabilities,
            ),
        ),
    )
    world = initialize_society_region_relationships(
        world,
        relationships=(
            SocietyRegionRelationshipState(
                society_id=society_id,
                core_region_id=core.id,
            ),
        ),
    )
    return world, {"society": society_id, "core": core, "seasonal": seasonal}


def _engine() -> SimulationEngine:
    return SimulationEngine((SeasonalSubsistenceAccessDomain(), SettlementDomain()))


def _starter_inputs(world: WorldState, ids: dict[str, object]):
    return starter_settlement_inputs(
        world,
        society_id=ids["society"],
        core_region_id=ids["core"].id,
        camp_region_id=ids["seasonal"].id,
    )


def _starter_tick(*, seed: int = 601):
    world, ids = _world(seed=seed)
    result = _engine().step(world, inputs=_starter_inputs(world, ids))
    return world, ids, result


def test_world_can_have_zero_settlements() -> None:
    world = WorldState.create(seed=600, world_key="no-settlements")
    assert world.settlements == SettlementDomainState()
    result = SimulationEngine((SettlementDomain(),)).step(world)
    assert result.world.settlements == SettlementDomainState()


def test_starter_fixture_has_permanent_settlement_seasonal_camp_and_strategic_structures() -> None:
    before, ids, result = _starter_tick()
    state = result.world.settlements
    assert len(state.settlements) == 2
    assert {settlement.archetype for settlement in state.settlements} == {
        "permanent",
        "seasonal_camp",
    }
    permanent = next(item for item in state.settlements if item.archetype == "permanent")
    camp = next(item for item in state.settlements if item.archetype == "seasonal_camp")
    assert permanent.region_id == ids["core"].id
    assert permanent.population_estimate == 700
    assert camp.region_id == ids["seasonal"].id
    assert camp.population_estimate == 120
    assert camp.status == "active"
    assert {structure.definition_id for structure in state.structures} == {
        "storage",
        "workshop",
        "livestock_enclosure",
    }

    assert before.population is not None and result.world.population is not None
    assert sum(item.total for item in result.world.population.regions) == sum(
        item.total for item in before.population.regions
    )


def test_seasonal_camp_presence_does_not_rewrite_core_region_or_imply_control() -> None:
    _, ids, result = _starter_tick(seed=603)
    relationship = result.world.society_regions[0]
    camp = next(
        item for item in result.world.settlements.settlements if item.archetype == "seasonal_camp"
    )

    assert relationship.core_region_id == ids["core"].id
    assert relationship.temporary_access[0].region_id == ids["seasonal"].id
    assert camp.region_id == ids["seasonal"].id
    assert result.world.knowledge is not None
    assert result.world.knowledge.societies[0].region_ids == (ids["core"].id,)
    assert result.world.governance == ()


def test_settlement_and_structure_ids_survive_serialization_and_match_stable_keys() -> None:
    _, _, result = _starter_tick(seed=607)
    restored = WorldState.model_validate_json(result.world.model_dump_json())
    assert tuple(item.id for item in restored.settlements.settlements) == tuple(
        item.id for item in result.world.settlements.settlements
    )
    assert tuple(item.id for item in restored.settlements.structures) == tuple(
        item.id for item in result.world.settlements.structures
    )
    for settlement in restored.settlements.settlements:
        assert settlement.id == entity_id(restored.id, "settlement", settlement.key)
    for structure in restored.settlements.structures:
        assert structure.id == entity_id(restored.id, "structure", structure.key)


def test_structure_lifecycle_is_small_and_deterministic() -> None:
    _, _, established = _starter_tick(seed=611)
    storage = next(
        item for item in established.world.settlements.structures if item.definition_id == "storage"
    )
    damaged = _engine().step(
        established.world,
        inputs=(structure_status_input(storage, "damaged", reason="Flood damage."),),
    )
    current = damaged.world.settlements.settlement(storage.settlement_id)
    damaged_storage = next(
        item for item in damaged.world.settlements.structures if item.id == storage.id
    )
    assert current.id == storage.settlement_id
    assert damaged_storage.status == "damaged"

    destroyed = _engine().step(
        damaged.world,
        inputs=(
            structure_status_input(
                damaged_storage,
                "destroyed",
                reason="The damaged storage was lost.",
            ),
        ),
    )
    final_storage = next(
        item for item in destroyed.world.settlements.structures if item.id == storage.id
    )
    assert final_storage.status == "destroyed"
    assert {event.kind for event in damaged.events} >= {"structure-damaged"}
    assert {event.kind for event in destroyed.events} >= {"structure-destroyed"}


def test_permanent_settlement_can_be_abandoned_without_city_progression_rules() -> None:
    _, _, established = _starter_tick(seed=613)
    permanent = next(
        item for item in established.world.settlements.settlements if item.archetype == "permanent"
    )
    result = _engine().step(
        established.world,
        inputs=(
            settlement_status_input(
                permanent,
                "abandoned",
                reason="Residents left the settlement.",
            ),
        ),
    )
    current = result.world.settlements.settlement(permanent.id)
    assert current.status == "abandoned"
    assert current.archetype == "permanent"
    assert any(event.kind == "settlement-abandoned" for event in result.events)


def test_history_records_establishment_completion_and_causal_camp_return() -> None:
    _, ids, result = _starter_tick(seed=617)
    history = EventHistory(result.events)
    assert len(history.query(event_type="settlement-established", source="settlements")) == 1
    assert len(history.query(event_type="camp-established", source="settlements")) == 1
    assert len(history.query(event_type="structure-completed", source="settlements")) == 3

    access = history.query(
        subject=ids["society"],
        event_type="seasonal-subsistence-access",
        source="seasonal_access",
    )
    returned = history.query(
        subject=ids["society"],
        event_type="camp-returned",
        source="settlements",
    )
    assert len(access) == len(returned) == 1
    assert returned[0].cause_event_ids == (access[0].id,)


def test_camp_becomes_dormant_when_50_temporary_presence_ends() -> None:
    _, ids, active = _starter_tick(seed=619)
    assert active.world.knowledge is not None
    society = active.world.knowledge.societies[0].model_copy(update={"capabilities": ()})
    without_mobile_capability = active.world.model_copy(
        update={"knowledge": KnowledgeDomainState(societies=(society,))}
    )

    ended = _engine().step(without_mobile_capability)
    relationship = ended.world.society_regions[0]
    camp = next(
        item for item in ended.world.settlements.settlements if item.archetype == "seasonal_camp"
    )
    assert relationship.core_region_id == ids["core"].id
    assert relationship.temporary_access == ()
    assert camp.region_id == ids["seasonal"].id
    assert camp.status == "dormant"
    access_ended = next(
        event for event in ended.events if event.kind == "seasonal-subsistence-access-ended"
    )
    camp_dormant = next(event for event in ended.events if event.kind == "camp-dormant")
    assert camp_dormant.cause_event_ids == (access_ended.id,)


def test_legacy_world_payload_without_settlement_state_loads_empty() -> None:
    world = WorldState.create(seed=623, world_key="legacy-without-settlements")
    payload = world.model_dump()
    payload.pop("settlements")
    restored = WorldState.model_validate(payload)
    assert restored.settlements == SettlementDomainState()


def test_replay_is_equivalent_for_settlement_and_camp_lifecycle() -> None:
    template, ids = _world(seed=631)
    inputs = (_starter_inputs(template, ids), (), ())
    first, second = assert_replay_equivalent(
        lambda: _world(seed=631)[0],
        _engine,
        years=3,
        inputs=inputs,
    )
    assert first.run.world.settlements == second.run.world.settlements


def test_visual_houses_and_tents_are_not_authoritative_structure_definitions() -> None:
    definition_keys = {definition.key for definition in STRUCTURE_DEFINITIONS}
    assert definition_keys.isdisjoint({"house", "dwelling", "tent", "garden", "fence", "shed"})
    _, _, result = _starter_tick(seed=641)
    assert len(result.world.settlements.structures) == 3
