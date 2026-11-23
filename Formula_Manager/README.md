# Formula GNSS Manager

Český správce jízd pro Raspberry Pi 5 s 2 GB RAM a přijímač simpleRTK3B Pro s modulem Septentrio mosaic-X5. Web i záznam běží na Pi. Uložené jízdy zůstávají na jeho NVMe.

Naměřená data základny můžeš nahrát na NVMe přes Sambu nebo vložit na USB. Záložka **Výpočet PPK** je použije k výpočtu přesné trasy a uloží souřadnice do databáze. [Postup pro Tailscale, Sambu a výpočet PPK](PPK.md)

## První jízda

### Stacionární měření přesnosti

V kartě **Přesnost** založ místo, zapiš fyzickou značku a způsob ustavení antény. Znáš-li její nezávisle zaměřené souřadnice WGS84, můžeš je zadat také. Umísti střed antény pokaždé nad stejný bod, zvol interval v sekundách a spusť test. Pi vzorkuje i po zavření prohlížeče. Bere čerstvé platné polohy s GNSS časem, nejvýše jednou za nastavený interval. Mezery při odpojení GPS nedoplňuje. Vynucenou pevnou polohu přijímače vynechá. **Zastavit** ukončí měření. **Vynulovat a začít znovu** archivuje dosavadní test a založí nový na stejném místě se stejným intervalem.

Body se promítají z elipsoidu WGS84 do místní vodorovné roviny východ–sever ukotvené první platnou polohou dané značky. Šikmá vzdálenost ani změna výšky se do odskoku nezapočítají. Těžiště je aritmetický průměr souřadnic všech vzorků testu. Pro každý bod se spočítá jeho vodorovná vzdálenost od tohoto těžiště. Karta zobrazí maximum a průměr těchto vzdáleností. Polární náhled dlouhých testů zobrazuje výběr bodů včetně nejvzdálenějšího, statistiky zahrnují všechny. [Transformace do místních souřadnic](https://proj.org/en/stable/operations/conversions/topocentric.html)

Při příští návštěvě vyber stejné místo a spusť další test. Tabulka porovná těžiště s první dokončenou sérií s body nebo se sérií zvolenou tlačítkem **Jako referenci**. Ukazuje posun na východ, na sever a celkovou vzdálenost. Popsaná značka bez nezávisle zaměřených souřadnic slouží pro měření opakovatelnosti. Známé souřadnice navíc umožní vyčíslit odchylku od značky. Místa, surové souřadnice, režimy řešení i jednotlivé testy uchovává samostatná databáze `accuracy.sqlite3` v datovém adresáři. Po restartu je rozpracovaný test označen jako přerušený.

### Export dat a soubory

Vlož flash disk do USB portu na Pi. V kartě **Export na USB** vyber jednotku a podle potřeby stiskni **Připojit**. Zvol jízdy, testy přesnosti nebo obojí, pak ruční výběr, vše, nové položky pro danou jednotku, nejnovější počet nebo posledních X × 24 hodin podle začátku záznamu. Exportují se ukončené a přerušené záznamy. Export běží na Pi a pokračuje po zavření prohlížeče. Po dokončení můžeš otevřít složku výsledku nebo stisknout **Bezpečně odpojit**. Volba **Exporty na NVMe** vytvoří stejnou strukturu na místním SSD.

Každý export má vlastní adresář s manifestem. Jízda obsahuje CSV vzorků, CSV událostí, původní SBF a metadata. Test obsahuje popis místa, souřadnice, odchylky od těžiště, poloměry, azimuty a statistiky. V metadatech najdeš velikosti a SHA-256 souborů. Na FAT se velké soubory dělí na části pod limitem 4 GiB. SBF části se pro další práci spojí binárně v pořadí uvedeném v metadatech. Dokončený export se zpřístupní po potvrzení zápisu na médium. **Soubory** prochází exportní složku na NVMe a adresáře na připojeném USB, zobrazí jejich velikosti a umožní stažení. USB mount zajišťuje systémový UDisks. [Oprávnění UDisks](https://storaged.org/doc/udisks2-api/latest/udisks-polkit-actions.html)

V průzkumníku můžeš zvolit **Data loggeru na NVMe** a stáhnout databázi jízd, přesnosti, přenosů nebo hardwaru. Pro stažení živé databáze Pi vytvoří konzistentní snímek SQLite na NVMe, který zahrnuje i potvrzené transakce v souboru WAL. Dočasný snímek po přenosu uvolní.

### Hardware

Od spuštění služby zapisuje Pi každých pět sekund jeden vzorek do `/var/lib/formula-manager/hardware.sqlite3` na NVMe. Záznam běží také mezi jízdami a při zavřeném webu. Tabulka `samples` uchovává čas `t` v milisekundách od počátku Unixové epochy, teploty čipu a NVMe, teplotu chladiče a otáčky ventilátoru, pokud je čidlo poskytuje, vytížení CPU a počty bajtů RAM a úložiště. Nedostupný údaj má hodnotu `NULL`. Dostupná RAM zahrnuje také mezipaměť, kterou Linux může uvolnit pro aplikace.

Na kartě **Hardware** vyber délku grafu 5, 15 nebo 30 minut. Pro starší měření zadej datum a čas konce období v místním čase prohlížeče. Tlačítko **Zpět na živá data** vrátí graf k aktuálním měřením. Databáze se po restartu zachová a služba staré vzorky automaticky nemaže. Celou databázi lze stáhnout v **Soubory → Data loggeru na NVMe → hardware.sqlite3**.

### Zahájení jízdy

1. Připoj počítač nebo telefon ke stejné Wi-Fi jako Pi a otevři [formula-logger.local](https://formula-logger.local/). Jméno v místní síti ohlašuje Avahi přes mDNS. Pokud router odděluje klienty nebo blokuje multicast, zjistíš IP adresu Pi v seznamu připojených zařízení.
2. Ověř otisk certifikátu HTTPS podle [návodu k instalaci](../docs/instalace.md).
3. Přihlas se jako `formula69` heslem nastaveným při instalaci Raspberry. Web má samostatně uložený ověřovací údaj. Pozdější změna hesla přes SSH se do webu automaticky nepřenese.
4. V **Živém přehledu** zkontroluj položky **Přijímač** a **Řešení polohy**. S připojeným USB můžeš nahrávat i bez fixu. Po připojení GNSS antény vyzkoušej příjem venku s výhledem na oblohu. Jakmile přijímač vrátí platnou polohu, objeví se bod a během pohybu trasa.
5. Stiskni **Spustit záznam**, zadej název jízdy a potvrď. Zkontroluj, že přibývá počet uložených vzorků. Nyní můžeš zavřít prohlížeč nebo se odpojit od Wi-Fi. Záznam na Pi pokračuje.
6. Po jízdě vyber **Zastavit záznam**. V **Záznamech jízd** otevři příslušnou jízdu. Zobrazíš trasu a graf rychlosti, výšky nebo počtu satelitů. CSV obsahuje všechny dekódované polohové zprávy dané jízdy, SBF původní data z USB2. Jízdu můžeš přejmenovat nebo po potvrzení smazat. Zápis běží na jediném SSD.

Manažer si přihlášení pamatuje i po zavření prohlížeče a restartu Pi. Při každé návštěvě a po obnovení spojení nastaví platnost cookie znovu na 400 dní. Otevřená stránka ji prodlužuje také jednou denně. Pro stejný prohlížeč používej stále stejnou adresu, protože jméno a IP adresa mají oddělené cookies. Tlačítko **Odhlásit se** ukončí přihlášení tohoto prohlížeče i na Pi. [Limit platnosti cookies v Chromu](https://developer.chrome.com/blog/cookie-max-age-expires)

## Nastavení přijímače a záznamu

Při měření na prototypu byl nastaven výstup **50 Hz**, potvrzení dávky do SQLite po **100 ms** a zapnutá **surová GNSS pozorování**. To odpovídá zhruba pěti polohovým zprávám v jedné potvrzené transakci. Počet může kvůli časování USB a systému kolísat. Interval zápisu není zaručená horní hranice ztráty dat při odpojení napájení. Živý přehled se obnovuje přibližně jednou za sekundu. Graf a mapa vykreslují výběr bodů, takže pro výpočty použij plný export.

V **Nastavení** můžeš při zastaveném záznamu zvolit 1, 5, 10, 20 nebo 50 Hz, interval zápisu a surová pozorování. Volby se ukládají na Pi. Kolektor přes USB1 přečte obsazení výstupních streamů, nastaví svůj stream na USB2 a přečte konfiguraci zpět. Zapnutí surových pozorování přidá bloky MeasEpoch, MeasExtra a navigační bloky. Pro pozdější PPK potřebuješ také časově odpovídající záznam základny a skutečná družicová měření.

Pro ostatní parametry zvol **Nastavení → Rozhraní přijímače**. Otevře se originální web Septentrio přes zabezpečenou bránu na portu 8444. Brána vyžaduje přihlášení v manažeru na témže hostiteli. Samotný přijímač má vlastní účet. Změny výstupů mohou přerušit měření. Při úpravách ponech USB2 pro kolektor. [Uživatelská příručka desky a přihlášení k přijímači](https://www.ardusimple.com/user-guide-simplertk3b-pro/)

Mapa na místní síti vykreslí souřadnice a trasu bez internetu. Tlačítkem **+** lze živou i uloženou trasu přiblížit až na milimetrové měřítko. **Vycentrovat** přesune pohled na živou polohu a zachová zvolené přiblížení. Přesnost zaměření závisí na řešení GNSS. Volba **Podklad OSM** načte uliční mapu přes internet. Při největším zvětšení zůstává pod trasou mřížka. Liberec slouží jako výchozí střed pohledu. [Leaflet](https://leafletjs.com/) · [Mapový podklad OpenStreetMap](https://www.openstreetmap.org/copyright)

### Provoz Pi a záloha přijímače

Na **Živém přehledu**, v **Nastavení** a v technickém zobrazení GPS najdeš panel Raspberry Pi. USB2 ukazuje rychlost příjmu SBF v aplikaci. Wi-Fi a datový oddíl NVMe zobrazují rychlosti spočtené z rozdílů systémových počítadel po pěti sekundách. Zápis na oddíl zahrnuje provoz celého systému. Graf CPU zobrazuje posledních 60 sekund z databáze hardwaru.

V **Nastavení → Záloha na microSD přijímače** zkontroluj stav DSK1 a stiskni **Nastavit obsah záznamu**. Otevře se přímo v manažeru stránka **Logging** z firmwaru Septentrio. U výstupu na DSK1 vyber typ zpráv a interval. Pro běžnou polohu lze vybrat NMEA, pro postprocessing měřicí a navigační bloky SBF. Použij ovládání přijímače pro potvrzení změny. Volba **Save current configuration to boot configuration** uloží aktuální konfiguraci celého přijímače také pro jeho příští start. Aktivní zápis zkontroluj podle stavu DSK1. [Příručka desky simpleRTK3B Pro](https://www.ardusimple.com/user-guide-simplertk3b-pro/)

### Připojení bez známé Wi-Fi

V **Nastavení → Wi-Fi připojení** můžeš přidávat a odebírat profily. Přetažením nebo šipkou změníš pořadí uložené v NetworkManageru. Číslo 1 je nejvyšší priorita. Při první inicializaci jsou přednostně seřazeny právě připojená běžná Wi-Fi, eduroam a připravený hotspot. Přesunutí profilu ponechá současné spojení v provozu a uplatní se při dalším výběru sítě. Prázdný hotspot hledá pouze sítě zařazené výše. Před odebráním aktivního profilu počítej s přerušením připojení.

U profilu **eduroam** zvol **Doplnit účet**, vyplň úplné školní jméno a heslo pro vzdálený přístup TUL. Do té doby je automatické připojení profilu vypnuté. Nastavení používá PEAP/MSCHAPv2, certifikační autoritu TUL a kontrolu jmen obou univerzitních RADIUS serverů. [Technické údaje TUL](https://liane.tul.cz/wifi/eduroam_parametry) · [Profil TUL v eduroam CAT](https://cat.eduroam.org/?idp=366)

V dosahu školní sítě stiskni u eduroamu **Ověřit přihlášení**. Test vyhledá síť, zkusí uložený účet a ověří, že Pi dostalo IP adresu. Probíhá lokálně a web může na chvíli ztratit spojení. Pi si před změnou připojení vytvoří bod obnovení v NetworkManageru. Po testu se pokusí obnovit původní síť a výsledek s časem zůstane v Nastavení i po zavření stránky. Uložení nových údajů předchozí výsledek vymaže.

Když je dostupná uložená Wi-Fi, Pi se k ní připojí. Jinak NetworkManager spustí na integrovaném rádiu síť **formula69** (WPA2). Připoj se k ní a otevři [formula-logger.local](https://formula-logger.local/). Pi na hotspotu přiděluje IP adresy a poskytuje místní DNS na `10.69.0.1`. Podporuje také mDNS.

Dokud je k hotspotu připojený klient, Pi jeho spojení zachová. Přibližně každé dvě minuty zkontroluje volný hotspot a pokusí se vrátit k dostupné uložené Wi-Fi. Pokud ovladač neumí vyhledat okolní sítě při vysílání, při kontrole prázdný hotspot nakrátko uvolní. Na další instalaci s názvem hostitele `formula-logger` lze nastavení zopakovat příkazem `sudo bash deploy/wifi-fallback.sh`; heslo se zadává skrytě. [Priorita připojení v NetworkManageru](https://networkmanager.dev/docs/api/latest/settings-connection.html)

## Ukládání a provoz

`collector.py` přijímá data i při zavřeném webu, kontroluje CRC paketů SBF a během záznamu ukládá surový proud i dekódované vzorky. `server.py` obsluhuje přihlášení, ovládání, čtení a export. Neprivilegovaná služba `formula-manager` běží pod systemd. Nginx ukončuje HTTPS a zprostředkuje přístup k originálnímu webu přijímače. Tato verze běží přímo na Raspberry Pi OS a používá distribuční Python a pySerial. [Rozhraní GNSS přes USB](https://github.com/septentrio-gnss/Septentrio-SUPL-3GPP-LPP/blob/main/getting_started.md)

Databáze je `/var/lib/formula-manager/logger.sqlite3`. Jedna služba zapisuje do SQLite v režimu WAL s `synchronous=FULL`, ostatní spojení mohou současně číst potvrzená data. Čas `t_ms` je čas příjmu podle systémových hodin Pi. Pro čas měření uchovej `gps_week` a `tow_ms` i původní SBF. Bez platného GNSS času mohou být tyto hodnoty prázdné. [SQLite WAL](https://sqlite.org/wal.html)

V záložce **Záznam po spuštění** zaškrtni **Spustit záznam po zapnutí Raspberry Pi**, vyber frekvenci polohy, interval zápisu na NVMe a RAW měření pro PPK. Stiskni **Uložit profil**. Profil můžeš upravit i během jízdy. Uplatní se při příštím zapnutí Pi. Pro ručně zahájené jízdy se hodnoty ukládají zvlášť v **Nastavení → Ručně spuštěný záznam**.

Po zapnutí logger počká na USB přijímač, ověří jeho nastavení a založí jízdu i bez fixu, Wi-Fi nebo otevřeného prohlížeče. Po odpojení a návratu USB pokračuje stejná jízda se stejným profilem. Ruční zastavení platí do dalšího zapnutí desky. Po pádu procesu uprostřed automatického záznamu vznikne nová jízda s dosavadními parametry a nedokončená jízda zůstane označená jako přerušená.

### Diagnostika a nastavení GPS

V **GPS diagnostika → Přehled přijímače** vidíš polohu a její směrodatnou odchylku, kvalitu příjmu, počty používaných a sledovaných družic podle konstelace, NTRIP a Ethernet. Datové toky zobrazují rychlost vypočtenou z posledních dvou čítačů odeslaných bajtů. Kruhový graf ukazuje interní disk přijímače, časový graf vytížení jeho CPU během sledování. Otevřený přehled si vyžádá doplňkové stavové bloky přes USB nejvýše jednou za čtyři sekundy. Při běžícím záznamu se tyto bloky uloží také do SBF jízdy. [Příručka Septentrio mosaic-X5, kapitola 4](https://docs.sparkfun.com/SparkFun_GNSS_mosaic-X5/assets/component_documentation/firmware/mosaic-X5_Firmware_v4.15.0_Reference_Guide.pdf)

V **Data a konfigurace** sleduj poslední blok každého typu SBF přijatého na USB2, počet zpráv, čas příjmu, jednotlivá pole a původní HEX. Volba **Pozastavit náhled** zastaví obnovu zobrazení během čtení. **Načíst diagnostické bloky** jednorázově vyžádá z přijímače jeho identifikaci, informace o kanálech, viditelnosti družic, geometrii, signálu, čase a vstupech.

V **Konfigurace GPS** vyhledej parametr z katalogu připojeného firmwaru. **Přečíst hodnotu** zobrazí odpověď desky. U podporovaných změn můžeš otevřít **Syntaxe**, vyplnit argumenty a změnu použít. Manažer ukáže nově přečtenou hodnotu. Například pro elevační masku polohového řešení používá parametr ElevationMask argumenty ve tvaru `PVT, 10` (stupně). Přímý zápis z manažeru je dostupný při ukončeném záznamu. Pro všechna ostatní nastavení otevři **Otevřít web GPS** a přihlas se účtem desky. Ve webu výrobce najdeš i expertní konzoli pod **Admin → Expert Control** a správu uložené konfigurace Boot. [Příručka mosaic-X5](https://www.ardusimple.com/wp-content/uploads/2024/10/mosaic-X5-Firmware-v4.14.10-Reference-Guide.pdf) · [Dekodér pysbf2](https://github.com/semuconsulting/pysbf2)

### RTK z vlastní základny

1. V **Nastavení → RTK korekce** zvol **Základna přes TCP**, pokud základna nebo její počítač poskytuje binární proud RTCM 3. Zadej jeho IPv4 a TCP port. Pro rádio zvol **Sériové USB rádio**, připoj transparentní modem nebo USB–UART, vyber jeho stabilní identifikátor a nastav stejnou rychlost jako na rádiu. Zdroj musí dodávat složené zprávy RTCM 3 včetně referenční polohy základny a družicových pozorování.
2. Podle potřeby zapni **Předávat kopii do pitu** a vyplň IPv4 a UDP port přijímající aplikace. Stiskni **Uložit RTK**. Raspberry ověřuje délku zpráv a CRC‑24Q, předává platné zprávy do vstupu RTCMv3 přijímače na USB2 a volitelně do pitu. USB2 souběžně vrací SBF. Spojení se po výpadku obnovuje.
3. V nastavení sleduj počet přijatých zpráv, počet zápisů do USB, počet odeslaných datagramů a čas poslední zprávy. Doručení UDP ověř na přijímajícím zařízení. V **Živém přehledu** sleduj řešení polohy hlášené přímo přijímačem (RTK float nebo RTK fix).

### Data pro PPK

Volba **RAW měření pro PPK** přidává do SBF měřicí bloky MeasEpoch a MeasExtra a dostupná navigační data GPS, GLONASS, Galileo a BeiDou. Na začátku jízdy a při obnovení USB logger také žádá o známé efemeridy a údaje o přijímači. Po jízdě otevři její detail a stáhni **SBF**. U nových jízd detail uvádí počet epoch MeasEpoch s alespoň jedním družicovým měřením a počet navigačních bloků. Bez antény může růst velikost SBF i počet polohových zpráv, zatímco počet družicových epoch zůstává nulový. Pro PPK zaznamenej ve stejném čase surová měření také na vlastní základně a uchovej souřadnice její antény. [Referenční příručka mosaic-X5](https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/6684/mosaic-X5%20Firmware%20v4.14.10.1%20Reference%20Guide.pdf)

Přes SSH zjistíš stav následujícími příkazy.

```sh
systemctl status formula-manager nginx --no-pager
journalctl -u formula-manager -b --no-pager
ls -l /dev/serial/by-id/
df -h /var/lib/formula-manager
```

Instalační soubory jsou v `deploy/`. Na tomto Pi lze verzi aktualizovat zkopírováním složky na Raspberry a spuštěním `sudo bash deploy/install.sh` v době, kdy neprobíhá záznam. Skript ověřuje certifikát konkrétního přijímače, zachová existující webový účet i uložené jízdy a restartuje službu. Ruční integrační kontrola `python deploy/check_live.py formula-logger.local --cafile web.crt` se spouští na počítači na stejné síti a vytvoří pojmenovaný testovací záznam.

## Ověření na fyzickém zařízení 18. 11. 2026

- Zkouška s lokálním TCP zdrojem na Raspberry ověřila dvě platné testovací zprávy RTCM 1029, předání obou do fyzického USB2 a shodu obou UDP datagramů po jednotlivých bajtech. Poškozená třetí zpráva zvýšila počet chyb CRC a nebyla předána. Testovací zpráva byla textová, bez polohy základny.
- Po restartu celého Pi začala před přihlášením jízda č. 5 s profilem 50 Hz, 100 ms a RAW. Binární export obsahoval 729 polohových zpráv, 729 bloků MeasEpoch, 729 MeasExtra, 108 navigačních bloků a jeden ReceiverSetup. Bez antény bylo všech 729 měřicích epoch prázdných. Test skončil ručním zastavením jízdy, automatický start zůstal zapnutý.


- Z počítače přes Wi-Fi proběhlo přihlášení, nastavení frekvence, spuštění i ukončení záznamu. Během jízdy přibýval počet potvrzených vzorků i při souběžném čtení.
- Přes **Rozhraní přijímače** proběhlo také samostatné přihlášení účtem výrobce. Originální web zobrazil mosaic-X5, nula sledovaných družic a nabídky GNSS, Communication, Corrections, NMEA/SBF Out, Logging a Admin.
- Záznam č. 1 při 5 Hz obsahoval 50 polohových zpráv a 7 440 bajtů surových dat. Binární export obsahoval bloky s platným CRC a počet řádků CSV souhlasil s databází.
- Záznam č. 2 při 50 Hz obsahoval 471 polohových zpráv a 64 696 bajtů. Rozdíl krajních časů příjmu na Pi byl 9,400 s, tedy 470 intervalů při 50,0 Hz. V obou testech byl přijímač bez antény a počet platných poloh byl nula. Ověření skutečné trasy, přesnosti polohy a obsahu PPK pozorování při příjmu družic vyžaduje venkovní jízdu.

