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
- For any substantial simulation mechanic or generic subsystem, **copy/adapt/reuse first and write from scratch only as a justified fallback**. Follow the mandatory OSS gate in section 5 before committing to a new implementation.
- Do not automatically create follow-up GitHub issues. **Propose them to the user first.**
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
- compatibility with existing worlds or saved data;
- licensing or provenance of third-party code when compatibility is not clear.

When uncertainty is minor, local and easily reversible, choose the least invasive option consistent with existing patterns and mention the assumption in the implementation/PR notes.

If code, documentation and the issue disagree, do not arbitrarily choose one. Identify the conflict and ask when it changes product behavior or architecture.

Never weaken or reinterpret acceptance criteria merely to make an implementation easier. If the issue itself appears wrong, incomplete or unnecessarily restrictive, raise that explicitly.

## 4. Vision is guidance, not immutable law

`docs/vision/` is the product direction and should strongly guide implementation decisions.

However, the vision is a **living design**, not a frozen specification.

- Do not violate the vision casually or silently.
- Do not force an implementation to match old wording when new evidence suggests a better design.
- Challenge or question the vision when implementation work exposes contradictions, unnecessary complexity, poor gameplay consequences or better alternatives.
- If a proposed change materially changes product direction, discuss it with the user before implementing it as the new truth.
- Once a design change is agreed, update the relevant vision/architecture documentation when appropriate so documentation and implementation do not drift apart.
- Small clarifications may be updated directly when they do not change the agreed product direction.

For narrow issues, read only the specific vision documents that are relevant. Start from `docs/vision/README.md` when you need to determine which document applies; do not automatically load all vision files.

## 5. Copy/adapt first: mandatory open-source gate

Cliova should not spend AI-generated code on a substantial mechanic that already has a suitable open-source implementation.

This gate applies to **both generic infrastructure and simulation/game-domain mechanics**. A mechanic is not exempt merely because its final behavior is Cliova-specific. Population, economy, production, storage, trade, knowledge/innovation, governance, diplomacy, warfare, migration, crises, world generation and similar domains must still be checked for reusable foundations before new substantial implementations are written.

Tiny helpers, straightforward adapters, presentation glue and genuinely small issue-local changes do not need an external survey.

### Mandatory reuse workflow

Before implementing substantial new behavior:

1. **Check Cliova first.** Determine whether the capability already exists in the repository or current dependencies.
2. **Search targeted OSS sources before designing from scratch.** Search maintained libraries **and** real games/simulators/reference projects that implement comparable behavior. Prefer targeted searches over broad surveys.
3. **Inspect actual implementation code.** A README or feature list is not enough when deciding whether code can be reused. Inspect the relevant files, data model and tests for promising candidates.
4. **Verify provenance and license before copying/adapting.** Confirm the repository/file license and obligations. Publicly visible code without a clear compatible license is not reusable source.
5. **Compare candidates explicitly.** For each serious candidate, consider functional fit, language/runtime fit, granularity, determinism, quality/tests, maintenance, dependency weight, security/reputation, license, and adaptation cost.
6. **Choose reuse before invention where practical.** Prefer an existing proven implementation when it can supply a meaningful part of the required behavior without violating Cliova's product or architecture constraints.
7. **Document the decision.** PR notes for substantial mechanics must name the OSS candidates checked, their licenses, and whether Cliova used, adapted or rejected them. Rejections need a concrete reason.

### Decision order

Prefer, where practical:

1. **Adapt/copy a compatible, well-understood implementation** when its mechanics substantially match the requested behavior and the license permits it.
2. **Use an established dependency through a thin Cliova adapter** when the dependency already owns the generic algorithm or simulation machinery.
3. **Combine reused foundations with Cliova-specific rules** when upstream code solves only part of the problem.
4. **Write a fresh Cliova implementation only when the checked alternatives are unsuitable.**

A from-scratch implementation is **not** the default just because adapting foreign code takes work or uses a different language. Translating a well-understood algorithm/model can be preferable to inventing a new one, provided attribution and license obligations are preserved.

If a plausible compatible implementation exists but the agent wants to reject it in favor of a substantial fresh design, **raise that trade-off to the user before coding**.

### Existing Cliova code is not automatically grandfathered

When materially extending a custom subsystem that has never had a proper OSS comparison, perform the reuse check then. Do not treat an earlier AI-generated implementation as permanently authoritative merely because later issues depend on it. Preserve public contracts where useful, but replacing or adapting internals is allowed when a better OSS foundation is identified and the user agrees to the migration.

### What must remain Cliova-specific

Reuse does not mean cloning another game's product design. Cliova still owns:

- player role and indirect-control model;
- emergent-history goals;
- authoritative domain boundaries and public contracts unless intentionally changed;
- tuning, pacing and balance;
- which mechanics are exposed to players;
- how reused mechanics are combined into Cliova's simulation.

Copy mechanisms before inventing them; do not copy product identity blindly.

### Licensing and provenance

Cliova is licensed under **GPLv3**. External code must have a license that can legally and practically be used with this project and must comply with its attribution/source obligations.

- Never assume that code is reusable merely because it is publicly visible on GitHub.
- **Do not copy or adapt code with no explicit license.**
- Verify the actual repository/file license before copying non-trivial code.
- Preserve required copyright, attribution and license notices.
- Do not remove upstream attribution.
- Prefer well-understood compatible licenses and established dependencies.
- If license compatibility or obligations are unclear, stop and ask the user before integrating or copying the code.
- Do not introduce an external project whose license would unexpectedly change Cliova's distribution obligations without explicit user approval.

Reuse is a strong default, **not** permission to add a huge or unsuitable dependency. Rejecting a candidate is valid when the mismatch is real and documented.

## 6. Product direction

Cliova is a persistent browser-based civilization simulation in which history should emerge from interacting systems rather than follow a predetermined historical path.

Key principles:

- **Simulation first.** The world should be interesting before the final UX is elaborate.
- **No fixed history.** Avoid hard-coded historical outcomes, mandatory ideology ladders and linear technology history when lower-level mechanics can produce outcomes instead.
- **Indirect control.** Players express priorities and directives; societies and institutions determine what can actually happen.
- **Explain everything.** Important simulation changes should retain structured causes.
- **Aggregates by default.** Do not simulate every citizen individually.
- **Systems create stories.** History, crises and narratives should emerge from simulation state.
- **Persistent asynchronous play.** The design target is approximately one real day = one game year, while development may support manual/headless ticks.

## 7. Architecture boundaries

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

## 8. Determinism and simulation safety

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

## 9. Issue implementation workflow

Before coding:

- read the complete issue and acceptance criteria;
- check listed dependencies and directly related issues when they affect the implementation;
- inspect existing behavior/tests before replacing it;
- identify whether the issue changes simulation truth, API contracts, persistence or only presentation;
- for any substantial simulation mechanic or generic functionality, complete the mandatory OSS gate from section 5 **before committing to a from-scratch design**;
- if the affected custom subsystem has never had a documented reuse comparison, do that comparison before materially extending it.

During coding:

- keep the diff as small as reasonably possible;
- follow existing patterns unless they are the reason for the issue;
- avoid solving future issues prematurely;
- avoid adding abstractions with no current use;
- add comments only where intent is not clear from code;
- keep configuration/constants centralized when behavior will need tuning;
- preserve upstream attribution in any copied/adapted implementation.

If you discover a separate bug or improvement:

- do not silently expand the current issue;
- **propose a follow-up issue to the user; do not create it automatically**;
- if it blocks the issue, explain why before broadening scope when user input is needed.

## 10. Testing expectations

AI agents should run **lightweight, focused automated tests themselves**. The user performs the heavier validation, including broad suites where appropriate and visual/manual testing.

### What the agent should normally run

- the narrow unit tests for directly changed code;
- small regression tests added for the issue;
- focused type/lint checks when they are quick and directly relevant;
- a lightweight build/check only when it is reasonably fast and useful for the affected area.

### What not to run by default

Do not consume substantial time/resources running every expensive project-wide suite after every issue unless specifically requested or necessary to validate a high-risk change.

The user is responsible for, or may explicitly request:

- heavy full-suite/integration runs;
- long-running simulation/stress tests;
- exhaustive cross-environment testing;
- browser/manual/visual validation.

### Test design

For simulation/domain changes, add deterministic unit coverage and relevant edge/failure cases. Add a multi-tick behavior test when the mechanic genuinely evolves over time, but keep it focused rather than turning every issue into a long-run simulation suite.

For API/persistence changes, test validation, serialization/contracts and the narrow persistence/idempotency behavior touched by the issue.

For frontend changes, add focused automated coverage when useful; leave visual acceptance to the user unless explicitly requested otherwise.

Do not add huge brittle snapshots merely to increase test count. Prefer invariants, behavior and causal structure.

Never claim a test passed unless it was actually run. Clearly state which tests were run and which heavier/manual checks remain for the user.

## 11. Documentation changes

Update documentation when the implementation materially changes:

- architecture boundaries;
- public contracts;
- simulation semantics;
- developer setup;
- agreed product/vision direction.

Prefer extending an existing relevant vision/architecture document over creating a new one when it can hold the concept cleanly. Principle/design documents that explain one concept should remain concise and fit within roughly two printed pages; move deeper implementation detail to focused architecture/reference docs instead of growing the principle document indefinitely.

Do not rewrite documentation that is unrelated to the issue.

When code reveals that a vision document should change, treat material product changes as a design discussion rather than silently rewriting the product direction.

## 12. Git, language and pull-request behavior

Use **English** for code, identifiers, comments, commit messages, issue text, pull-request text and project documentation unless the user explicitly requests otherwise.

### Branch naming

For issue work, use:

`issue/<number>-<short-kebab-description>`

Examples:

- `issue/3-world-state-seeded-rng`
- `issue/7-resource-production-shortages`

Keep names concise and tied to the GitHub issue.

### Git/PR rules

- Use a focused branch/PR for the issue when working through Git.
- Keep commits and PR descriptions scoped to the requested work.
- Include what changed, why, lightweight tests actually run, heavier/manual tests still recommended, assumptions and proposed follow-ups.
- For substantial mechanics, include an **OSS reuse decision**: candidates inspected, license, selected source or concrete reasons for rejecting each serious candidate.
- When third-party code or an external implementation influenced the solution, include the upstream project/source and license in the PR notes and preserve required source-level attribution.
- Do not claim tests passed unless they were actually run.
- Do not hide known failures.
- Do not create unrelated follow-up issues automatically; propose them to the user.
- Do not merge automatically; leave final merge decisions to the user unless explicitly instructed otherwise.

## 13. Definition of a good AI contribution

A good contribution:

- solves the requested issue rather than a larger imagined problem;
- reads only enough repository context to make a correct decision;
- asks rather than invents when product intent is genuinely unclear;
- performs the copy/adapt-first OSS gate for substantial simulation mechanics and generic functionality;
- inspects promising upstream implementation code rather than stopping at README-level inspiration;
- verifies licensing/provenance before reusing external code;
- writes substantial new mechanics from scratch only when checked alternatives are unsuitable and the decision is documented;
- keeps authoritative simulation logic in the correct layer;
- remains deterministic and explainable where simulation behavior is involved;
- includes proportionate lightweight automated tests;
- clearly leaves heavy/visual validation to the user unless requested;
- documents meaningful design changes;
- leaves unrelated code alone;
- proposes rather than automatically creates unrelated follow-up issues;
- clearly surfaces assumptions, trade-offs and follow-up work.
