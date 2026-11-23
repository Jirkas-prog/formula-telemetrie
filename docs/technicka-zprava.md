# Palubní záznam a vyhodnocení GNSS

**Elektronická příloha k bakalářské práci Jiřího Buršíka „Využití RTK systému pro telemetrii studentské formule“, Technická univerzita v Liberci, 24. listopadu 2026.** Dokument popisuje vydanou implementaci. Odkazy na moduly vedou na místa, podle nichž lze tvrzení ověřit. Soupis použitého softwaru, dokumentace výrobců a spolupráce s AI je v [registru zdrojů](zdroje.md).

## 1. Co je předmětem měření

Rover na vozidle tvoří přijímač simpleRTK3B Pro s modulem mosaic-X5 a Raspberry Pi 5 s 2 GB RAM a NVMe. Při jízdě vznikají dva odlišné výsledky. Přijímač průběžně odhaduje polohu, kterou lze zobrazit na mapě. Pro pozdější relativní výpočet potřebujeme také původní družicová pozorování roveru, časově souběžná pozorování základny, efemeridy a známé souřadnice antény základny. Samotná trasa tvořená zeměpisnou šířkou a délkou k rekonstrukci fázových pozorování nestačí. [Příručka desky](https://www.ardusimple.com/user-guide-simplertk3b-pro/) · [Dokumentace RTKLIB](https://www.rtklib.com/rtklib_document.htm)

## 2. Cesta jedné epochy

| Krok | Co vzniká | Kde se to ověřuje |
|---|---|---|
| Nastavení přijímače | Kolektor zvolí výstupní bloky a frekvenci přes USB1. Z USB2 přijímá binární proud SBF. | [Konfigurace a čtecí smyčka](../Formula_Manager/collector.py) |
| Přijetí na Pi | U proudových dat rozliší hranice rámců, zkontroluje délku a CRC. U polohového vzorku vede platnost řešení. Surové bajty mají vlastní záznam. | [Kolektor](../Formula_Manager/collector.py), [diagnostika SBF](../Formula_Manager/diagnostics.py) |
| Potvrzení transakce | V SQLite vznikají řádky pro jízdu, vzorky, binární bloky a provozní události. Záznam běží na Pi i při zavřeném prohlížeči. | [Schéma loggeru](../Formula_Manager/collector.py), [služba systemd](../Formula_Manager/deploy/formula-manager.service) |
| Čtení | Web čte přehled nebo uloženou jízdu. Pro analýzu lze stáhnout úplný CSV a SBF. | [HTTP rozhraní](../Formula_Manager/server.py), [uživatelský návod](../Formula_Manager/README.md) |

Čas přijetí `t_ms` pochází ze systémových hodin Pi. Čas měření udává GPS týden a čas uvnitř týdne (`gps_week`, `tow_ms`), pokud jej přijímač poskytl. Pro spárování roveru a základny se používá čas měření. Rozdíl časů přijetí navíc zahrnuje přenos přes USB a plánování procesů. Při diagnostice se proto zvlášť počítají přijaté zprávy, platné polohy a epochy s využitelným měřením. [Datová pole a dekódování](../Formula_Manager/collector.py)

## 3. Databáze a interval zápisu

| Databáze na NVMe | Uložené objekty | Účel |
|---|---|---|
| `logger.sqlite3` | `sessions`, `samples`, `raw_chunks`, `events`, `config` | Průběh jízdy, diagnostika a rekonstruovatelný SBF |
| `accuracy.sqlite3` | `marks`, `runs`, `fixes` | Fyzická značka, série měření a jednotlivé polohy |
| `hardware.sqlite3` | `samples` | Časový průběh zatížení, teplot a kapacity |
| `ppk.sqlite3` | `assets`, `chunks`, `jobs`, `epochs` | Importované soubory, parametry úlohy a její výsledné epochy |
| `transfers.sqlite3` | `sent`, `last_job` | Průběh exportu a evidence již exportovaných položek |

Výchozí profil kolektoru je 50 Hz s intervalem potvrzení 100 ms. Mezi dvěma polohami tedy nominálně uplyne 20 ms a do jedné dávky typicky vstoupí asi pět polohových zpráv. Jednosekundová dávka by za stejných podmínek pojala přibližně padesát. Kratší interval snižuje množství rozpracovaných dat za cenu častější synchronizace disku. Režim WAL umožňuje souběžné čtení potvrzených transakcí. Kolektor používá `synchronous=FULL`; skutečná odolnost při výpadku napájení závisí také na disku a okamžiku výpadku. Pro přenos otevřené databáze nabízí správce konzistentní snímek. [Kolektor](../Formula_Manager/collector.py) · [Export souborů](../Formula_Manager/mediafiles.py) · [SQLite WAL](https://sqlite.org/wal.html) · [SQLite synchronous](https://www.sqlite.org/pragma.html#pragma_synchronous)

## 4. Opakovatelnost stacionárního měření

Anténu při každém opakování ustavíme nad stejnou fyzickou značku. Zapíšeme její polohu, způsob ustavení a interval vzorkování. Pro bodovou sérii program promítá polohy WGS 84 do vodorovné roviny s osami východ a sever. Počátek místního systému přísluší značce. Pro polohy $(E_i,N_i)$ spočte těžiště $(\bar E,\bar N)$ a vzdálenosti

$$d_i=\sqrt{(E_i-\bar E)^2+(N_i-\bar N)^2}.$$

Průměrný odskok je aritmetický průměr $d_i$, maximální odskok je největší $d_i$. Mezi dny se srovnává vodorovná vzdálenost těžišť jednotlivých sérií. Série s jediným bodem má z definice nulový odskok od svého těžiště a neposkytuje odhad rozptylu. I těsný shluk může ležet daleko od skutečné polohy. Absolutní chybu proto vyjadřujeme jen vůči nezávisle zaměřeným souřadnicím. K výsledku patří počet platných epoch, délka a režim řešení. [Implementace stacionárního testu](../Formula_Manager/accuracy.py) · [Topocentrické souřadnice](https://proj.org/en/stable/operations/conversions/topocentric.html)

## 5. Výpočet trajektorie PPK

1. V profilu jízdy zapneme RAW a ukončíme záznam až po měření. Na základně současně zaznamenáme observace a navigaci. Zdokumentujeme referenční bod a elipsoidickou výšku antény.
2. Data základny přeneseme přes USB nebo sdílení SMB. V kartě **Výpočet PPK** provedeme import. Databáze přidělí souboru identifikátor a uchová obsah i SHA-256.
3. Vybereme měření roveru, základny, navigaci a zdroj souřadnic základny. Program převádí podporované binární vstupy nástrojem `convbin` a spouští `rnx2rtkp`. Výsledky přidružuje k úloze, takže lze zopakovat výpočet s jinými vstupy.
4. Porovnáme rozsah epoch, časové mezery a četnost stavů Fix a Float. Podíl Fix je vlastnost řešení. Nezávislou přesnost trasy je třeba stanovit porovnáním s referencí. Nižší frekvence základny vyžaduje ověření na reálných souběžných měřeních.

[Modul PPK](../Formula_Manager/ppk.py) · [Postup obsluhy a podporované vstupy](../Formula_Manager/PPK.md) · [Zdrojový kód RTKLIB](https://github.com/tomojitakasu/RTKLIB)

## 6. Provoz a přejímací kritéria

Web běží nad HTTPS. Samostatné služby řeší záznam, správu profilů Wi-Fi a dočasný test eduroamu. Při tomto testu správce ověří přidělení adresy a zaznamená výsledek návratu na původní síť. Místní přístup používá mDNS, volitelný vzdálený přístup Tailscale a sdílení PPK protokol SMB. Karta Hardware zapisuje údaje průběžně, včetně období mezi jízdami. Chybějící senzor má v databázi hodnotu NULL. [Nastavení sítě](../Formula_Manager/deploy/wifi-profiles.py) · [Hardwarové vzorky](../Formula_Manager/hardware.py) · [Přístup k souborům](../Formula_Manager/PPK.md)

Před vyhodnocením závodní jízdy je třeba doložit návaznost GNSS epoch, případné výpadky, použitý výstupní profil, společné časové pokrytí se základnou a možnost znovu sestavit výsledek z uloženého SBF a referenčních vstupů. Pro převzetí kopie jízdy se porovná počet vzorků a kontrolní součty souborů v manifestu. Dosavadní laboratorní zkoušky a jejich omezení uvádí [protokol ověření](overeni.md).
