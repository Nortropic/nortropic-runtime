# Granskningsrunda 2 — DOM: UNDERKÄND

Oberoende granskning 2026-09-29 (klar 16:09:11Z) av kandidaterna Runtime `1737f36` och
kontoret `5e313b6`. Granskare: Codex `gpt-6-astra`, resonemang high, Runtimes pinnade
`codex-0.155.1`, läsrätt utan nät, 252 s, 39 egna kommandon. Rundan fick runda 1:s dom med sig
och ombads pröva varje blockerare självständigt.

Domen nedan är granskarens ord ordagrant. Hur varje blockerare besvarades står i D040 och i
`LAS-FORST.md`. Blockerare 3 (kvittensen) avgjordes av ägaren, inte av mig: hans ord och frågan
de svarade på står i kontorets DIGITALA-VECKODRIFT-20260929.

---

DOM: UNDERKÄND

Blockerare 1: Monitorns deadline omfattar fortfarande inte hela HTTP-anropet

Fil: [kontor-driftoperation.py, rad 116](</Users/elinhaggstrom/nortropic-repos/Nortropic Runtime/.runtime/ap11/integrations/veckodrift/.scratch/review-r2/kontor-driftoperation.py:116>).

`opener.open()` väntar på statusrad och headers innan kroppens deadlinekontroll nås. En server kan därför skicka headerbyte med mindre än åtta sekunders mellanrum och överskrida samtliga deklarerade tidsgränser. `read1` rättar inte denna väg.

Reproducerat med den verkliga HTTP-parsern, minnesbaserad transport och simulerad klocka: sju sekunder per byte gav 757 sekunder innan monitorn återvände, mot deklarerade 33. Hanterarens 255 sekunder är därmed inget väggklocketak. Runtime stoppar inte den bakomliggande tråden när städväntan upphör; tillståndslåset kan blockera senare körningar. Det nya provet skickar färdiga headers och missar felet.

Blockerare 2: Återupptagning utför fortfarande en redan stängd period igen

Fil: [kontor-driftoperation.py, rad 436](</Users/elinhaggstrom/nortropic-repos/Nortropic Runtime/.runtime/ap11/integrations/veckodrift/.scratch/review-r2/kontor-driftoperation.py:436>), samt rad 507–522 och 555–561.

`own_period_record` ger `due: true`. Därefter körs intag och drift igen; endast sekvensökningen undviks.

En minnesbaserad reproduktion med avbrott efter periodskrivningen men före `result.json` gav två driftanrop, `resumed_performed: true` och oförändrad sekvens 1. Dubbelarbetet kvarstår alltså. En omkörning inom samma sekund kan dessutom skriva över det första kundkvittot.

[Avbrottsprovet, rad 504](</Users/elinhaggstrom/nortropic-repos/Nortropic Runtime/.runtime/ap11/integrations/veckodrift/.scratch/review-r2/kontor-test_driftoperation.py:504>) kontrollerar sekvensen men inte att kanalerna förblir oanropade vid färdigställandet.

Blockerare 3: Dokumentationsändringen upphäver inte det läsande mandatet

Filer: [kontor-driftoperation.py, rad 202](</Users/elinhaggstrom/nortropic-repos/Nortropic Runtime/.runtime/ap11/integrations/veckodrift/.scratch/review-r2/kontor-driftoperation.py:202>) och [digitala-kundstart.py, rad 937](</Users/elinhaggstrom/nortropic-repos/Nortropic Runtime/.runtime/ap11/integrations/veckodrift/.scratch/review-r2/digitala-kundstart.py:937>).

Den startade konsumenten gör fortfarande `POST /api/intern/arenden/{id}/kvittens` efter import. Det ändrar serverns kvittensläge och strider mot granskningsuppdragets uttryckliga gräns att hämtningen är läsande.

D040 beskriver nu skrivningen sannare, men kandidatens egen beskrivning ger ingen utökad auktoritet. Att konsumenten är oförändrad och skrivningen idempotent ändrar inte detta. Motorprovets tomma signallistor utövar aldrig skrivvägen.

Blockerare 4: Ett påstående om helt grön svit saknar fortfarande kvitto

Fil: [LAS-FORST.md, rad 18](</Users/elinhaggstrom/nortropic-repos/Nortropic Runtime/.runtime/ap11/integrations/veckodrift/evidence/runs/runtime-veckodrift-2/LAS-FORST.md:18>).

Texten påstår att samma kod tidigare under dagen passerade 663/663 prov. Något motsvarande körkvitto finns inte i det granskade underlaget; det bifogade kandidatkvittot visar 663 prov med ett fel.

De fyra redovisade svitutfallen är annars belagda, inklusive samma Chrome-testfel i kandidat och baslinje. Det obelagda gröna resultatet måste ändå tas bort eller styrkas enligt uppdragets uttryckliga evidenskrav.

Anmärkningar som inte självständigt fäller kandidaten

- [install_ap10.py, rad 73](</Users/elinhaggstrom/nortropic-repos/Nortropic Runtime/.runtime/ap11/integrations/veckodrift/scripts/install_ap10.py:73>) validerar bara schemanamn och absolut tillståndssökväg i operationsinnehållet. Reproducerat: både kanalfria indata och `period_seconds: 60` accepteras av installeraren och Runtime-validatorn men vägras av hanteraren. Rundturstestet visar därför filbindning, inte körbar operationskonfiguration.
- Samma-sekund-provet framtvingar fortfarande ingen tidskollision. Runbooken hänvisar dessutom till det ersatta runda-1-kvittot.

Jag har läst samtliga uppräknade filer och runda-1-domen. Framtidsdatum och år 9999 hamnar nu korrekt i karantän i reproduktionen. Hashbindningarna för hanteraren, operationsindatan, båda Digitala-verktygen och båda kundkvittona stämmer.

Inga filer eller driftinställningar ändrades. Helsviterna och motorprovet kördes inte om. Git-kontroller, commitmeddelanden och processlistan kunde inte verifieras med granskarens åtkomst; produktion, aktivering och faktisk macOS-sömn prövades inte.
