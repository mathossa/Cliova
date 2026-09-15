# Knowledge and innovation (#11)

Knowledge belongs to a stable society identity. Regional participation identifies where
its practical activity occurs; it is neither territorial ownership nor a permanent home.
A caller supplies society IDs and participating region IDs explicitly. A society may
participate in zero, one or several regions. Knowledge survives replacing this mapping.
Movement simulation, territorial control and regional attachment are outside this issue.

The initial economy adapter attributes each participating region's whole economic output
to one society. Overlapping attribution is rejected rather than double-counting practice
or applying competing modifiers. This is an integration limitation of the current regional
economy, not a rule that multiple societies cannot inhabit a region. Shared participation
will require an explicit activity allocation contract. Unmapped regions retain neutral bonuses.

## Rules

Four generic capabilities cover cultivation efficiency, soil management, ore extraction
and advanced extraction. A disposable NetworkX DAG validates missing references and cycles.
The catalog and saved state are immutable Pydantic models, not graph objects. There are
no eras, global research currency or compulsory progression between the two branches.

Each capability has proficiency in [0, 1], an activation threshold, composable resource,
experience and capability prerequisites, and an economic effect. All prerequisites must
hold within one participating region. Experience and capability prerequisites use the
pre-step society snapshot; this tick's new practice becomes available next tick. Dependent
capabilities cannot unlock each other during the same evaluation.

The initial adapter reads #7 food and metal_ore outputs. Per region/track/tick:

- Practice gain is `production / max(production, demand)`, or zero when both are zero.
  It is at most one unit, avoiding an arbitrary advantage from resource quantity units.
- Pressure is `0.25 + 0.75 * shortage_severity` when demand is positive, otherwise zero.
  Ordinary demand motivates improvement; shortage strengthens it.
- Proficiency gain is `0.1 * pressure * min(1, accumulated_track_experience / 5)`.
  Unavailable prerequisites or zero pressure prevent any proficiency gain.

Gains are rounded to six decimals and proficiency is capped at one. Society experience
sums regional practice. Proficiency uses the strongest locally eligible opportunity once
per capability per tick, breaking ties by stable region ID. Different regions cannot
pool resource prerequisites. Existing practical experience can support innovation under
new demand even when that tick has no production; resource requirements still apply.
Constants and activation/experience thresholds are provisional tuning in `catalog.py`.

Once activated, an effect contributes `max_bonus * proficiency` to the regional multiplier.
Multiple relevant effects add to the neutral multiplier of one. Economy still owns every
production, extraction, demand and reserve formula. Resource scarcity can make a retained
capability unusable through the existing production formula without deleting knowledge.

## Headless integration

```python
from cliova.simulation.domains.economy import EconomyDomain
from cliova.simulation.domains.knowledge import KnowledgeDomain, initialize_knowledge
from cliova.simulation.engine import SimulationEngine
from cliova.simulation.types import SocietyKnowledgeState, entity_id

# world already has geography, initialized population and economy.
world = initialize_knowledge(world, (
    SocietyKnowledgeState(
        society_id=entity_id(world.id, "society", "travellers"),
        region_ids=(world.geography.region("fertile-lowlands").id,),
    ),
))
knowledge = KnowledgeDomain()
engine = SimulationEngine((EconomyDomain(knowledge.capability_modifier), knowledge))
result = engine.run(world, years=12)
```

Economy must run before the default knowledge adapter, in the existing economy phase.
The adapter reads the resulting current-tick production/demand; it must not be scheduled
alone against stale economy output. Knowledge runs in `KNOWLEDGE_SCENARIOS`, so newly
activated capabilities first affect production next tick. No engine ordering changes are
needed. A knowledge-only test or alternate caller can supply a `learning_adapter` returning
explicit `RegionalLearningInput` values. This is not a directive implementation.

Numeric writes use knowledge-owned `SimulationChange` values and the existing reducer
protocol. WorldState gains only optional knowledge state and region-reference validation;
old snapshots without it remain loadable. No population pressure boundary or governance
files change. Runtime movement/input lifecycle is intentionally not introduced.

## Causality and future traces

Crossing activation emits exactly one `knowledge.capability_discovered` event, with society
and the selected region as subjects, numeric proficiency change, practice, pressure and
regional context in the explanation. Relevant current-tick economic event IDs propagate
through learning inputs to changes and discovery events. Ordinary growth remains numeric;
if there is no significant economic event, the reason still records the measured inputs.
`EventHistory.causal_chain()` and `why()` work unchanged. Earlier experience is represented
by its accumulated value; this first model does not retain every past activity's event ID.

Historical discoveries remain in history independently of later location. Physical traces,
knowledge loss, rediscovery and regional attachment need a separate design; these events
do not automatically transfer knowledge to other societies.

## Reuse and validation

Uses the existing NetworkX dependency through its public `DiGraph` and
`is_directed_acyclic_graph` APIs. NetworkX 3.6.1's installed license was checked: BSD-3-Clause.
Upstream: https://github.com/networkx/networkx. No external implementation was copied or
adapted, and no dependencies were added. Progression and adapters are small Cliova-specific
rules; Mesa or an additional graph library would add unnecessary machinery.

Focused tests cover prerequisites, contextual divergence, deterministic replay, serialization,
actual economic effects, activation causality, practical learning over multiple ticks,
local prerequisite checks, changing participation, invalid inputs and numeric bounds.
