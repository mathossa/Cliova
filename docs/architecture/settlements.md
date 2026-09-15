# Authoritative settlements and structures

Issue #60 adds only simulation truth needed to remember **where a meaningful settlement or camp exists and which strategically relevant constructed structures exist there**. It does not turn Cliova into a per-building city builder.

## Authoritative state

`SettlementDomainState` contains stable settlement/camp identities and strategic structure instances. Settlement IDs and structure IDs are deterministic `EntityId` values derived from the world ID plus a stable key. A settlement records its region, optional society/polity association, establishment year, aggregate population estimate, permanence/archetype, lifecycle status, and causal references. There is deliberately no mandatory `camp -> village -> town -> city` ladder.

A strategic structure instance references a small reusable definition key plus its settlement, establishment year, lifecycle status, and causal references. The starter catalog proves the definition/instance boundary with generic entries such as storage, workshop, trading place, ritual structure, water infrastructure, livestock enclosure, fortification, harbour/transport infrastructure, and administrative structures.

The settlement domain owns only existence and lifecycle. Definition metadata exposes **integration seams**, not bonuses. Economy/storage owns reserve accounting; logistics owns travel effects; warfare owns defensive effects; trade/economy owns market calculations; governance owns governance effects; knowledge owns capability availability.

## Camps and population

Seasonal/temporary camps consume issue #50's `SocietyRegionRelationshipState.temporary_access`. The settlement domain does not choose resource access, move population, alter the core region, or create territorial ownership/control. A dormant camp becomes active when #50 reports temporary presence in its region and can become dormant again when that presence ends. The persistent camp identity may therefore survive between seasons.

`population_estimate` is settlement-scale association only. The population domain remains authoritative for aggregate regional population; no people, households, or residence records are created. Worlds may have zero settlements, which remains important for highly mobile societies.

## Simulation truth vs visual fabric

Ordinary houses, tents, gardens, fences, sheds, yards, minor paths, trees, and similar visual fabric are **not** authoritative structure instances. A future local renderer may generate hundreds of those objects without adding simulation entities. Only gameplay-relevant constructed objects that other domains may consume belong in the authoritative structure list.

Issue #61 may consume stable inputs such as settlement ID, population/scale, archetype/permanence, region context, and the strategic structure list. It owns local coordinates, parcels, roads, house placement, SVG/GeoJSON, and other procedural layout/presentation concerns. Issue #62 owns later settlement-growth/history rendering.

## Lifecycle, history, and compatibility

The initial lifecycle is intentionally small: settlements are `active`, `dormant`, `abandoned`, or `destroyed`; structures are `active`, `damaged`, or `destroyed`. Explicit establishment and lifecycle changes use the existing `SimulationInput` / domain-owned `SimulationChange` protocol. There are no construction-time, resource-cost, workforce, upgrade, or era-tree mechanics in #60.

Meaningful establishment/completion/lifecycle changes become normal causal history events. Automatic camp return/dormancy events retain the relevant #50 access event as a cause. The settlement state defaults to empty, so snapshots created before #60 load without synthesizing settlements or historical events. Existing persistence stores the added state inside the authoritative world snapshot.

## Copy-first provenance review

The implementation inspected source code before choosing the model:

- **Unknown Horizons**, `unknown-horizons/unknown-horizons` at `af9c8ef5c7f6cf9ec0b8c9e7d172c555f2793615`: **licensed-reusable, patterns only**. `horizons/world/settlement.py` and `horizons/world/building/building.py` carry GPL-2.0-or-later headers. Useful patterns are persistent settlement identity and settlement-associated building instances. Direct source reuse was rejected because those classes are tightly coupled to tile coordinates, scheduler/storage/production behavior, and mutable engine state that #60 explicitly does not own.
- **FreeCol**, `FreeCol/freecol` at `ce471f6701615614b6b479734f2902e148e323e2`: **licensed-reusable, patterns only**. `Building.java` and `BuildingType.java` carry GPL-2.0-or-later headers. The useful pattern is a reusable building/type definition separated from a concrete settlement-associated building instance. Direct code reuse was rejected because the Java/XML, colony labour/production, upgrade, and era-specific mechanics do not fit Cliova's aggregate authoritative boundary.
- **Prosperity Wars**, `Nashet/Prosperity-Wars` at `6c521ec463785ec7e7d49f7e6a150a41c2c10fb8`: **rejected for functional fit**, not licensing. The repository license is GPLv3. `FactoryProject.cs` binds construction directly to factories, provinces, markets, countries, and investment costs. Reusing that model would blur #60 into the economy domain.

No source code was copied or translated from these projects. The implementation adapts only the compatible architectural patterns above. The same #58 reference-only rule applies to any future unlicensed or incompatible candidate.
