# Command Center live integration

The Simulation Lab consumes the stable FastAPI `/api/v1` boundary from issue #15. Browser code imports the shared TypeScript DTOs from `packages/contracts/v1.ts`, then maps them into small presentation-only view models in `command-center.view.ts`. React does not import Python domain models or reproduce authoritative simulation rules.

`HttpCliovaApiClient` is the centralized HTTP boundary. In development the browser calls same-origin `/api/v1/...`; Next.js rewrites those requests to `CLIOVA_API_URL` (falling back to `NEXT_PUBLIC_API_BASE_URL` and then `http://localhost:8000`). Failed live requests remain visible as errors and never fall back to demo simulation data.

`CommandCenterLoader` lists development worlds, loads one world plus regions, recent history and directives, and supports seeded development-world creation when none exist. Refresh is explicit. Directive submission and the development-only manual tick both revalidate the relevant world/history/directive data afterwards; no realtime polling or WebSocket layer is used.

The strategic map and region artwork are presentation-only. API v1 does not expose map coordinates, so the browser deliberately does not infer simulation positions. Modules without an authoritative v1 projection are marked as not modeled rather than populated with placeholders.

## Focused validation

Run:

- `npm run test:web`
- `npm run lint:web`
- `npm run typecheck:web`
- `npm run typecheck:contracts`
- `npm run build:web`

`npm run check:web` runs the full web sequence above.

Manual checks should cover world switching/creation, API-down recovery, a directive queue → later lifecycle transition, manual-tick conflict feedback, empty history/directives, and responsive layout at desktop/mobile widths.
