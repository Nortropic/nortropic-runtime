# Granskningsrunda 5 — DOM: UNDERKÄND

Oberoende granskning 2026-09-29 av kandidaterna Runtime `d910694` och kontoret `ff98676`.
Granskare: Codex `gpt-6-astra`, resonemang high, Runtimes pinnade `codex-0.155.1`, läsrätt
utan nät, 236 s, 38 egna kommandon. Rundan fick rundorna 1–4:s domar och ägarens beslut om
kvittensen med sig.

**Ingen av dessa fyra blockerare är rättad.** Ägaren beslutade 2026-09-29 ca 18:08Z att
uppdraget pausas för veckokvotens skull: runda 5 fick gå, och eftersom den underkände stannar
arbetet här. Domen är alltså en öppen arbetslista för nästa session, inte en historik.

**Rundans anmärkning om provantalet är kontrollerad och riktig.** Tolv `test_`-metoder ligger
i `DriftFixture` och ärvs av två testklasser: insamlingen ger 61 körningar men 49 olika
metodnamn. Mitt påstående i `runtime-veckodrift-5/LAS-FORST.md` att delningen tog bort
dubbelräkningen var därmed fel; det är rättat där. Talen 671/656 och 560/509 och fördelningen
av processgruppsfelet bekräftade granskaren mot kvittona.

---

DOM: UNDERKÄND

Blockerare 1: Transportfel stänger en monitorperiod utan läst svar

Fil: [kontor-driftoperation.py:159](</Users/elinhaggstrom/nortropic-repos/Nortropic Runtime/.runtime/ap11/integrations/veckodrift/.scratch/review-r5/kontor-driftoperation.py:159>), även rad 215–223 och 696.

`observed: true` sätts när tråden avslutats med ett resultat, även när båda försöken enbart gav transportfel. Det visar inte att något hälsosvar lästes.

Reproducerat med verklig monitorlogik och transportattrapp: två `URLError` gav `observed: true`, stängd monitorperiod och `not_due` vid nästa väckning. Ett tillfälligt DNS-fel kan alltså skjuta upp den fortfarande skyldiga kontrollen en hel vecka. Det nya kanalprovet injicerar redan färdigt `observed: false` och upptäcker inte felet.

Blockerare 2: Återupptagning med olika kanalperioder gör fortfarande incidentkvitton gröna

Fil: [kontor-driftoperation.py:589](</Users/elinhaggstrom/nortropic-repos/Nortropic Runtime/.runtime/ap11/integrations/veckodrift/.scratch/review-r5/kontor-driftoperation.py:589>), även rad 613 och 624.

Hälsoläget återläses bara om samtliga kanaler har `own_period_record`. Om någon kanal redan var `not_due` används i stället ovillkorligt `completed: true`. När andra kanaler fortfarande behöver köras ignoreras också tidigare utförda kanalutfall i slutresultatet.

Reproducerat: intaget hade en tidigare stängd period; driftkontrollen fann en incident och stängde sin period; körningen avbröts före slutkvittot. Återupptagningen gav `skipped: not_due` och `completed: true`, samtidigt som `drift.json` fortfarande innehöll `healthy: false`. Detta motsvarar kanalernas olika periodlägen i kvalificeringens tredje väckning.

Blockerare 3: Attesteringen godtar saknat, feltypat och gammalt hälsounderlag

Fil: [kontor-driftoperation.py:603](</Users/elinhaggstrom/nortropic-repos/Nortropic Runtime/.runtime/ap11/integrations/veckodrift/.scratch/review-r5/kontor-driftoperation.py:603>).

Saknad tillståndsfil tolkas uttryckligen som frisk. Befintligt innehåll passerar inte `validate_state`; `all(health.values())` godtar exempelvis strängen `"false"`. Ingen koppling till körningen eller dess period kontrolleras.

Reproducerat efter en avbruten incidentkörning: borttagen hälsofil, `{"healthy":"false"}` respektive ett gammalt grönt tillstånd daterat 2020 gav samtliga `completed: true` och `attested_by: persisted_channel_state`. Det befintliga provet täcker trasig JSON men inte dessa fall. Saknat underlag kan dessutom uppstå normalt eftersom `transition()` inte skriver tillstånd vid oförändrat grönt.

Blockerare 4: Avbrott före periodskrivningen ger dubbel driftkontroll

Fil: [kontor-driftoperation.py:652](</Users/elinhaggstrom/nortropic-repos/Nortropic Runtime/.runtime/ap11/integrations/veckodrift/.scratch/review-r5/kontor-driftoperation.py:652>), även rad 666–667.

Kontrollen och incidentleveransen utförs före periodskrivningen. Ett avbrott däremellan lämnar inget periodbundet utföranderesultat som nästa väckning återanvänder.

Reproducerat med avbrott precis före `record_period`: nästa kör-ID gjorde driftkontrollen igen. Två driftanrop utfördes inom samma period, trots att den första incidenten redan levererats. Periodsekvensen blev bara 1. Rättningen av kanalordningen löser monitorns senare bindningsfel, men inte denna avbrottslucka.

Anmärkningar som inte självständigt fäller kandidaten

- [install_ap10.py:111](</Users/elinhaggstrom/nortropic-repos/Nortropic Runtime/.runtime/ap11/integrations/veckodrift/scripts/install_ap10.py:111>) kontrollerar att `digitala_files` finns, men inte att rätt verktyg ingår. Reproducerat: driftbindning med endast `verktyg/kundstart.py` accepteras vid staging men vägras av hanteraren.
- LAS-FORST:s påstående att dubbelräknade prov försvunnit stämmer inte. Tolv testmetoder i `DriftFixture` ärvs av två testklasser. Insamlingen ger 61 provkörningar men 49 olika testmetoder.
- De tolv svitkvittona stöder däremot antalen 671/656 respektive 560/509 och processgruppsfel i en kandidat- och en baslinjekörning vardera.
- Ägarbeslutet täcker Kundstart-kvittensen. Jag fann ingen ytterligare API-skrivning i den anropade konsumentvägen.

Jag har läst samtliga uppräknade filer, tidigare domar och D038–D040. Hashbindningarna för hanteraren, operationsindatan, båda Digitala-verktygen och kundkvittona stämmer. Tre riktade trådregisterprov passerade, inklusive omladdning och städning.

Motproven använde minnestillstånd och transportattrapper; inga filer eller driftinställningar ändrades. Helsviterna och motorprovet kördes inte om. Git-kontroller, commitmeddelanden och processlistan kunde inte verifieras med tillgänglig åtkomst. Produktion, aktivering och faktisk macOS-sömn prövades inte.
