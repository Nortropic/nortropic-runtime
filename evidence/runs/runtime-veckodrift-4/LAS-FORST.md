# Kvalificering runtime-veckodrift-4 — 2026-09-29, efter granskningsrunda 3

Ersätter `runtime-veckodrift-1`, `-2` och `-3`. Alla tre tidigare domarna ligger här ordagrant:
`GRANSKNING-r1-DOM.md`, `-r2-` och `-r3-`.

## Vad runda 3 fällde, och vad som ändrades

Runda 2 bad om att en återupptagen körning inte skulle göra om redan gjort arbete, och jag gjorde det
med en beständig cache per kanal och körning. Runda 3 visade att den lösningen var sämre än felet:
ett kanalresultat från den 1 september kunde återanvändas den 9 september och stänga den nya perioden
med den senare körningens klocka — alltså dölja en missad vecka, precis det beställningen förbjuder.
Och eftersom cachen låg under körningens id kunde nästa schemaväckning ändå inte använda den, så ett
bestående intagsfel gjorde den veckovisa driftkontrollen timvis.

Cachen är därför tillbakadragen. I stället har **varje kanal sin egen period**
(`period-<kanal>.json`), och båda halvorna av beställningen håller samtidigt:

- Ett resultat återanvänds aldrig. En period stängs bara av den körning som gjorde arbetet, med den
  körningens egen starttid, så gammalt arbete kan inte stänga en ny period.
- En kanal som fortsätter misslyckas görs om vid varje väckning utan att dra med sig en kanal som
  redan gjort sin vecka. Driftkontrollen förblir veckovis även när intaget är trasigt.
- En körning som avbröts efter att den stängt sin egen periods arbete känner igen sitt eget kvitto
  (`own_period_record`), läser ingenting igen, flyttar ingen sekvens och skriver klart sitt kvitto.
  Det läget heter `already_performed`, inte `not_due`, så det går att skilja i kvittot.

Monitorns kvarvarande trådar är också bundna. En join binder kanalen, inte uttaget: en övergiven tråd
får nu en stoppflagga, så den kan inte starta ett andra försök efter att kanalen redan svarat, och
högst två får vara vid liv samtidigt — därutöver vägrar kanalen direkt
(`monitor_stranded_limit`) i stället för att lägga på mer nätarbete i den långlivade arbetaren.

## Svitkvitton: tre körningar av varje, alla bevarade

| kvitto | prov | utfall |
|---|---|---|
| `runtime-svit-korning-1..3.txt` | 669 | Chrome-provet i alla tre |
| `runtime-svit-baslinje-korning-1..3.txt` | 656 | Chrome-provet i alla tre, `test_bounded` i en |
| `kontor-svit-korning-1..3.txt` | 541 | OK i alla tre |
| `kontor-svit-baslinje-korning-1..3.txt` | 509 | OK i alla tre |

Kandidaten lägger till 13 Runtime-prov och 32 kontorsprov; hanterarens egen provfil går från 10 till
42 prov. Alla tolv körningarna ligger som kvitto, inte en sammanfattning av dem.

Om de två fallerande Runtime-proven, sagt bara så långt kvittona bär:
`test_web_profiles`-provet om Chrome-processer faller i **varje** körning, kandidat som baslinje: dess
`/bin/ps`-listning hittar inte processen provet startade. `test_bounde`-provens processgruppfel är
ostadiga och slutar i `PermissionError: Operation not permitted` ur `os.killpg`; över alla bevarade
körningar har de fallit i två kandidatkörningar och två baslinjekörningar av sex vardera, utan mönster.
Båda finns alltså på oförändrad main på samma maskin med samma tolk, och ingendera har någon kodväg
till det kandidaten ändrar: `scripts/bounded.py` och dess prov importerar varken `operation_schedule`
eller `scheduled_operation`, och kontorets hanterare ligger i ett annat repo. Vad som orsakar dem är
**inte** utrett: `/bin/ps` och `os.killpg` fungerar när de körs för sig i samma skal, så jag påstår
ingen orsak — bara att felen finns i båda revisionerna och inte kommer av den här ändringen.

## Kvalificeringen mot den verkliga motorn

`RESULTAT.json` ur `scripts/probe_veckodrift.py`: tre verkliga schemalagda väckningar på den befintliga
Temporal-motorn, egen kö och eget schemanamn, kandidatens kontorshanterare och Digitalas verkliga frysta
`verktyg/drift_kontroll.py` och `verktyg/kundstart.py` startade som riktiga delprocesser över
loopback-HTTP.

- Väckning 1: båda kanalerna förfallna. Ren driftkontroll, och en signalhämtning som nådde
  `lage: inget nytt` genom två verkliga sidor av `/api/intern/signaler`. Båda perioderna stängda vid
  sekvens 1, var och en med den stängande körningens eget `run_id`.
- Väckning 2: båda inne i sin period. `not_due`, noll anrop, inget körkvitto.
- Väckning 3: **bara driftkanalens** periodkvitto flyttat bakåt, som när värden sovit förbi just den
  tiden, och sajten ur funktion. Driftkontrollen utfördes (`period_elapsed`, `overdue_seconds` 3620),
  fann incidenten, skrev kvittot i kundmappen och levererade händelsen en gång till kontorets privata
  driftyta. Intaget stod kvar inne i sin egen period och gjorde inte ett enda anrop —
  `signal_requests` är 2 för hela provet, alltså bara väckning 1:s två sidor. Det är perioderna per
  kanal visade i drift: drift slutade på sekvens 2, intaget på sekvens 1.

Bundna tal, lästa ur de hanterarbyte som prövas och inte kopierade in i något Runtime-prov: kontorets
`BOUND_SECONDS` 255 < `ACTIVITY_BOUND` 300 < `SCHEDULE_TO_CLOSE_BOUND` 330 < `EXECUTION_BOUND` 360.
Provet vägrar också om hanterarens godtagna periodintervall skiljer sig från det installeraren tvingar:
båda är [3600, 2678400]. Den ordinarie väckningen är 3600 sekunder; provet accelererade bara det
isolerade schemat till 10 sekunder och prövade perioden vid dess golv.

`DRIFT-20260929T164930Z.json` (incidenter 0) och `DRIFT-20260929T164950Z.json` (incidenter 1) är de
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
  och det är den mekanismen provet prövade. Den verkliga veckoperioden 604800 sekunder är inte utövad
  i verklig tid.
- Monitorns väggklocka och dess bundna kvarvarande trådar är bevisade i kontorets prov mot en droppande
  server och en frusen transport, inte i motorprovet.
- Ingen release stagades, valdes eller aktiverades, och AP-10:s schema, tjänst och arbetare rördes inte.

---

**ERSATT 2026-09-29 av `evidence/runs/runtime-veckodrift-5/`.** Granskningsrunda 4 underkände kandidaten
efter denna runda. Kvittot bevaras som spår; läs r5 för det läge som gäller.

---

**ERSATT 2026-09-29 av `evidence/runs/runtime-veckodrift-6/`.** Kvittot bevaras som spår; läs r6
för det läge som gäller.
