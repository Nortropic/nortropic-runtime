# Kvalificering runtime-veckodrift-1 — 2026-09-29

`RESULTAT.json` är kvittot ur `scripts/probe_veckodrift.py`: tre verkliga schemalagda
väckningar på den befintliga Temporal-motorn, egen kö och eget schemanamn, kandidatens
kontorshanterare och Digitalas verkliga frysta `verktyg/drift_kontroll.py` och
`verktyg/kundstart.py` startade som riktiga delprocesser över loopback-HTTP.

Väckning 1 var förfallen (inget periodkvitto fanns) och gav en ren driftkontroll samt en
signalhämtning som nådde `lage: inget nytt` genom två verkliga sidor av
`/api/intern/signaler`. Väckning 2 låg inom perioden: den läste ingenting, gjorde inget
anrop och skrev inget körkvitto. Sedan flyttades kontorets eget periodkvitto bakåt, som
när värddatorn sovit förbi tiden, och sajten sattes ur funktion: väckning 3 utförde den
försenade perioden (`overdue_seconds` 3620), fann incidenten, skrev kvittot i kundmappen
och levererade händelsen en gång till kontorets privata driftyta.

`DRIFT-20260929T152040Z.json` (incidenter 0) och `DRIFT-20260929T152100Z.json`
(incidenter 1) är de faktiska kvitton kontrollen skrev i provets kundmapp. Det är samma
form som Digitalas `underhall.py besked` läser, alltså den ordinarie vägen vidare.

`operation-input.json` är den bundna operationsindatan som prövades, och
`qualification-config.json` den injicerade releasekonfigurationen. Båda namnger absoluta
sökvägar i provets egen scratch-katalog. Ingen release stagades, valdes eller aktiverades,
och AP-10:s schema, tjänst och arbetare rördes inte.

Bundna tal ur kvittot: kontorets `BOUND_SECONDS` 239 < Runtimes `ACTIVITY_BOUND` 300 <
`EXECUTION_BOUND` 360. Den ordinarie väckningen är 3600 sekunder; provet accelererade bara
det isolerade schemat till 10 sekunder och prövade perioden vid dess golv, 3600 sekunder.

Inte visat: sajten och signalytan är loopback-provdata, inte en kundadress och inte
Kundstarts produktion eller dess lokala provtjänst. macOS-sömn är inte utövad; det är
kontorets beständiga periodkvitto som bär igentagningen, och det är den mekanismen provet
prövade. Den verkliga veckoperioden 604800 sekunder är inte utövad i verklig tid.
