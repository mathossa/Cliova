# Cliova

Cliova is een browser-based persistent civilization simulation waarin geschiedenis niet vooraf vastligt. Samenlevingen ontwikkelen economie, politiek, kennis, spiritualiteit, cultuur en conflicten vanuit onderliggende systemen en omstandigheden.

De eerste ontwikkelfase is **simulation first**: een reproduceerbare, uitlegbare wereldsimulatie met een eenvoudige webterminal. De uiteindelijke kaart- en game-UX wordt bovenop dezelfde authoritative simulation core gebouwd.

## Repository-opbouw

- `apps/web/` — Next.js/React browserclient en vroege simulation-lab UX.
- `backend/` — FastAPI, CLI en authoritative Python simulation core.
- `packages/contracts/` — gedeelde API- en eventcontracten tussen backend en frontend.
- `database/` — databaseconventies, migrations en seeds zodra persistence wordt toegevoegd.
- `docs/vision/` — product- en simulatievisie.
- `docs/architecture/` — technische architectuur en dependency-regels.
- `docs/adr/` — Architecture Decision Records.
- `infra/` — lokale en productie-infrastructuur zodra die nodig is.

## Architectuurprincipe

Cliova start als een **modulaire monoliet**, niet als microservices. De webclient en Python-backend zijn afzonderlijke runtimes, maar de simulatie zelf blijft één deterministische core. Simulation domains communiceren via expliciete changes/events en mogen niet ongecontroleerd elkaars interne state muteren.

Zie `docs/architecture/application-structure.md` en `docs/vision/README.md`.
