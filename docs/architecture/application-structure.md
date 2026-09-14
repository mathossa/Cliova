# Application Structure

## Keuze

Cliova gebruikt een monorepo met een **Next.js webclient** en een afzonderlijke **Python/FastAPI backend**. Anders dan Weaveryn wordt Cliova niet primair als één Next.js full-stack applicatie opgebouwd: de authoritative simulation core is het producthart en moet zelfstandig via CLI/tests kunnen draaien zonder browser of Node.js.

## Structuur

```text
Cliova/
├── apps/
│   └── web/                    # Next.js / React UX
├── backend/
│   ├── src/cliova/
│   │   ├── api/                # HTTP boundary
│   │   ├── simulation/
│   │   │   ├── engine.py       # tick orchestration
│   │   │   ├── types.py        # shared simulation primitives
│   │   │   └── domains/        # world, economy, politics, ...
│   │   └── infrastructure/     # persistence, GIS, scheduling
│   └── tests/
├── packages/
│   └── contracts/              # backend ↔ browser contracts
├── database/                   # migrations / seed fixtures
├── docs/
│   ├── vision/
│   ├── architecture/
│   └── adr/
└── infra/
```

## Waarom anders dan Weaveryn?

Weaveryn kan veel logica logisch binnen één Next.js-codebase houden omdat het vooral webapplicatie- en CRUD/workspacegedrag betreft. Cliova moet honderden jaren headless kunnen simuleren, reproduceerbare seeds kunnen testen en mogelijk zware numerieke/graph-berekeningen uitvoeren. Python krijgt daarom een zelfstandige runtime en Node/React blijft presentatie en spelerinteractie.

## Backend: modulaire monoliet

We starten bewust niet met microservices. Eén Python-proces/package maakt transacties, determinisme, profiling en cross-domain tests eenvoudiger. Domeinen worden wel scherp gescheiden zodat een toekomstige worker of service mogelijk blijft zonder nu distributiecomplexiteit te introduceren.

## Frontend: feature-oriented

De browser wordt georganiseerd rond spelerstaken zoals `terminal`, `world`, `directives`, `history`, `government`, `economy` en later `map`. De UI spiegelt dus niet één-op-één de Python-folderstructuur. De browser mag gegevens presenteren, filteren en invoer structureren, maar berekent geen authoritative speluitkomsten.

## Eerste ontwikkelfase

De eerste UX is het Simulation Lab: terminal/status/debug-functionaliteit bovenop de backend. De kaart en rijke game-UX komen pas nadat de simulation core betekenisvolle, uitlegbare historie kan produceren.
