"""Figures and Czech LaTeX report from the exact analysis core used by the viewer."""
from pathlib import Path
import os,sys,json,shutil
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'.deps'))
os.environ['MPLCONFIGDIR']=str(ROOT/'.cache/matplotlib')
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
R=ROOT/'report_jizdy';I=R/'images';I.mkdir(exist_ok=True)
d=json.loads((ROOT/'output/Analyza_jizd.json').read_text())
body=np.fromfile(ROOT/'cache/driving_body100.f64',dtype='<f8').reshape(-1,5)
body=body[(body[:,0]>=677)&(body[:,0]<1007)]
t=body[:,0];long=body[:,1]/9.80665;lat=body[:,2]/9.80665;yaw=body[:,3]
s=d['summary'];events=d['events'];top=sorted(events,key=lambda e:e['peak_g'],reverse=True)
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'axes.spines.top':False,'axes.spines.right':False,'axes.titleweight':'bold','axes.labelcolor':'#203b55'})
red='#bf5148';green='#25816d';blue='#266da1';muted='#657886'
def save(fig,name):fig.savefig(I/name,dpi=180,bbox_inches='tight');plt.close(fig)
def style(ax):ax.grid(alpha=.2);ax.set_axisbelow(True)
fig,axs=plt.subplots(2,1,figsize=(10,4.5),sharex=True,layout='constrained')
axs[0].plot(t,long,color=red,lw=.7);axs[0].axhline(-.3,color=muted,ls='--',lw=.7)
for e in events:axs[0].axvspan(e['start_s'],e['end_s'],color=red,alpha=.08)
axs[0].set(ylabel='Podélné a [g]',title='330 sekund použitelné jízdy / filtr 2 Hz')
axs[1].plot(t,lat,color=green,lw=.7);axs[1].set(ylabel='Boční a [g]',xlabel='Čas v souboru [s]')
for ax in axs:style(ax)
save(fig,'drive.png')

fig,axs=plt.subplots(1,2,figsize=(10,3.4),sharey=True,layout='constrained')
for ax,e in zip(axs,[top[0],next(e for e in events if e['id']=='B35')]):
    sel=(t>e['start_s']-.7)&(t<e['end_s']+.7)
    ax.plot(t[sel],long[sel],color=red,label='Podélné');ax.plot(t[sel],lat[sel],color=green,label='Boční')
    ax.axvspan(e['start_s'],e['end_s'],color=red,alpha=.07);ax.axhline(-.3,color=muted,ls='--',lw=.7)
    ax.scatter(e['peak_time_s'],-e['peak_g'],s=28,color=red,zorder=3)
    ax.set(title=e['id']+' / maximum '+f"{e['peak_g']:.2f}"+' g',xlabel='Čas v souboru [s]');style(ax)
axs[0].set_ylabel('Zrychlení [g]');axs[1].legend(loc='upper right',fontsize=8)
save(fig,'braking-detail.png')

fig,axs=plt.subplots(1,2,figsize=(10,4.1),layout='constrained')
sc=axs[0].scatter(lat[::3],long[::3],c=t[::3],s=2,cmap='viridis',alpha=.55,rasterized=True)
axs[0].axhline(0,color=muted,lw=.7);axs[0].axvline(0,color=muted,lw=.7);axs[0].axhline(-.3,color=red,lw=.8,ls='--')
axs[0].set(xlabel='Boční a [g]',ylabel='Podélné a [g]',title='Kombinace podélného a bočního zatížení');axs[0].set_aspect('equal');style(axs[0])
fig.colorbar(sc,ax=axs[0],label='Čas [s]',shrink=.8)
labels=['Zpomalení\nbez |bočního a| ≥ 0,3 g','Zpomalení\ns |bočním a| ≥ 0,3 g']
axs[1].bar(labels,[s['braking_s']-s['combined_braking_s'],s['combined_braking_s']],color=[blue,green],width=.6)
axs[1].set(ylabel='Čas při podélném a ≤ −0,3 g [s]',title='Zpomalení a zatáčení se časově překrývají');style(axs[1])
save(fig,'combined.png')

fig,axs=plt.subplots(3,1,figsize=(10,5.5),sharex=True,layout='constrained')
colors=[blue,green,'#bc7934','#8056a2']
for lap,col in zip(d['laps'],colors):
    ix=(t>=lap['start_s'])&(t<=lap['end_s']);phase=(t[ix]-lap['start_s'])/lap['duration_s']*100
    for ax,v in zip(axs,[long,lat,yaw]):ax.plot(phase,v[ix],lw=.85,alpha=.85,label=str(lap['lap']),color=col)
for ax,label in zip(axs,['Podélné a [g]','Boční a [g]','Yaw [°/s]']):ax.set_ylabel(label);style(ax)
axs[0].legend(title='Kandidát kola',ncol=4,fontsize=8);axs[2].set_xlabel('Normalizovaný čas segmentu [%]')
save(fig,'laps-profiles.png')
for name in ['quality.png','transients.png']:
    shutil.copyfile(ROOT/'output/figures'/name,I/name)

def num(x,n=2):return f'{x:.{n}f}'.replace('.',',')
def tex(s):return str(s).replace('_',r'\_').replace('%',r'\%')
event_rows='\n'.join(f"{e['id']} & {num(e['peak_time_s'],3)} & {num(e['peak_g'])} & {num(e['duration_s'])} & {num(e['mean_g'])} & {num(e['max_abs_lat_g'])} \\\\" for e in top[:8])
lap_rows='\n'.join(f"{l['lap']} & {num(l['duration_s'],1)} & {num(-l['stats']['long']['min'])} & {num(l['stats']['long']['max'])} & {num(l['stats']['lat_abs_p95_g'])} & {num(l['stats']['braking_s'])} \\\\" for l in d['laps'])
threshold_rows='\n'.join(f"{num(r['threshold'])} & {num(r['threshold']/2)} & {r['events']} \\\\" for r in d['threshold_sensitivity'])
sensitivity=[]
for degrees in [-5,0,5]:
    a=long*np.cos(np.deg2rad(degrees))+lat*np.sin(np.deg2rad(degrees));ix=int(a.argmin());sensitivity.append((degrees,float(-a[ix]),float(t[ix])))
sensitivity_rows='\n'.join(f"{deg:+d}° & {num(v,3)} & {num(time,3)} \\\\" for deg,v,time in sensitivity)
source=r'''\documentclass[11pt,a4paper]{article}
\usepackage{fontspec}
\setmainfont{lmroman10-regular.otf}[BoldFont=lmroman10-bold.otf,ItalicFont=lmroman10-italic.otf,BoldItalicFont=lmroman10-bolditalic.otf]
\setsansfont{lmsans10-regular.otf}[BoldFont=lmsans10-bold.otf]
\setmonofont{lmmono10-regular.otf}
\usepackage[czech]{babel}
\usepackage[margin=19mm,top=22mm,bottom=21mm]{geometry}
\usepackage{graphicx,booktabs,tabularx,array,amsmath,xcolor,fancyhdr,enumitem,hyperref,xurl}
\definecolor{navy}{HTML}{203B55}\definecolor{muted}{HTML}{526877}\definecolor{red}{HTML}{A33D36}
\hypersetup{colorlinks=true,linkcolor=navy,urlcolor=navy,pdftitle={Formule: brzdění, zatáčení a závěry z jízd},pdfauthor={Analýza měření IMU}}
\graphicspath{{images/}}\pagestyle{fancy}\fancyhf{}
\fancyhead[L]{\small\sffamily FORMULE / ANALÝZA JÍZDY}\fancyhead[R]{\small\sffamily 26. 10. 2026}
\fancyfoot[L]{\small\color{muted}Naměřený signál, odhad a ověřitelný závěr}\fancyfoot[R]{\thepage}
\setlength{\headheight}{14pt}\setlength{\parindent}{0pt}\setlength{\parskip}{5pt}\setlength{\emergencystretch}{3em}
\setlist[itemize]{leftmargin=5mm,itemsep=3pt,topsep=3pt}\renewcommand{\arraystretch}{1.18}
\newcommand{\fig}[3]{\begin{center}\includegraphics[width=\linewidth,height=#2,keepaspectratio]{#1}\par\small\color{muted}#3\end{center}}
\newcommand{\key}[1]{\textbf{\color{navy}#1}}
\begin{document}
{\sffamily\color{navy}\Huge Formule:\\[3mm]brzdění, zatáčení\\a závěry z jízd}\par
{\large Navazující analýza ICM-20948 / ESP32-S3}\par
{\color{muted}38 zdrojových souborů / 330 s použitelné jízdy / 26. října 2026}

\section*{Co z těchto jízd můžeme říci}
\textbf{V použitelném jízdním úseku se opakovaně objevuje podélné zpomalení kolem jednoho g.} Nejvyšší filtrovaný odhad je \textbf{@BRAKE@\,g}, tedy @BRAKEMS@\,m/s$^2$. Nejsilnější sekundový průměr je @SECOND@\,g. Tato čísla popisují pozorované manévry; neprokazují maximální účinnost brzd ani limit pneumatik.

\begin{center}\begin{tabularx}{\linewidth}{@{}Xr@{}}\toprule
Použitelná jízda / záznam 181 & 677--1007 s / 5,5 min\\
Největší filtrované zpomalení & @BRAKE@\,g v 950,035 s\\
Největší filtrované zrychlení vpřed & @ACCEL@\,g v 995,675 s\\
Největší absolutní boční zrychlení & @LATERAL@\,g v 967,445 s\\
Čas při podélném $a\leq-0{,}30g$ & 63,47 s / 19,2\,\% jízdy\\
Z toho současně $|a_\mathrm{boční}|\geq0{,}30g$ & 32,09 s / 50,6\,\%\\\bottomrule
\end{tabularx}\end{center}

\begin{itemize}
\item \key{Nejvyšší špička není totéž co nejsilnější delší brzdění.} Událost kolem 950 s má nejvyšší maximum; kolem 787 s je vyšší průměr přes jednu sekundu i vyšší průměr celé vymezené události.
\item \key{Zpomalení často probíhá současně se zatáčením.} Přibližně polovina času nad zvoleným prahem zpomalení současně překračuje boční práh 0,30 g. Bez brzdového tlaku nelze potvrdit práci jezdce s pedálem.
\item \key{Čtyři kandidáty kol nelze zatím hodnotit jako ověřená kola stejné trati.} Jejich normalizované profily se shodují slabě. Čas 48,5 s nelze prezentovat jako prokázané zlepšení proti 55,5 s.
\item \key{Největší omezení je kvalita měření.} 78,05\,\% všech uložených řádků obsahuje zjištěný digitální poruchový vzor. Vadné části neobnoví filtr ani vynucení rozměru plochy.
\end{itemize}
\key{Rozsah závěrů:} jde o jednu použitelnou 330sekundovou jízdní pasáž. Výsledky nelze zobecnit na všechny skutečně odjeté manévry v poškozených záznamech.

\clearpage
\section{Které soubory a které veličiny hodnotíme}
Nový průchod zahrnul všech \textbf{38 původních CSV a 12\,536\,353 řádků}. SHA-256 každého zdroje se shoduje s předchozím kompletním auditem. Bylo znovu nalezeno 9\,784\,717 řádků se shodným rekonstruovaným digitálním slovem v šesti inerciálních kanálech. V prvním auditu byly všechny CRC a pořadová čísla v pořádku; textový soubor tedy může být neporušený a přesto obsahovat vadné měření.
\fig{quality.png}{57mm}{Převzatá kontrola kvality dlouhých záznamů. Zelená znamená souvislé použitelné měření, nikoliv automaticky jízdu.}
\textbf{Záznam 181} je jediný s prokázanou souvislou dynamikou jízdy v použitelných datech. Z něj hodnotíme 677--1007 s. Čas před jízdou slouží ke kalibraci offsetu; interval končí před poruchou začínající přibližně v 1008,24 s. V úvodních testech 144--150 jsou i silné rázy, například projekce 12,11 g v souboru 145/002. Ty nejsou důkazem brzdění vozidla.

\subsection*{Zpracování společné s aplikací}
\begin{itemize}
\item Z původních 500Hz A/G vzorků se používají jen hodnoty označené jako nové; pro prohlížeč vznikají 100Hz průměry po 10 ms.
\item Vozidlové veličiny používají obousměrný Butterworthův filtr 3. řádu s mezí 2 Hz. Každý souvislý platný úsek se filtruje odděleně. Nejde o nárazová maxima ani o online kauzální filtr.
\item Odčítá se klidový vektor a používá se odhad pevné montáže; směr vpřed je přibližně $-9{,}55^\circ$ od osy +X k +Y senzoru. Dynamické naklánění karoserie není nezávisle ověřené.
\item Znaménko podélného zrychlení: kladné vpřed, záporné zpomalení při dopředné jízdě. Tabulky uvádějí velikost zpomalení kladně. Boční znaménko bez fyzické kontroly montáže neoznačujeme jako levá/pravá zatáčka.
\end{itemize}
Magnetometr přestal dodávat nová data již v 534,295 s. Závěry o jízdě proto nepoužívají kompas. Polohový model ani jeho rychlost nejsou referenční měření pro následující statistiky.

\clearpage
\section{Brzdné události v celé použitelné jízdě}
\fig{drive.png}{83mm}{Červeně podélné a zeleně boční zrychlení. Lehké pásy označují kandidáty brzdění; čárkovaná čára je vstupní práh $-0{,}30g$.}
Detektor začne událost při zpomalení alespoň 0,30 g a ukončí ji při poklesu pod 0,15 g. Hystereze omezuje štěpení kolem prahu. Zůstávají události dlouhé alespoň 0,30 s; mezera v datech událost přeruší. Nalezeno je \textbf{102 kandidátů}, nikoli 102 prokázaných sešlápnutí brzdy. Délka je počet zahrnutých 10ms vzorkových intervalů; uvedené časy jsou středy prvního a posledního intervalu.

\begin{center}\small\begin{tabular}{@{}lrrrrr@{}}\toprule
ID & Vrchol [s] & Maximum [g] & Délka [s] & Průměr [g] & Max. $|a_b|$ [g]\\\midrule
@EVENT_ROWS@
\bottomrule\end{tabular}\end{center}
\key{102 není univerzální vlastnost jízdy.} Při stejném minimu 0,30 s a výstupním prahu rovném polovině vstupního vyjde:
\begin{center}\small\begin{tabular}{rrr}\toprule Vstupní práh [g] & Výstupní práh [g] & Počet kandidátů\\\midrule
@THRESHOLD_ROWS@
\bottomrule\end{tabular}\end{center}
Pro porovnání více měření musí být prahy i filtr stejné. Přehled všech 102 událostí je v doprovodném CSV, včetně přesných časů pro vyhledání v aplikaci.

\clearpage
\section{Dvě nejsilnější brzdné pasáže}
\fig{braking-detail.png}{77mm}{Srovnání B83 a B35. Podélný a boční průběh používají stejné měřítko; barevná plocha je interval vymezený detektorem.}
\begin{center}\begin{tabularx}{\linewidth}{@{}Xrr@{}}\toprule
Veličina & B83 / kolem 950 s & B35 / kolem 787 s\\\midrule
Nejvyšší filtrované zpomalení & 1,067 g & 1,058 g\\
Délka detekované události & 1,71 s & 1,85 s\\
Průměrné zpomalení v události & 0,628 g & 0,755 g\\
Boční zrychlení v okamžiku vrcholu & 0,116 g & 0,036 g\\
Největší $|a_\mathrm{boční}|$ v události & 0,857 g & 0,154 g\\\bottomrule
\end{tabularx}\end{center}
\textbf{B83 má jen o přibližně 0,009 g vyšší špičku.} Tak malý rozdíl není důkazem lepšího brzdného výkonu. B35 má naopak výrazně vyšší průměr detekovaného zpomalení. Nejvyšší klouzavý sekundový průměr celé jízdy, \textbf{0,866 g}, leží mezi 786,585 a 787,575 s (100 vzorkových intervalů).

V B83 začíná vrchol zpomalení při poměrně malé boční složce, ale do stejné události později zasahuje boční zrychlení až 0,86 g. To je \textbf{slučitelné s přechodem ze zpomalování do zatáčky}; samo o sobě to nedokládá techniku práce s brzdovým pedálem. B35 je podle IMU výrazně méně bočně zatížené.

\subsection*{Jak přesně číst uvedená maxima}
Syrová podélná špička 1,391 g v 949,973269 s je po stejném odhadu montáže vyšší než filtrované maximum. Obsahuje i rychlé složky, které filtr potlačil. Ani tuto špičku nelze bez referenčního měření vydávat za stálé brzdné zpomalení.

Pro ilustraci citlivosti přepočtu: samotné otočení odhadnuté podélné osy v rovině o $\pm5^\circ$, při stejném filtru a offsetu, změní celkové maximum takto:
\begin{center}\small\begin{tabular}{rrr}\toprule Změna montáže & Maximum [g] & Čas [s]\\\midrule
@SENSITIVITY_ROWS@
\bottomrule\end{tabular}\end{center}
To je scénář citlivosti, nikoliv interval spolehlivosti. Skutečná chyba montáže, offsetu a dynamického náklonu nebyla nezávisle změřena.

\clearpage
\section{Zatáčení a kombinované zatížení}
\fig{combined.png}{89mm}{Diagram podélného a bočního zrychlení a časový překryv prahů. Body nejsou přímým měřením sil pneumatik ani jejich třecí kružnice.}
Absolutní boční maximum vychází \textbf{1,127 g v 967,445 s}; protilehlé znaménko dosahuje $-1{,}037g$ v 955,605 s. 95. percentil absolutní boční hodnoty je \textbf{0,921 g}. V této jízdě tedy nejde pouze o jediný osamělý boční výkyv.

Podélné zpomalení přesahuje 0,30 g po \textbf{63,47 s}, tedy 19,2\,\% analyzovaného času. Z toho \textbf{32,09 s} současně překračuje boční práh 0,30 g. Těchto 50,6\,\% je podíl \emph{času se zpomalením nad prahem}, ne podíl celkové jízdy ani počtu událostí. Podélné zrychlení nad +0,30 g zaujímá 77,82 s.

\key{Podporovaný závěr:} měření obsahuje četné kombinace podélného a bočního zatížení a je vhodné k vyhledání konkrétních přechodů mezi manévry. Prohlížet pouze minimum osy X bez odhadu montáže by směšovalo podélnou a boční složku.

\key{Co z grafu nelze vyvodit:} nelze určit součinitel přilnavosti, rozdělení brzd mezi nápravy, nedotáčivost či přetáčivost ani rezervu do zablokování kola. Chybí rychlosti kol, řízení, tlak brzd a nezávislá orientace. Ani blízké velikosti maxim obou bočních znamének neprokazují symetrii podvozku: zatáčky a rychlosti nejsou kontrolovaný experiment.

Nezávisle měřená rychlost by dovolila ověřit, zda záporné podélné zrychlení odpovídá skutečnému poklesu rychlosti. Bez ní neuvádíme brzdnou dráhu ani čas 100--0 km/h jako naměřený výsledek.

\clearpage
\section{Čtyři kandidáti kol: co lze porovnávat}
\begin{center}\small\begin{tabular}{@{}rrrrrr@{}}\toprule
Kandidát & Doba [s] & Brzdění max. [g] & Zrychlení max. [g] & $P_{95}|a_b|$ [g] & Brzdění [s]\\\midrule
@LAP_ROWS@
\bottomrule\end{tabular}\end{center}
Poslední sloupec počítá dobu s podélným $a\leq-0{,}30g$, nikoli součet délek hysteretických událostí. Hranice segmentů jsou 781,305; 831,405; 881,605; 937,105 a 985,605 s.
\fig{laps-profiles.png}{105mm}{Profily po přepočtu na relativní čas segmentu. Stejné procento času není zárukou stejného místa na trati.}
\textbf{Důležitá korekce interpretace:} průměrné korelace normalizovaných profilů podélného zrychlení, bočního zrychlení a yaw vůči předchozímu kandidátu jsou pouze \textbf{0,286; 0,048 a 0,049} (původní 10Hz analýza, 500 normalizovaných bodů). To je slabá shoda, zejména u posledních dvojic. Sama podobná délka a přibližně jedna otočka tedy nepotvrzují stejné uzavřené kolo.

Čtvrtý segment je o 7,0 s kratší než třetí a má vyšší 95. percentil bočního zatížení (0,971 proti 0,900 g). Jde o pozorované rozdíly mezi \textbf{segmenty}, nikoliv o prokázaný zisk času na stejné trati. K posuzování jezdce nebo nastavení auta je nutná ověřená společná startovní čára a srovnatelná trajektorie. Osmička ani ustálený skidpad nejsou touto sadou potvrzené.

\clearpage
\section{Rázy a anomálie, které stojí za prohlédnutí}
\fig{transients.png}{105mm}{Původní 500Hz vzorky v okolí dvou událostí. Tyto vysokofrekvenční detaily nejsou patrné stejně výrazně po filtraci 2 Hz.}
\begin{itemize}
\item \key{863,907255 s: vrchol gyroskopu Y přibližně $-220{,}95^\circ$/s v krátké sérii prudkých výkyvů.} Ty mohou významně ovlivnit integraci orientace. Z IMU samotné nelze spolehlivě rozlišit skutečný rychlý pohyb a chybu jednotlivých měření; tato událost není tím samým šestiosým opakovaným digitálním vzorem jako dlouhá porucha.
\item \key{898,331268 s: osa Z dosahuje 2,211 g; v 898,355267 s klesá na $-0{,}269g$.} Rychlé střídání je kompatibilní s rázem a odlehčením, případně anomálií čidla. Bez videa, povrchu tratě a druhého snímače nelze určit příčinu. Osa Z zde obsahuje i gravitační složku, není to čisté svislé zrychlení karoserie.
\item \key{1008,24 s: přechod do dlouhé digitální poruchy.} Následující zdánlivé extrémy nesmějí vstupovat do hodnocení jízdy. Správný CRC je neodhalí, protože vadná hodnota byla zapsána již před jeho výpočtem.
\end{itemize}
V jízdním intervalu 677--1007 s je 165\,000 nových A/G vzorků a \textbf{žádný zaznamenaný příznak clippingu}. Pro tuto pasáž tedy není doloženo překročení nastaveného rozsahu. To nevylučuje jiné poruchy nebo šum a neříká nic o měření uvnitř následného vadného proudu.

\key{Praktický závěr:} před dalším dlouhým měřením má vyšší prioritu ověřit stabilitu komunikace a chybové příznaky než dále zvyšovat vzorkovací frekvenci. Návrh konkrétní opravy hardwaru nelze z těchto CSV určit; pro diagnostiku chybí přímý záznam komunikace a napájení.

\clearpage
\section{Závěry a navazující ověření}
\begin{tabularx}{\linewidth}{@{}p{35mm}X@{}}\toprule
Co lze uzavřít & Opora v datech a omezení\\\midrule
Pozorované zpomalení kolem 1 g & Více oddělených událostí, 1,067 g maximum po 2Hz filtru, 0,866 g sekundový průměr. Odhad z IMU; nejde o certifikaci brzd.\\
Výrazné boční zatížení & Maximum 1,127 g a 95. percentil $|a_b|$ 0,921 g v 330 s. Bez rychlosti a řízení neurčuje stabilitu podvozku.\\
Časové překrytí zpomalování a zatáčení & 32,09 s nad oběma prahy. Bez tlaku brzd nepotvrzuje techniku jezdce.\\
Pracovní segmenty připomínající kola & Čtyři úseky 48,5--55,5 s, ale slabá korelace profilů a chybějící časomíra. Nelze vyhlásit nejlepší ověřené kolo.\\
Měření potřebuje diagnostiku & 78,05\,\% všech řádků s prokázaným poruchovým vzorem; příčina závady nezjištěna.\\\bottomrule
\end{tabularx}

\subsection*{Co doplnit v příštím testu}
\begin{enumerate}[leftmargin=6mm,itemsep=4pt]
\item \textbf{Ověřit montáž a orientaci senzoru.} Označit fyzické směry X/Y/Z a zaznamenat klid před jízdou i po jízdě. Oddělit kalibraci od jízdního úseku.
\item \textbf{Přidat nezávislou rychlost a časovou referenci.} GNSS nebo rychlost kol a společná časová značka umožní ověřit integraci a opakované průjezdy. Výslednou trasu nepřizpůsobovat rozměru 82 × 130 m jako náhradu měření.
\item \textbf{Pro hodnocení brzd přidat brzdový tlak nebo pedál.} Teprve potom lze rozlišit brzdění, dojezd a jiné příčiny záporného podélného zrychlení. Pro podvozek doplnit úhel řízení.
\item \textbf{Zaznamenávat diagnostiku souběžně s měřením.} Stavy senzorů, nové vzorky, chyby komunikace, přetečení a resety; ověřit dlouhý běh na stole i při vibracích. Zachovat původní časové značky.
\end{enumerate}

\subsection*{Jak výsledky znovu najít a přepočítat}
V aplikaci otevřete záznam 181. Sekce \emph{Statistiky a brzdné události} obsahuje klikatelné extrémy, nastavení prahů a export událostí. Akce \emph{Vlaječka maximum} označí vrchol; \emph{Hranice} vytvoří dva body pro export původních dat mezi nimi. ID B01--B102 patří k výchozím prahům tohoto reportu; při změně parametrů se přepočítají.

Výpočty jsou sdílené s aplikací v \path{app/analysis_core.js}. Reprodukce: \path{build_driving_analysis.mjs}, \path{make_driving_report.py}, kompilace tohoto projektu. Doprovodné výsledky: \path{Analyza_jizd.json}, \path{Brzdne_udalosti.csv}, \path{audit_deceleration_all.csv}. Časy jsou relativní k začátku příslušného CSV, nikoliv UTC. Zdrojem závěrů jsou dodaná měření a popsané výpočty, nikoliv externí jízdní reference.

\small\color{muted}Zdroj jízdních závěrů: \path{boot_000181_run_001.csv}. SHA-256:\\
\path{@SHA@}
\end{document}
'''
values={'BRAKE':num(-s['long']['min']),'BRAKEMS':num(-s['long']['min']*9.80665),'SECOND':num(d['strongest_second']['mean_g'],3),'ACCEL':num(s['long']['max']),'LATERAL':num(max(abs(s['lat']['min']),abs(s['lat']['max']))),'EVENT_ROWS':event_rows,'LAP_ROWS':lap_rows,'THRESHOLD_ROWS':threshold_rows,'SENSITIVITY_ROWS':sensitivity_rows,'SHA':d['sha256']}
for key,value in values.items():source=source.replace('@'+key+'@',value)
assert not __import__('re').search(r'@[A-Z_]+@',source)
(R/'main.tex').write_text(source,encoding='utf-8')
print('Report source and 6 figures ready.',flush=True)
print('Mount sensitivity',sensitivity,flush=True)
