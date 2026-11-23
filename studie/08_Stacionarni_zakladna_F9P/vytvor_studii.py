from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Flowable
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4

ROOT = Path(__file__).resolve().parent
OUT = ROOT / '08_Stacionarni_zakladna_F9P_a_spolehlivy_zaznam.pdf'
for name, file in [('Arial','arial.ttf'),('Arial-Bold','arialbd.ttf'),('Arial-Italic','ariali.ttf'),('Arial-BoldItalic','arialbi.ttf')]:
    pdfmetrics.registerFont(TTFont(name, 'C:/Windows/Fonts/' + file))
pdfmetrics.registerFontFamily('Arial', normal='Arial', bold='Arial-Bold', italic='Arial-Italic', boldItalic='Arial-BoldItalic')
INK = colors.HexColor('#182735')
TEAL = colors.HexColor('#007F82')
LIGHT = colors.HexColor('#EDF5F5')
GREY = colors.HexColor('#596875')
AMBER = colors.HexColor('#FFF3DB')
WIDTH = A4[0] - 92
styles = {
    'body': ParagraphStyle('body',fontName='Arial',fontSize=10.2,leading=14.2,textColor=INK,spaceAfter=7),
    'small': ParagraphStyle('small',fontName='Arial',fontSize=8.6,leading=11.5,textColor=GREY,spaceAfter=6),
    'h1': ParagraphStyle('h1',fontName='Arial-Bold',fontSize=23,leading=27,textColor=INK,spaceAfter=14),
    'h2': ParagraphStyle('h2',fontName='Arial-Bold',fontSize=13,leading=17,textColor=TEAL,spaceBefore=10,spaceAfter=7),
    'cell': ParagraphStyle('cell',fontName='Arial',fontSize=9,leading=12,textColor=INK),
    'head': ParagraphStyle('head',fontName='Arial-Bold',fontSize=9,leading=12,textColor=colors.white),
    'label': ParagraphStyle('label',fontName='Arial-Bold',fontSize=9,leading=12,textColor=TEAL,spaceAfter=9),
    'source': ParagraphStyle('source',fontName='Arial',fontSize=9.1,leading=12.5,textColor=INK,spaceAfter=10),
}
story=[]
def p(t, style='body'):
    story.append(Paragraph(t, styles[style]))
def h(t): p(t,'h2')
def page(n,t):
    if story: story.append(PageBreak())
    p('STUDIE 08  /  NÁVRH K OVĚŘENÍ  /  16. 11. 2026','label')
    p(f'{n}. {t}','h1')
def box(t, warn=False):
    tb=Table([[Paragraph(t,styles['body'])]], colWidths=[WIDTH])
    tb.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),AMBER if warn else LIGHT),('BOX',(0,0),(-1,-1),.5,TEAL),('LEFTPADDING',(0,0),(-1,-1),12),('RIGHTPADDING',(0,0),(-1,-1),12),('TOPPADDING',(0,0),(-1,-1),10),('BOTTOMPADDING',(0,0),(-1,-1),4)]))
    story.extend([tb,Spacer(1,9)])
def table(headers,rows,widths):
    data=[[Paragraph(x,styles['head']) for x in headers]]+[[Paragraph(str(x),styles['cell']) for x in row] for row in rows]
    tb=Table(data,colWidths=[WIDTH*x for x in widths],repeatRows=1,hAlign='LEFT')
    tb.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),INK),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,LIGHT]),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7),('LINEBELOW',(0,-1),(-1,-1),.5,TEAL)]))
    story.extend([tb,Spacer(1,9)])

class Scheme(Flowable):
    def __init__(self): Flowable.__init__(self); self.width=WIDTH; self.height=104
    def draw(self):
        c=self.canv
        labels=[('ANTÉNA','na pevném stativu'),('simpleRTK2B','ZED-F9P / raw'),('ESP32','příjem + buffer'),('microSD','binární UBX')]
        bw=110; gap=(WIDTH-4*bw)/3
        for i,(a,b) in enumerate(labels):
            x=i*(bw+gap)
            c.setFillColor(LIGHT);c.setStrokeColor(TEAL);c.roundRect(x,50,bw,44,5,fill=1,stroke=1)
            c.setFillColor(INK);c.setFont('Arial-Bold',9.5);c.drawCentredString(x+bw/2,76,a)
            c.setFont('Arial',8);c.drawCentredString(x+bw/2,61,b)
            if i<3:
                c.line(x+bw,72,x+bw+gap,72);c.line(x+bw+gap-4,75,x+bw+gap,72);c.line(x+bw+gap-4,69,x+bw+gap,72)
        c.setFillColor(INK);c.setFont('Arial',9)
        c.drawCentredString(WIDTH/2,28,'Baterie + ochrany + stabilizace + řízené ukončení zápisu')
        c.setFont('Arial',8);c.setFillColor(GREY)
        c.drawCentredString(WIDTH/2,12,'USB do počítače: konfigurace a nezávislé porovnání při zkouškách')

page(1,'Doporučená základna')
p('<b>Postavit samostatný raw logger k již vybrané desce simpleRTK2B Budget.</b> Základna bude na stativu zaznamenávat vlastní GNSS pozorování po dobu nejméně 15 hodin. Rover mosaic-X5 bude ukládat vlastní měření; obě sady se spojí při následném zpracování PPK. Internet, NTRIP, cizí referenční stanice ani rádiové spojení nejsou podmínkou sběru.')
story.append(Scheme())
table(['Část','Výchozí návrh'],[
    ['Přijímač','Stávající simpleRTK2B Budget. Před konfigurací zjistit označení modulu, revizi desky a UBX-MON-VER. Název desky neurčuje firmware. [1]'],
    ['Logger','ESP32 s PSRAM; pro návaznost na SparkFun prověřit variantu s ESP32-WROVER a 8 MB PSRAM. Konkrétní desku vybrat až podle portu firmwaru a pinů. [6,22]'],
    ['Záznam','UBX-RXM-RAWX, UBX-RXM-SFRBX a vybraná diagnostika. Výchozí cíl základny 10 Hz; ověřit na konkrétním F9P.'],
    ['Úložiště','32GB průmyslová microSD, FAT32; kandidát pSLC Swissbit S-56u. Výběr konkrétního SKU podmínit testem latencí a výpadků. [15]'],
    ['Napájení','Chráněný hotový akumulátorový pack, stabilní napájení, dohled a doběh zápisu. Orientačně třída 90-100 Wh; rozhoduje změřená spotřeba.'],
    ['Mechanika','Pevný stativ, anténa nad elektronikou, odlehčené kabely, uzavřená skříň. Záznam pokračuje bez telefonu i bez sítě.'],
], [.23,.77])
box('<b>„100 %“ převést na ověřitelný požadavek:</b> během stanovených testů nesmí logger ztratit žádnou přijatou raw epochu; každou zjištěnou mezeru musí označit. To není záruka trvalého GNSS signálu, bezporuchové karty ani centimetrové polohy v každé epoše.')
p('Stav dokumentu: rešerše dokumentace a zdrojového kódu, vlastní návrh a plán zkoušek. Hardware nebyl v rámci této rešerše sestaven ani změřen. Studie doplňuje projekt samostatně; není novou kapitolou bakalářky.','small')

page(2,'Zapojení a režim přijímače')
h('Použít UART1 a ponechat USB pro servis')
p('Na Arduino liště spojit TX1 přijímače s RX loggeru, RX1 s TX loggeru a společnou zem. Pro ESP32 nastavit IOREF na 3,3 V. Podle návodu musí být IOREF při tomto zapojení připojen; nastavení přepínače ověřit na vlastní revizi desky. Alternativou je Pixhawk konektor: pin 2 RX1, pin 3 TX1, pin 6 GND, logika 3,3 V. [1]')
p('Desku napájet přes dokumentovaný vstup 5 V / USB. ESP32 a kartu napájet vlastní vhodně dimenzovanou větví ze společného zdroje, nikoli automaticky z pomocného výstupu lišty. Před připojením ověřit orientaci konektoru, zem a napětí. Krátké kabely, pevné konektory; nepoužít nepájivé pole v závodním provozu.')
box('<b>Navržený sériový profil:</b> UART1, 921 600 baud, 8N1; na záznamovém portu UBX. F9P nemá RTS/CTS. Když jeho výstupní buffer přeteče, zprávy se zahodí už v přijímači. USB může mít nezávislý profil a sloužit jako kontrolní větev. [2]')
h('Frekvenci nelze určit jen názvem „F9P“')
table(['Doložená varianta','RAW se čtyřmi hlavními soustavami','Důsledek'],[
    ['ZED-F9P-01B, HPG 1.12','Až 20 Hz podle datasheetu. [4]','20 Hz je kandidát ke zkoušce, ne výchozí slib.'],
    ['ZED-F9P-05B, HPG 1.51','Až 10 Hz podle datasheetu. [3]','Pro vyšší rychlost mění výrobce kombinace soustav; neomezovat je bez porovnání.'],
    ['Uživatelova Budget deska','Sufix a firmware zatím nezjištěny.','Začít 1 Hz, potom 5 a 10 Hz; maximum potvrdit skutečnými epochami.'],
], [.28,.39,.33])
p('Tabulka uvádí konkrétní kombinace výrobku a firmwaru z datasheetů, nikoli vlastnost všech dodaných Budget desek. RAW, výstup polohy PVT a RTK mají rozdílná maxima. [3,4]')
h('Pro čisté PPK není nutné čekat na survey-in')
p('První profil navrhuji jako stacionární sběr raw pozorování bez RTCM vysílání a bez čekání loggeru na „RTK FIX“. Survey-in je odhad polohy používaný při inicializaci referenční stanice; raw data mají vlastní podmínky dostupnosti. Pozici základny a její nejistotu určit a uložit zvlášť pro PPK. Režim TMODE i skutečné tempo RAWX ověřit po startu. [2,3]')
p('PPS lze připojit pro časování diagnostiky loggeru. Pro párování GNSS pozorování jsou určující časové značky v raw zprávách; čas příchodu bajtů po UARTu je nenahrazuje.','small')

page(3,'Jaká data opravdu uchovat')
p('Zachovat původní binární proud <b>.ubx</b>. CSV souřadnic slouží jen k prohlížení: neobsahuje dost informací pro fázové PPK. Převod do RINEX provádět až po měření a originály uchovat. RAWX nese kód, fázi, Doppler i příznaky kvality; SFRBX přijaté navigační zprávy. [3,5]')
table(['Zpráva / soubor','Požadavek tohoto návrhu'],[
    ['UBX-RXM-RAWX','Každá měřicí epocha, cílově 10 Hz. Uložit celý obsah včetně času, identifikátorů signálů, locktime a příznaků platnosti.'],
    ['UBX-RXM-SFRBX','Všechny dostupné zprávy. Jde o události příjmu navigačních dat; nejde o rovnoměrný 10Hz proud.'],
    ['UBX-MON-COMMS','Přibližně 1 Hz pro stav portů a TX bufferu. Oddělit chybové příznaky vysílání přijímače od chyb UARTu loggeru.'],
    ['UBX-MON-RF, NAV-SAT / NAV-SIG','Přibližně 1 Hz pro RF a signálovou diagnostiku; dostupnost a skutečné intervaly podle firmwaru.'],
    ['UBX-NAV-PVT, případně NAV-SVIN','Přibližně 1 Hz pro přehled stavu. SVIN jen při aktivním survey-in. Nenahrazují RAWX.'],
    ['Manifest a deník loggeru','Identita běhu, konfigurace, firmware, časy, baterie, SD chyby, zaplnění bufferů, restarty a zjištěné mezery.'],
], [.36,.64])
p('Význam a dostupnost zpráv ověřit v odpovídající verzi Interface Description. [5] Uvedené četnosti diagnostiky jsou vlastní startovní návrh, nikoli univerzální nastavení výrobce. „Všechna data“ zde znamenají úplná potřebná pozorování a účelnou diagnostiku, nikoli zapnutí všech dostupných zpráv.')
h('Konfigurační postup')
p('1. Přes USB uložit původní konfiguraci a MON-VER; identifikovat hardware.<br/>2. Zapnout UBX na UART1 a RAWX/SFRBX, vypnout nepotřebné NMEA a RTCM výstupy.<br/>3. Cílit na měřicí interval 100 ms; související navigační režim a děliče zpráv přizpůsobit konkrétnímu firmwaru. Skutečných 10 Hz ověřit z obsahu souboru, ne z menu.<br/>4. Nastavení přečíst zpět a ověřit po úplném odpojení a zapnutí napájení.<br/>5. Zakázat automatické změny profilu aplikací, přechodem do jiného režimu nebo po návratu do menu. [5]')
h('Co patří do manifestu')
p('ID stanice a relace; modul a firmware F9P; commit loggeru; export konfigurace a jeho hash; karta a formát; typ antény; fotografie umístění; výška referenčního bodu antény (ARP); datum, časový systém a intervaly; souřadnice základny, způsob jejich určení a nejistota. Čas GNSS může být při startu neplatný: názvy souborů nesmějí způsobit přepsání starší relace.')

page(4,'Přenos a buffery bez ztrát')
p('Vlastní výpočet z formátu RAWX: kompletní rámec má <b>24 + 32 × N bajtů</b>, kde N je počet měření signálů, nikoli počet družic. [5] Pro N = 60 vychází 1 944 B na epochu, 19 440 B/s při 10 Hz a 38 880 B/s při 20 Hz. SFRBX a diagnostika přidávají další, proměnlivý provoz.')
table(['Rozhraní 8N1','Teoretické maximum','Posouzení návrhu'],[
    ['115 200 baud','11 520 B/s','Nestačí ani na model RAWX 60 signálů při 10 Hz.'],
    ['460 800 baud','46 080 B/s','10 Hz může vyhovět; 20 Hz má menší rezervu.'],
    ['921 600 baud','92 160 B/s','Výchozí volba pro krátký interní UART; ověřit kvalitu přenosu.'],
], [.26,.27,.47])
p('ArduSimple Serial Datalogger AS-XBEE-LOG-MICROSD-01 je výrobcem specifikován na 115 200 b/s. Proto ho pro tento 10Hz profil nedoporučuji. Údaj o logování samotné GGA ve vysoké frekvenci neprokazuje kapacitu pro RAWX. [12]')
h('Konkrétní zjištění ve SparkFun firmwaru')
p('V prohlédnutém commitu má RTK Firmware výchozí UART buffer 2 KiB a GNSS handler 4 KiB. Typ offsetu kruhového bufferu je 16bitový. Při zaplnění kód zahazuje nejstarší data a posouvá také ukazatel SD. To je důvod firmware před použitím prověřit a upravit. [8,9]')
p('Návod Reference Station u 20Hz RAWX popisuje vypnutí Bluetooth a zvětšení handleru na 16 384-65 535 B. Jde o konkrétní produkt a popsanou verzi, nikoli důkaz bezeztrátovosti vlastní sestavy. [11]')
box('<b>Velikost bufferu se odvodí z latence:</b> B ≥ R × t<sub>blokace</sub> + rezerva na dávky. Při návrhových 50 000 B/s vydrží 4 KiB jen 82 ms, 65 535 B asi 1,31 s, 256 KiB asi 5,24 s a 1 MiB asi 21 s. Platí pouze tehdy, když příjem do bufferu mezitím dál funguje.')
p('Pro vlastní port navrhuji interní UART frontu a oddělený zapisovač; větší datový buffer podle měření v PSRAM. <b>256 KiB / 1 MiB nejsou pouhá změna nastavení původního 16bitového bufferu.</b> Vyžadují úpravu typů, alokace, indexace a test mezních stavů. Při záznamu neprovádět OTA ani zápisy nastavení do interní flash; u klasického ESP32 má PSRAM omezení při vypnuté cache. [8,14]')
p('Monitorovat UART FIFO overflow, zaplnění RX fronty, rámcové chyby, obsazení všech bufferů a dobu zápisu. ESP-IDF pro UART takové události zpřístupňuje; jejich vyvedení z použité Arduino vrstvy je součást portu. [13]','small')

page(5,'Karta, soubory a důkaz úplnosti')
h('Rychlá karta sama nestačí')
p('Pro návrhových 50 kB/s vznikne za 15 h přibližně <b>2,70 GB</b>; dvojnásobná kapacitní rezerva znamená 5,40 GB. 32GB karta má dost prostoru. Rozhodující je nejdelší pozastavení zápisu a chování při výpadku, nikoli jen reklamní MB/s. Průmyslová pSLC S-56u je kandidát; ověřit konkrétní SKU a rozsah případné ochrany proti ztrátě napájení. [15]')
p('Navrhuji záznam po 5minutových segmentech, při uvedeném toku přibližně 15 MB. Nevytvářet jeden soubor za celý závod. FAT má limit souboru 2<super>32</super>-1 B a přerušený zápis může poškodit souborový systém; malé segmenty riziko omezují, neodstraňují. [17]')
h('Požadované chování zapisovače - vlastní návrh')
p('• Jeden zapisovač, binární bloky, kontrola skutečně zapsaného počtu bajtů a návratových kódů.<br/>• Návrhový interval synchronizace 1 s, dále při uzavření segmentu a před vypnutím. Změřit maximální latenci. U FatFs použít f_sync; v konkrétní knihovně ověřit skutečný ekvivalent sync/flush. [16]<br/>• Jedinečná jména a číslování, žádné automatické přepisování nejstarších jízd. Otevřený segment označit jako neuzavřený.<br/>• Po uzavření uložit délku, první/poslední epochu a SHA-256. Po restartu zachovat originál a analyzovat i platný začátek nedokončeného souboru.<br/>• Na záznamové kartě během měření neprovádět prohlížení, kopírování, formátování ani jiné dlouhé operace.')
box('<b>Synchronizace není úplná ochrana:</b> ani úspěšný flush nevrátí data, která přijímač či UART už zahodily. Záruka přežití náhlého odpojení dále závisí na napájení a řadiči karty. Hash odhalí změnu souboru, ale neprokazuje, že byly původně zaznamenány všechny epochy.',True)
h('Tři oddělené výsledky kontroly')
table(['Kontrola','Co prokazuje / neprokazuje'],[
    ['Bajty a rámce','UBX checksum, délky, parserové chyby. Platný checksum není důkaz, že žádná celá zpráva nechybí.'],
    ['Časová úplnost','Počty RAWX, posloupnost týden + TOW, mezery a duplicity. Zohlednit start, změnu tempa a příznak resetu hodin; neporovnávat desetinné časy na přesnou rovnost.'],
    ['Použitelnost pro PPK','Počet společných platných signálů, fáze, locktime/cycle slips, navigační data a překryv roveru se základnou. Souvislý log může obsahovat nekvalitní měření.'],
], [.26,.74])
p('10 Hz po přesně 15 hodinách v intervalu [t0, t0 + 15 h) znamená 540 000 očekávaných epoch po zahájení platného sběru. Kvalitu příjmu reportovat zvlášť; chybějící epochy nikdy potichu nevyplňovat a neoznačovat za naměřené.','small')

page(6,'Napájení a umístění na trati')
h('Baterii dimenzovat ve Wh')
p('Vlastní model: <b>E<sub>jmen</sub> ≥ P<sub>zátěže</sub> × 15 h / (η × u)</b>. P zahrnuje F9P, aktivní anténu, logger, kartu a indikaci za regulátorem. η je účinnost napájení; u využitelný podíl jmenovité energie po zohlednění stáří, teploty a prahu řízeného vypnutí.')
table(['Spotřeba sestavy','Předpoklady modelu','Potřebná jmenovitá energie'],[
    ['2 W','η = 0,85; u = 0,80','44,1 Wh'],
    ['3 W','η = 0,85; u = 0,80','66,2 Wh'],
    ['4 W','η = 0,85; u = 0,80','88,2 Wh'],
], [.25,.34,.41])
p('Z toho plyne orientační volba packu 90-100 Wh pro sestavu do přibližně 4 W, nikoli potvrzená výdrž. Požadovaných 15 h už obsahuje tříhodinovou časovou rezervu. Po změření spotřeby a účinnosti výpočet přepočítat; při měření přímo na baterii nezapočítat účinnost podruhé. Údaj mAh bez napětí není dostatečný.')
h('Řízené vypnutí před poklesem napětí')
p('Použít chráněný hotový pack, pojistku a stabilizátor s rezervou pro špičky SD. Hlídání nízkého stavu musí zareagovat dřív než ochrana baterii odpojí. Tlačítko STOP má vyžádat ukončení sběru: označit konečnou epochu, zpracovat frontu, synchronizovat data a signalizovat „lze vypnout“.')
p('Pro přežití odpojení externího zdroje navrhnout skutečný energetický doběh nebo power-path s baterií. Potřebný čas vychází z nejhoršího zjištěného vyprázdnění fronty a synchronizace, ne z odhadnutých 100 ms. Osciloskopem ověřit napájení F9P, MCU a karty při zápisu i přepnutí zdroje. Dokončení posledního souboru nezajistí pokračování měření po vybití.')
h('Anténa, skříň a stativ')
p('Pevné místo s otevřeným výhledem na oblohu, mimo pohybující se překážky a silné odrazy. Anténa nesmí být pod karbonem ani kovovým víkem. Stativ zatížit, kabel odlehčit a zaznamenat každý přesun. Oddělit anténu od DC/DC a digitální elektroniky; porovnat signálovou diagnostiku při klidu a intenzivním zápisu.')
p('Pokud zůstane anténa ANN-MB2: výrobce uvádí napájení 3-5 V a měření fázového centra na kruhové podložce o průměru 120 mm. Změna podložky může změnit fázové centrum. Zapsat geometrii a orientaci konkrétní montáže. [21] Budget poskytuje pro aktivní anténu 3,3 V, nejvýše 75 mA. [1]')
p('Uzavřenou skříň otestovat v očekávaném slunci, teplotě a vlhkosti; samotné označení IP na prázdné krabici není důkaz těsnosti celé sestavy s průchodkami. Baterii, elektroniku a nabíjení provozovat v mezích konkrétních výrobců.','small')

page(7,'PPK a ověřovací zkoušky')
h('Nejprve ověřit celý řetězec základna + rover')
p('Na PC převést krátký souběžný UBX a SBF záznam do RINEX a zpracovat RTKLIB-EX. Projekt obsahuje dekodér Septentrio i interpolaci reziduí základny. To podporuje zkoušku nestejných frekvencí, ale samo nedokazuje přesnost konkrétního páru při 50 Hz. [18-20]')
p('Zpracovat rover v kinematickém režimu s pevnou základnou, zachovat 20ms epochy roveru, ověřit společné signály a nepoužít výstupní decimaci. Porovnat základnu 1 / 5 / 10 Hz, případně 20 Hz, pokud ho hardware opravdu poskytuje. Posoudit počet řešení, FIX/FLOAT, rezidua, výpadky a opakovatelnost; interpolace není nové měření.')
box('<b>Bez externích korekcí lze určit kvalitní relativní dráhu vůči vlastní základně. Absolutní centimetrovou polohu nelze odvodit pouhým průměrováním běžného fixu.</b> Chyba souřadnic základny se promítá do absolutní polohy roveru. [2] Pokud nebude k dispozici zaměřený bod, výsledek uvést v místní soustavě a absolutní nejistotu přiznat. Použít vlastní zachycené vysílané efemeridy; bez NTRIP a externích PPP produktů.')
h('Navržená přijímací kritéria - zatím neprovedeno')
table(['Zkouška','Rozsah a kritérium přijetí'],[
    ['Datová cesta','Známý binární proud do UARTu při maximálním provozním toku a dávkách: po korektním STOP shoda délky i hash, nula ztrát a UART chyb.'],
    ['Živý F9P','Současný kontrolní USB log na PC: shoda RAWX epoch a obsahu pozorování v překryvu. Celé soubory nemusí být identické kvůli jiným stavovým zprávám.'],
    ['Výdrž','3 úplné běhy na baterii po ≥15 h, jeden v nejhorší očekávané teplotě. Bez restartů, overflow a nevysvětlených mezer loggeru; RF výpadky reportovat odděleně.'],
    ['Dlouhý běh a karta','72 h s napájením; karta prázdná i z 80 % zaplněná. Změřit maximum latence write/sync, obsazení bufferu, paměť a přechody segmentů.'],
    ['Výpadek napájení','Nejméně 100 řízených náhodných odpojení v různých fázích zápisu. S doběhem uchovat vše do definovaného STOP; bez doběhu změřit ztracený konec a poškození.'],
    ['Poruchy','Chybějící/plná karta, výpadek GNSS, zatuhnutí zapisovače, opakované starty bez sítě. Žádné falešné „OK“ ani přepsání starších dat.'],
], [.25,.75])
p('Jde o návrh vstupních zkoušek, ne statistický důkaz 100% spolehlivosti. Po každé změně loggeru, karty, konfigurace nebo napájení zopakovat příslušné zkoušky. Testované mezní podmínky musí být součástí protokolu.','small')

page(8,'Postup realizace a provozu')
h('Co realizovat jako první')
p('<b>1. Oživení s počítačem:</b> identifikovat F9P, uložit konfiguraci, připojit anténu a pořídit 30-60 minut UBX přes USB. Paralelně zaznamenat mosaic-X5 a ověřit převod i první PPK. Tím se oddělí problém GNSS konfigurace od budoucího SD loggeru.')
p('<b>2. Prototyp ESP32:</b> vyjít ze SparkFun RTK Firmware, ale vytvořit profil vlastní desky: piny, SD, indikace, napájení a řídicí i datová komunikace přes UART1. Nelze převzít předpoklad jiného zapojení I2C/SPI. Hotová binárka pro jiný výrobek není port pro Budget. Build workflow používá Arduino-ESP32 2.0.2; zaznamenat commit a závislosti. [6,9,10]')
p('<b>3. Úpravy pro spolehlivý sběr:</b> vypnout síťové a rádiové služby během logování; oddělit příjem a SD zápis; přidat počítadla ztrát a latencí, kontrolu epoch, jedinečné relace, řízený STOP a čitelnou signalizaci. Nastavit celkový limit logování nad 15 h a ověřit rotaci souborů. SparkFun tyto dva limity rozlišuje. [7]')
p('<b>4. Zátěžové testy, baterie, skříň:</b> podle předchozí strany. Teprve po jejich splnění uzavřít výběr komponent a zapojení. Pokud port původního bufferu vyjde příliš složitý, porovnat RTK Everywhere: existuje pro ESP32-WROVER s PSRAM a F9P, ale i zde je vlastní deska další port. [23]')
h('Co indikovat obsluze')
table(['Stav','Význam'],[
    ['ZÁZNAM','Přibývají platné RAWX a úspěšně se dokončují zápisy. Stav GNSS a záznamu zobrazit odděleně.'],
    ['VAROVÁNÍ','Málo energie/místa, špatné GNSS, velká fronta nebo dlouhý zápis. Pokračovat v zachycení dostupných dat.'],
    ['CHYBA','Ztráta, overflow, SD chyba nebo neočekávaný restart. Uchovat dostupná data a viditelně označit neúplnost.'],
    ['LZE VYPNOUT','Fronta zpracována a soubory uzavřeny; tento stav nenahrazuje test ochrany karty proti výpadku.'],
], [.24,.76])
h('Před jízdou, při měření, po závodě')
p('Předem nabít baterii a ověřit kapacitu karty; na místě uložit polohu/montáž a spustit základnu s předstihem, například 30 minut. Předstih zahrnout do celkové 15h energetické bilance. Zkontrolovat skutečný růst logu a stabilní příjem. Během měření neměnit konfiguraci ani polohu stativu. Po jízdě nechat doběhnout i základnu, použít STOP a data zkopírovat do dvou ověřených archivních kopií.')
box('<b>Hranice jedné karty:</b> její úplná fyzická porucha může zničit jediný záznam. Pro kritická měření lze přidat nezávislý druhý logger přes USB s vlastním úložištěm a napájením. Neodstraní společné selhání přijímače či antény. Watchdog má sledovat postup zpracování; slabý GNSS signál nesmí vyvolávat restartovací smyčku. Každý restart vytváří mezeru a musí být zaznamenán.')

spark='c324958d5ca4b23c18da181b8bfbe14e73caa98e'
rtk='755e6379ae600e71980b6b20d846d6d35ca8a1aa'
sources=[
('ArduSimple. User Guide: simpleRTK2B Budget.','Zapojení, IOREF, UART1, napájení a anténní bias.','https://www.ardusimple.com/user-guide-simplertk2b-budget/'),
('u-blox. ZED-F9P Integration manual, R16, 30. 10. 2024.','Kap. 3.1.5.5 a 3.5: základna, souřadnice, UART, přetížení portu.','https://content.u-blox.com/sites/default/files/ZED-F9P_IntegrationManual_UBX-18010802.pdf'),
('u-blox. ZED-F9P-05B Data sheet, R02, 16. 10. 2024.','Str. 4 a 9: RAW frekvence a dostupnost měření.','https://content.u-blox.com/sites/default/files/documents/ZED-F9P-05B_DataSheet_UBXDOC-963802114-12824.pdf'),
('u-blox. ZED-F9P-01B Data sheet, R09, 24. 3. 2023.','Str. 2 a 4: konkrétní hardware/firmware a frekvence.','https://content.u-blox.com/sites/default/files/documents/ZED-F9P-01B_DataSheet_UBX-17051259.pdf'),
('u-blox. F9 HPG 1.51 Interface description, R01, 8. 11. 2024.','RAWX str. 198-199; SFRBX str. 201; MON-COMMS str. 130-131; CFG-RATE str. 282. Pro jiný firmware použít odpovídající dokument.','https://content.u-blox.com/sites/default/files/documents/u-blox-F9-HPG-1.51_InterfaceDescription_UBXDOC-963802114-13124.pdf'),
('SparkFun. SparkFun RTK Firmware.','Výchozí open source projekt; nepředstavuje hotový port vlastní desky.','https://github.com/sparkfun/SparkFun_RTK_Firmware'),
('SparkFun. Data Logging Menu.','RAW log, segmentace a celkový časový limit.','https://docs.sparkfun.com/SparkFun_RTK_Firmware/menu_data_logging/'),
('SparkFun. settings.h, RTK Firmware.','Zjištěny 2KiB/4KiB výchozí buffery a uint16_t RING_BUFFER_OFFSET; commit '+spark[:12]+'.','https://github.com/sparkfun/SparkFun_RTK_Firmware/blob/'+spark+'/Firmware/RTK_Surveyor/settings.h'),
('SparkFun. Tasks.ino, RTK Firmware.','Chování při přetečení handleru a posun SD ukazatele; commit '+spark[:12]+'.','https://github.com/sparkfun/SparkFun_RTK_Firmware/blob/'+spark+'/Firmware/RTK_Surveyor/Tasks.ino'),
('SparkFun. compile-rtk-firmware.yml.','Build závislost Arduino-ESP32 2.0.2; commit '+spark[:12]+'.','https://github.com/sparkfun/SparkFun_RTK_Firmware/blob/'+spark+'/.github/workflows/compile-rtk-firmware.yml'),
('SparkFun. RTK Reference Station Hookup Guide.','Sekce o 20Hz logování a GNSS Handler Buffer. Návod výrobce, dostupný též v přetisku DigiKey; nejde o měření vlastní stanice.','https://learn.sparkfun.com/tutorials/sparkfun-rtk-reference-station-hookup-guide/all?print=1'),
('ArduSimple. Serial Datalogger to microSD, AS-XBEE-LOG-MICROSD-01.','Specifikace sériové rychlosti 115 200 b/s.','https://www.ardusimple.com/product/serial-datalogger-to-microsd/'),
('Espressif. ESP-IDF v5.3, UART API.','Události přetečení a rámcových chyb. Referenční API, nikoli tvrzení o SDK původního SparkFun buildu.','https://docs.espressif.com/projects/esp-idf/en/v5.3/esp32/api-reference/peripherals/uart.html'),
('Espressif. Support for external RAM, ESP32 / ESP-IDF v4.4.','Omezení PSRAM při vypnuté flash cache a nároky na interní RAM.','https://docs.espressif.com/projects/esp-idf/en/v4.4/esp32/api-guides/external-ram.html'),
('Swissbit. Industrial microSD memory card.','Produktová řada S-56u, pSLC a kapacitní varianty. Rozsah power-fail ochrany musí doložit konkrétní objednaný produkt.','https://www.swissbit.com/en/products/flash-storage/industrial-microsd-card'),
('ChaN. FatFs - f_sync.','Synchronizace dlouho otevřeného souboru a její účel.','https://elm-chan.org/fsw/ff/doc/sync.html'),
('ChaN. FatFs Module Application Note.','Limit velikosti FAT souboru a kritické úseky při přerušení zápisu.','https://elm-chan.org/fsw/ff/doc/appnote.html'),
('RTKLIB Explorer. RTKLIB-EX, readme.','Kandidát pro PPK; původní název demo5. Commit '+rtk[:12]+'.','https://github.com/rtklibexplorer/RTKLIB/blob/'+rtk+'/readme.txt'),
('RTKLIB Explorer. src/rtkpos.c.','Interpolace reziduí základny při intpref a práce se společnými družicemi; commit '+rtk[:12]+'.','https://github.com/rtklibexplorer/RTKLIB/blob/'+rtk+'/src/rtkpos.c'),
('RTKLIB Explorer. src/rcv/septentrio.c.','Dekodér SBF; jeho přítomnost nenahrazuje test převodu konkrétního logu. Commit '+rtk[:12]+'.','https://github.com/rtklibexplorer/RTKLIB/blob/'+rtk+'/src/rcv/septentrio.c'),
('u-blox. ANN-MB2 Data sheet, R03, 27. 2. 2025.','Str. 5 a 9: napájení, podložka a fázové centrum antény.','https://content.u-blox.com/sites/default/files/documents/ANN-MB2_DataSheet_UBXDOC-963802114-12775.pdf'),
('Espressif. ESP32-WROVER-E / IE Data sheet.','Varianty paměti; ověřit objednací kód a vyvedené piny modulu/desky.','https://documentation.espressif.com/esp32-wrover-e_esp32-wrover-ie_datasheet_en.pdf'),
('SparkFun. RTK EVK Hardware Overview.','Existující sestava ESP32-WROVER + PSRAM + F9P pro RTK Everywhere.','https://docs.sparkfun.com/SparkFun_RTK_EVK/hardware_overview/'),
]
for k,(start,end) in enumerate([(0,11),(11,len(sources))]):
    page(9+k,'Zdroje a dohledatelnost' if k==0 else 'Zdroje - pokračování')
    p('Primární dokumentace výrobců a zdrojové kódy autorů. Přístup 16. 11. 2026. Čísla v textu odkazují na následující položky. Vlastní výpočty, doporučené hodnoty a testovací kritéria jsou návrhem této studie.','small')
    for i in range(start,end):
        title,note,url=sources[i]
        p(f'<b>[{i+1}] {escape(title)}</b><br/>{escape(note)}<br/><link href="{escape(url)}" color="#007F82">Otevřít zdroj</link>', 'source')
    if k==0:
        p('Přetisk návodu [11]: <link href="https://www.digikey.com/en/maker/projects/sparkfun-rtk-reference-station-hookup-guide/feae5e6ca56749e08745bc9480ad20f5" color="#007F82">SparkFun Hookup Guide na DigiKey</link>. Originál výrobce byl při rešerši částečně dostupný přes index; podrobná sekce byla ověřena v přetisku.','small')

def footer(c,doc):
    c.saveState();c.setStrokeColor(TEAL);c.setLineWidth(.5);c.line(46,40,A4[0]-46,40)
    c.setFillColor(GREY);c.setFont('Arial',8);c.drawString(46,27,'STUDIE 08  |  Stacionární základna F9P  |  16. 11. 2026')
    c.drawRightString(A4[0]-46,27,str(doc.page));c.restoreState()

doc=SimpleDocTemplate(str(OUT),pagesize=A4,rightMargin=46,leftMargin=46,topMargin=43,bottomMargin=53,title='Stacionární základna F9P a spolehlivý záznam',author='Rešeršní podklad k bakalářské práci',pageCompression=1)
doc.build(story,onFirstPage=footer,onLaterPages=footer)
print(str(OUT))
