# Granskningsrunda 6 — DOM: UNDERKÄND

Oberoende granskning 2026-09-29 av kandidaterna Runtime `539bb98` och kontoret `007230e`.
Granskare: Codex `gpt-6-astra`, läsrätt utan nät, 210 s, 34 egna kommandon.

Alla tre blockerare är rättade; se `LAS-FORST.md`. Blockerare 2 är besvarad med en
uttalad avvägning i stället för en mekanism, och skälet står där.

---

DOM: UNDERKÄND

Blockerare 1: Avbrott efter periodstängningen kan fortfarande göra incidentkvittot grönt

Fil: [kontor-driftoperation.py:488](</Users/elinhaggstrom/nortropic-repos/Nortropic Runtime/.runtime/ap11/integrations/veckodrift/.scratch/review-r6/kontor-driftoperation.py:488>), samt rad 685–701.

`validate_settled()` godtar bara utfallet för `sequence + 1`. När perioden redan stängts ignoreras alltså dess utfall. Saknas därefter `result.json` skapar återupptagningen ett svar med `completed: true`.

Reproducerat i minnet: driftkontrollen fann en incident, utfall och period sparades, sedan avbröts skrivningen av slutkvittot. Återupptagning med samma kör-ID gav `skipped: not_due`, `completed: true` och tomma `settled_channels`, trots sparat `healthy: false`. Ingen ny kontroll gjordes. Runtime kan därmed redovisa den avbrutna incidentkörningen som lyckad.

Provet i [kontor-test_driftoperation.py:593](</Users/elinhaggstrom/nortropic-repos/Nortropic Runtime/.runtime/ap11/integrations/veckodrift/.scratch/review-r6/kontor-test_driftoperation.py:593>) använder en frisk körning och kontrollerar inte detta incidentfall. Rättningen täcker avbrott före periodstängningen, men inte efter.

Blockerare 2: Dubbelkontrollsluckan har flyttats till före utfallsskrivningen

Fil: [kontor-driftoperation.py:740](</Users/elinhaggstrom/nortropic-repos/Nortropic Runtime/.runtime/ap11/integrations/veckodrift/.scratch/review-r6/kontor-driftoperation.py:740>), samt rad 756.

Kontrollen och hela incidentleveransen sker fortfarande innan det periodbundna utfallet skrivs. Ett avbrott före `settle_outcome()` lämnar inget som nästa väcknings förfallokontroll återanvänder.

Reproducerat i minnet: incidenten var levererad till inkorgen, men utfallsposten saknades efter avbrottet. Nästa kör-ID gjorde driftkontrollen igen. Två driftanrop utfördes inom samma period; periodsekvensen blev bara 1.

Det nya avbrottsprovet bryter vid `record_period()`, efter utfallsskrivningen, och missar denna kvarvarande lucka. Garantin mot dubbelarbete är därför inte uppfylld.

Blockerare 3: Monitorn kan rapportera att inget svar kom trots mottaget HTTP-svar

Fil: [kontor-driftoperation.py:199](</Users/elinhaggstrom/nortropic-repos/Nortropic Runtime/.runtime/ap11/integrations/veckodrift/.scratch/review-r6/kontor-driftoperation.py:199>), samt rad 137–164 och 223–226.

Ett normalt statussvar registreras inte som observerat när `open()` återvänder. Om kroppsläsningen sedan får timeout behandlas försöket som om ändpunkten aldrig svarade.

Reproducerat med transportattrapp: två mottagna HTTP 200-svar med efterföljande kroppstimeout gav `observed: false` och `endpoint_unavailable`.

Även yttergränsen tappar tidigare observationer: ett mottaget HTTP 503 följt av utlöst deadline gav `observed: false` och endast `monitor_bound_exceeded`. Det motprovet använde verklig tråd med förkortad deadline.

Perioden lämnas därmed öppen trots ett statussvar som enligt kontraktet ska räknas som observation. Felet kan göra kontrollen återkommande vid varje väckning. Ett 3xx som blir `HTTPError` räknas däremot som observerat, utan att omdirigeringen följs.

Anmärkningar som inte självständigt fäller kandidaten

- Stagingkontrollen är fortfarande ofullständig. [install_ap10.py:115](</Users/elinhaggstrom/nortropic-repos/Nortropic Runtime/.runtime/ap11/integrations/veckodrift/scripts/install_ap10.py:115>) accepterade i ett minnesbaserat motprov `python_sha256: "y"` och `plan_sha256: "z"`. Dessa kan aldrig motsvara hanterarens SHA256-jämförelser. Rundturstestet visar filbindning, inte fullständig körbarhet.
- De tolv svitkvittona stöder 675/656 respektive 563/509, ökningen 19/54 och processgruppsfel i en kandidat- och en baslinjekörning. Testklassernas arv ger också 64 provkörningar på 52 olika metodnamn.
- Ägarbeslutet täcker Kundstart-kvittensen. Jag fann ingen ytterligare API-skrivning i den anropade konsumentvägen.

Jag har läst samtliga uppräknade filer, tidigare domar och D038–D040. Hashbindningarna stämmer för hanteraren, operationsindatan, båda Digitala-verktygen och kundkvittona.

Motproven använde minnestillstånd och transportattrapper; inga filer eller driftinställningar ändrades. Helsviterna och motorprovet kördes inte om. Gitkontroller och commitmeddelanden kunde inte verifieras med tillgänglig åtkomst. Produktion, aktivering och faktisk macOS-sömn prövades inte.
