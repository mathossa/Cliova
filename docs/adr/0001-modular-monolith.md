# ADR 0001: Modular monolith with separate web and simulation runtimes

**Status:** Accepted

## Context

Cliova requires a browser UX but its core value is a deterministic, potentially compute-heavy civilization simulation. Putting authoritative simulation rules inside Next.js would couple gameplay to presentation and make headless long-run tests harder. Splitting every simulation domain into microservices would add distributed-state complexity before scaling needs are known.

## Decision

Use one repository with:

- a Next.js/TypeScript web application;
- one Python backend containing FastAPI, CLI tooling and a modular simulation core;
- explicit domain boundaries inside the Python package;
- stable cross-runtime contracts between browser and backend.

## Consequences

The simulation can run without the webclient and can be tested over hundreds or thousands of years. Cross-domain behavior remains easy to profile and debug. A future worker/service split remains possible, but requires a separate ADR backed by an actual operational need.
