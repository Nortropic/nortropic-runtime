# Kvalificering runtime-veckodrift-2 — 2026-09-29, efter granskningsrunda 1

Ersätter `evidence/runs/runtime-veckodrift-1/`, som hörde till den kandidat granskningsrunda 1
underkände. `GRANSKNING-r1-DOM.md` bär granskarens dom ordagrant.

## Svitkvitton, mätta och inte påstådda

| kvitto | vad | utfall |
|---|---|---|
| `runtime-svit.txt` | Runtimes helsvit, kandidaten | 663 prov, 1 fel |
| `runtime-svit-baslinje.txt` | Runtimes helsvit, OFÖRÄNDRAD main `af78312` | 656 prov, 1 fel |
| `kontor-svit.txt` | kontorets helsvit, kandidaten | 534 prov, OK |
| `kontor-svit-baslinje.txt` | kontorets helsvit, OFÖRÄNDRAD main `34bcedd` | 509 prov, OK |

Det enda felet är samma i kandidaten och i baslinjen:
`test_web_profiles.ChildProcessTests.test_only_the_processes_of_the_named_chrome_profile_are_ended`.
Det faller på oförändrad main på samma maskin med samma tolk, och kommer alltså inte av den här
kandidaten; det är en maskinberoende kontroll av Chrome-processer, och samma svit gick 663/663 tidigare
i dag på samma kod. Kandidaten lägger till 7 Runtime-prov och 25 kontorsprov och inför inget nytt fel.

## Kvalificeringen mot den verkliga motorn

`RESULTAT.json` är kvittot ur `scripts/probe_veckodrift.py`: tre verkliga schemalagda väckningar på den
befintliga Temporal-motorn, egen kö och eget schemanamn, kandidatens kontorshanterare och Digitalas
verkliga frysta `verktyg/drift_kontroll.py` och `verktyg/kundstart.py` startade som riktiga
delprocesser över loopback-HTTP.

- Väckning 1: förfallen (`no_period_recorded`). Ren driftkontroll, och en signalhämtning som nådde
  `lage: inget nytt` genom två verkliga sidor av `/api/intern/signaler`. Perioden stängd, sekvens 1,
  med den stängande körningens eget `run_id`.
- Väckning 2: inne i perioden (`not_due`). Noll anrop till sajten, noll till signalytan, inget
  körkvitto skrivet.
- Väckning 3: kontorets eget periodkvitto flyttat bakåt, som när värden sovit förbi tiden, och sajten
  ur funktion. `period_elapsed`, `overdue_seconds` 3620, incidenten funnen, kvittot skrivet i
  kundmappen och händelsen levererad en gång till kontorets privata driftyta. Sekvens 2.

Bundna tal ur kvittot: kontorets `BOUND_SECONDS` 255 < `ACTIVITY_BOUND` 300 < `SCHEDULE_TO_CLOSE_BOUND`
330 < `EXECUTION_BOUND` 360. Provet läser 255 ur de hanterarbyte som faktiskt prövas; talet står inte
kopierat i något Runtime-prov. Den ordinarie väckningen är 3600 sekunder; provet accelererade bara det
isolerade schemat till 10 sekunder och prövade perioden vid dess golv, 3600 sekunder.

`DRIFT-20260929T155010Z.json` (incidenter 0) och `DRIFT-20260929T155030Z.json` (incidenter 1) är de
faktiska kvitton kontrollen skrev i provets kundmapp — samma form som Digitalas `underhall.py besked`
läser, alltså den ordinarie vägen vidare.

`operation-input.json` är den bundna operationsindatan som prövades och `qualification-config.json` den
injicerade releasekonfigurationen. Båda namnger absoluta sökvägar i provets egen scratch-katalog.

## Inte visat

- Sajten och signalytan är loopback-provdata, aldrig en kundadress och aldrig Kundstarts produktion
  eller dess lokala provtjänst.
- Signalhämtningens verkliga import och dess `POST .../kvittens` är inte utövad här: provets
  signallistor är tomma, så bara full scan och `inget nytt` prövades. Den vägen är Digitalas egen och
  täcks av `verktyg/test_kundstart_konsumtion.py`, som denna kandidat inte ändrar.
- macOS-sömn är inte utövad. Det är kontorets beständiga periodkvitto som bär igentagningen, och det är
  den mekanismen provet prövade. Den verkliga veckoperioden 604800 sekunder är inte utövad i verklig tid.
- Ingen release stagades, valdes eller aktiverades, och AP-10:s schema, tjänst och arbetare rördes inte.
