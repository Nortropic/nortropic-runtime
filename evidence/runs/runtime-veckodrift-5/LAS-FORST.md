# Kvalificering runtime-veckodrift-5 — 2026-09-29, efter granskningsrunda 4

Ersätter rundorna 1–4. Alla fyra domarna ligger här ordagrant: `GRANSKNING-r1-DOM.md` till `-r4-`.

## Vad runda 4 fällde, och vad som ändrades

Fyra blockerare, alla mina:

1. **Trådtaket gällde inte mellan Runtime-aktiviteter.** Runtime laddar hanteraren på nytt för varje
   aktivitet, så en registeruppgift i modultillståndet nollställdes vid varje väckning medan tidigare
   trådar levde. Registret är nu förankrat i tolken i stället, under ett uttryckligt namn, och ett prov
   laddar modulen på nytt tre gånger precis som Runtime gör och visar att taket håller.
2. **Ett bestående kanalfel kunde fortfarande göra veckokontrollen timvis.** Alla perioder bokfördes
   efter att alla kanaler behandlats, och monitorns bindningsfel kastas med avsikt vidare — vilket
   hindrade en redan utförd driftkontroll från att stänga sin egen vecka. Varje kanal levererar och
   stänger nu sin period i samma stund dess eget arbete är klart, och monitorn behandlas sist.
3. **En monitor som aldrig nådde ändpunkten stängde ändå sin period.** `monitor_bound_exceeded` och
   `monitor_stranded_limit` betyder att ingenting kontrollerades. De bär nu `observed: false`, och en
   kanal räknas som utförd bara om den faktiskt fick ett svar; perioden står alltså kvar som skyldig.
4. **Återupptagning kunde göra ett incidentkvitto grönt.** En körning som tappat sitt slutkvitto svarade
   ovillkorligt `completed: true`. Den läser nu tillbaka kanalernas egna beständiga hälsolägen och
   redovisar `attested_by: persisted_channel_state`; en avbruten incidentkörning förblir
   `completed: false`, och ett oläsbart hälsoläge läses aldrig som grönt.

Dessutom, ur rundans anmärkningar: installeraren godtog en kandidat som inte var en sträng (`str()`
tvättade ett heltal förbi kontrollen) och ett ofullständigt kanalobjekt utan `python_path`; båda vägras
nu, med krav på varje nyckel hanteraren behöver och att sökvägarna är absoluta. Runbookens rad om
`period.json` pekar nu på `period-<kanal>.json`. Och provklasserna är delade så att en delad fixtur inte
längre gör att samma prov räknas två gånger.

## Svitkvitton: tre körningar av varje, alla tolv bevarade, allt ur DENNA runda

| kvitto | prov | utfall |
|---|---|---|
| `runtime-svit-korning-1..3.txt` | 671 | Chrome-provet i alla tre, `test_bounded` i en |
| `runtime-svit-baslinje-korning-1..3.txt` | 656 | Chrome-provet i alla tre, `test_bounded` i en |
| `kontor-svit-korning-1..3.txt` | 560 | OK i alla tre |
| `kontor-svit-baslinje-korning-1..3.txt` | 509 | OK i alla tre |

Kandidaten lägger till 15 Runtime-prov och 51 kontorsprov; hanterarens egen provfil går från 10 till 61
prov. Antalen är räknade ur de bifogade kvittona, inte ur minnet, och de gäller bara den här rundans
revisioner: Runtime `af78312` mot kandidaten, kontoret `34bcedd` mot kandidaten.

Om de två fallerande Runtime-proven, sagt bara så långt kvittona bär:
`test_web_profiles`-provet om Chrome-processer faller i **varje** körning, kandidat som baslinje: dess
`/bin/ps`-listning hittar inte processen provet startade. `test_bounde`-provens processgruppfel slutar i
`PermissionError: Operation not permitted` ur `os.killpg` och faller ostadigt: **i den här rundan en
kandidatkörning och en baslinjekörning av tre vardera**. Båda finns alltså på oförändrad main på samma
maskin med samma tolk, och ingendera har någon kodväg till det kandidaten ändrar: `scripts/bounded.py`
och dess prov importerar varken `operation_schedule` eller `scheduled_operation`, och kontorets hanterare
ligger i ett annat repo. Vad som orsakar dem är **inte** utrett: `/bin/ps` och `os.killpg` fungerar när de
körs för sig i samma skal, så ingen orsak påstås — bara att felen finns i båda revisionerna och inte
kommer av den här ändringen. Tidigare rundors kvitton finns kvar men räknas inte in här, eftersom de
gäller andra kandidatrevisioner.

## Kvalificeringen mot den verkliga motorn

`RESULTAT.json` ur `scripts/probe_veckodrift.py`: tre verkliga schemalagda väckningar på den befintliga
Temporal-motorn, egen kö och eget schemanamn, kandidatens kontorshanterare och Digitalas verkliga frysta
`verktyg/drift_kontroll.py` och `verktyg/kundstart.py` startade som riktiga delprocesser över
loopback-HTTP.

- Väckning 1: båda kanalerna förfallna. Ren driftkontroll, och en signalhämtning som nådde
  `lage: inget nytt` genom två verkliga sidor av `/api/intern/signaler`. Båda perioderna stängda vid
  sekvens 1, var och en med den stängande körningens eget `run_id`.
- Väckning 2: båda inne i sin period. `not_due`, noll anrop, inget körkvitto.
- Väckning 3: **bara driftkanalens** periodkvitto flyttat bakåt, och sajten ur funktion.
  Driftkontrollen utfördes (`period_elapsed`, `overdue_seconds` 3620), fann incidenten, skrev kvittot i
  kundmappen och levererade händelsen en gång till kontorets privata driftyta. Intaget stod kvar inne i
  sin egen period och gjorde inte ett enda anrop: `signal_requests` är 2 för hela provet, alltså bara
  väckning 1:s två sidor. Drift slutade på sekvens 2, intaget på sekvens 1.

Bundna tal, lästa ur de hanterarbyte som prövas och inte kopierade in i något Runtime-prov: kontorets
`BOUND_SECONDS` 255 < `ACTIVITY_BOUND` 300 < `SCHEDULE_TO_CLOSE_BOUND` 330 < `EXECUTION_BOUND` 360.
Provet vägrar också om hanterarens godtagna periodintervall skiljer sig från det installeraren tvingar:
båda är [3600, 2678400]. Den ordinarie väckningen är 3600 sekunder; provet accelererade bara det
isolerade schemat till 10 sekunder och prövade perioden vid dess golv.

`DRIFT-20260929T173250Z.json` (incidenter 0) och `DRIFT-20260929T173310Z.json` (incidenter 1) är de
faktiska kvitton kontrollen skrev i provets kundmapp — samma form som Digitalas `underhall.py besked`
läser, alltså den ordinarie vägen vidare.

## Inte visat

- Sajten och signalytan är loopback-provdata, aldrig en kundadress och aldrig Kundstarts produktion
  eller dess lokala provtjänst.
- Signalhämtningens verkliga import och dess `POST .../kvittens` är inte utövad här: provets
  signallistor är tomma, så bara full scan och `inget nytt` prövades. Ägaren godtog den skrivningen
  2026-09-29 före 16:07Z (kontorets DIGITALA-VECKODRIFT-20260929 bär hans ord). Vägen är Digitalas egen
  och täcks av `verktyg/test_kundstart_konsumtion.py`, som denna kandidat inte ändrar.
- macOS-sömn är inte utövad. Det är kontorets beständiga periodkvitto per kanal som bär igentagningen,
  och det är den mekanismen provet prövade. Den verkliga veckoperioden 604800 sekunder är inte utövad i
  verklig tid.
- Monitorns väggklocka, dess bundna kvarvarande trådar och taket över modulomladdningar är bevisade i
  kontorets prov mot en droppande server och en frusen transport, inte i motorprovet. `BOUND_SECONDS`
  binder när kanalen återvänder, inte livstiden på ett uttag som operativsystemet ännu håller; det som
  är bundet om övergivet arbete är att det inte kan göra ett nytt försök och att högst två får leva.
- Ingen release stagades, valdes eller aktiverades, och AP-10:s schema, tjänst och arbetare rördes inte.
