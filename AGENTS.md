# Cliova agent instructions

These instructions define how AI coding agents should work in this repository. They are intentionally reusable across issues and should be followed before starting implementation work.

## 1. Core working principles

- Work **issue-first and scope-first**. Understand the requested issue before exploring the codebase.
- Be **token- and context-efficient**. Do not read the entire repository unless the task genuinely requires it.
- Prefer the smallest relevant context and the smallest correct change.
- Do not invent missing requirements, domain rules, architecture, data or product behavior.
- If a material requirement is unclear, contradictory or underspecified, **ask the user** rather than hallucinating an answer.
- Keep changes focused on the issue. Do not opportunistically refactor unrelated code.
- Preserve existing working behavior unless the issue explicitly requires changing it.
- Do not automatically merge pull requests.

## 2. Context discipline: do not read the whole repository

The repository should be explored progressively.

### Default workflow

1. Read this `AGENTS.md`.
2. Read the issue/task description and its acceptance criteria.
3. Identify the likely subsystem(s) involved.
4. Inspect only the relevant directory tree, symbols, tests and nearby documentation.
5. Follow imports/references only when needed to understand or implement the change.
6. Expand context only when evidence shows that another subsystem is involved.

### Prefer targeted discovery

Use targeted search for:

- exact class/function/component names;
- route names and API contracts;
- domain/event/change types;
- tests for the affected behavior;
- direct imports and callers;
- documentation explicitly related to the issue.

Avoid by default:

- recursively opening every source file;
- reading every vision document for a narrow issue;
- loading unrelated frontend and backend code together;
- rereading files already understood unless they changed or new evidence requires it;
- broad refactors justified only by “cleaning things up”.

For a narrow change, it is normal to work from only a handful of files.

## 3. Handling uncertainty

Never silently fill important gaps with assumptions.

Ask the user when uncertainty could materially affect:

- gameplay or simulation behavior;
- data ownership or authoritative state;
- public API/contracts;
- persistence/schema choices;
- architecture boundaries;
- UX behavior visible to players;
- issue scope or acceptance criteria;
- compatibility with existing worlds or saved data.

When uncertainty is minor, local and easily reversible, choose the least invasive option consistent with existing patterns and mention the assumption in the implementation/PR notes.

If code, documentation and the issue disagree, do not arbitrarily choose one. Identify the conflict and ask when it changes product behavior or architecture.

## 4. Vision is guidance, not immutable law

`docs/vision/` is the product direction and should strongly guide implementation decisions.

However, the vision is a **living design**, not a frozen specification.

- Do not violate the vision casually or silently.
- Do not force an implementation to match old wording when new evidence suggests a better design.
- Challenge or question the vision when implementation work exposes contradictions, unnecessary complexity, poor gameplay consequences or better alternatives.
- If a proposed change materially changes product direction, discuss it with the user before implementing it as the new truth.
- Once a design change is agreed, update the relevant vision/architecture documentation when appropriate so documentation and implementation do not drift apart.

For narrow issues, read only the specific vision documents that are relevant. Start from `docs/vision/README.md` when you need to determine which document applies; do not automatically load all vision files.

## 5. Product direction

Cliova is a persistent browser-based civilization simulation in which history should emerge from interacting systems rather than follow a predetermined historical path.

Key principles:

- **Simulation first.** The world should be interesting before the final UX is elaborate.
- **No fixed history.** Avoid hard-coded historical outcomes, mandatory ideology ladders and linear technology history when lower-level mechanics can produce outcomes instead.
- **Indirect control.** Players express priorities and directives; societies and institutions determine what can actually happen.
- **Explain everything.** Important simulation changes should retain structured causes.
- **Aggregates by default.** Do not simulate every citizen individually.
- **Systems create stories.** History, crises and narratives should emerge from simulation state.
- **Persistent asynchronous play.** The design target is approximately one real day = one game year, while development may support manual/headless ticks.

## 6. Architecture boundaries

Cliova uses a Next.js/React webclient and a separate Python/FastAPI authoritative backend.

### Authoritative simulation

- The Python simulation core is authoritative.
- The browser may present, filter and structure input, but must not calculate authoritative game outcomes.
- LLM integrations may interpret, summarize or present simulation results, but must not become the source of simulation truth.
- The simulation must remain runnable headlessly without the browser or Node.js.

### Backend

- Keep the backend a **modular monolith** until there is concrete evidence that distribution is required.
- Simulation domains live under `backend/src/cliova/simulation/domains/`.
- `backend/src/cliova/simulation/engine.py` owns tick orchestration.
- Domains communicate through explicit state inputs, changes/events and causes.
- Avoid hidden cross-domain mutation.
- Infrastructure code such as persistence, scheduling and external services must not leak into domain rules.
- API routes may call application/domain services but must not reimplement simulation rules.

### Frontend

- Organize frontend code around player-facing features rather than mirroring Python folders mechanically.
- Keep API access behind a small typed client/boundary.
- Do not duplicate simulation formulas in React/TypeScript.
- Presentation-only map/visual state must not accidentally become authoritative world state.

### Contracts

- New or changed backend ↔ frontend payloads belong in explicit boundary models/contracts.
- Shared cross-language contracts belong under `packages/contracts/` where practical.
- Do not expose internal mutable domain/database objects directly as public API contracts.

## 7. Determinism and simulation safety

For the same initial state, seed and ordered player/world inputs, authoritative simulation results should be reproducible.

Therefore:

- inject/use deterministic seeded randomness rather than hidden global RNG;
- make tick ordering explicit;
- keep stable identifiers stable across serialization/replay;
- do not depend on wall-clock time inside domain rules;
- avoid unordered behavior whose outcome can change across runs;
- preserve causal information for significant state changes;
- prefer atomic tick application over partial mutation.

If a proposed feature would knowingly break determinism, raise it explicitly before implementation.

## 8. Issue implementation workflow

Before coding:

- read the complete issue and acceptance criteria;
- check listed dependencies and directly related issues when they affect the implementation;
- inspect existing behavior/tests before replacing it;
- identify whether the issue changes simulation truth, API contracts, persistence or only presentation.

During coding:

- keep the diff as small as reasonably possible;
- follow existing patterns unless they are the reason for the issue;
- avoid solving future issues prematurely;
- avoid adding abstractions with no current use;
- add comments only where intent is not clear from code;
- keep configuration/constants centralized when behavior will need tuning.

If you discover a separate bug or improvement:

- do not silently expand the current issue;
- record it clearly as a follow-up suggestion/issue unless it blocks the requested work;
- if it blocks the issue, explain why before broadening scope when user input is needed.

## 9. Testing expectations

Testing should match the risk and scope of the change.

### Simulation/domain changes

Normally include:

- deterministic unit tests;
- edge/failure cases relevant to the mechanic;
- at least one multi-tick or behavior-level test when the mechanic evolves over time;
- regression seeds/fixtures for bugs involving emergent behavior when practical.

### API/persistence changes

Test:

- validation and failure behavior;
- serialization/contracts;
- persistence/reload where relevant;
- transaction/idempotency behavior when tick state is involved.

### Frontend changes

Test the changed behavior at the appropriate level and at minimum ensure the web build/type checks remain green.

Do not add huge brittle snapshots merely to increase test count. Prefer invariants, behavior and causal structure.

Before declaring an issue complete, run the narrowest relevant tests first, then the broader project checks appropriate to the files changed.

## 10. Documentation changes

Update documentation when the implementation materially changes:

- architecture boundaries;
- public contracts;
- simulation semantics;
- developer setup;
- agreed product/vision direction.

Do not rewrite documentation that is unrelated to the issue.

When code reveals that a vision document should change, treat that as a design discussion rather than silently rewriting the product direction.

## 11. Git and pull-request behavior

- Use a focused branch/PR for the issue when working through Git.
- Keep commits and PR descriptions scoped to the requested work.
- Include what changed, why, relevant tests and any assumptions/follow-ups.
- Do not claim tests passed unless they were actually run.
- Do not hide known failures.
- Do not merge automatically; leave final merge decisions to the user unless explicitly instructed otherwise.

## 12. Definition of a good AI contribution

A good contribution:

- solves the requested issue rather than a larger imagined problem;
- reads only enough repository context to make a correct decision;
- asks rather than invents when product intent is genuinely unclear;
- keeps authoritative simulation logic in the correct layer;
- remains deterministic and explainable where simulation behavior is involved;
- includes proportionate tests;
- documents meaningful design changes;
- leaves unrelated code alone;
- clearly surfaces assumptions, trade-offs and follow-up work.
