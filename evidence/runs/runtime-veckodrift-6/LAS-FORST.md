# Kvalificering runtime-veckodrift-6 — 2026-09-29, efter granskningsrunda 5

Ersätter rundorna 1–5. Alla fem domarna ligger här ordagrant: `GRANSKNING-r1-DOM.md` till `-r5-`.

Arbetet var pausat på ägarens beslut medan runda 5:s dom stod orättad. Pausen upphävdes 2026-09-29 ca
18:32Z: hans ord står i kontorets DIGITALA-VECKODRIFT-20260929.

## Vad runda 5 fällde, och vad som ändrades

Fyra blockerare, alla mina. Tre av dem hade samma rot — att ett kvitto eller ett hälsoläge fick attestera
något det inte visste — och löses av samma sak: **två faser, i tur och ordning.**

1. **Transportfel stängde en monitorperiod utan att något hälsosvar lästes.** `observed` sattes när
   tråden slutförts, inte när ändpunkten svarat. Ett tillfälligt DNS-fel kunde alltså skjuta upp en
   fortfarande skyldig kontroll en hel vecka. `observed` sätts nu av den kod som faktiskt vet: ett
   statussvar eller en läst kropp är en observation av sajten (frisk eller inte, och veckan är gjord),
   medan transportfel, DNS-fel och timeout inte är det — då står perioden kvar som skyldig. En ny
   `reason`, `endpoint_unhealthy`, skiljer "svarade, men osunt" från `endpoint_unavailable`.
2. **Återupptagning blev grön när någon kanal bara var `not_due`.** Hälsan lästes tillbaka bara om
   *samtliga* kanaler var återupptagningar.
3. **Attesteringen godtog saknat, feltypat och gammalt hälsounderlag.** Saknad tillståndsfil lästes
   uttryckligen som frisk, innehållet validerades inte, och inget bands till perioden.
4. **Avbrott före periodskrivningen gav dubbel driftkontroll** inom samma vecka, eftersom nästa
   väckning inte hittade något återanvändbart.

**Rättningen: settle-then-commit.** När en kanal är klar skrivs först ett `settled-<kanal>.json` med vad
den fann, och först därefter stängs perioden. Posten namnger den *enda* period den stänger
(`closes_sequence`), så den kan aldrig återanvändas i en senare — det var runda 3:s fälla, och den
förblir stängd. Ett avbrott mellan faserna lämnar arbetet hittbart: nästa väckning, med vilket kör-id
som helst, slutför commit:en ur det som observerades i stället för att läsa kundens sajt igen (4), och
kvittot bär den hälsa som faktiskt uppmättes (2 och 3). Posten valideras med stängd form, typad
`healthy`, mönsterprövad `reason` och `run_id` och en riktig tidsstämpel; saknad post betyder att inget
är bokfört, alltså att arbetet är skyldigt — aldrig att det var friskt. En post för en redan stängd
period ignoreras som passerad, en trasig bevaras för diagnos, och ingen av dem attesterar något.

Dessutom, ur rundans anmärkning: staging kontrollerade inte att kanalen fryser det verktyg den faktiskt
startar. Den kräver nu `verktyg/drift_kontroll.py` respektive `verktyg/kundstart.py` i `digitala_files`,
att varje fryst sökväg är relativ och säker och att varje hash är 64 hexadecimaler, och den vägrar ett
kanalobjekt som inte är ett objekt i stället för att krascha på det.

**Två fel jag själv hittade under rättningen, båda samma sort.** I `bind_operations` skuggade två
loopvariabler yttre namn: `files` (releasens filtabell) och `value` (operationens indata). Följden av den
första var att operationsindatans hash föll ur releasen, så `scheduled_operation.operation` hade vägrat
operationen vid körning; följden av den andra var att periodkontrollen tystnade helt, eftersom
`'period_seconds' in value` prövade medlemskap i en hashsträng. Rundturstestet fällde båda. Namnen är
nu åtskilda med en kommentar om varför, och två prov låser fast dem.

## Svitkvitton: tre körningar av varje, alla tolv bevarade, allt ur DENNA runda

| kvitto | prov | utfall |
|---|---|---|
| `runtime-svit-korning-1..3.txt` | 675 | Chrome-provet i alla tre, `test_bounded` i en |
| `runtime-svit-baslinje-korning-1..3.txt` | 656 | Chrome-provet i alla tre, `test_bounded` i en |
| `kontor-svit-korning-1..3.txt` | 563 | OK i alla tre |
| `kontor-svit-baslinje-korning-1..3.txt` | 509 | OK i alla tre |

Kandidaten lägger till 19 Runtime-prov och 54 kontorsprov. Hanterarens egen provfil ger **64
provkörningar på 52 olika metodnamn**, mot 10 på oförändrad main: tolv `test_`-metoder ligger i den
delade fixturen `DriftFixture` och ärvs av två testklasser, så körningar och metodnamn är inte samma tal.
Runda 5 fann att en tidigare formulering dolde det. Baslinjen är kandidatens egen bas, kontoret `34bcedd`
och Runtime `af78312`, mätt på samma maskin med samma tolk i anslutning till varandra.

Om de två fallerande Runtime-proven, sagt bara så långt kvittona bär: `test_web_profiles`-provet om
Chrome-processer faller i **varje** körning, kandidat som baslinje — dess `/bin/ps`-listning hittar inte
processen provet startade. `test_bounded`-provens processgruppfel slutar i `PermissionError: Operation
not permitted` ur `os.killpg` och faller ostadigt: i den här rundan **en kandidatkörning och en
baslinjekörning av tre vardera**. Båda finns alltså på oförändrad main, och ingendera har någon kodväg
till det kandidaten ändrar: `scripts/bounded.py` och dess prov importerar varken `operation_schedule`
eller `scheduled_operation`, och kontorets hanterare ligger i ett annat repo. Vad som orsakar dem är
**inte** utrett — `/bin/ps` och `os.killpg` fungerar när de körs för sig i samma skal — så ingen orsak
påstås. Tidigare rundors kvitton finns kvar men räknas inte in här; de gäller andra revisioner.

## Kvalificeringen mot den verkliga motorn

`RESULTAT.json` ur `scripts/probe_veckodrift.py`: **fyra** verkliga schemalagda väckningar på den
befintliga Temporal-motorn, egen kö och eget schemanamn, kandidatens kontorshanterare och Digitalas
verkliga frysta `verktyg/drift_kontroll.py` och `verktyg/kundstart.py` startade som riktiga delprocesser
över loopback-HTTP.

- Väckning 1: båda kanalerna förfallna. Ren driftkontroll, och en signalhämtning som nådde
  `lage: inget nytt` genom två verkliga sidor av `/api/intern/signaler`. Båda perioderna stängda vid
  sekvens 1, var och en med den stängande körningens eget `run_id`. `completed: true`.
- Väckning 2: båda inne i sin period. `not_due`, noll anrop, inget körkvitto. `completed: true`.
- Väckning 3: bara driftkanalens periodkvitto flyttat bakåt, och sajten ur funktion. Driftkontrollen
  utfördes (`period_elapsed`, `overdue_seconds` 3620), fann incidenten, skrev kvittot i kundmappen och
  levererade händelsen en gång till kontorets privata driftyta. Intaget stod kvar inne i sin egen period
  och gjorde inte ett enda anrop. `completed: false`.
- Väckning 4 (ny i denna runda): en settle-then-commit som avbrutits. Ett `settled-drift.json` med
  `healthy: false` planterades, i exakt den form hanteraren själv skriver, med perioden ostängd.
  Väckningen svarade `already_performed`, `attested_by: settled_outcome`, stängde perioden vid sekvens 3
  **ur den observerade hälsan** och kom tillbaka `completed: false` — inte grön — utan att göra ett enda
  nytt anrop till sajten eller signalytan. Hela provets `signal_requests` är 2, alltså bara väckning 1:s
  två sidor.

Bundna tal, lästa ur de hanterarbyte som prövas och inte kopierade in i något Runtime-prov: kontorets
`BOUND_SECONDS` 255 < `ACTIVITY_BOUND` 300 < `SCHEDULE_TO_CLOSE_BOUND` 330 < `EXECUTION_BOUND` 360.
Provet vägrar också om hanterarens godtagna periodintervall skiljer sig från det installeraren tvingar:
båda är [3600, 2678400]. Den ordinarie väckningen är 3600 sekunder; provet accelererade bara det
isolerade schemat till 10 sekunder och prövade perioden vid dess golv.

## Inte visat

- Sajten och signalytan är loopback-provdata, aldrig en kundadress och aldrig Kundstarts produktion eller
  dess lokala provtjänst.
- Signalhämtningens verkliga import och dess `POST .../kvittens` är inte utövad här: provets
  signallistor är tomma, så bara full scan och `inget nytt` prövades. Ägaren godtog den skrivningen
  2026-09-29 före 16:07Z. Vägen är Digitalas egen och täcks av `verktyg/test_kundstart_konsumtion.py`,
  som denna kandidat inte ändrar.
- macOS-sömn är inte utövad. Det är periodkvittot per kanal som bär igentagningen, och det är den
  mekanismen provet prövade. Den verkliga veckoperioden 604800 sekunder är inte utövad i verklig tid.
- Väckning 4:s avbrott är planterat tillstånd, inte ett verkligt kraschat schemalagt anrop. Det
  verkliga avbrottet precis mellan faserna prövas i kontorets egna prov, där `record_period` avbryts
  med ett undantag på exakt den punkten.
- Monitorns väggklocka, dess bundna kvarvarande trådar och taket över modulomladdningar är bevisade i
  kontorets prov mot en droppande server och en frusen transport, inte i motorprovet. `BOUND_SECONDS`
  binder när kanalen återvänder, inte livstiden på ett uttag som operativsystemet ännu håller.
- Ingen release stagades, valdes eller aktiverades, och AP-10:s schema, tjänst och arbetare rördes inte.
