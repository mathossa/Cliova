# Dependency Rules

1. **Simulation is authoritative.** Frontend, API en toekomstige LLM-integraties bepalen geen spelwaarheid.
2. **Domains own rules.** Economische regels horen bijvoorbeeld in `domains/economy`, niet in API-routes of databasequeries.
3. **Engine owns order.** Alleen de simulation engine bepaalt de tickvolgorde en orchestratie.
4. **Changes are explainable.** Betekenisvolle mutaties leveren oorzaakmetadata/events op waarmee debugging en `why`-UX mogelijk zijn.
5. **No hidden cross-domain writes.** Een domein wijzigt niet rechtstreeks willekeurige interne state van een ander domein; gebruik gedeelde primitives, changesets of expliciete interfaces.
6. **Infrastructure points inward.** PostgreSQL/PostGIS, schedulers en externe libraries zijn adapters. Domeinregels blijven bruikbaar in unit tests zonder database of HTTP-server.
7. **Determinism first.** Dezelfde seed + state + directives moeten dezelfde uitkomst opleveren. Randomness loopt later via expliciete seeded RNG-context, niet via globale willekeur.
8. **Aggregate by default.** Simuleer populatiecohorten/groepen; maak alleen betekenisvolle instituties, facties en notable individuals tot individuele actors.
9. **Optimize after evidence.** Mesa, SimPy, OR-Tools of andere libraries worden toegevoegd wanneer een concreet domeinprobleem ze nodig heeft.
10. **No premature services.** Een domeingrens is niet automatisch een netwerkgrens.
