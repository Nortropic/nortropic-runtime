# Granskningsrunda 1 — DOM: UNDERKÄND

Oberoende granskning 2026-09-29 av kandidaterna Runtime `9429c8b` och kontoret `89e54a5`.
Granskare: Codex `gpt-6-astra`, resonemang high, Runtimes pinnade `codex-0.155.1`, läsrätt
utan nät, 261 s, 45 egna kommandon. Författaren var Claude Opus 5, alltså en annan leverantör:
separationen är verklig och inte samma modellfamilj.

Claude-granskaren kunde inte användas: `seven_day_overage_included` stod på utnyttjande 1,0 och
vägrade Fable 5.1, Opus 5 och Sonnet 5. Mätt per modell, inte antaget — Haiku 4.5 svarade på det
plain `seven_day`-fönstret (0,92, `allowed_warning`). Kvoten återställs 2026-10-04.

Domen nedan är granskarens ord ordagrant. Hur varje blockerare besvarades står i D040 och i
`LAS-FORST.md`.

---

DOM: UNDERKÄND

Blockerare 1: Signalhämtningen skriver till Kundstarts interna API

Fil: [kontor-driftoperation.py, rad 180](</Users/elinhaggstrom/nortropic-repos/Nortropic Runtime/.runtime/ap11/integrations/veckodrift/.scratch/review-r1/kontor-driftoperation.py:180>).

Hanteraren startar `kundstart.py konsumera`. Den hashbundna konsumenten gör efter import ett `POST /api/intern/arenden/<id>/kvittens`, se [kundstart.py, rad 937](</Users/elinhaggstrom/nortropic-repos/Nortropic Runtime/.runtime/ap11/integrations/veckodrift/.scratch/veckodrift-r1/frozen-digitala/verktyg/kundstart.py:937>). Därmed ändras serverns kvittensläge när en ny signal kommer. Det strider mot granskningsuppdragets läsande mandat.

Motorprovets signallistor är alltid tomma, så denna väg prövas aldrig. Konsumentens hash stämmer med kvalificeringens bindning; fyndet gäller de faktiskt bundna verktygsbyten.

Blockerare 2: Tidsbudgeten är ingen faktisk övre körgräns

Fil: [kontor-driftoperation.py, rad 103](</Users/elinhaggstrom/nortropic-repos/Nortropic Runtime/.runtime/ap11/integrations/veckodrift/.scratch/review-r1/kontor-driftoperation.py:103>).

`MONITOR_BOUND = 17` räknar två åttasekundersförsök och en sekunds väntan. Men `urlopen(timeout=8)` begränsar blockerande nätoperationer, inte hela försöket. `response.read(65537)` kan fortsätta mycket längre om servern skickar små mängder data med mindre än åtta sekunders mellanrum.

Därför är totalsumman 239 sekunder inte ett väggklocketak. Monitorn körs dessutom i en tråd som Runtime inte stoppar när väntetiden för städning löper ut. Den kan behålla tillståndslåset efter workflowtimeout och hindra senare veckokörningar. Konstantjämförelserna i proven visar inte den utlovade tidsgränsen.

Blockerare 3: Fördärvat perioddatum kan stoppa igentagningen

Fil: [kontor-driftoperation.py, rad 400](</Users/elinhaggstrom/nortropic-repos/Nortropic Runtime/.runtime/ap11/integrations/veckodrift/.scratch/review-r1/kontor-driftoperation.py:400>).

Valideringen accepterar framtida tidsstämplar, och additionen av perioden ligger utanför felhanteringen. Reproducerat utan filskrivningar:

- `completed_at = 2099-01-01T00:00:00+00:00` ger `not_due` fram till januari 2099.
- `completed_at = 9999-12-31T00:00:00+00:00` ger obehandlad `OverflowError`.

Det första fallet rapporteras som en lyckad överhoppad väckning; det andra misslyckas vid varje väckning. Ingetdera bevaras och återhämtas som `invalid_period_state`. Detta bryter den påstådda återhämtningen från fördärvat periodtillstånd.

Blockerare 4: Återupptagning utför en redan stängd period igen

Fil: [kontor-driftoperation.py, rad 449](</Users/elinhaggstrom/nortropic-repos/Nortropic Runtime/.runtime/ap11/integrations/veckodrift/.scratch/review-r1/kontor-driftoperation.py:449>), samt rad 514–520.

Perioden skrivs före `result.json`. Vid avbrott däremellan gör befintlig `binding.json` att återupptagningen passerar förfallokontrollen trots `due: false`. Båda kanalerna körs på nytt och periodsekvensen ökas igen.

En minnesbaserad reproduktion med avbrott exakt före slutkvittot gav två driftanrop, `resume_due: false`, `resume_performed: true` och sekvens 1 → 2. Återupptagningen behöver kunna färdigställa kvittot för redan utfört arbete. Det befintliga avbrottsprovet accepterar i stället dubbelkörningen.

Blockerare 5: Påstådda godkända testantal saknar körkvitton

Fil: [docs/decisions.md, rad 1812](</Users/elinhaggstrom/nortropic-repos/Nortropic Runtime/.runtime/ap11/integrations/veckodrift/docs/decisions.md:1812>) och [docs/plan.md, rad 52](</Users/elinhaggstrom/nortropic-repos/Nortropic Runtime/.runtime/ap11/integrations/veckodrift/docs/plan.md:52>).

Texterna påstår att 663 Runtime-prov och 30 kontorsprov passerar. Det angivna kvalificeringskvittot redovisar tre schemaväckningar, men inga sådana svitkörningar, slutstatusar eller överhoppningar. Jag fann inga motsvarande körloggar i granskningsunderlaget. Att kontorsfilen innehåller 30 testmetoder bevisar inte att de passerade. Enligt uppdragets punkt 7 är detta en blockerande evidenslucka.

Anmärkningar som inte självständigt fäller kandidaten

- Runtime-provet jämför mot det hårdkodade talet 245, medan hanteraren deklarerar 239.
- `int()` i `due()` gör att arbetet kan bedömas förfallet mindre än en sekund för tidigt; reproducerat.
- Samma-sekund-provet kräver olika kvittohashar. Identiska mätvärden kan legitimt ge identiska hashvärden, och provet tvingar inte fram en faktisk tidskollision.

Granskningens omfattning

Jag har läst samtliga uppräknade filer, inklusive D038–D040, och verifierat hashbindningen för hanteraren, operationsindatan och båda DRIFT-kvittona. Inga filer eller driftinställningar ändrades.

Hela testsviten och motorprovet kördes inte om. Git-kontroller och commitmeddelanden kunde inte verifieras med granskarens filåtkomst. Produktion, aktivering och verklig macOS-sömn prövades inte.
