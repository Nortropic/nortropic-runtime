# Nortropic Runtime — genomförandeuppdrag till färdig v0.1

**Uppdragsgivare:** Johnny Strand  
**Första kedjedrivare:** Codex med Astra. Claude Code får ta över samma arbete.  
**Projekt:** Nytt privat repo, `Nortropic/nortropic-runtime`.  
**Mandat:** Genomför arbetet stegvis till verifierad Runtime v0.1. Inget fast projekttak i timmar gäller. Delmål är kontrollpunkter, inte krav på en ny startprompt eller rutinmässigt ägargodkännande.

## 1. Syfte och bindande slutmål

Nortropic är ett personligt organisatoriskt operativsystem. Det ska omsätta accepterade uppdrag i professionellt utfört arbete och bevara sambandet **avsikt → underlag → beslut → arbete → verifierat resultat → erfarenhet**.

**Nyttomålet är kognitiv avlastning:** Johnny anger riktning, prioriteringar och befogenheter. Arbetskedjan ska hålla ihop utförandet. Han ska inte behöva minnas arbetsläget, återberätta beslut, förmedla rapporter mellan modeller eller beställa nästa tekniska steg. Detta gäller även utvecklingen av Runtime. Projektets dokumentation och arbetsflöde ska bära den fortsatta samordningen.

**Runtime v0.1 är en verksamhetsneutral uppdragskörare:** den ska genomföra accepterade, avgränsade utvecklingsuppdrag i ett utpekat målrepo med befintliga AI-utförare, bevara sammanhanget över sessions- och utförarbyten och föra godkända resultat till kontrollerad integration inom mandatet — utan att Johnny återberättar projektet eller promptar varje övergång.

Slutacceptansen omfattar följande:

| Förmåga | Observerbart slutvillkor |
|---|---|
| Självständigt genomförande | Ett accepterat, avgränsat utvecklingsuppdrag går från uppdragskälla till användbart, integrerat resultat. Körspåret visar vilka samordningshandlingar motorn utförde utan manuell vidarebefordran eller rutinpromptning. |
| Bestående kontinuitet | En färsk utvecklingssession kan från projektet återfinna syfte, mandat, arbetsrevision, relevanta beslut, resultat, aktuella begränsningar och nästa tillåtna handling. |
| Utbytbart utförande | Samma påbörjade uppdrag fortsätter Codex → Claude Code → Codex, eller omvänt, genom Runtime. Arbetet börjar inte om och försöks-/resurshistoriken försvinner inte. |
| Avbrott och kapacitetsbrist | Ett avbrott före slutrapport hanteras med bevarat arbetsläge. Återstart ger inte konkurrerande skrivare, dubbla publiceringar eller nollställda försöksräknare. Känd kvotbrist ger ett bestående vänteläge, inte täta kända felanrop. |
| Kontrollerad integration | Tillämpliga prov och separat granskning gäller rätt kandidat. Ett underkänt, uteblivet, odömbart, avbrutet eller föråldrat obligatoriskt underlag ger inte godkännande. Kandidaten kan inte själv ändra de godkännandekrav eller rättigheter som bedömer dess pågående försök. |
| Upprepbar användning | Ytterligare ett accepterat, avgränsat uppdrag genomförs via samma arbetsväg utan att grunden byggs om. Installation och körning använder endast uttryckligt valda och dokumenterade beroenden. |

Varje rad binds till åtkomliga körbevis, prövad revision, miljö och angivna begränsningar. Modellsvar, filförekomst och en grön totalsumma ersätter inte dessa bevis. Ett godkänt v0.1 gäller de prövade uppgifterna och förutsättningarna, inte generell eller obegränsad autonomi.

Johnny får signalera ett planerat utförarbyte. Automatisk avläsning av veckokvot och konvertering av leverantörernas interna chatthistorik krävs inte. Dokumenterad projektöverlämning mellan utvecklare och Runtimes eget byte av utförare är två olika förmågor; båda ska provas inom sina respektive sammanhang.

**Avgränsning:** Bygg genomförandegrunden enligt slutvillkoren ovan. Verksamhetsspecifika funktioner hör till respektive målrepo, inte till Runtime. En fullständig organisationsplattform, generell självutveckling och separata dashboardprojekt ingår inte.

### Customer Zero och gränsen mot metodkompetensen

**Projekt- och innovationskontoret är Customer Zero:** Nortropics eget projekt- och innovationsarbete är den första verkliga användningen som ska visa nyttan. Kontoret är en verksamhetsförmåga ovanpå Runtime och använder motorn genom accepterade uppdrag. Detta är en ansvarsfördelning, inte en beställning av en ny tjänst, ett nytt repo eller en färdig kontorsprodukt före Runtime.

| Ansvar | Hemvist |
|---|---|
| Förstå behovet, välja professionell metod, formulera tillämpliga kvalitetskrav och bedöma resultatets betydelse | Projekt- och innovationsfunktionen och relevant fackkompetens, inom uppdragsgivarens mandat. |
| Starta tillåtna arbetssteg, bevara arbetsläge, hantera utförarbyte/avbrott och verkställa verifierings- och integrationsvillkor | Runtime enligt slutvillkoren ovan. |
| Instruktioner, exempel och verktyg för en viss metod | Uppdragsanknutet underlag eller ett återanvändbart metodpaket som utföraren läser vid behov, inte hårdkodad verksamhetslogik i motorn. |

Integrationen använder den befintliga uppdragsvägen: **önskat resultat, relevant underlag, metod vid behov, tillåtna handlingar och acceptanskrav in; kandidat, körresultat, begränsningar och fortsatt arbetsläge tillbaka.** Inför inte ett extra schema, statusregister eller en andra orkestrerare för denna ansvarsfördelning. Metodinstruktioner ger inga nya rättigheter och får inte ändra de godkännandekrav som bedömer ett pågående försök.

För v0.1 används ett litet verkligt utvecklingsuppdrag ur denna användning enligt §5F. Om kontoret ännu saknar egen implementation kan uppdraget hämtas ur det egna Runtime-utvecklingsarbetet. Fullständig idéhantering, portföljstyrning, metodbibliotek och autonom metodutveckling är inte förutsättningar för v0.1. Det tidiga motorprovet i §5B kan fortfarande använda en ofarlig fixtur.

## 2. Självständighet, rättigheter och verkliga hinder

Driv planering, källkontroll, implementation, tester, separat granskning, dokumentation och bevarande till slutmålet. Efter ett uppfyllt delmål uppdaterar du planen och går vidare inom mandatet. Stanna inte vid en plan, installerad motor eller etapprapport för att fråga om du ska fortsätta.

Du får etablera det nya privata repot och avgränsade testytor, använda befintliga godkända verktyg och abonnemang samt bevara arbetet och genomföra granskade integrationer i detta projekt och uttryckligt tillåtna målrepon. Kontrollera faktisk åtkomst och konfiguration; uppdraget upphäver inte verktygspolicy eller serverregler. Kör inga automatiska produktionsändringar eller ändringar utanför de uttryckligt tillåtna mål- och testmiljöerna.

Nya abonnemang, credits, API-debitering, betaltjänster, utökad extern behörighet eller ändrat produktlöfte kräver Johnnys beslut. Kontrollera betalningsvägen före modellkörning. Använd tillgängliga resursmått och redovisa luckor; hitta inte på ett tim-, token- eller veckokvotstak som ägarkrav. Ett senare uttryckligt ägarbestämt resurstak gäller tills ägaren ändrar det.

Ett tekniskt problem inom mandatet hanteras av dig, inte genom att Johnny hämtar en ny prompt. Vid ett verkligt externt hinder bevarar du läget, fortsätter säkert oberoende arbete när sådant finns och lämnar en koncentrerad fråga med underlag, rekommendation och exakt saknad åtkomst eller befogenhet. Utan tillgänglig kapacitet väntar arbetet säkert; väntan är inte godkännande eller avslut.

Symphony är första motorkandidat, inte målet. En begränsad teknisk omplanering som bevarar omfattning, säkerhetskrav och kostnads-/rättighetsnivå ligger inom mandatet och dokumenteras. Om kandidaten kräver ett nytt generellt motorbygge ska du inte fortsätta lägga lager runt den. Belägg hindret och välj en mindre återanvändningsväg inom mandatet; ett större arkitektur-, kostnads- eller ambitionsbyte tas direkt med Johnny. En avvisad kandidat betyder inte automatiskt att projektet avslutas.

## 3. Ren projektstart och gemensam instruktioningång

Kontrollera reponamn och lokal katalog innan skapande. Överskriv inte ett befintligt repo. Skapa egen Git-historik och verifiera privat synlighet och rätt origin. Lämna andra projekt, deras arbetsmaterial och processer orörda.

**Behovsstyrd återanvändning av tekniskt arbete och evidens:** Codex, eller den utförare som tar över, ansvarar för att bedöma vad från tidigare trust kernel/bootstrap-försök som kan förenkla ett konkret Runtime-steg. Johnny ska inte behöva hitta, välja eller kvalitetsbedöma materialet, och bedömningen ska inte hänvisas tillbaka till ChatGPT. När behovet uppstår, undersök avgränsat relevant material där det kan minska nybyggande, felsökning eller osäkerhet. Gör ingen fullständig inventering före starten.

Återanvändning omfattar mer än allmänna lärdomar:
- **Kod och verktyg:** avgränsade komponenter, skript och hjälpfunktioner.
- **Körbara prov:** positiva och negativa testfall, reproducerare, fixturer och testdata.
- **Körevidens:** råloggar, kommandon, utfall, kandidat-/testrevisioner, miljöuppgifter och bevarade artefakter.
- **Granskningsunderlag:** konkreta fynd, motexempel och dokumenterade resultat från prövade eller förkastade angreppssätt.

**Bedöm delarna på sina egna meriter.** Att helhetsleveransen inte blev färdig gör inte all dess evidens eller kod oanvändbar. Omvänt bevisar omfattande dokumentation, höga testantal, strikt formalia eller tidigare beröm inte att en del är korrekt eller lämplig. Ett användbart felprov kan följa med även när den gamla implementationen lämnas kvar. Pröva den nödvändiga egenskapen, inte historiska filnamn, interna steg eller hela den gamla arkitekturen.

För material som används: fastställ vad det faktiskt visar, vilken revision, miljö och provomfattning det gäller samt kända fel och begränsningar. Skilj råa körresultat från sammanfattningar och modellbedömningar. Gammalt PASS godkänner inte Runtime automatiskt, och gammalt FAIL gör inte en ny lösning omöjlig. Återanvänd fortfarande relevant underlag; verifiera riktat de ändrade förutsättningarna och den nya kopplingen. Kör inte om hela den gamla kvalificeringen slentrianmässigt. Saknat eller otillgängligt underlag redovisas, inte gissas fram.

Lämna original och evidensytor orörda. Granska äldre skripts åtkomst, hookar och sidoeffekter innan eventuell körning; prova utvalt material i isolerad kopia. Ta endast in komponenter vars nytta, beroenden och beteende i Runtime är kontrollerade och som förenklar lösningen. Dokumentera kort **behov → källa/revision → vad som återanvänds → begränsningar → aktuellt prov/resultat** i befintlig `docs/decisions.md`, med hänvisning från berört plansteg.

Ingen massimport, obligatorisk återanvändning, separat arkivplattform eller återbruksetapp före motorprovet. Tidigare planer, instruktioner, befogenheter och godkännanden blir inte bindande i det nya projektet. Återbruket ska minska vägen till v0.1, inte återskapa det gamla projektets omfattning.

**Använd `AGENTS.md` i reporoten som enda gemensamma projektinstruktion som standard.** Den ska kort ange syfte, viktiga gränser, faktiska bygg-/testkommandon och var uppdrag, plan och beslut finns. Kopiera inte hela detta uppdrag, driftläge eller chatthistorik till den. Använd vanliga sökvägshänvisningar för gemensamt underlag; förutsätt inte att alla verktyg tolkar importsyntax likadant.

### Claude Code och Codex: verifiera den faktiska inläsningen

Anthropics changelog anger direktstöd för `AGENTS.md` från **Claude Code 2.1.277, den 18 september 2026**. [S1] Enligt manualen påverkar bland annat överordnade `CLAUDE.md`/`CLAUDE.local.md`, Project instructions-inställningen, feature flags och hookpolicy om stödet används. Första sessionen efter uppgradering kan sakna stödet. Direktläst `AGENTS.md` visas inte i `/context` och utlöser inte `InstructionsLoaded`. [S2]

Kontrollera version och inlästa instruktioner i den startprofil som faktiskt ska användas, från reporot och relevant underkatalog. Använd dokumenterad inläsningssignal och ett ofarligt prov där en färsk session återger en unik uppgift ur ingången utan att svaret ges i prompten. Det visar tillgänglig kontext, inte efterlevnad i allt arbete.

Behåll giltiga globala säkerhetsregler. Aktivera inte telemetri eller försvaga hookpolicy för att få direktstödet att fungera. Saknas det används vid behov en minimal `CLAUDE.md` med importen `@AGENTS.md`, prövad i den faktiska miljön. Ingen handunderhållen kopia eller egen synkroniseringsmekanism. [S2] För Codex kontrolleras även globala/nästlade instruktioner och `AGENTS.override.md`; gemensamma projektregler ska inte gömmas i verktygsspecifika overrides. [S3]

Kontrollera relevanta inställningar, autentisering och åtkomst även för icke-interaktiva och underordnade körningar. Att modellen fungerar interaktivt visar inte att samma modell fungerar genom motorns programgränssnitt. Ändra inte andra projekts konfiguration för att ordna denna körprofil.

## 4. En arbetsplan som går att fortsätta från

Använd principen bakom OpenAI:s ExecPlans: den aktuella planen ska räcka för en ny utförare, uppdateras med resultat och leda till nästa handling. [S4] Gör inga parallella planer och kopiera inte hela en extern mall.

| Innehåll | Hemvist |
|---|---|
| Uppdrag, mandat och v0.1-slutmål | Denna fil, sparad en gång i projektet. |
| Aktuellt utvecklingssteg, nästa handling och återupptagningspunkt | `docs/plan.md`. |
| Betydelsefulla tekniska beslut och vad de ersätter | `docs/decisions.md`, korta poster. |
| Kod och bevis | Git-kandidat, PR och beständigt åtkomliga körresultat, länkade från planen. |

`README.md` hjälper en människa att starta och hitta rätt. `AGENTS.md` hjälper utförarna att hitta samma underlag. De bär inte egna kopior av plan och status. En tracker kan äga status för ett runtimeuppdrag; utvecklingsplanen länkar dit i stället för att konkurrera med den. Bestående runtimeuppgifter ska inte ersättas av modellredigerad prosa.

Arbeta med **en liten leverans åt gången**. Skriv närmaste steg konkret och senare steg översiktligt. Följande korta struktur räcker i planen:

```text
RESULTAT: Efter steget kan arbetskedjan ...
VARFÖR NU: Det undanröjer ... / prövar antagandet ...
METOD VID BEHOV: Tillvägagångssätt, varför det passar och relevant källstöd.
ARBETSYTA: Repo, katalog, gren och revision.
FÖRUTSÄTTNINGAR: Vad som måste finnas; källor och redan giltiga bevis.
NÄSTA HANDLING: Konkret åtgärd/kommando, arbetskatalog och väntat utfall.
PROV OCH KLART-NÄR: Positivt beteende och relevant negativt fall.
UTFALL: Ej kört / underkänt / odömbart / godkänt; länkar till faktiska bevis.
ÅTERUPPTAGNING: Bevarat arbete, pågående processer, försöksläge och nästa steg.
```

Skilj **beslutat, implementerat, verifierat och integrerat**. Ett resultat måste finnas där nästa steg använder det. Kod, berörda instruktioner och resultatbeskrivning ska stämma överens. Bevara arbetssteg löpande på rätt remote; säkerhetskopiering är inte godkännande. Verifiera att push lyckats och lämna inte unikt arbete bara i scratchpad eller tillfälliga kataloger. Integrera små färdiga leveranser efter relevanta kontroller i stället för att stapla fler beroende grenar.

När ett antagande faller uppdaterar du det berörda steget med orsak och ny väg. Parkera orelaterade förbättringar. Återanvänd belagda beslut och resultat; utred på nytt när relevanta förutsättningar har ändrats. Efter delresultat rapporterar du kort vad arbetskedjan nu kan göra, kvarvarande hinder och nästa handling, och fortsätter inom mandatet.

### Professionell praxis genom hela arbetet

Välj och anpassa etablerade tillvägagångssätt efter arbetets natur, osäkerhet, risk och önskat resultat: behovsförståelse, krav, alternativanalys, tekniska experiment, design, implementation, felsökning, verifiering, integration och uppföljning. Använd relevant litteratur, primärkällor och officiella versionsaktuella manualer där de påverkar ett beslut. OpenAI:s och Anthropics agentpraxis kompletterar yrkeskunskapen; den ersätter den inte. [S4–S7]

Anpassa både det övergripande arbetssättet och metoden för nästa steg. En känd bugg behöver normalt reproduktion, avgränsad diagnos och regressionstest — inte en ny discoveryprocess. En osäker integration behöver ett avgörande kompatibilitetsprov före större bygge. En bedömning mellan alternativ behöver jämförbara kriterier, inte ett på förhand valt svar. Dokumentera bara betydelsefulla metodval, nödvändigt underlag och tillräckligt resultat i det befintliga plansteget. Vanliga rutinval kräver ingen separat metodrapport, inget extra modellanrop och ingen ägarapproval.

**Double Diamond och autoresearch är exempel, inte universella processer eller motorberoenden.** Använd en enkel arbetsbeskrivning, mall eller befintlig skill när det räcker. Skapa ett återanvändbart metodpaket först när ett konkret behov motiverar det; bygg inget komplett metodkontor, ingen automatisk metodväljare och ingen separat forskningsmotor för att komma igång. En ny metod ska normalt kunna användas som uppdragsinnehåll utan ändring i Runtimes styrlogik. [S6–S8]

Om ett autoresearch-liknande experiment passar uppgiften: ange frågan och baslinjen, tillåten förändringsyta, jämförbara körförutsättningar, bedömning och vad som räcker för nästa beslut. Håll kontrollunderlaget utanför kandidatens ändringsrätt. Bevara även negativa resultat och relevanta artefakter. Ett förkastat antagande kan vara ett lyckat undersökningsresultat; en krasch eller saknad mätning är inte en förbättring, och en lovande experimentvariant är inte automatiskt godkänd för integration. Bekräfta förbättringar proportionerligt när brus eller anpassning till provfallen kan påverka slutsatsen. Ta inte över en källas oändliga loop, fasta femminutersbudget, oskyddade rättigheter eller destruktiva återställningar som projektpolicy. Det accepterade uppdragets klart-när gäller. [S5, S8]

Uttryck om underlaget kommer från faktisk observation, tillhandahållen källa, analys eller modellgenererad hypotes. En metodrubrik bevisar inte att metoden använts, och ett experiment ersätter inte en implementationsleverans. Att ändra metoden eller dess bedömningskriterier är ett separat, motiverat ändringssteg enligt det befintliga mandatet — inte något kandidaten får göra för att godkänna sig själv.

## 5. Genomförande i prövbara leveranser

Stegen nedan är en sammanhängande väg till v0.1, inte separata uppdrag som kräver nytt ägarmandat. Förfina ordningen utifrån verifierade beroenden utan att ändra slutmålet. Koppla varje ny förmåga till den fungerande lilla arbetskedjan direkt; bygg inte alla komponenter först och helheten sist.

### A. Etablera projekt och körväg

Skapa projektet enligt §3–4. Läs relevanta primärkällor och installations-/lifecycle-hookar. Välj en bestämd revision av befintlig Symphony, kontrollera den verkliga uppdragsadaptern, Codex-kopplingen, körmiljön och betalningsvägen. Välj minsta fungerande uppdragskälla och konfigurera uttryckligt accepterade testärenden samt en aktiv skrivande körning åt gången.

**Klart när:** rätt projekt, instruktioner, isolerad arbetsyta och faktisk körväg är identifierade och provbara. Installation ensam är inte en autonom leverans. Starten ska vara reproducerbar med de uttryckligt valda och dokumenterade beroendena.

### B. Visa både ett arbetsresultat och motorns nytta

Definiera före körning vilken samordningshandling motorn ska ta över, exempelvis att hitta ett accepterat ärende, starta rätt utförare, bevara resultatet och föra det till nästa tillåtna läge. Beskriv vilka manuella handlingar som annars behövts; ett extra stort jämförande benchmark krävs inte.

Välj en liten uppgift på en ofarlig testyta, exempelvis filbearbetning med kända indata och förväntade utdata. Ange tillåtna ändringar och acceptans före implementation. Låt befintlig Symphony använda Codex. Bygg inte om `SPEC.md` och inför ingen andra orkestrerare.

Mät vad motorn faktiskt gjorde, vad agenten gjorde och vad kedjedrivaren eller Johnny fick göra utanför flödet. En manuellt startad agent som löser uppgiften bevisar inte automatisk samordning. Behåll resultatspår och prova ett kontrollerat fel eller avbrott enligt §6.

**Klart när:** motorn driver det definierade uppdragsflödet till ett prövat, bevarat resultat och samordningseffekten kan beläggas. Ett stopp på grund av saknad åtkomst är ett hinder, inte ett godkänt motorprov. Fortsätt därefter till nästa nödvändiga steg.

### C. Anslut Claude till samma väg

Använd leverantörens officiella programgränssnitt och motorns avgränsade anslutningspunkt. Kontrollera uppdragsåtkomst, resultat, stopp och verktyg — inte bara att Claude svarar på en prompt. Kör samma typ av liten uppgift genom Claude-vägen.

**Klart när:** båda utförarna genomför ett uppdrag genom samma yttre väg med begriplig resultat- och felhantering. Direkt stöd för `AGENTS.md` är inte i sig en Symphony-adapter. Om anslutningen blir ett nytt generellt motorbygge omprövar du komponentvalet enligt §2.

### D. Visa fortsatt arbete över byte och avbrott

Låt ett påbörjat uppdrag fortsätta mellan utförarna enligt §8. Bevara uppdrag, relevanta beslut, arbetsartefakter, försöksräknare och aktuella återhämtningsvillkor utanför den tillfälliga agentprocessen. Återanvänd befintlig beständig lagring när den räcker; bygg inte ett allmänt minnessystem.

**Klart när:** verkligt utförarbyte i båda riktningarna och kontrollerad omstart fungerar i arbetskedjan utan återberättelse, borttappat bevarat arbete, dubbla skrivare eller återställda försöksgränser. En läst README räcker inte. Fortsätt med samma kedja.

### E. Slut den kontrollerade integrationsvägen

Koppla tillämpliga tester, separat granskning och integration till den exakta kandidaten. Återanvänd motorns och GitHubs relevanta funktioner i stället för att anta att en egen publiceringsplattform behövs. Kandidatarbete och godkännande/publiceringsbehörighet ska vara åtskilda enligt den valda, prövade rättighetsmodellen. Kontrollera serverns verkliga villkor; lokala stubbar eller ett checknamn bevisar inte serverbeteende.

**Klart när:** en legitim kandidat når integration utan rutinmässig ägarapproval, medan ett relevant fel eller uteblivet obligatoriskt bevis hindrar integrationen. Ny kandidat får inte ärva fel granskningsresultat. Vid ett oklart publiceringsutfall kontrolleras verkligt PR-/remote-läge före omförsök.

### F. Leverera och upprepa

Genomför ett litet, verkligt, accepterat utvecklingsuppdrag med utförarbyte för Customer Zero enligt §1. Välj ett faktiskt behov i Nortropics eget projekt- och utvecklingsarbete, i detta projekt eller ett uttryckligt tillåtet målrepo. Finns ingen lämplig arbetsorder kan du formulera ett konkret utvecklingsuppdrag inom Runtime-mandatet med användbart slutresultat och i förväg definierad acceptans. Ett extra demonstrationsdokument eller ett påhittat behov räcker inte som verklig nytta. Använd proportionerlig metod enligt §4; bygg inte hela Projekt- och innovationskontoret som del av provet. Det tidigare motorprovet ersätter inte denna användningsprövning.

Genomför därefter ytterligare ett accepterat uppdrag genom samma väg, med den metod uppgiften behöver. Återanvänd samma generiska integration; ett nytt arbetssätt ska inte i sig kräva ett nytt motorbygge. Ange hur mycket manuell samordning som faktiskt krävdes, skilt från giltiga beslut om mandat eller åtkomst. Begär ingen separat dagbok av Johnny och gör inga påståenden om medicinsk effekt.

**Klart när:** samtliga slutvillkor i §1 är uppfyllda och slutredovisningen i §9 är komplett. Nytta kan visas för den prövade användningen; installationen bevisar inte all framtida avlastning.

## 6. Testa rätt beteende och håll granskningen avgränsad

Välj minsta tillräckliga verifiering för den aktuella förändringen. Skriv förväntat observerbart resultat innan utföraren implementerar. Använd deterministiska tester där de räcker och modellbedömning där uppgiften kräver omdöme. Bedöm resultatet och relevanta sidoeffekter, inte bara agentens sluttext eller en obligatorisk intern arbetssekvens. [S5]

Behåll kontrollunderlaget utanför kandidatens fria skrivbehörighet. Nya prov får avslöja tidigare missade fel i samma krav; de får inte tyst göra nya produktönskemål obligatoriska. Nödvändiga rättningar av felaktiga prov ska motiveras mot kravet och granskas separat från den kandidat de bedömer. Rätt test får inte försvagas för att få grönt.

Bygg följande prov när respektive förmåga kopplas in, inte som en stor testplattform före motorstart:

| Prov | Vad som måste observeras |
|---|---|
| Legitim lösning | Rätt ändring accepteras och når avsedd resultatplats. En mekanism som stoppar allt är inte korrekt. |
| Felaktig lösning eller uteblivet prov | Felet/frånvaron syns; obligatoriskt godkännande och integration uteblir. |
| Kvot-/autentiseringsfel | Rätt vänteläge och ingen upprepad känd felstorm; arbetet finns kvar. |
| Byte eller processavbrott | Nästa utförare fortsätter samma arbete med bevarade artefakter och försöksuppgifter. |
| Ny eller fel kandidat | Gammal review eller felbundna prov godkänner inte det nya subjektet. |
| Osäkert integrationsutfall | Faktiskt server-/Git-läge klarläggs före omförsök; inte dubbla handlingar. |

Använd isolerade fixturer för felprov och verkliga begränsade integrationer för integrationspåståenden. Kontrollera bevarande före terminalstatus och städning. Kör inte okänd kod med produktionshemligheter eller bred åtkomst till arbetsmaskinen. Återanvänd giltiga bevis när orelaterade saker ändras; inventera inte hela historiken igen.

**Separat granskning:** en annan agentprocess/kontext läser den relevanta kandidaten och dess krav utan att vara författaren. Den får inte publicera, ändra godkännandeunderlaget eller påverka den riktiga kandidatytan; nödvändiga mutationer görs i ofarliga kopior. Separat kontext ger ytterligare granskning, inte automatiskt en teknisk säkerhetsgräns.

Ett blockerande fynd ska ange **tillämpligt krav → konkret underlag/reproduktion → konsekvens**. Smakfrågor, önskvärd framtida härdning och orelaterade förbättringar parkeras som rådgivande. Risker som faktiskt bryter gällande säkerhets- eller acceptanskrav får inte döljas som rådgivande för att spara resurser. Föreskriv inte dubbla fullständiga modellgranskningar av samma oförändrade kandidat. Efter rättning prövas fyndet och berörd regression; helhetsgranskning görs när förändringens risk motiverar det, inte som tom ritual.

## 7. Fortsätt till målet utan blinda upprepningar

**Projektets slut styrs av §1, inte av en klocka eller ett godtyckligt antal granskningsvarv.** Samtidigt ska en hängd process eller en automatisk fel-loop kunna begränsas. Dessa skydd gäller körningar och återhämtning, inte ett automatiskt avslut av Runtime-projektet. Principen att begränsa agenters enskilda körningar finns även i Anthropics vägledning. [S6]

Före modellkörning väljer kedjedrivaren konkreta, motiverade värden för det aktuella försöket: vad som räknas som aktivitet/framsteg, när en hängd körning avbryts, hur många automatiska omförsök som är tillåtna och när nästa återkontroll av extern kapacitet får ske. Använd befintliga inställningar/standardverktyg. Skilj turngräns, försöksgräns och faktiskt kostnadstak; påstå inte att ett värde täcker de andra.

När en körgräns nås bevaras arbetet och samma blinda repetition upphör. Gör en avgränsad diagnos och välj nästa säkra åtgärd inom mandatet. Ett nytt försök ska ange vad som ändrats eller vilken ny evidens som motiverar det. Anpassa lokala tekniska gränser endast med motivering; historiken består. Höj inte gränser automatiskt eller döp om samma försök för att fortsätta oförändrat. Ett faktiskt ägarbestämt ekonomiskt tak får du inte höja.

Första lilla modellkörningen ska ge synliga tillgängliga användningsmått och en bedömning av nödvändig förbrukning före större körning. Okända mått markeras okända. Optimera genom att undvika tomma återförsök, onödig kontext och omgranskning, inte genom att hoppa över nödvändiga tester. Bygg ingen ny budgetplattform bara för projektledning.

## 8. Dokumenterad överlämning utan återberättelse

Bevara på meningsfulla delsteg. Återupptagningspunkten ska ange faktisk repo-/gren-/kandidatidentitet, bevarade ändringar, åtkomliga bevis, giltiga beslut, aktuellt försök, resurs-/kapacitetsläge, kvarvarande processer och exakt nästa handling. Nödvändigt underlag får inte finnas enbart i chatt, privat modellminne, scratchpad eller `/tmp`.

När Johnny säger **”usage börjar ta slut”**, **”förbered handover”** eller motsvarande: öppna inget nytt större steg. Nå en säker brytpunkt eller bevara arbetet som ofärdigt. Kontrollera vad mottagaren faktiskt kan nå. Lämna en kort hänvisning till projektets återupptagningspunkt, inte en ny masterprompt.

Mottagaren börjar utan skrivningar: läser `AGENTS.md`, uppdraget, aktuellt plansteg och relevanta beslut, och kontrollerar Git, artefakter, åtkomst och processläge. Den säkerställer att föregående skrivare är avslutad eller effektivt avskärmad; en förlorad anslutning är inte bevis för att processen är död. Den bekräftar därefter kort vad den tar över och fortsätter utan rutinmässig ägarfråga.

Överlämning förberedd, mottagen och faktiskt återupptagen är olika lägen. Sessionerna behöver inte vara igång samtidigt. Dokumentationen ger inte credentials. Efter abrupt avbrott används senast bevarat arbete och verifierbara senare fakta, inte antaganden om osparat innehåll.

Pröva tidigt att en verkligt färsk utvecklingssession hittar nästa handling från projektet. Använd en redan behövd överlämning eller granskning när möjligt. Pröva senare Runtimes eget utförarbyte enligt §5D. Att Claude kan ta över utvecklingen kräver inte en färdig Claude-adapter i motorn. Ett prov bara med Codex får inte rapporteras som Claude-stöd.

Känd kvotbrist väntas ut eller hanteras genom redan godkänd och prövad utförarväg. Inga återkommande dyra modellanrop för att upptäcka samma kända stopp. Saknad kapacitet markerar berörda prov EJ KÖRDA och lämnar projektet återupptagningsbart; den avslutar inte uppdraget.

## 9. Slutredovisning och ansvar

Lämna efter varje väsentligt delresultat ett kort besked: **vad arbetskedjan nu kan göra, vilket bevis som stöder det och nästa nödvändiga steg**. Fortsätt utan att invänta ”fortsätt”. Framsteg mäts inte i antal commits, dokument, agenter eller gröna stödtester.

När samtliga slutvillkor är uppfyllda redovisar du:

- levererad revision, motorberoende och faktisk drift-/startkonfiguration;
- en hänvisning till bevis för varje rad i §1, inklusive negativt utfall där det krävs;
- hur systemet startas, används, återupptas och lämnas över;
- kvarvarande begränsningar och vad v0.1 inte bevisar;
- Customer Zero-uppdragen, vald metod där den var betydelsefull, faktisk samordningsavlastning, resursförbrukning och okända mått.

Redovisa Customer Zero-provet som användning av Runtime, inte som acceptans av ett fullständigt projektkontor eller allmän metodkompetens. En avslutad utvecklingsuppgift är inte ett tillstånd att därefter optimera obegränsat. Vidare verksamhetsutveckling kräver ett tillämpligt accepterat uppdrag.

Om ett obligatoriskt villkor ännu saknar bevis är v0.1 inte färdig. Redovisa verkliga hinder utan att gömma dem eller hitta på ett nytt delmål som ser klart ut. Ändra inte omfattningen för att få ett avslut; för ett verkligt ändringsbehov direkt till Johnny. Projektet ska kunna fortsätta från det bevarade läget utan uppdragsgivarens återberättelse.

## Primärkällor för utföraren — läs vid behov

Dessa källor stödjer arbetssättet och versionsberoende kontroller. De ersätter inte uppdraget. Spara bara relevanta tekniska slutsatser, källhänvisning och version i plan eller beslutspost. Ingen ny litteraturstudie före motorprovet. Skilj dokumenterad funktion, eget designval och observerat körresultat.

- **S1 — Claude Code changelog, 2.1.277:** `https://code.claude.com/docs/en/changelog` — release och förutsättningar för direkt AGENTS.md-stöd.
- **S2 — Claude Code, Memory / AGENTS.md:** `https://code.claude.com/docs/en/memory#agentsmd` — direkt inläsning, inställningar, undantag, begränsningar i laddningsindikatorer och import som reservlösning. Kontrollera aktuell manual vid installation.
- **S3 — Codex, Custom instructions with AGENTS.md:** `https://developers.openai.com/codex/guides/agents-md/` — hierarki, overrides och faktisk konfiguration.
- **S4 — OpenAI, Using PLANS.md for multi-hour problem solving:** `https://developers.openai.com/cookbook/articles/codex_exec_plans` — självbärande levande plan, observerbara delresultat och fortsatt arbete. Tillämpas i `docs/plan.md`, inte som en andra planfil.
- **S5 — Anthropic, Demystifying evals for AI agents:** `https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents` — verkliga utfall, ändamålsenliga bedömare och felprov; ingen ny evalplattform beställs.
- **S6 — Anthropic, Building effective agents:** `https://www.anthropic.com/engineering/building-effective-agents` — enkelhet, sammansättbara arbetsflöden och avgränsade agentkörningar.
- **S7 — Yrkesmetoder efter behov:** NASA, Decision Analysis: `https://www.nasa.gov/reference/6-8-decision-analysis/`; GDS, Documenting architecture decisions: `https://gds-way.digital.cabinet-office.gov.uk/standards/architecture-decisions.html`. Exempel på proportionerlig alternativanalys och beslut som följs genom genomförandet; inför inte organisationernas hela processer. Välj andra relevanta primärkällor när uppgiften kräver det.
- **S8 — Karpathy, autoresearch:** `https://github.com/karpathy/autoresearch` — `README.md` och `program.md`; tidigare läst referensrevision `228791fb499afffb54b46200aca536f79142f117`. Källa för ett avgränsat experimentmönster med baslinje och utvärdering, inte ett installationskrav, en allmän workflow eller rätt att kopiera dess behörighets-/fortsättningspolicy. Kontrollera den version som faktiskt används som referens.
- **Symphony:** `https://github.com/openai/symphony` — läs README, relevant specifikation, referensimplementation och kod för den valda revisionen. Skriv inte en ny implementation från specifikationen.
- **Codex programgränssnitt och åtkomst:** `https://developers.openai.com/codex/app-server/`, `https://developers.openai.com/codex/auth/`, `https://developers.openai.com/codex/security/`.
- **Claude Code / Agent SDK:** `https://code.claude.com/docs/en/headless`, `https://platform.claude.com/docs/en/agent-sdk/overview`, `https://code.claude.com/docs/en/agent-sdk/secure-deployment` — befintlig agentloop, sessionsgränssnitt, rättigheter och betalningsväg.
- **Arbetsmiljö och kontext:** `https://openai.com/index/harness-engineering/`, `https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents`, `https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents` — återanvänd relevanta principer och anpassa exemplen till det aktuella uppdraget.

**Börja med att kontrollera projektets faktiska utgångsläge, etablera den korta levande planen och genomför första konkreta steget. Äg fortsättningen till den definierade v0.1-leveransen inom mandatet.**
