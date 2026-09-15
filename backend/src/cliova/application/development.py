"""Development-only application assembly for the first playable vertical slice."""

from cliova.simulation.domains.directives import DirectiveAwareEconomyDomain, DirectiveDomain
from cliova.simulation.domains.economy import initialize_economy
from cliova.simulation.domains.knowledge import KnowledgeDomain, initialize_knowledge
from cliova.simulation.domains.politics import GovernanceDomain, initialize_governance
from cliova.simulation.domains.population import PopulationDomain, initialize_population
from cliova.simulation.domains.scenarios import ScenarioDomain
from cliova.simulation.domains.world.fixtures import create_starter_world
from cliova.simulation.engine import SimulationEngine
from cliova.simulation.types import (
    GovernanceState,
    InstitutionProfile,
    SocietyKnowledgeState,
    WorldState,
    entity_id,
)


def create_development_world(*, seed: int, world_key: str) -> WorldState:
    """Create the deterministic seeded fixture used by development HTTP workflows.

    This is intentionally a development fixture, not a production world-generation policy.
    The society/governance values mirror the existing persistence integration fixture so the
    first vertical slice has one valid directive target without inventing production setup UX.
    """

    world = initialize_economy(
        initialize_population(create_starter_world(seed=seed, world_key=world_key))
    )
    assert world.geography is not None
    region_id = world.geography.region("fertile-lowlands").id
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
    return initialize_knowledge(
        world,
        societies=(SocietyKnowledgeState(society_id=society_id, region_ids=(region_id,)),),
    )


def create_simulation_engine() -> SimulationEngine:
    """Assemble the currently merged authoritative domains for persisted manual ticks."""

    knowledge = KnowledgeDomain()
    return SimulationEngine(
        (
            PopulationDomain(),
            DirectiveAwareEconomyDomain(capability_modifier=knowledge.capability_modifier),
            GovernanceDomain(),
            DirectiveDomain(),
            knowledge,
            ScenarioDomain(),
        )
    )
