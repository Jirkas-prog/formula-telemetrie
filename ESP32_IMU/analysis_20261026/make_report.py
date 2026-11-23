from pathlib import Path
import json,shutil
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'output';REPORT=ROOT/'report'
r=json.loads((OUT/'results.json').read_text(encoding='utf-8'));raw=json.loads((OUT/'drive_raw.json').read_text(encoding='utf-8'))
(REPORT/'images').mkdir(exist_ok=True)
for p in (OUT/'figures').glob('*.png'):shutil.copyfile(p,REPORT/'images'/p.name)
def f(x,n=1):return f'{x:.{n}f}'.replace('.',',')
def esc(x):return str(x).replace('\\',r'\textbackslash{}').replace('_',r'\_').replace('%',r'\%').replace('&',r'\&').replace('−','-').replace('→',r'$\rightarrow$').replace('≥',r'$\geq$').replace('–','--')
laprows='\n'.join(f"{x['lap']} & {f(x['start_s'])}--{f(x['end_s'])} & {f(x['duration_s'])} & {f(x['turn_deg'])} & {f(x['model_distance_m'],0)} & {f(x['closure_error_m'])} \\\\" for x in r['laps'])
driftrows='\n'.join(f"{x['horizon_s']} & {x['windows']} & {f(x['gyro_mean_m'],2)} & {f(x['gyro_median_m'],2)} & {f(x['gyro_p95_m'],2)} & {f(x['fixed_median_m'],2)} \\\\" for x in r['drift_summary'])
rawrows='\n'.join(f"{esc(x['axis'])} & {f(x['min'],3)} & {f(x['max'],3)} & {f(x['p01'],3)} & {f(x['p99'],3)} \\\\" for x in raw['extrema'])
sensrows='\n'.join(f"{esc(x['scenario'])} & {f(x['distance_m'],0)} & {f(x['max_speed_kmh'])} & {f(x['endpoint_change_m'])} \\\\" for x in r['sensitivity'])
shortcats={'Test / manipulace':'Test / manipulace','Klid / test':'Klid / test','Klid / drobné pohyby':'Klid / drobné pohyby','Klid → neplatná data':'Klid, pak porucha','Neplatná data':'Porucha','Jízda: slalom + kandidáti delších kol':'Jízda + porucha'}
def invtable(items):return '\n'.join(f"{esc(x['id'].replace('boot_','').replace('_run_',' / '))} & {f(x['duration_s']/60,2)} & {f(x['digital_fault_fraction']*100,2)} & {esc(shortcats[x['category']])} \\\\" for x in items)
text=r'''\documentclass[11pt,a4paper]{article}
\usepackage{fontspec}
\setmainfont{lmroman10-regular.otf}[BoldFont=lmroman10-bold.otf,ItalicFont=lmroman10-italic.otf,BoldItalicFont=lmroman10-bolditalic.otf]
\setsansfont{lmsans10-regular.otf}[BoldFont=lmsans10-bold.otf]
\setmonofont{lmmono10-regular.otf}
\usepackage[czech]{babel}
\usepackage[margin=19mm,top=22mm,bottom=21mm]{geometry}
\usepackage{graphicx,booktabs,tabularx,array,amsmath,xcolor,fancyhdr,enumitem,hyperref,xurl}
\setlength{\emergencystretch}{3em}
\definecolor{navy}{HTML}{203B55}\definecolor{muted}{HTML}{526877}\definecolor{red}{HTML}{A33D36}
\hypersetup{colorlinks=true,linkcolor=navy,urlcolor=navy,pdftitle={Formule: analýza IMU a rekonstrukce jízdy},pdfauthor={Analýza měření}}
\graphicspath{{images/}}
\pagestyle{fancy}\fancyhf{}\fancyhead[L]{\small\sffamily FORMULE / IMU}\fancyhead[R]{\small\sffamily 26. 10. 2026}\fancyfoot[L]{\small\color{muted}Měření, model a nejistota}\fancyfoot[R]{\thepage}
\setlength{\headheight}{14pt}\setlength{\parindent}{0pt}\setlength{\parskip}{5pt}
\setlist[itemize]{leftmargin=5mm,itemsep=3pt,topsep=3pt}\renewcommand{\arraystretch}{1.2}
\newcommand{\fig}[3]{\begin{center}\includegraphics[width=\linewidth,height=#2,keepaspectratio]{#1}\par\small\color{muted}#3\end{center}}
\newcommand{\key}[1]{\textbf{\color{navy}#1}}
\begin{document}
{\sffamily\color{navy}\Huge Formule:\\[3mm]co skutečně říkají data IMU}\par
{\large Rekonstrukce jízdy, kvalita měření a soupiska záznamů}\par
{\color{muted}ICM-20948 / ESP32-S3 / 38 CSV / analýza 26. října 2026}

\section*{Hlavní výsledek}
Z dodaných dat lze sestavit \textbf{podmíněnou přibližnou trasu asi 5,5 minuty jízdy} v souboru \texttt{boot\_000181\_run\_001.csv}. Největším problémem není pouze integrační drift: značná část dlouhých souborů obsahuje \textbf{neplatné digitální měření}. Tyto úseky nelze napravit kalibrací na velikost plochy.

\begin{itemize}
\item Zkontrolováno \textbf{12\,536\,353 řádků}, celkový čas souborů \textbf{6,94 h}. Žádná chyba CRC ani vynechané pořadové číslo řádku.
\item \textbf{9\,784\,717 řádků (78,05\,\%)} obsahuje opakované shodné digitální slovo ve všech šesti inerciálních kanálech. Správné CRC tyto hodnoty nečiní fyzikálně platnými.
\item Soubor 181 obsahuje \textbf{čtyři kandidáty delších kol}: 50,1; 50,2; 55,5 a 48,5 s. Jsou to odhady hranic podle zatáček, nikoli ověřené laptimy.
\item \textbf{Osmička ani ustálený kruhový skidpad nejsou potvrzené.} U neplatných dat nelze rozhodnout, jaký manévr auto skutečně jelo.
\end{itemize}
\fig{quality.png}{63mm}{Souvislé použitelné začátky dlouhých souborů jsou krátké; červené části nejsou klid auta.}
\key{Co dostáváte:} datový balíček s původními CSV, offline prohlížeč, Excel se všemi soubory a tento report v PDF i LaTeXu. Originály a firmware zůstaly beze změny.

\clearpage
\section{Integrita souborů versus správnost senzoru}
Audit proběhl nad všemi 38 CSV, celkem 1\,819\,964\,781 B. Každý datový řádek byl ověřen CRC32 přes původní text před poslední čárkou; všechny soubory mají uložený SHA-256. Čas je monotónní, nebyla nalezena mezera mezi řádky nad 50 ms ani chybějící \texttt{seq}. Tím se potvrzuje integrita uloženého proudu, \emph{nikoli} nepřerušené měření všech senzorů.

Při rozsahu $\pm16\,g$ odpovídá $-0{,}00049\,g$ přibližně jednomu zápornému LSB. Při $\pm2000\,{}^\circ/\mathrm{s}$ odpovídá $-0{,}0610\,{}^\circ/\mathrm{s}$ rovněž jednomu zápornému LSB. Současný výskyt v šesti kanálech znamená šest slov \texttt{FFFF}. Další poruchové hodnoty zachovávají stejný digitální vzor; následné zdánlivé špičky či zatáčky se proto nesmějí interpretovat jako jízda.

\begin{center}\begin{tabular}{lrrr}\toprule
Soubor & Neplatné řádky & Podíl & Souvislý začátek [s]\\\midrule
178 / 001 & 3\,335\,207 & 97,01\,\% & 179,17\\
180 / 001 & 1\,646\,707 & 99,9998\,\% & žádný $\geq1$ s\\
181 / 001 & 4\,802\,803 & 89,63\,\% & 1008,24\\\bottomrule
\end{tabular}\end{center}
Maska poruchy testuje shodu všech šesti rekonstruovaných 16bitových slov. Pro rekonstrukci se vyžaduje souvislé pásmo bez poruchy; ojedinělá odlišná slova uvnitř vadného proudu nejsou považována za obnovené měření. Detektor nemusí zachytit všechny možné chyby SPI, proto udaný podíl není horní mez chybovosti.

\fig{overview181.png}{112mm}{Soubor 181: přibližně do 677 s převládá klid, potom jízda; od 1008,24 s digitální porucha. Magnetická data končí již před jízdou.}
Záznamy o obnově po vypnutí často uvádějí \texttt{repaired:false} a nulový odstraněný konec. Přítomnost takového souboru tedy sama o sobě neznamená poškozené CSV. Zde je problém doložen ve významu hodnot, ne v textovém formátu.

\clearpage
\section{Výběr dat, orientace a výpočet}
Prvních devět souborů, boot 144 až 150, odpovídá testům, klidu či manipulaci: mění se náklon, v některých jsou prostorové rotace přes 1000 $^\circ$/s. Nebyly vyřazeny pouze podle pořadí. Pozdější krátké soubory převážně obsahují stabilní gravitaci a malé úhlové rychlosti. \textbf{Klidový signál nevylučuje rovnoměrnou přímou jízdu}; tyto záznamy proto nejsou důkazem nulové ujeté vzdálenosti.

\subsection*{Vzorkování a filtrace}
Při zpracování se používají pouze nové vzorky označené \texttt{accel\_new}, \texttt{gyro\_new} a validní \texttt{mag\_new}. Opakované držené hodnoty nejsou nové měření. Původní proud A/G má požadovaných 500 Hz, magnetometr 100 Hz; součet CSV řádků proto není frekvence akcelerometru. Jízdní úsek 677--1007 s obsahuje přesně \textbf{165\,000 nových A/G vzorků}; příznaky A/G se zde shodují.

Pro prohlížení jsou vytvořeny průměry v 10 ms intervalech (100 Hz). Pro rovinný model následuje obousměrný Butterworthův filtr 3. řádu s mezí 2 Hz a výpočet na 10 Hz. Nízkofrekvenční průběh není vhodný k měření nárazových maxim; ta se hodnotí z originálních 500 Hz dat. Filtr se nepřenáší přes poruchové úseky. Originální soubory v balíčku se nemění.

\subsection*{Osy a nulové hodnoty}
V klidovém úseku 560--650 s souboru 181 vychází medián akcelerace $(-0{,}010744; -0{,}045802; 0{,}979392)\,g$ a gyroskopu $(-0{,}61034; 0{,}70802; 0{,}10986)\,{}^\circ/\mathrm{s}$. Osa \textbf{+Z míří přibližně nahoru}. Jediná klidová poloha však nerozliší přesně náklon, offset a chybu citlivosti akcelerometru.

Po srovnání odhadované svislice je směr dopředu určen z rovinného modelu pohybu, přibližně \textbf{+X, natočení $-9{,}5^\circ$ směrem k $-Y$}; kladná boční osa je přibližně +Y. Jde o modelový odhad, nikoli fyzicky ověřenou montáž. Zpětný směr je znevýhodněn požadavkem převážně nezáporné dopředné rychlosti.

\subsection*{Podmíněný vozidlový model}
Pro nulový boční skluz a přibližně rovnou plochu platí
\[a_\parallel\simeq\dot v,\qquad a_\perp\simeq r v,\qquad \dot\psi=r,\qquad \dot x=v\cos\psi,\quad\dot y=v\sin\psi.\]
Profil $v_i$ minimalizuje součet kvadrátů reziduí $[(v_{i+1}-v_i)/\Delta t-\bar a_{\parallel,i}]$ a $[r_i v_i-a_{\perp,i}]$, s rovnými vahami obou akceleračních složek, $\Delta t=0{,}1$ s a měkkou podmínkou $v(650\,\mathrm{s})=0$. Směr montáže se hledá minimalizací stejné chyby s penalizací záporné rychlosti. Orientace vůči severu i počáteční souřadnice jsou volné.

Tento výpočet doplňuje integraci o vztah bočního zrychlení a zatáčení. \textbf{Neprokazuje skutečnou polohu}. Dynamický náklon, smyk, páka mezi IMU a těžištěm a nejistota nulových hodnot zůstávají zdroji systematické chyby. Magnetometr se do modelu nezapojuje.

\clearpage
\section{Přibližná trasa a rychlost}
\fig{trajectory.png}{116mm}{Vlevo odhad z vozidlového modelu; vpravo srovnání s prostou integrací podélného zrychlení. Barva trasy odpovídá času souboru.}

\begin{center}\begin{tabularx}{\linewidth}{Xr}\toprule
Modelový výsledek, úsek 650--1007 s & Hodnota\\\midrule
Ujetá vzdálenost (podmíněný model) & 2,56 km\\
Maximum rychlosti (podmíněný model) & 70,1 km/h\\
95. percentil rychlosti & 47,3 km/h\\
Rozpětí lokálních souřadnic celé trasy & 110,7 $\times$ 321,4 m\\
RMS podélného / bočního rezidua modelu & 0,67 / 2,04 m/s$^2$\\\bottomrule
\end{tabularx}\end{center}

Přibližně 677--710 s odpovídá rozjezdu a manévrům. Úsek 710--772 s obsahuje střídavé zatáčení a delší přejezd; model zde vytváří protáhlou část trasy. To je \textbf{kandidát delšího slalomu či přejezdu}, nikoli důkaz přesné délky rovinky. Dlouhá přímá jízda je pro IMU obtížná: konstantní rychlost z nulové akcelerace určit nelze.

Od zhruba 781 s se opakuje podobný tvar. Jednotlivé modelové okruhy mají před uzavřením rozpětí přibližně 50--64 $\times$ 87--114 m. To je slučitelné s uvedenou plochou 82 $\times$ 130 m. \textbf{Rozměry plochy nebyly použity k násilnému přepočtu měřítka}, neboť uživatel připouští delší jízdy mimo ni. Shoda velikosti sama o sobě model neověřuje.

Prostá integrace během jízdy dosahuje záporných rychlostí přes 100 km/h. Za předpokladu převážně dopředné jízdy jde o zjevně nevhodný odhad. Vozidlová vazba tento rozpad výrazně omezuje, avšak boční reziduum kolem 0,21 $g$ ukazuje, že model není přesným popisem každého okamžiku.

\clearpage
\section{Delší kola, osmičky a skidpad}
\begin{center}\small\begin{tabular}{rrrrrr}\toprule
Kandidát & Čas souboru [s] & Doba [s] & Otočení [$^\circ$] & Délka* [m] & Neuzavření* [m]\\\midrule
@LAPS@
\bottomrule\end{tabular}\end{center}
{\small * Délka a neuzavření pocházejí z modelu. Doba je rozdíl vybraných časových hranic.}

\fig{laps-map.png}{102mm}{Všechny úseky začínají v lokálním počátku. Vpravo je navíc vynucen návrat na začátek; měřítko zůstává stejné.}

Hranice kandidátů jsou vybrány u opakujících se výrazných kladných špiček zatáčení. Celková změna směru v úseku je 336--372$^\circ$. Časy ukazují přibližnou periodicitu kolem 50 s, ale \textbf{nelze je vydávat za soutěžní laptime}. Čas špičky zatáčení nemusí být pokaždé totožný s průjezdem stejným bodem.

Neuzavření před korekcí činí 9,0--25,8 m, tedy 2,4--6,3\,\% modelové délky kola. Průměr je 15,8 m na kandidátní kolo. Toto číslo zahrnuje drift, chybné předpoklady modelu i případnou odlišnost hranic; není to průměrná skutečná polohová chyba.

Podmíněná korekce používá
\[\mathbf p_c(t)=\mathbf p(t)-\frac{t-t_0}{t_1-t_0}\,[\mathbf p(t_1)-\mathbf p(t_0)].\]
Odstraní koncový rozdíl, ale rozloží ho do celé trajektorie. Žádný bod uvnitř kola se tím automaticky nestane přesnějším. Proto aplikace standardně ukazuje model bez této korekce.

\key{Osmička a skidpad:} střídání levé a pravé zatáčky zde odpovídá spíše slalomu a členitému okruhu. Pro označení skidpadu by bylo potřeba doložit opakované souvislé otáčky stejného směru, případně dvě opačné kruhové části s návratem. Takový jednoznačný vzor v použitelných datech nebyl potvrzen.

\clearpage
\section{Jak přesvědčivé je opakování kol}
\fig{lap-profiles.png}{123mm}{Kandidáti kol po lineárním přepočtu času na 0--100\,\%. Lokální průběhy a rychlost jízdy se liší.}
Průměrná korelace tří normalizovaných kanálů (yaw, podélná a boční akcelerace) mezi sousedními úseky je pouze 0,286; 0,048 a 0,049. Autokorelace delšího úseku má lokální maximum při posunu 48,8 s s hodnotou 0,244. \textbf{Důkaz opakování není dost silný pro automatické prohlášení přesných kol.} Pro kandidáty hovoří podobné pořadí zatáček, přibližně jedna celá změna směru a podobný modelový tvar.

Rozdílné tempo a různě dlouhé lokální manévry snižují korelaci po pouhém lineárním přepočtu času. Agresivní časové deformování by mohlo křivky přiblížit, ale mohlo by také vytvořit zdání shody. Proto není použito k potvrzení laptimů.

V Excelu je rozlišeno \emph{zařazení souboru} a \emph{konkrétní úsek}. Soubor 181 tedy neznamená tři hodiny kol: obsahuje klid, přibližně 330 s použitelné jízdy a dlouhou poruchovou část. Soubor 180 nelze označit jako dlouhou trať pouze proto, že běžel skoro hodinu.

\key{Nejhodnotnější doplnění:} jediný záznam videa, známý průjezd startem nebo souřadnice několika bodů by umožnily ověřit kandidáty i přibližné rozměry trasy. Bez takové reference zůstává soupisku nutné číst jako klasifikaci důkazů, ne jako úplný jízdní deník.

\clearpage
\section{Odhad driftu z klidových kandidátů}
Vybráno bylo 19 nepřekrývajících se 90s oken z klidových souborů. V každé sekundě celého okna musela směrodatná odchylka každé akcelerační osy zůstat pod 0,008 $g$ a každé osy gyroskopu pod 0,2 $^\circ$/s. Prvních 30 s slouží k odhadu nul a gravitace; dalších 60 s k nezávislé integraci. Žádná korekce koncové polohy se nepoužívá.

\begin{center}\small\begin{tabular}{rrrrrr}\toprule
Horizont [s] & Oken & Průměr [m] & Medián [m] & P95 [m] & Pevná orientace [m]\\\midrule
@DRIFT@
\bottomrule\end{tabular}\end{center}
{\small Poslední sloupec je medián při zmrazené orientaci; ostatní sloupce propagují také chybu gyroskopu.}
\fig{drift.png}{82mm}{Zdánlivá vodorovná poloha při předpokladu skutečného klidu. Ojedinělé hodnoty jsou ponechány.}

Průměrný zdánlivý posun po minutě je asi \textbf{26,5 m}, medián 25,1 m. Při pevné orientaci je medián jen 2,27 m. Rozdíl ukazuje význam chyby náklonu: malá část gravitace se po chybné rotaci promítne do horizontální akcelerace. Tento test je \textbf{proxy driftu v klidu}, nikoli ověření přesnosti během jízdy. Klid nebyl potvrzen externím referenčním měřením.

V této klidové zkoušce se rotace počítá z integrálu malých úhlů; nejde o plnohodnotný strapdown filtr pro velké prostorové rotace. Použití je omezeno na vybrané klidové úseky. Pro konstantní chybu akcelerace $b$ platí $\Delta p=\tfrac12 b t^2$. Chyba náklonu 0,1$^\circ$ odpovídá asi 0,0171 m/s$^2$ a samotná by za 60 s vytvořila asi 30,8 m chyby. Jediné číslo v m/s proto není vhodný univerzální popis driftu.

\clearpage
\section{Zajímavé události a skutečná maxima}
Následující tabulka vychází z \textbf{původních 500 Hz vzorků} jízdního úseku 677--1007 s. Akcelerometr obsahuje gravitaci; osy jsou osy senzoru. P1/P99 omezují vliv ojedinělých špiček, ale nenahrazují minima a maxima.
\begin{center}\small\begin{tabular}{lrrrr}\toprule
Kanál & Minimum & Maximum & P1 & P99\\\midrule
@RAW@
\bottomrule\end{tabular}\end{center}
\fig{transients.png}{87mm}{Dvě krátké události v původních datech. Horní řada: akcelerace; dolní řada: gyroskop. Barvy X/Y/Z jsou červená/zelená/modrá.}

V 863,907 s dosahuje gyro Y $-220{,}95^\circ$/s. Je to krátký impulz s následným dozníváním, nikoli běžné zatáčení kolem svislé osy. V 898,331 s dosahuje vertikální kanál 2,21 $g$, o přibližně 24 ms později klesá na $-0{,}27g$. Může jít o ráz, vibraci či odlehčení a odezvu montáže; bez videa nelze určit příčinu ani označit konkrétní obrubník.

V celém vybraném jízdním úseku je \textbf{nula řádků s příznakem klipování}. Nastavených $\pm16g$ a $\pm2000^\circ$/s zde nebylo dosaženo. Špičky z pozdější digitální poruchy se do těchto maxim nezahrnují.

Po filtraci 2 Hz a odhadu roviny vozidla vychází podélná akcelerace přibližně $-1{,}06$ až $+0{,}81g$ a boční $-1{,}04$ až $+1{,}12g$. Tyto hodnoty se vztahují k jinému zpracování než syrová maxima výše; nemají se vzájemně zaměňovat.

\clearpage
\section{Citlivost výsledku a limity kalibrace}
\begin{center}\small\begin{tabularx}{\linewidth}{Xrrr}\toprule
Změna předpokladu & Délka [m] & Max. [km/h] & Posun konce [m]\\\midrule
@SENS@
\bottomrule\end{tabularx}\end{center}
Každý řádek mění jediný parametr a znovu dopočítá rychlost; ostatní předpoklady zůstávají stejné. Udaný posun konce je vůči základnímu modelu, ne vůči pravdě. Změna montážního úhlu o $\pm5^\circ$ změní koncový bod asi o 22 m. Změna gyro biasu o $\pm0{,}05^\circ$/s jej posune asi o 16 m. To je dost velké vzhledem k šířce plochy 82 m.

Malá citlivost tohoto konkrétního fitu na konstantní podélný offset neznamená obecnou odolnost IMU. Boční vazba zde rychlost silně určuje. Na dlouhé rovince bez zatáčení tato informace chybí. Tabulka není interval spolehlivosti; neobsahuje například proměnný náklon, skluz ani chybu časových značek.

\subsection*{Magnetometr během jízdy není k dispozici}
Poslední čerstvý magnetický vzorek souboru 181 připadá na 534,295 s, jízda začíná přibližně v 677 s. Chybějící kompas nelze zpětně dopočítat z jiných os. Navíc už v klidu se mění velikost magnetického vektoru, takže by bylo nutné zvlášť prověřit rušení a kalibraci v autě. Prohlížeč ukazuje chybějící data jako mezery, nikoli interpolovaný sever.

\subsection*{Co opravuje a co neopravuje uzavření kol}
Znalost návratu na stejné místo může omezit integrační rozpad. Nemůže však sama určit, kudy auto uvnitř kola jelo, jaká byla absolutní rychlost na rovince ani zda se celý model nenatočil. Jedno opakování není zároveň nezávislá validace parametrů, které se na něm vyladily. Proto není z těchto dat deklarována metrová přesnost.

\subsection*{Pravděpodobná poruchová oblast}
Vzor \texttt{FFFF} ukazuje na problém při získávání či dekódování dat před výpočtem CSV CRC. Mezi možné příčiny patří SPI/MISO, napájení senzoru, obsluha FIFO či reset senzoru. Samotný log nerozliší konektor od firmwaru. V aktuálním čtecím kódu se kontroluje návratový stav přenosu, ale úspěšný SPI přenos nemusí potvrdit fyzicky správnou odpověď senzoru. \textbf{Konkrétní příčina tedy není dokázána a firmware nebyl při této analýze měněn.}

\clearpage
\section{Soupiska všech souborů}
Kompletní editovatelná tabulka je v Excelu. Zde je stručný přehled; číslo vlevo odpovídá \texttt{boot / run}. Kategorie popisuje pouze doložený obsah. „Klid“ není důkaz nulové rychlosti ani potvrzení testu na stole.
\begin{center}\small\begin{tabular}{lrrl}\toprule
Boot / run & Doba [min] & Poruchové řádky [\%] & Zařazení\\\midrule
@INV1@
\bottomrule\end{tabular}\end{center}
Prvních devět souborů bylo vyřazeno z rekonstrukce jízdy, nikoli odstraněno. Původní odhad uživatele „první 3--5“ byl pouze vodítkem; skutečné zařazení vychází z charakteru signálů. U klidových souborů nelze bez dalšího tvrdit, zda šlo o stůl nebo již o zaparkované auto.

\clearpage
\section*{Soupiska, pokračování}
\begin{center}\small\begin{tabular}{lrrl}\toprule
Boot / run & Doba [min] & Poruchové řádky [\%] & Zařazení\\\midrule
@INV2@
\bottomrule\end{tabular}\end{center}
\subsection*{Požadované typy jízdy}
\begin{description}[leftmargin=0pt,style=nextline]
\item[Delší trasa / rovinka] Kandidát v 181, zhruba 710--772 s: protáhlý přejezd se střídavým zatáčením. Přesná rovinka a její délka nejsou ověřeny.
\item[Delší kola] Čtyři kandidáti v 181, zhruba 781,3--985,6 s. Jednotlivé úseky jsou vypsány v kapitole 4 a v Excelu.
\item[Osmička] Nepotvrzena. Střídání směrů zatáčení nestačí k identifikaci dvou uzavřených protilehlých kruhů.
\item[Kruh / skidpad] Nepotvrzen. U rozsáhlých poruchových částí 178 a 180 je typ skutečné jízdy neurčitelný.
\end{description}

\clearpage
\section{Použití aplikace a reprodukovatelnost}
Otevřete \texttt{Prohlizec\_IMU.html} v aktuálním prohlížeči Edge nebo Chrome a tlačítkem \emph{Otevřít data} vyberte \texttt{Formule\_IMU.fimu}. Zpracování probíhá lokálně. Balíček je standardní ZIP: původní CSV jsou v adresáři \texttt{raw/}, odvozená pole v \texttt{derived/} a popis formátu v \texttt{manifest.json}. Pro extrakci největších originálů je možné použít i 7-Zip.

Záznam a časové okno vybíráte nahoře. Společný kurzor synchronizuje polohu a všechny grafy, klepnutí do grafu ukáže konkrétní hodnoty. Čas lze přibližovat tlačítky nebo kolečkem. Tabulka kandidátů kol otevře vybraný úsek. K dispozici je export původního CSV i 100Hz výřezu. Varianta uzavřených kol je výslovně označena jako vynucená.

\subsection*{Reprodukce výpočtů}
Zdrojové skripty jsou v adresáři analýzy. \texttt{ingest.py} ověřuje CRC, pořadí a vytváří 100Hz cache; \texttt{quality.py} maskuje opakovaná digitální slova; \texttt{vehicle.py} počítá rovinný model; \texttt{final\_analysis.py} klasifikaci, drift a grafy; \texttt{drive\_raw.py} syrová maxima. \texttt{bundle.py} sestavuje archiv, \texttt{build\_workbook.mjs} Excel a \texttt{make\_report.py} tento LaTeX. Časy a hranice kandidátů jsou ve skriptech uvedeny explicitně.

Použity byly Python 3.12, NumPy, Pandas, SciPy a Matplotlib; Excel vznikl přes Artifact Tool a PDF přes Tectonic/XeTeX. Odvozená binární pole jsou float32 little-endian s popisem sloupců v manifestu. Prvotní výpočty modelu proběhly ve float64. NaN značí chybějící nebo nedůvěryhodný výsledek. Označení 100 Hz neznamená obnovení ztracených měření.

\subsection*{Co je potřeba pro další spolehlivý test}
\begin{enumerate}[leftmargin=6mm,itemsep=5pt]
\item Nejprve odstranit poruchu akvizice: ověřit konektor, napájení a SPI, opakovaně kontrolovat identitu a konfiguraci senzoru, příznaky FIFO a fyzikálně nemožné digitální vzory. Při poruše zapsat explicitní stav místo pokračování v zdánlivě platných datech.
\item Před jízdou a po ní udělat doložený klid alespoň 30--60 s, zaznamenat skutečnou montáž os a provést vícepolohovou kalibraci akcelerometru. Změřit páku IMU vůči referenčnímu bodu vozidla.
\item Přidat alespoň jednu nezávislou referenci: GNSS, rychlost kol, video se známými průjezdy nebo geodeticky známé body. Pro smyk je model $a_\perp=rv$ omezený.
\item Změřit několik známých kol a rovinku zvlášť. Parametry odhadnout na části jízd a přesnost vyhodnotit na jiné části, podle skutečné polohové či rychlostní reference.
\end{enumerate}

\clearpage
\section*{Závěr}
Senzor v použitelné části zachytil věrohodnou dynamiku jízdy, přibližně jednotkové podélné a boční přetížení, opakované zatáčky a krátké rázy. Z těchto dat lze vytvořit přibližný model okruhu a užitečný analytický prohlížeč. \textbf{Nelze z nich doložit přesnou polohu, skutečný průměrný drift během jízdy ani kompletně rekonstruovat poruchové hodiny.}

Kalibrace na oblast a kola pomáhá pouze tehdy, když jsou data fyzikálně platná a samotné předpoklady kol správné. Rozsah 82 $\times$ 130 m zde slouží k ověření přiměřenosti výsledku, nikoli k výrobě předem očekávané trasy. Nejdůležitějším dalším krokem je spolehlivá akvizice a nezávislá referenční informace, nikoli vyšší vzorkovací frekvence.

\section*{Zdroje a metodické opory}
Všechna číselná zjištění o konkrétních jízdách pocházejí z dodaných CSV a vlastních výpočtů. Následující zdroje slouží pouze k principům a specifikaci senzoru.
\begin{enumerate}[leftmargin=6mm]
\item O. J. Woodman: \emph{An introduction to inertial navigation}, University of Cambridge, 2007. Základy integrace IMU a role chyb orientace. \url{https://www.cl.cam.ac.uk/techreports/UCAM-CL-TR-696.html}
\item TDK InvenSense: \emph{ICM-20948 Datasheet}, rev. 1.6. Rozsahy, digitální rozhraní a konfigurace senzoru. \url{https://invensense.tdk.com/wp-content/uploads/2024/03/DS-000189-ICM-20948-v1.6.pdf}
\item SBG Systems: \emph{Inertial sensor installation}. Umístění, mechanická montáž a magnetické rušení. \url{https://support.sbg-systems.com/sc/kb/latest/inertial-sensors-installation/inertial-sensor-installation}
\end{enumerate}
Žádný publikovaný údaj o driftu jiného senzoru nebyl použit jako naměřená přesnost této sestavy. Výsledky v tabulkách jsou zaokrouhlené; vyšší počet desetinných míst ve strojových datech nevyjadřuje odpovídající metrologickou přesnost.
\end{document}
'''
for key,val in {'@LAPS@':laprows,'@DRIFT@':driftrows,'@RAW@':rawrows,'@SENS@':sensrows,'@INV1@':invtable(r['files'][:20]),'@INV2@':invtable(r['files'][20:])}.items():text=text.replace(key,val)
(REPORT/'main.tex').write_text(text,encoding='utf-8')
print('LaTeX source written')
