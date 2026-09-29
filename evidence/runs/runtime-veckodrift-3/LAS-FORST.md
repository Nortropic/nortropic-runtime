# Kvalificering runtime-veckodrift-3 — 2026-09-29, efter granskningsrunda 2

Ersätter `runtime-veckodrift-1` och `-2`. Båda tidigare rundornas domar ligger här ordagrant:
`GRANSKNING-r1-DOM.md` och `GRANSKNING-r2-DOM.md`.

## Svitkvitton, mätta och inte påstådda

Tre körningar av varje helsvit efter varandra på samma maskin med samma tolk, kandidat mot OFÖRÄNDRAD
main, eftersom två av proven visade sig vara ostadiga under last:

| kvitto | prov | utfall |
|---|---|---|
| `runtime-svit-korning-1.txt` | 666 | Chrome-provet + `test_bounded.test_timeout_with_term_ignoring_child` |
| `runtime-svit-korning-2.txt` | 666 | bara Chrome-provet |
| `runtime-svit-korning-3.txt` | 666 | Chrome-provet + `test_bounded.test_normal_leader_exit_with_term_ignoring_child` |
| `runtime-svit-baslinje-korning-1.txt` | 656 | bara Chrome-provet |
| `runtime-svit-baslinje-korning-2.txt` | 656 | Chrome-provet + `test_bounded.test_sigterm_with_term_ignoring_child` |
| `runtime-svit-baslinje-korning-3.txt` | 656 | bara Chrome-provet |
| `kontor-svit.txt` | 537 | OK |
| `kontor-svit-baslinje.txt` | 509 | OK |

Slutsatsen är mätt, inte antagen: `test_web_profiles`-provet om Chrome-processer faller i varje körning,
kandidat som baslinje. `test_bounded`-proven om processgrupper faller ostadigt under last i båda — tre
olika prov i tre av sex körningar, ett i kandidaten och ett i baslinjen utan mönster. Ingen av dem har
någon kodväg till det kandidaten ändrar: `scripts/bounded.py` och dess prov importerar varken
`operation_schedule` eller `scheduled_operation`, och kontorets hanterare ligger i ett annat repo.
Kandidaten lägger till 10 Runtime-prov och 28 kontorsprov.

Ett tidigare påstående om att samma svit gick 666/666 tidigare under dagen är borttaget: det kvittot
sparades inte, och ett tal utan kvitto hör inte i en post.

## Kvalificeringen mot den verkliga motorn

`RESULTAT.json` ur `scripts/probe_veckodrift.py`: tre verkliga schemalagda väckningar på den befintliga
Temporal-motorn, egen kö och eget schemanamn, kandidatens kontorshanterare och Digitalas verkliga frysta
`verktyg/drift_kontroll.py` och `verktyg/kundstart.py` startade som riktiga delprocesser över
loopback-HTTP.

- Väckning 1: förfallen (`no_period_recorded`). Ren driftkontroll, och en signalhämtning som nådde
  `lage: inget nytt` genom två verkliga sidor av `/api/intern/signaler`. Perioden stängd, sekvens 1, med
  den stängande körningens eget `run_id`.
- Väckning 2: inne i perioden (`not_due`). Noll anrop till sajten, noll till signalytan, inget körkvitto.
- Väckning 3: kontorets eget periodkvitto flyttat bakåt, som när värden sovit förbi tiden, och sajten ur
  funktion. `period_elapsed`, `overdue_seconds` 3620, incidenten funnen, kvittot skrivet i kundmappen och
  händelsen levererad en gång till kontorets privata driftyta. Sekvens 2.

Bundna tal, lästa ur de hanterarbyte som prövas och inte kopierade in i något Runtime-prov: kontorets
`BOUND_SECONDS` 255 < `ACTIVITY_BOUND` 300 < `SCHEDULE_TO_CLOSE_BOUND` 330 < `EXECUTION_BOUND` 360.
Provet vägrar också om hanterarens godtagna periodintervall skiljer sig från det installeraren tvingar:
båda är [3600, 2678400]. Den ordinarie väckningen är 3600 sekunder; provet accelererade bara det
isolerade schemat till 10 sekunder och prövade perioden vid dess golv.

`DRIFT-20260929T161550Z.json` (incidenter 0) och `DRIFT-20260929T161610Z.json` (incidenter 1) är de
faktiska kvitton kontrollen skrev i provets kundmapp — samma form som Digitalas `underhall.py besked`
läser, alltså den ordinarie vägen vidare.

## Inte visat

- Sajten och signalytan är loopback-provdata, aldrig en kundadress och aldrig Kundstarts produktion eller
  dess lokala provtjänst.
- Signalhämtningens verkliga import och dess `POST .../kvittens` är inte utövad här: provets signallistor
  är tomma, så bara full scan och `inget nytt` prövades. Ägaren godtog den skrivningen 2026-09-29 före
  16:07Z (kontorets DIGITALA-VECKODRIFT-20260929 bär hans ord). Vägen är Digitalas egen och täcks av
  `verktyg/test_kundstart_konsumtion.py`, som denna kandidat inte ändrar.
- macOS-sömn är inte utövad. Det är kontorets beständiga periodkvitto som bär igentagningen, och det är
  den mekanismen provet prövade. Den verkliga veckoperioden 604800 sekunder är inte utövad i verklig tid.
- Monitorns väggklocka är bevisad i kontorets prov mot en droppande server, både i kropp och i
  statusrad/headers, inte i motorprovet.
- Ingen release stagades, valdes eller aktiverades, och AP-10:s schema, tjänst och arbetare rördes inte.
