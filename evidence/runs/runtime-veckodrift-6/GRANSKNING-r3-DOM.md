# Granskningsrunda 3 — DOM: UNDERKÄND

Oberoende granskning 2026-09-29 av kandidaterna Runtime `5d2f3ac` och kontoret `487dc8f`.
Granskare: Codex `gpt-6-astra`, resonemang high, Runtimes pinnade `codex-0.155.1`, läsrätt
utan nät, 270 s, 34 egna kommandon. Rundan fick runda 1:s och 2:s domar med sig, och
ägarens beslut om kvittensen, och ombads pröva varje blockerare självständigt.

Domen nedan är granskarens ord ordagrant. Hur varje blockerare besvarades står i D040 och i
`LAS-FORST.md`. Blockerare 1 och 2 fällde den kanalcache runda 2 hade bett om: den är
tillbakadragen och ersatt av en period per kanal.

---

DOM: UNDERKÄND

Blockerare 1: Gammalt kanalresultat kan stänga en ny vecka

Fil: [kontor-driftoperation.py, rad 307](</Users/elinhaggstrom/nortropic-repos/Nortropic Runtime/.runtime/ap11/integrations/veckodrift/.scratch/review-r3/kontor-driftoperation.py:307>), samt rad 558 och 622.

Kanalresultatet saknar tidpunkt och periodbindning. Vid återupptagning återanvänds resultatet, men `started_at` sätts till återupptagningens tid och används som periodens `completed_at`.

Reproducerat i minnet: kontroll den 1 september, avbrott före periodskrivningen, återupptagning den 9 september. Ingen ny kontroll kördes, men perioden bokfördes som utförd den 9 september med `performed: true`. Nästa väckning gav `not_due`. Därmed kan en missad vecka döljas av ett gammalt resultat.

Blockerare 2: Nästa schemaväckning återanvänder inte redan utfört arbete

Filer: [kontor-driftoperation.py, rad 533](</Users/elinhaggstrom/nortropic-repos/Nortropic Runtime/.runtime/ap11/integrations/veckodrift/.scratch/review-r3/kontor-driftoperation.py:533>) och [scheduled_operation.py, rad 67](</Users/elinhaggstrom/nortropic-repos/Nortropic Runtime/.runtime/ap11/integrations/veckodrift/runtime/scheduled_operation.py:67>).

Kanalresultaten ligger under workflowets `run_id`. Nästa schemaväckning får ett nytt sådant ID och hittar därför inte föregående väcknings utförda kanaler.

Reproducerat i minnet: intaget misslyckas medan driftkontrollen lyckas. En timme senare kör nästa väckning driftkontrollen igen; `resumed_channels` är tom och perioden förblir öppen. Ett bestående intagsfel gör alltså den veckovisa driftkontrollen timvis.

Även avbrott före periodskrivningen följt av ett nytt kör-ID gav två driftanrop. Med samma kör-ID finns dessutom luckan mellan `produce()` och kanalresultatets skrivning, rad 326–327: avbrott där gav också dubbelarbete. Det befintliga återupptagningsprovet täcker bara avbrott efter periodstängningen med samma ID.

Blockerare 3: Monitorns kvarvarande trådar kan samlas och göra sena omförsök

Fil: [kontor-driftoperation.py, rad 113](</Users/elinhaggstrom/nortropic-repos/Nortropic Runtime/.runtime/ap11/integrations/veckodrift/.scratch/review-r3/kontor-driftoperation.py:113>), samt rad 143–174.

`join()` begränsar väntan men stoppar inte nätarbetet. Det finns varken avbrottssignal, stängning av anslutningen eller begränsning av antalet kvarvarande trådar. Efter ett sent transportfel kan tråden dessutom starta försök två, trots att kanalen redan rapporterat timeout.

Reproducerat med verkliga trådar, förkortad deadline och blockerande transportattrapp: tre avslutade monitoranrop lämnade tre levande trådar. När transporten släpptes ökade antalet öppningsförsök från tre till sex.

Rättningen löser den tidigare låshållningen och väntan på långsamma headers. Den begränsar däremot inte nätarbetets livstid eller resursansamlingen i den långlivade arbetaren. Talet 255 beskriver därför inte ett tak för allt pågående arbete.

Blockerare 4: Dokumentationen motsvarar fortfarande inte den aktuella evidensen

Filer: [kontor-docs.diff, rad 91](</Users/elinhaggstrom/nortropic-repos/Nortropic Runtime/.runtime/ap11/integrations/veckodrift/.scratch/review-r3/kontor-docs.diff:91>), rad 122, samt [LAS-FORST.md, rad 8](</Users/elinhaggstrom/nortropic-repos/Nortropic Runtime/.runtime/ap11/integrations/veckodrift/evidence/runs/runtime-veckodrift-3/LAS-FORST.md:8>).

Kontorets aktuella poster anger 35 hanterarprov, 25 nya och 534 helsvitsprov samt hänvisar till runda 2. Kandidatens testfil innehåller 38 prov och det bifogade helsvitskvittot visar 537; ökningen mot baslinjen är 28.

LAS-FORST och D040 anger tre körningar av varje helsvit. Underlaget innehåller tre Runtime-körningar per revision, men bara en kontorskörning per revision. LAS-FORST:s fördelning av processgruppsfelen är också fel: två kandidatkörningar och en baslinjekörning faller, inte en av vardera.

Detta blandar äldre och aktuell kvalificering och tillskriver underlaget fler körningar än det visar. Uppdragets uttryckliga evidenskrav är inte uppfyllt.

Anmärkningar som inte självständigt fäller kandidaten

- Stagingkontrollen är fortfarande ofullständig. Reproducerat: en monitor med extern HTTP-adress accepteras av `bind_operations` men vägras av hanteraren. Periodintervallens likhet kontrolleras däremot i kvalificeringsprovet.
- Kvittona belägger processfel i både kandidat och baslinje. Den granskade koden stöder frånvaron av direkt kodkoppling till ändringen. Att felen orsakas av belastning är däremot inte visat; processgruppsfelen redovisar `PermissionError`.
- Ägarens godkännande täcker Kundstart-kvittensen. Jag fann ingen ytterligare API-skrivning i den anropade konsumentvägen.

Jag har läst samtliga uppräknade filer, inklusive tidigare domar och D038–D040. Hasharna stämmer för hanteraren, operationsindatan, båda Digitala-verktygen och båda DRIFT-kvittona.

Inga filer eller driftinställningar ändrades. Motproven kördes i minnet. Helsviterna och motorprovet kördes inte om. Git-kontroller, commitmeddelanden och processlistan kunde inte verifieras med tillgänglig åtkomst; produktion, aktivering och faktisk macOS-sömn prövades inte.
