# Simulation primitives (schema 1)

The authoritative core uses immutable Pydantic models in
`backend/src/cliova/simulation/types.py`. These are internal simulation/snapshot
models, not production API contracts.

## Creating and restoring worlds

```python
from cliova.simulation.types import WorldState, entity_id

world = WorldState.create(seed=42)
region_id = entity_id(world.id, "region", "initial:0")
snapshot = world.model_dump_json()
restored = WorldState.model_validate_json(snapshot)
assert restored == world
```

A seed is mandatory. A seed plus an optional stable `world_key` determines the
world UUID. Use different world keys for distinct instances with the same seed.
Entity IDs combine an explicit kind (world, region, society, polity or individual)
with a UUID. Entity keys must be stable creation keys, never mutable display names.
UUIDv5 uses the world UUID as a namespace and does not consume simulation randomness.
IDs and causal event references survive JSON round trips.

The aggregate intentionally contains only identity, seed, metadata and time.
There are no generated regions, society rules, individual citizens or speculative
domain fields. Future domain state must use immutable typed values and tuples;
Pydantic freezing alone does not make a nested dictionary immutable. The unused
mutable scaffold `metrics` dictionary has been removed.

The explicit metadata header contains `schema_version`, `simulation_version`
and `rng_algorithm`. Missing or unsupported headers are rejected rather than
silently interpreted as current data. Schema changes require a versioned migration;
rule or stream changes require a simulation/RNG version decision. There is no
database persistence or migration runner in this issue.

## Simulation time and ownership

`SimulationTime.year` is a calendar year (negative years are allowed).
`tick` is the non-negative count of completed steps, independent of the year.
New worlds start at year/tick zero. The yearly engine advances each by one.
An optional phase string is reserved for sub-year work; the yearly engine rejects
non-null phases instead of guessing how to advance them.

Domains receive the immutable pre-tick world, next year and an explicit
`RandomSource`. They return ordered `SimulationChange` proposals. The engine
returns a new world only after all domains succeed; the caller's world is unchanged
on success or failure. It retains the scaffold's behavior of returning proposals
without applying domain metrics. Domain-specific change application belongs to later
mechanics, not a generic arbitrary-path mutation system.

`SimulationChange` keeps source, key, delta and human-readable reason, with an
optional target and causal event IDs. `SimulationEvent` adds stable event identity,
time, kind, subjects and an ordered tuple of changes. Event producers derive their
UUIDs from stable world/tick/source/sequence keys, not wall-clock time or global RNG.
These envelopes establish communication primitives; no event dispatcher or
history persistence is introduced.

## Deterministic randomness

`randomness.py` adapts the existing NumPy PCG64 dependency behind the small
`RandomSource.random()` protocol. SHA-256 of the version label, seed, target tick
and domain name initializes a separate stream. JSON array encoding makes stream
keys unambiguous and supports negative integer world seeds.

A fixed conversion from PCG64's raw 64-bit integer to a 53-bit fraction produces
values in [0, 1). We use the raw integer stream's compatibility guarantee rather
than relying on distribution implementations or an implicit default generator.
Domains must reuse their injected stream during a step and must not read global
Python/NumPy randomness. Domain names are non-empty and unique.

Streams restart deterministically at tick boundaries. An unrelated domain's draws
do not perturb another domain, and snapshot restoration needs no hidden generator
state at those boundaries. Mid-tick snapshots are not supported. Initialization
currently consumes no random draws; future generation can use a named tick-zero
stream. Replay requires the same ordered inputs, rules and versioned stream
convention. No cross-version replay guarantee is claimed for future rule changes.

## Reuse and validation

No dependencies were added and no upstream source code was copied.
Pydantic handles validation/JSON through its public API
([MIT license](https://github.com/pydantic/pydantic/blob/main/LICENSE)).
NumPy supplies PCG64
([BSD-3-Clause license](https://github.com/numpy/numpy/blob/main/LICENSE.txt);
[raw-stream guarantee](https://numpy.org/doc/stable/reference/random/bit_generators/pcg64.html)).
Both were already backend dependencies. Dependency distributions retain their
upstream notices; redistribution must preserve them.

Focused checks, from `backend/`:

```bash
python -m pytest tests/test_world_state.py tests/test_randomness.py tests/test_engine.py
python -m ruff check src/cliova/simulation src/cliova/cli.py tests/test_world_state.py tests/test_randomness.py tests/test_engine.py
python -m mypy src/cliova/simulation src/cliova/cli.py
```

Coverage includes seed reproducibility, serialization and metadata rejection,
identity kinds, immutability, RNG isolation/injection, ordered domain execution,
failed-tick retry and a three-tick snapshot/resume comparison.
