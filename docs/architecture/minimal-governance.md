# Minimal governance (#8)

`WorldState.governance` contains one `GovernanceState` per explicitly initialized
playable society/polity. Each has a stable `subject_id` independent of its current
`region_id`. Presence is not territorial ownership. #8 supports one current region
per society; multiple societies there observe the same aggregate regional facts.
Movement, multi-region aggregation and distinct within-region populations are deferred.

`initialize_governance(world, states=...)` requires callers to supply every state's
institution, legitimacy, execution capacity and internal resistance. There are no
production political presets or starting-value defaults. Construct society IDs with
`entity_id(world.id, "society", stable_key)`; do not derive identity from location.
Existing snapshots without governance load with an empty tuple. World creation does
not automatically create playable societies. Initialization requires population and
food economy records for each associated region, and rejects duplicate subjects.

Register `GovernanceDomain()` alongside population/economy domains in the existing
`SimulationEngine`. Its `GOVERNANCE` phase observes finalized same-tick population
and economy state. `governance_pressure` creates an explicit immutable observation:

- `population.region(region_id).needs.social_confidence`;
- `population.region(region_id).migration_pressure`;
- `economy.region(region_id).resource("food").shortage_severity`.

Population food security is not read again. The existing economy-to-population
next-tick pressure boundary remains unchanged and can be queued by the caller as
before. Missing observations are errors, not silently assumed healthy conditions.

For institution parameters coordination `c`, resilience `r`, adaptation `a`:

```
stress = max(1 - confidence, migration_pressure, food_shortage) * (1 - r)
next_resistance = approach(resistance, stress)
next_legitimacy = approach(legitimacy, 1 - max(stress, next_resistance))
next_capacity = approach(capacity, c * next_legitimacy * (1 - next_resistance))
approach(current, target) = round(current + (target - current) * a, 6)
```

All values are finite and bounded to [0, 1]. There is no RNG, profile-name branching
or historical ladder. Max avoids adding overlapping manifestations of scarcity.
With stress removed, values approach resistance 0, legitimacy 1 and capacity `c`.
Adaptation 0 freezes values; adaptation 1 reaches each calculated target immediately.
These endpoints are intentionally permitted. Structural parameters are explicit
configuration; the profile key is descriptive identity only.

`execution_strength(state)` returns
`min(capacity, legitimacy, 1 - resistance)`. #9 can use this normalized political
bottleneck; #8 does not decide directive outcomes, costs, progress or effects.

Changes are governance-owned numeric deltas targeting the society/polity, with keys
`governance.legitimacy`, `governance.execution_capacity`, and
`governance.internal_resistance`. Reducers reject foreign ownership, unknown targets,
unknown keys and out-of-range results. Population/economy/geography remain untouched.

One `governance-condition-changed` event is emitted per subject when any rounded
per-tick delta is at least `SIGNIFICANT_GOVERNANCE_CHANGE` (0.05). Smaller movements
remain in tick changes; this threshold does not accumulate movements over ticks.
The event contains all of that subject's proposed changes and measured pressures
and profile parameters in its reason. Subjects include society and current region.
Causes are prior same-tick events containing changes to the three consumed regional
fields, including recovery changes. Unrelated fields/regions are excluded. Persistent
pressure without a new event is explained by the measured snapshot values; no past
event IDs are invented. `EventHistory.why()` traverses the existing causal protocol.

No third-party implementation was copied or adapted and no dependency was added.
The existing immutable Pydantic models, engine protocol and history implementation
are reused; these bounded Cliova-specific rules do not need a generic framework.
