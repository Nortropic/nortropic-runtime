# Kvalificering runtime-veckodrift-7 — 2026-09-29, efter granskningsrunda 6

Ersätter rundorna 1–6. Alla sex domarna ligger här ordagrant: `GRANSKNING-r1-DOM.md` till `-r6-`.

## Vad runda 6 fällde, och vad som ändrades

1. **Ett avbrott EFTER periodstängningen kunde fortfarande göra incidentkvittot grönt.** Utfallsposten
   godtogs bara för perioden som ännu inte stängts, så när perioden var stängd ignorerades dess eget
   utfall och en återupptagning svarade `completed: true`. Posten beskriver nu antingen den period som
   ska stängas (`sequence + 1`) eller den som ÄR stängd (`sequence`), och en körning som tappat sitt
   kvitto skriver det ur sitt eget utfall. Bara ur sitt eget: en vanlig väckning senare i veckan ärver
   inte förra periodens incident, vilket ett eget prov låser fast.

2. **Dubbelkontrollen före utfallsskrivningen.** Här väljer jag en uttalad avvägning i stället för en
   mekanism, och det är ett beslut värt att läsa som sådant. Ett avbrott mellan kontrollens start och
   utfallets bokföring gör det *okänt* om kontrollen hann klart. Ingen post kan känna utfallet av arbete
   som inte är gjort, så de två utgångarna är: läsa om en gång, eller stänga en period vars resultat
   aldrig setts. Det andra skulle dölja veckan, vilket är precis det beställningen förbjuder — och det
   var exakt vad mina rättningar i runda 3 och runda 5 gjorde när jag försökte eliminera dubbelarbetet.
   Därför läses det om, **en gång**, och det syns: en `attempt-<kanal>.json` skrivs innan läsningen får
   någon verkan, och nästa väckning redovisar `retried_after_interruption` i sitt kvitto. Två prov låser
   fast både att det sker en gång och att perioden sedan är stängd. Kostnaden är en extra läsning av
   kundens egen sajt och ett extra DRIFT-kvitto i kundmappen; ingenting skrivs hos någon leverantör.

3. **Monitorn kunde rapportera att inget svar kom trots mottaget HTTP-svar.** Observationen bokförs nu i
   samma stund `open()` återvänder, alltså före kroppsläsningen, och den yttre deadlinen läser av samma
   flagga — så ett mottaget 200 med droppande kropp, och ett 503 följt av utlöst deadline, är båda
   observationer. Annars hade perioden stått öppen och kontrollen återkommit vid varje väckning.

Dessutom, ur rundans anmärkning: staging godtog `python_sha256: "y"` och `plan_sha256: "z"`, värden som
aldrig kan vara lika med en SHA256. Båda krävs nu som 64 hexadecimaler.

Under rättningen fällde min egen provsvit två saker jag införde: en karantänregel som slutade bevara
trasiga utfallsposter, och ett nytt prov som lämnade övergivna monitortrådar bakom sig så att ett senare
prov fick `monitor_stranded_limit`. Båda är rättade, det senare med en `drain`-städning som också
dokumenterar att trådtaket är processvitt med avsikt.

## Svitkvitton: tre körningar av varje, alla tolv bevarade, allt ur DENNA runda

| kvitto | prov | utfall |
|---|---|---|
| `runtime-svit-korning-1..3.txt` | 676 | Chrome-provet i alla tre |
| `runtime-svit-baslinje-korning-1..3.txt` | 656 | Chrome-provet i alla tre, `test_bounded` i en |
| `kontor-svit-korning-1..3.txt` | 584 | OK i alla tre |
| `kontor-svit-baslinje-korning-1..3.txt` | 509 | OK i alla tre |

Kandidaten lägger till 20 Runtime-prov och 75 kontorsprov. Hanterarens egen provfil ger **85
provkörningar på 61 olika metodnamn**, mot 10 på oförändrad main: tolv `test_`-metoder ligger i den
delade fixturen `DriftFixture` och ärvs av tre testklasser, så körningar och metodnamn är inte samma tal.
Baslinjen är kandidatens egen bas, kontoret `34bcedd` och Runtime `af78312`, mätt på samma maskin med
samma tolk i anslutning till varandra.

Om de två fallerande Runtime-proven, sagt bara så långt kvittona bär: `test_web_profiles`-provet om
Chrome-processer faller i **varje** körning, kandidat som baslinje — dess `/bin/ps`-listning hittar inte
processen provet startade. `test_bounded`-provens processgruppfel slutar i `PermissionError: Operation
not permitted` ur `os.killpg` och faller ostadigt: i den här rundan **noll kandidatkörningar och en
baslinjekörning av tre vardera**. Båda finns alltså på oförändrad main, och ingendera har någon kodväg
till det kandidaten ändrar: `scripts/bounded.py` och dess prov importerar varken `operation_schedule`
eller `scheduled_operation`, och kontorets hanterare ligger i ett annat repo. Vad som orsakar dem är
**inte** utrett — `/bin/ps` och `os.killpg` fungerar när de körs för sig i samma skal — så ingen orsak
påstås. Tidigare rundors kvitton finns kvar men räknas inte in här; de gäller andra revisioner.

## Kvalificeringen mot den verkliga motorn

`RESULTAT.json` ur `scripts/probe_veckodrift.py`: fyra verkliga schemalagda väckningar på den befintliga
Temporal-motorn, egen kö och eget schemanamn, kandidatens kontorshanterare och Digitalas verkliga frysta
`verktyg/drift_kontroll.py` och `verktyg/kundstart.py` startade som riktiga delprocesser över
loopback-HTTP.

- Väckning 1: båda kanalerna förfallna. Ren driftkontroll, och en signalhämtning som nådde
  `lage: inget nytt` genom två verkliga sidor av `/api/intern/signaler`. Båda perioderna stängda vid
  sekvens 1. `completed: true`.
- Väckning 2: båda inne i sin period. `not_due`, noll anrop, inget körkvitto. `completed: true`.
- Väckning 3: bara driftkanalens periodkvitto flyttat bakåt, och sajten ur funktion. Driftkontrollen
  utfördes (`overdue_seconds` 3620), fann incidenten, skrev kvittot i kundmappen och levererade händelsen
  en gång till kontorets privata driftyta. Intaget stod kvar inne i sin egen period och gjorde inte ett
  enda anrop. `completed: false`.
- Väckning 4: en avbruten settle-then-commit. Svarade `already_performed`,
  `attested_by: settled_outcome`, stängde perioden vid sekvens 3 ur den observerade hälsan, kom tillbaka
  `completed: false` och gjorde inget nytt anrop. Hela provets `signal_requests` är 2.

`DRIFT-20260929T192730Z.json` (incidenter 0) och `DRIFT-20260929T192750Z.json` (incidenter 1) är de
faktiska kvitton kontrollen skrev i provets kundmapp — samma form som `underhall.py besked` läser.

Bundna tal, lästa ur de hanterarbyte som prövas: `BOUND_SECONDS` 255 < `ACTIVITY_BOUND` 300 <
`SCHEDULE_TO_CLOSE_BOUND` 330 < `EXECUTION_BOUND` 360, och provet vägrar om installerarens och
hanterarens periodintervall skiljer sig (båda [3600, 2678400]).

## Inte visat

- Sajten och signalytan är loopback-provdata, aldrig en kundadress och aldrig Kundstarts produktion eller
  dess lokala provtjänst.
- Signalhämtningens verkliga import och dess `POST .../kvittens` är inte utövad här: provets
  signallistor är tomma, så bara full scan och `inget nytt` prövades. Ägaren godtog den skrivningen
  2026-09-29 före 16:07Z. Vägen täcks av Digitalas egen `verktyg/test_kundstart_konsumtion.py`, oförändrad.
- macOS-sömn är inte utövad. Den verkliga veckoperioden 604800 sekunder är inte utövad i verklig tid.
- Väckning 4:s avbrott är planterat tillstånd. De verkliga avbrotten, på varje gräns en körning kan dö
  vid, prövas i kontorets egna prov med ett undantag på exakt den punkten.
- Monitorns väggklocka, observationsflaggan, de övergivna trådarnas tak över modulomladdningar och
  staging-vägranden är bevisade i enhetsproven, inte i motorprovet. `BOUND_SECONDS` binder när kanalen
  återvänder, inte livstiden på ett uttag som operativsystemet ännu håller.
- Ingen release stagades, valdes eller aktiverades, och AP-10:s schema, tjänst och arbetare rördes inte.
