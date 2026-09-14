# Time, Action Economy & Multiplayer

## Doel

Cliova is ontworpen als een **langzame, persistente multiplayerwereld** waarin spelers dagelijks kort kunnen terugkeren en toch eeuwen geschiedenis opbouwen. Het uitgangspunt is ongeveer **één echte dag = één speljaar**.

## World tick

Gedurende de dag verzamelen spelers informatie, geven directives, onderhandelen en bereiden besluiten voor. Op een vast moment verwerkt de server de volgende wereldtick. Intern hoeft een jaar niet één enkele berekening te zijn: seizoenen, maanden of discrete gebeurtenissen kunnen binnen die tick in de juiste volgorde worden afgehandeld.

De tick moet authoritative zijn: dezelfde wereldstatus en dezelfde ingevoerde acties produceren reproduceerbare resultaten zolang willekeur via opgeslagen seeds wordt beheerd. Dit maakt debugging, replay en uitleg mogelijk.

## Action economy

De speler heeft niet simpelweg een vast aantal abstracte action points. Iedere samenleving beschikt over verschillende vormen van **maatschappelijke capaciteit**, bijvoorbeeld arbeid, productie, kennis, bestuur en logistiek/bereik. Directives en projecten vragen capaciteit uit één of meerdere categorieën.

Een project kan over meerdere jaren worden opgebouwd. Nieuwe infrastructuur of instituties kunnen later in dezelfde of volgende ticks extra capaciteit creëren, waardoor geplande kettingreacties mogelijk zijn. Dit neemt inspiratie uit engine-building games zonder de wereld terug te brengen tot kaarten en blokjes.

## Uitvoering is niet hetzelfde als capaciteit

Een samenleving kan theoretisch veel middelen hebben maar organisatorisch weinig mobiliseren. Corruptie, zwakke bureaucratie, politieke weerstand, afstand en instituties beïnvloeden hoeveel capaciteit effectief beschikbaar is. Groei betekent daarom niet automatisch meer directe controle voor de speler.

## Asynchrone multiplayer

Spelers hoeven niet tegelijk online te zijn. Diplomatieke berichten, handelsvoorstellen, verdragen en dreigingen kunnen gedurende de dag worden uitgewisseld. Bij de tick worden geldige beslissingen en wederzijdse afspraken verwerkt. Dit ondersteunt een speelstijl waarin een campagne maanden of jaren kan lopen.

## NPC-samenlevingen

Niet iedere staat hoeft door een mens bestuurd te worden. AI-gestuurde samenlevingen blijven via dezelfde onderliggende systemen handelen en kunnen ontstaan, splitsen, verdwijnen of later door spelers relevant worden. Daardoor blijft de wereld levend bij lage spelersaantallen.

## Resources

Het dagelijkse tick-model is ook technisch gunstig. De zware simulatie hoeft niet permanent realtime te draaien; werelden kunnen als jobs over worker-processen worden verdeeld. De browser en API verwerken overdag vooral lichte interacties en dataweergave.

De combinatie van traag tempo en diepe simulatie moet Cliova laten voelen als **een geschiedenis waar je elke dag naar terugkeert**, niet als een game die vereist dat je voortdurend online bent.
