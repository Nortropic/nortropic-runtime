# Granskningsrunda 7 — DOM: UNDERKÄND (ORÄTGÄRDAD, arbetet pausat)

Oberoende granskning 2026-09-29 av kandidaterna Runtime `18a3171` och kontoret `e15ad76`.
Granskare: Codex `gpt-6-astra`, läsrätt utan nät, 239 s, 40 egna kommandon.

**Ingen av dessa fem blockerare är rättad.** Ägaren beslutade 2026-09-29 ca 20:0xZ att runda 7
skulle avgöra: godkänd betydde integrera och leverera, underkänd betydde pausa tills en riktig
kund är på väg. Den underkände. Domen är därför en öppen arbetslista, inte en historik.

Två av blockerarna (nr 5) var dokumentationsfel och är rättade på plats, eftersom ett osant tal
i ett kvitto inte får stå kvar: `overdue_seconds` var 3619 i denna rundas kvitto och inte 3620,
och en kvarlämnad mening i planen sa att processgruppsfelet föll i en kandidatkörning när de tre
kandidatkvittona visar noll. Övriga fyra blockerare och anmärkningen står öppna.

**Granskarens viktigaste mening för omstarten**, i blockerare 4: "Det finns ingen generell
lösning som både undviker omläsning och säkerställer utförande när utfallet saknar beständigt
bevis." Det stämmer med ägarens eget förslag — hellre en körning för mycket än exakt en gång —
och det är den vägen en omstart bör ta i stället för att bygga vidare på den här mekaniken.

---

DOM: UNDERKÄND

Blockerare 1: Blandad återupptagning kan fortfarande göra incidentkvittot grönt

Fil: [kontor-driftoperation.py:774](</Users/elinhaggstrom/nortropic-repos/Nortropic Runtime/.runtime/ap11/integrations/veckodrift/.scratch/review-r7/kontor-driftoperation.py:774>), även rad 691 och 744.

Återläsningen av körningens eget utfall för en redan stängd period sker bara när inga kanaler behöver köras. Den andra utgången använder `commit_settled()`, som ignorerar `outcome`.

Reproducerat i minnet: driftkontrollen fann en incident och stängde perioden; körningen avbröts före monitorn. Återupptagning med samma kör-ID och lyckad monitor gav `completed: true` och tomma `settled_channels`, trots att resultatets egen `periods.drift.outcome` innehöll `healthy: false` för samma körning. Driftkontrollen anropades bara en gång. Incidentutfallet måste påverka båda utgångarna.

Blockerare 2: Saknat utfallsunderlag efter periodstängningen tolkas som framgång

Fil: [kontor-driftoperation.py:659](</Users/elinhaggstrom/nortropic-repos/Nortropic Runtime/.runtime/ap11/integrations/veckodrift/.scratch/review-r7/kontor-driftoperation.py:659>), samt rad 744–765.

När perioden är stängd men utfallsposten saknas blir `mine` tom. Återupptagningen skriver då ett grönt slutkvitto för den tidigare körningen.

Reproducerat: efter en incidentkörning togs dess slutkvitto och `settled-drift.json` bort ur minnesfixturen. Samma kör-ID svarade `completed: true`, `skipped: not_due`, utan observation eller ny kontroll. Periodkvittot fanns kvar. Detta motsäger uttryckligen dokumentationens löfte att saknat utfall aldrig betyder friskt. Karantän av en trasig utfallspost lämnar samma beslutsläge.

Blockerare 3: Monitorn kan stänga veckan utan något HTTP-svar

Fil: [kontor-driftoperation.py:234](</Users/elinhaggstrom/nortropic-repos/Nortropic Runtime/.runtime/ap11/integrations/veckodrift/.scratch/review-r7/kontor-driftoperation.py:234>), samt rad 854.

Undantagsgrenen sätter `observed: true` för alla `ValueError`, `TypeError` och `AttributeError` inom hela försöket, även före ett svar.

Reproducerat med verklig urllib-kod: `https://example.invalid/å` passerade staging men gav ett lokalt kodningsfel före anslutningen. Resultatet blev ändå `observed: true`, `performed: true` och stängd period vid sekvens 1. Nästa väckning svarade `not_due`. Antalet anslutningsanrop var noll. Lokala begärandefel får inte räknas som mottagna hälsosvar.

Blockerare 4: Avvägningen är rimlig men beskriven med garantier som saknas

Filer: [D040:1875](</Users/elinhaggstrom/nortropic-repos/Nortropic Runtime/.runtime/ap11/integrations/veckodrift/docs/decisions.md:1875>), [LAS-FORST.md:14](</Users/elinhaggstrom/nortropic-repos/Nortropic Runtime/.runtime/ap11/integrations/veckodrift/evidence/runs/runtime-veckodrift-7/LAS-FORST.md:14>) och [kontor-driftoperation.py:858](</Users/elinhaggstrom/nortropic-repos/Nortropic Runtime/.runtime/ap11/integrations/veckodrift/.scratch/review-r7/kontor-driftoperation.py:858>).

Att försöka igen när utfallet verkligen är okänt är rimligt. Men ”exakt en gång” och kostnaden ”en extra läsning” är inte garanterade.

Reproducerat: två avbrott före `settle_outcome()` följt av ett lyckat försök gav tre driftanrop inom samma period. Kvittot redovisade endast `retried_after_interruption: ['drift']`; markören hade skrivits över. Även ett normalt avslutat timeoutförsök gav samma avbrottsetikett vid nästa väckning.

Avvägningen behöver beskrivas som upprepade försök tills utfallet bokförts, med korrekt historik och omfattning. Den gäller också intaget, vars omförsök kan upprepa den tillåtna Kundstart-kvittensen. Påståendet att inget skrivs hos någon leverantör är därför för brett.

Det finns ingen generell lösning som både undviker omläsning och säkerställer utförande när utfallet saknar beständigt bevis. Befintliga verifierbara verktygskvitton kan däremot återanvändas i vissa avbrottslägen.

Blockerare 5: Två aktuella sifferpåståenden motsäger kvittona

Filer: [docs/plan.md:140](</Users/elinhaggstrom/nortropic-repos/Nortropic Runtime/.runtime/ap11/integrations/veckodrift/docs/plan.md:140>) och [LAS-FORST.md:75](</Users/elinhaggstrom/nortropic-repos/Nortropic Runtime/.runtime/ap11/integrations/veckodrift/evidence/runs/runtime-veckodrift-7/LAS-FORST.md:75>).

Planen anger processgruppsfel i en kandidatkörning. De tre kandidatkvittona visar noll; endast baslinjekörning 1 har felet. Planen motsäger dessutom sin egen rad 137.

LAS-FORST och planens rad 124 anger `overdue_seconds` 3620. RESULTAT.json anger 3619. Enligt uppdragets uttryckliga evidenskrav är dessa blockerande dokumentationsfel. Antalen 676/656, 584/509, ökningen 20/75 och fördelningen 85 körningar över 61 metodnamn stämmer däremot.

Anmärkning som inte självständigt fäller kandidaten

[install_ap10.py:148](</Users/elinhaggstrom/nortropic-repos/Nortropic Runtime/.runtime/ap11/integrations/veckodrift/scripts/install_ap10.py:148>) använder fortfarande `str()` vid hashvalideringen. Reproducerat: 64-siffriga heltal accepteras som `python_sha256` och `plan_sha256`, trots att de aldrig kan motsvara hanterarens strängdigest. Inga ytterligare skuggade namn hittades.

Granskningens omfattning

Samtliga uppräknade filer är lästa, inklusive tidigare domar och D038–D040. Hashbindningarna för hanteraren, operationsindatan, Digitala-verktygen och DRIFT-kvittona stämmer. Sex riktade monitor- och trådregisterprov passerade. Ägarbeslutet täcker kvittensen; ingen ytterligare API-skrivning hittades i den anropade konsumentvägen.

Inga filer eller driftinställningar ändrades. Motproven använde minnestillstånd och spärrad eller simulerad transport. Helsviterna och motorprovet kördes inte om. Git- och processkontroller blockerades av åtkomsten. Produktion, aktivering och faktisk macOS-sömn prövades inte.
