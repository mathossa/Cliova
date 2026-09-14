# Command Center UI scaffold

## Goal

The command center is the first visual shell for Cliova: approximately 40% command/context workspace and 60% map/data workspace. The visual language borrows the information density and operational feel of command-center interfaces while remaining neutral and modern rather than strongly themed.

This UI is deliberately a **presentation and input layer**. It must not reproduce simulation rules in TypeScript. Authoritative world state, causes and directive outcomes remain server-side.

## Layout

- **Header:** world identity, year/season, next tick, treasury/resource summary and global status.
- **Module navigation:** exposes the intended product surface early, including modules that are not implemented yet.
- **Left 40%:** terminal/world feed, selected context, command/directive entry or the active module scaffold.
- **Right 60%:** operational map, selected map context, key indicators and detected pressures/issues.
- **Footer:** explicit integration state so mock/presentation data cannot be confused with simulation output.

## Module coverage

| UI module | Primary future backend/source responsibility |
| --- | --- |
| Terminal | API/application command/query surface |
| Directives | Player intent, priorities, proposals, execution |
| World | Geography, environment, resources, routes |
| Society | Population, psychology, values, culture |
| Economy | Production, consumption, markets, trade |
| Knowledge | Knowledge, innovation and diffusion |
| State | Politics, institutions, legitimacy and capacity |
| Belief | Spirituality, belief systems and movements |
| People | Notable individuals, factions and movements |
| Diplomacy | Relations, treaties, claims, conflict and messages |
| Issues | Scenario detection and player-facing pressures |
| History | Chronicle, causal history and explainability |

The navigation labels may later be regrouped without changing the underlying feature ownership. For example, Society could expose Population/Culture subviews while State can expose Government/Capacity subviews.

## Control principles

1. Clickable proposals and semi-free terminal/directive input should coexist.
2. Controls submit intent; they do not calculate whether the intent succeeds.
3. `why`/explainability views render explicit causes returned by the backend.
4. Tick controls display schedule/readiness first. Manual tick execution should only exist in development/admin contexts if the backend exposes it.
5. Map controls manipulate presentation (selection/layers/filter/zoom) and should not directly mutate world state.
6. Disabled placeholder controls are intentional until their contracts exist.

## Data integration stages

1. **Current branch:** presentation-only mock snapshot and interactive shell.
2. Add read-only world summary / feed / entity inspection contracts.
3. Add directives and proposals write contracts.
4. Add explainability/history contracts.
5. Replace the map placeholder with MapLibre when geography contracts and map data exist.
6. Add asynchronous diplomacy/inbox workflows and tick readiness.

## Assets

See `apps/web/public/assets/README.md`. The code already references the final asset paths so replacing the placeholders does not require component changes.
