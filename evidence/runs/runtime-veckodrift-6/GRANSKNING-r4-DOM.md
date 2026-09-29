# Granskningsrunda 4 — DOM: UNDERKÄND

Oberoende granskning 2026-09-29 av kandidaterna Runtime `5efc25e` och kontoret `8672e9a`.
Granskare: Codex `gpt-6-astra`, resonemang high, Runtimes pinnade `codex-0.155.1`, läsrätt
utan nät, 276 s, 45 egna kommandon. Rundan fick rundorna 1–3:s domar och ägarens beslut med
sig, och ombads pröva varje blockerare självständigt.

Domen nedan är granskarens ord ordagrant. Hur varje blockerare besvarades står i D040 och i
`LAS-FORST.md`.

---

DOM: UNDERKÄND

Blockerare 1: Trådtaket gäller inte mellan Runtime-aktiviteter

Filer: [scheduled_operation.py:62](</Users/elinhaggstrom/nortropic-repos/Nortropic Runtime/.runtime/ap11/integrations/veckodrift/runtime/scheduled_operation.py:62>) och [kontor-driftoperation.py:51](</Users/elinhaggstrom/nortropic-repos/Nortropic Runtime/.runtime/ap11/integrations/veckodrift/.scratch/review-r4/kontor-driftoperation.py:51>).

Runtime skapar en ny modul vid varje aktivitet. Därmed återställs `_monitor_stranded` till en tom lista medan tidigare modulers övergivna trådar fortfarande lever.

Reproducerat med samma laddningssekvens, verkliga trådar och blockerande transportattrapp: tre anrop lämnade tre levande trådar trots taket två. Varje modul rapporterade bara sin egen tråd. Stoppflaggan förhindrade sena omförsök när transporten släpptes, men begränsar inte det pågående anropets livstid. Resurser kan därför fortsätta samlas i arbetaren. Talet 255 begränsar inte allt kvarvarande nätarbete.

Blockerare 2: Ett senare kanalfel kan fortfarande göra veckokontrollen timvis

Fil: [kontor-driftoperation.py:629](</Users/elinhaggstrom/nortropic-repos/Nortropic Runtime/.runtime/ap11/integrations/veckodrift/.scratch/review-r4/kontor-driftoperation.py:629>), samt rad 649–656.

Samtliga perioder bokförs först efter att alla kanaler och leveranser har behandlats. Monitorns bindningsfel kastas vidare. Ett sådant fel hindrar därför även en redan utförd driftkontroll från att stänga sin period.

Reproducerat i minnet: driftkontrollen lyckades, men monitorns saknade credentialfil avbröt körningen. Nästa väckning körde driftkontrollen igen. Två väckningar gav två driftanrop och inget periodkvitto. Ett bestående monitorfel gör alltså kontrollen timvis.

Även avbrott precis före periodskrivningen gav dubbelarbete vid nästa kör-ID. Det befintliga återupptagningsprovet täcker bara avbrott efter periodstängningen.

Blockerare 3: En monitor som inte körts stänger ändå perioden

Fil: [kontor-driftoperation.py:642](</Users/elinhaggstrom/nortropic-repos/Nortropic Runtime/.runtime/ap11/integrations/veckodrift/.scratch/review-r4/kontor-driftoperation.py:642>), tillsammans med rad 126–128.

Monitorn räknas som utförd enbart därför att nyckeln `monitor` finns i resultatet. Det gäller även `monitor_stranded_limit`, där inget nätanrop startas, och `monitor_bound_exceeded`.

Reproducerat genom `run()` med uppnått trådtak: noll hälsokontroller, men `performed: true` och stängd monitorperiod. Nästa väckning gav `not_due`. Om transporten blir tillgänglig strax därefter uteblir igentagningen tills nästa period. Detta motsäger också dokumentationens uttryckliga löfte att timeout lämnar perioden förfallen.

Blockerare 4: Återupptagning kan göra ett incidentkvitto grönt

Fil: [kontor-driftoperation.py:562](</Users/elinhaggstrom/nortropic-repos/Nortropic Runtime/.runtime/ap11/integrations/veckodrift/.scratch/review-r4/kontor-driftoperation.py:562>), särskilt rad 571–577.

Efter avbrott mellan periodstängningen och `result.json` skapar återupptagningen ett nytt svar med ovillkorligt `completed: true`. Det ursprungliga kanalutfallet och leveranserna återställs inte.

Reproducerat: driftkontrollen fann en incident, periodkvitto och incidenttillstånd sparades, sedan avbröts slutkvittot. Återupptagningen gav `already_performed` och `completed: true`, utan driftresultat eller leveranser, medan beständigt hälsotillstånd fortfarande var falskt. Runtime kan därmed redovisa `business_completed: true` för den avbrutna incidentkörningen.

Anmärkningar som inte självständigt fäller kandidaten

- Staging och hanteraren är fortfarande inte överens. [install_ap10.py:98](</Users/elinhaggstrom/nortropic-repos/Nortropic Runtime/.runtime/ap11/integrations/veckodrift/scripts/install_ap10.py:98>) accepterar ett fyrtiosiffrigt heltal som kandidat genom `str(...)`; hanteraren kastar `TypeError`. Även provets ofullständiga driftobjekt accepteras men saknar obligatoriskt `python_path`. Reproducerat utan filskrivningar. Rundturstestet bevisar filbindning, inte körbar konfiguration.
- Svitantalen 669/656 och 541/509 stöds av de tolv aktuella kvittona. Uppgiften två kandidat- och två baslinjekörningar med processgruppsfel av sex vardera kan beläggas när runda 3 och 4 räknas tillsammans. Det är olika kandidatrevisioner; detta bör anges tydligare. Aktuell runda ensam visar noll sådana kandidatfel och ett baslinjefel.
- Runbookens rad 422 hänvisar fortfarande till `period.json`, trots periodfiler per kanal.
- Ägarbeslutet täcker Kundstart-kvittensen. Jag fann ingen ytterligare API-skrivning i den anropade konsumentvägen.

Jag har läst samtliga uppräknade filer, inklusive tidigare domar och D038–D040. Hashbindningarna stämmer för hanteraren, operationsindatan, båda Digitala-verktygen och båda DRIFT-kvittona.

Inga filer eller driftinställningar ändrades. Motproven använde minnestillstånd och transportattrapper. Helsviterna och motorprovet kördes inte om. Git-kontroller, commitmeddelanden och processlistan kunde inte verifieras med tillgänglig åtkomst. Produktion, aktivering och faktisk macOS-sömn prövades inte.
