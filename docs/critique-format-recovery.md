# Avgränsad formåterhämtning av kritik

`runtime.web_critique` kan återhämta ett komplett `StructuredOutput`-försök som
leverantören avvisade på en uttryckligt vald prosalängd, varefter körningen nådde
tidsgränsen utan terminal. Det gamla försöket är fortsatt misslyckat; en init eller
ett verktygsanrop räknas aldrig om till en leverantörsterminal.

Ordinarie profil tar `--aterhamta GAMMAL-RUN --formfalt summary --formtid 180`
tillsammans med **exakt gamla** `--underlag`, `--fraga`, `--schema`, modell och
utförare samt en ny etikett. `--formtid` gäller separat för vardera två små
textsessioner, inte en förlängning av den misslyckade granskningen. Ingen automatisk
retry-loop eller implicit full bildgranskning görs. Digitalas `kor_profil.py` är
fortsatt dess ordinarie konsument och måste återbinda den gamla KORNING-posten.

Före modellstart prövas källkvittots hash och alla hashbundna utdata, kopierat och
aktuellt underlags bytes, frågan och det oförändrade schemat. Exakt ett komplett
objekt krävs från en kvalificerad Claude-start med en observerad schemaavvisning.
Samtliga fält valideras; bara maxLength-fel i de uttryckligt valda överlånga
strängarna tillåts. Fel enum, typ, listlängd, bindning enligt schemat eller saknad
egenskap vägras. Originalets lyckade bildresultat kopplas till dess Read-anrop;
enbart anrop eller en deklarerad seen_files-lista räcker inte. Konsumenten prövar
fortfarande faktisk dom, aktuell kandidat, kriterier, räckvidd och bildmanifest.

Första nya native-sessionen får hela råobjektet, fältgränser och enbart de ändringsbara
prosfälten i sitt svarsschema. Värden förenar dess svar med de exakt bevarade övriga
värdena och validerar hela objektet. Den andra, fristående native-sessionen jämför
gammal och ny innebörd: varje förlorad eller ändrad risk, invändning, begränsning,
påstående, källstatus eller räckvidd vägrar återhämtningen. Det är en redovisad
modellbedömning, inte ett mekaniskt bevis på semantisk likvärdighet. Inga nya
bilder läses och ingen ny produktdom beställs.

Den nya körningen bevarar `original-svar.json`, `FORMATERHAMTNING.json`, de två
nya sessionernas egna frågor, scheman, strömmar och resultat. Gamla strömmen och
arbetsytan kopieras byteoförändrade; gammalt kvitto skrivs aldrig över. Dess
tidsgräns, avsaknad av terminal och okända usage ligger kvar i proveniensen.
`session.valid_terminal` är fortsatt false för den ursprungliga bildgranskningen;
de två nya sessionernas kvalificerade terminaler redovisas var för sig. Ett lyckat
formresultat ger vanlig `svar_giltigt` med explicit `format_recovery`; det är inte
liktydigt med professionell `approved`. Misslyckad innebördskontroll lämnar inget
`svar.json`. Den fulla originaltexten sparas, aldrig tyst trunkeras.

Begränsning: den första versionen återhämtar bara den belagda Claude-felvägen.
Flera konkurrerande sakutkast, saknat fullständigt objekt, utebliven bildläsning,
annat schemafel, andra utförare eller ändrat underlag kräver relevant nytt
sakarbete. Ändring av själva bedömningen är aldrig formåterhämtning.

Prov: `NR_HOST_ROOT='/sökväg/Nortropic Runtime' python3 -B -m unittest
scripts.test_critique_format scripts.test_web_profiles -q`. Kontrakterade dubblar
prövar förmedlingen utan kostnad; ett separat verkligt native-prov behövs för den
observerade modellvägen. Rapportera nya textsessioners resursfält separat från
gamla 600,6 sekunder/okänd kostnad och tidigare 45-bildersomtag. Det visar inte
total besparing eller bättre produktomdöme.
