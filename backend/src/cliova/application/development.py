"""Development-only application assembly for the first playable vertical slice."""

from cliova.simulation.domains.directives import DirectiveAwareEconomyDomain, DirectiveDomain
from cliova.simulation.domains.economy import initialize_economy
from cliova.simulation.domains.knowledge import KnowledgeDomain, initialize_knowledge
from cliova.simulation.domains.politics import GovernanceDomain, initialize_governance
from cliova.simulation.domains.population import (
    PopulationDomain,
    SeasonalSubsistenceAccessDomain,
    initialize_population,
    initialize_society_region_relationships,
)
from cliova.simulation.domains.scenarios import ScenarioDomain
from cliova.simulation.domains.settlements import SettlementDomain
from cliova.simulation.domains.world.fixtures import create_starter_world
from cliova.simulation.engine import SimulationEngine
from cliova.simulation.types import (
    GovernanceState,
    InstitutionProfile,
    SocietyKnowledgeState,
    SocietyRegionRelationshipState,
    WorldState,
    entity_id,
)


def create_development_world(
    *, seed: int, world_key: str, generated_geography: bool = False
) -> WorldState:
    """Create a seeded development world with fixture or production-generated geography.

    Existing callers keep the fast hand-authored fixture by default. The Command Center can
    explicitly request #59 generation so strategic-map development uses real persisted geometry.
    Generated worlds begin inhabited only in the society's deterministic core region rather than
    assigning population to every physical region, including ocean regions.
    """
    base = (
        WorldState.create(seed=seed, world_key=world_key)
        if generated_geography
        else create_starter_world(seed=seed, world_key=world_key)
    )
    assert base.geography is not None

    if generated_geography:
        core_region = max(
            base.geography.regions,
            key=lambda region: (
                region.surface != "ocean",
                region.habitability,
                region.water_access,
                -region.climate_pressure,
                region.key,
            ),
        )
        region_id = core_region.id
        world = initialize_economy(initialize_population(base, region_ids=(region_id,)))
    else:
        region_id = base.geography.region("fertile-lowlands").id
        world = initialize_economy(initialize_population(base))

    society_id = entity_id(world.id, "society", "river-council")
    governance = GovernanceState(
        subject_id=society_id,
        region_id=region_id,
        institution=InstitutionProfile(
            key="neutral-coordination",
            coordination_efficiency=1.0,
            stress_resilience=1.0,
            adaptation_rate=0.0,
        ),
        legitimacy=0.9,
        execution_capacity=0.9,
        internal_resistance=0.1,
    )
    world = initialize_governance(world, states=(governance,))
    world = initialize_knowledge(
        world,
        societies=(SocietyKnowledgeState(society_id=society_id, region_ids=(region_id,)),),
    )
    return initialize_society_region_relationships(
        world,
        relationships=(
            SocietyRegionRelationshipState(
                society_id=society_id,
                core_region_id=region_id,
            ),
        ),
    )


def create_simulation_engine() -> SimulationEngine:
    """Assemble the currently merged authoritative domains for persisted manual ticks."""

    knowledge = KnowledgeDomain()
    return SimulationEngine(
        (
            PopulationDomain(),
            SeasonalSubsistenceAccessDomain(),
            SettlementDomain(),
            DirectiveAwareEconomyDomain(capability_modifier=knowledge.capability_modifier),
            GovernanceDomain(),
            DirectiveDomain(),
            knowledge,
            ScenarioDomain(),
        )
    )
