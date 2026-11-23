# RTK GNSS/IMU — semestrální práce a rešeršní zpráva TUL

Aktualizace integrace do vozidla: 13. 10. 2026. Výběr a cenový snímek
původní GNSS/IMU sestavy zůstávají k 30. 9. 2026. Projekt používá TUL 2.3,
třídu tulthesis (FM, SP, twoside), XeLaTeX a Biber. Lokální písma jsou součástí
projektu. Oba dokumenty sdílejí texty a settings.tex. Pro tisk a vazbu mají
vnitřní okraj 30 mm a vnější 20 mm; šířka sazby A4 je 160 mm. Horní a dolní
rozměry zůstávají podle školní šablony. Oba hlavní dokumenty používají
režim `twoside` pro oboustranný tisk: liché stránky mají 30 mm vlevo
a 20 mm vpravo, sudé 20 mm vlevo a 30 mm vpravo. Tisknout oboustranně
s převracením přes dlouhý okraj, ve skutečné velikosti 100 %, nikoli
přizpůsobit stránce. Zachovat pořadí všech stran PDF včetně případných
prázdných stran, aby se neposunula strana vazby.

## Integrace do vozidla - centrální ADC, návrh k 13. 10. 2026

- Nová kapitola 3 spojuje bakalářskou práci s celovozidlovou senzorikou.
- Analogové snímače vedou samostatně přibližně 1,5 m k centrální vstupní
  desce u Pi. Kandidát ADC je MCP3208, 8 kanálů/12 bitů/SPI; Pi samo nemá
  analogové vstupy na GPIO. Čtyři polohové kanály: oživení 200 Hz, cíl 500 Hz
  na kanál. To vyžaduje 2000 převodů/s; nejde o hotové ani synchronní měření.
- CAN 1: auto -> RPi, 1 Mbit/s, listen-only. CAN 2: RPi -> auto, předběžně
  500 kbit/s; jen vybraná data pro ADU. CAN 3 a CAN 4 ani dva nápravové MCU
  nejsou součástí výchozí instalace. Zůstávají pouze záložním řešením.
- Otáčky se čtou přes chráněné digitální vstupy a časované události GPIO;
  termočlánky mají čtyři centrální specializované převodníky. U MLX90614
  je k ověření PWM přenos s centrálním převodem střídy na napětí; dlouhé
  neověřené I2C není výchozí kabeláží. Nelze považovat všechna čidla za analogová.
- Měřen je roll/heave, nikoli odklon kol; u brzd třmeny. Počet kanálů,
  mechanika a kabeláž čekají na ověření v CAD. Schéma vstupů ještě není hotové.
- Výpočty pokrývají ADC 200/500 Hz, obsazení SPI, hrany kol, datový záznam
  a přírůstek CAN 2. Rozměr kola, počet cílů i ukládací formát jsou předpoklady.
- Pi 5 potřebuje jen dvě externí CAN rozhraní; jeden 2-CH CAN HAT+ je kandidát.
  Společná pinová mapa ADC, IMU, PPS, teplot, CAN, M.2 HAT+ a časování se ověří.
- Před přijetím centrálního řešení: skutečný kabel, šum při provozu auta,
  přesnost a fázový posun, jitter a mezikanálové zpoždění pod plnou zátěží.
- Napájení: elektronicky jištěný výstup stávající PMU -> 8-16 V ->
  DC/DC -> 5 V. Pololu D42V55F5 zůstává dosavadní referenční kandidát,
  nikoli schválený nákup; levnější náhrada dosud není vybrána.
  Samostatná tavná pojistka není automatický nákup;
  ověřit nastavení PMU, ochranu kabeláže, rozběh, přepětí, úbytky a vypínání.
  Konkrétní typ PMU a kanál ještě doplnit. Není to hotový automobilový zdroj.
- Původní BOM a nákupní seznam nejsou rozpočtem celé senzoriky. Nové
  komponenty nejsou v jejich součtu automaticky zahrnuty.
- Stejná kapitola je v main.tex i research.tex, se společnými okraji
  30 mm u vazby a 20 mm na vnější straně.

## Současná sestava GNSS/IMU

- Rover: ArduSimple simpleRTK3B Pro se Septentrio mosaic-X5 a u-blox ANN-MB2-00.
- Jediná přenosná základna: simpleRTK2B Budget se ZED-F9P a u-blox ANN-MB2-00.
  Celkem dvě stejné GNSS antény: jedna pro rover a jedna pro základnu.
  Cílově UART do XIAO, vlastní webová správa přes Wi-Fi a místní raw logger;
  v první etapě raw log na týmovém notebooku. Úložiště základny dosud neoceněno.
- IMU: Adafruit ICM-20948, kód RPiShop ADA076. Původní ISM330DHCX je zachována
  v rešerši jako dříve uvažovaná alternativa, nikoli další nákup.
- Akcelerometr a gyroskop: nominálně 562,5 Hz, ±16 g a ±2000 °/s.
  Magnetometr: nejvýše 100 Hz, použití až po kalibraci a ověření rušení.
- Raspberry Pi 5 2 GB, Active Cooler, M.2 HAT+ a vlastní NVMe 2230/2242.
  Raspberry Pi OS; přímé SPI a INT, GNSS PPS na GPIO. Časová nejistota se musí
  změřit, nepředpokládá se bezchybný hardwarový timestamp každého raw vzorku.
- Čtyři XIAO ESP32S3 + Wio-SX1262 sady SEE319. Dvě pro aktivní LoRa spoj,
  dvě plánované pro vývoj a rezervu. Vlastní USB/UART–LoRa firmware pro RTCM
  místo předinstalovaného Meshtastic. ESP32 neobsluhuje sběr IMU.
- Dva dodavatelé: RPiShop a ArduSimple. Elektronika 24 289,53 Kč bez DPH,
  přibližně 24 290 Kč. Napájení, doprava, kabeláž a mechanické díly nejsou
  v tomto mezisoučtu; SSD a vývojový notebook základny jsou vlastní.

## Zdůvodnění aktualizace košíku

- Rozlišena přesnost vůči základně (místní ENU) a přesnost absolutního
  umístění na mapě. Uložený počátek a ustavení jsou nutné pro porovnání jízd.
- Doplněno posouzení Holybro UART/DroneCAN pro základnu. simpleRTK2B volím
  pro přístup k rozhraním a vlastní konstrukci, ne pro údajně přesnější čip.
- Vysvětlena náhrada Budget Survey druhou ANN-MB2: vlastní kryty, sjednocení
  a úspora 37 EUR. Popsán pevný kabel, zemní plocha a nutnost A/B testu montáže.
- Oddělena autonomní základna od prvního laboratorního provozu s notebookem.
  Vlastní firmware, úložiště, napájení a jejich ověření ještě nejsou hotové.
- Mouser je pouze dražší nákupní alternativa. Košík a BOM zůstávají RPiShop
  + ArduSimple; jeho položky ani cenový snímek tato obsahová aktualizace nemění.
- Abstrakty, úvaha autora, diagram, rozpočet, implementační plán, rizika
  a validační kritéria jsou sjednocené v obou výstupech.

Text je návrh a plán validace, nikoli zpráva o uskutečněných experimentech.
U nové IMU jsou uvedeny kompromisy v šumu a stav EOL. LoRa vyžaduje ověření
propustnosti RTCM, rádiových podmínek a reálného pokrytí trati.

## O-Leaf / Overleaf

1. Importovat aktualizovaný ZIP rtk-gnss-semestralka-overleaf.zip.
2. Nastavit kompilátor XeLaTeX.
3. Hlavní dokument main.tex vytváří semestrální práci; research.tex vytváří
   samostatně pojmenovanou rešerši pro školitele.
4. nakupni-kosik.tex vytváří stručný nákupní seznam s veřejnými produktovými odkazy.
5. Ověřit osobní údaje, studijní program a název podle schváleného zadání.

Projekt nemá online závislost na Overleafu; lze jej kompilovat lokálně pomocí
latexmk a Biberu. V kořeni projektu:

```sh
latexmk -xelatex -interaction=nonstopmode -halt-on-error main.tex
latexmk -xelatex -interaction=nonstopmode -halt-on-error research.tex
```

## Struktura

- main.tex, research.tex: vstupní dokumenty se společnými kapitolami.
- frontmatter/: abstrakty a vlastní úvaha autora.
- chapters/01-vyber-systemu.tex: výběr, vývoj rozhodnutí, architektura a zpracování dat.
- chapters/02-realizace-a-overeni.tex: rozpočet, sestavení, zkoušky a rizika.
- chapters/03-integrace-do-vozidla.tex: využití práce ve vozidle, senzorika,
  centrální ADC, CAN 1/2, výpočty přenosu, časování, napájení a validační milníky.
- references.bib: technické a cenové zdroje.
- settings.tex: společná sazba a okraje pro vazbu (vnitřní 30 mm, vnější 20 mm).
- BOM.csv: nákupní datový podklad; neoceněné položky nejsou nulovým nákladem.
- tulthesis.cls, tul.sty, pisma/, loga a symboly: školní balík TUL 2.3.

Oficiální zdroj šablony: https://www.nti.tul.cz/~satrapa/vyuka/latex-tul/

V elektronické příloze jsou zveřejněny autorské texty a výsledné PDF. Školní třídu, loga a písma pro nový překlad poskytuje [šablona TUL](https://www.nti.tul.cz/~satrapa/vyuka/latex-tul/).
