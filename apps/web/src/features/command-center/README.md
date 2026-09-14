# Command Center shell

The Simulation Lab defaults to the centralized presentation snapshot in
`command-center.data.ts`. The map artwork and marker positions are illustrative.

`CommandCenterLoader` accepts a `WorldClient`. Its `load()` resolves to a
`WorldSnapshot`, or null when there is no world; rejection shows an unavailable
state with retry. Pending requests show loading. Results from an unmounted
request are ignored. Failed requests never fall back to preview data.

`WorldSnapshot` is a frontend display model, not a public API contract.
When API integration is implemented, adapt shared contracts inside the client
boundary. Components receive data through props; no simulation rules run here.
No backend endpoint or shared contract is introduced by this issue.

World status, history, region inspection and the command workspace are separate
components. Only Northreach has preview region details: selecting other markers
must show missing details rather than relabeling Northreach's statistics.
Unimplemented controls are disabled; commands only produce preview responses.

## Focused validation

Run `npm run lint:web`, `npm run typecheck:web` and `npm run build:web`.

Manual checks:
- Inspect at 1440, 1280, 1024, 768 and 390 pixel widths; document must not scroll
  horizontally (the module/status strips can scroll within their containers).
- Select Northreach, then Kesh: Northreach statistics must disappear.
- Open History and Directives, then return to Terminal.
- Submit help/status and check that no world values change.
- Inject a client resolving null, rejecting, or remaining pending into
  CommandCenterLoader to inspect empty, unavailable and loading states.
- With a client rejecting once then resolving a snapshot, retry must recover.
- Inject a snapshot with empty feed/markers/metrics/pressures and null region;
  panels should explain missing data without throwing.
