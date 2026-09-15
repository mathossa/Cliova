# Simulation Architecture

## Doel

De technische architectuur moet de simulatie modulair houden. Geen enkele library of engine bepaalt hoe Cliova werkt; de unieke spelregels blijven eigen code. Externe open-source libraries leveren alleen algemene bouwstenen zoals agents, netwerken, optimalisatie en kaartberekeningen.

## Simulation Core

De authoritative simulation core draait server-side in Python. Iedere module leest relevante wereldstatus, berekent veranderingen en publiceert zowel resultaten als oorzaken. Een jaarlijkse tick kan bijvoorbeeld deze volgorde volgen:

1. klimaat en omgeving;
2. resources en oogst;
3. bevolking, psychologie en cultuur;
4. productie, consumptie en handel;
5. kennis en innovatie;
6. spiritualiteit en bewegingen;
7. politiek en instituties;
8. diplomatie en conflict;
9. scenario-detectie;
10. historie en explainability;
11. nieuwe wereldstatus opslaan.

De precieze volgorde mag later veranderen; afhankelijkheden moeten expliciet zijn en met tests worden bewaakt.

## Schaal en ruimtelijke representatie

De simulatie moet uiteindelijk een wereldschaal ondersteunen met veel regio’s en samenlevingen, terwijl vroege testwerelden bewust klein mogen blijven. Regio’s beschrijven de fysieke wereld; samenlevingen, bevolkingsgroepen en politieke structuren zijn aparte entiteiten die over één of meerdere regio’s verspreid kunnen zijn. Een regio kan tegelijk door meerdere groepen worden bewoond of gebruikt.

Schaalbaarheid komt vooral uit aggregatie: niet iedere inwoner, akker of kaartcel krijgt een zelfstandige agent. Fijnere geografische data kan onder regio’s bestaan voor generatie en kaartberekeningen, terwijl dure sociale en economische simulatie op geaggregeerde groepen, regio’s en netwerken draait. Zo blijft wereldschaal mogelijk zonder de simulatie tot een klein bordspel te reduceren.

## Herbruikbare software

**Mesa** kan gebruikt worden voor betekenisvolle agents zoals staten, clans, facties, instituties en notable individuals. Miljoenen inwoners worden niet als agents gemodelleerd.

**NumPy** ondersteunt bulkberekeningen voor geaggregeerde bevolking, economie en andere numerieke staten.

**NetworkX** kan relaties, handelsnetwerken, kennisspreiding, politieke invloed en routeproblemen modelleren.

**OR-Tools** is optioneel voor echte optimalisatieproblemen zoals logistiek, verdeling en planning onder beperkingen.

**SimPy** kan later worden toegevoegd wanneer processen binnen een jaar nauwkeurige discrete timing nodig hebben. Voor vroege versies is een eenvoudige vaste tick waarschijnlijk beter.

## Data en API

**PostgreSQL** bewaart werelden, spelers, acties, historische toestanden en configuratie. **PostGIS** kan geografische queries en polygonen ondersteunen. **FastAPI** vormt de API tussen simulation core en browser.

De browser wordt een webapp, waarschijnlijk met **React/Next.js + TypeScript**. **MapLibre GL JS** kan later de interactieve wereldkaart renderen. De eerste UX mag bewust veel eenvoudiger zijn: een web-based terminal/simulation lab waarin developers werelden kunnen maken, jaren vooruitspoelen, waarden inspecteren en oorzaken opvragen.

## Event-gedreven koppeling

Modules moeten niet ongecontroleerd elkaars interne staat aanpassen. Waar mogelijk publiceren zij gebeurtenissen of changesets zoals `FoodShortage`, `MigrationPressure` of `KnowledgeSpread`. Andere modules reageren daarop via duidelijke contracten. Dit maakt uitbreiden en testen veel eenvoudiger.

## Eerste technische doel

De eerste mijlpaal is niet een mooie gameclient, maar een **headless reproduceerbare wereldsimulatie** die honderden jaren kan draaien en interessante, uitlegbare geschiedenis produceert. De definitieve UX wordt daarna bovenop dezelfde simulation core gebouwd.
