# Scenarios, History & Explainability

## Doel

Cliova moet verhalen laten ontstaan uit systemen in plaats van vooral uit vooraf geschreven events. De scenario-engine herkent betekenisvolle combinaties van omstandigheden en vertaalt die naar kwesties waarop samenlevingen en spelers kunnen reageren. De history engine bewaart vervolgens niet alleen wat gebeurde, maar ook waarom.

## Scenario’s als herkenning

Een scenario is meestal geen oorzaak maar een **interpretatie van bestaande toestand**. Lage voedselvoorraden, dalende productie en hoge prijzen kunnen samen een voedselcrisis vormen. Migratie, territoriale claims en negatieve relaties kunnen samen een grenscrisis creëren. Het scenario bundelt zulke signalen zodat de wereld begrijpelijk en speelbaar blijft.

## Dynamische gevolgen

Een scenario heeft geen verplicht eindpunt. Een voedselcrisis kan leiden tot import, rantsoenering, migratie, politieke hervorming, oorlog of technologische innovatie, afhankelijk van instituties en keuzes. Daardoor kan dezelfde uitgangssituatie in twee werelden totaal andere geschiedenis opleveren.

## Causaliteit opslaan

Elke belangrijke verandering moet expliciete oorzaken publiceren. Bijvoorbeeld:

`food_reserve -8.4%`

- slechte oogst: -5.1%
- bevolkingsgroei: -2.0%
- export: -2.3%
- betere opslag: +1.0%

Deze gegevens zijn zowel voor debugging als voor spelerinformatie essentieel. Explainability wordt daarom vanaf de eerste simulation prototype ingebouwd, niet achteraf toegevoegd.

## Historisch geheugen

De history engine bewaart belangrijke gebeurtenissen, betrokken actoren, oorzaken, gevolgen en relaties met eerdere gebeurtenissen. Niet iedere dagelijkse verandering wordt permanent een “historisch feit”; alleen gebeurtenissen die later betekenis kunnen hebben worden gepromoveerd naar de kroniek.

Collectief geheugen kan bovendien onderdeel van de simulatie worden. Oorlogen, verdragen, vervolging of gouden perioden kunnen generaties later nog identiteit, vertrouwen of claims beïnvloeden. Geschiedenis is daarmee niet alleen output maar ook toekomstige input.

## Kroniek

De speler kan terugkijken via een tijdlijn of kroniek. Idealiter kan een gebeurtenis als een burgeroorlog worden teruggevolgd naar economische spanningen, politieke hervormingen, invloedrijke personen en eerdere crises. De wereld moet voelen alsof zij een werkelijk verleden heeft opgebouwd.

## Geen scriptloos dogma

Handgeschreven content mag bestaan voor bijzondere presentatie, tutorial of zeldzame flavour, maar mag de simulation core niet vervangen. De standaardregel is: **systemen veroorzaken de gebeurtenis; content helpt haar begrijpelijk en menselijk te presenteren**.

Deze module is cruciaal om complexe emergentie niet als willekeur te laten voelen. Cliova moet de speler altijd zo goed mogelijk kunnen beantwoorden: **“Waarom is dit gebeurd?”**
