# IMU Test — ESP32-S3-LCD-1.47 + Adafruit ICM-20948

**Aktuální ověření (21. 10., boot 139):** finální firmware je nahraný přes OTA a uložený v release/firmware.bin (lokální archiv zkoušek), jeho SHA-256 a protokoly jsou v release/firmware.json (lokální archiv zkoušek). Na poslední přání uživatele je maximum **500 / 500 / 100 Hz**. Vyšší frekvence byly odstraněné z webu, API je odmítá a případné starší uložené hodnoty nad limitem se při startu převedou na 500 Hz. Každá skupina má nadále vlastní nastavení.

Závěrečný záznam při souběžném načítání webových grafů má **40 478 řádků, nulové ztráty, nulová přetečení FIFO a žádnou chybu CRC ani mezeru v pořadí**. Naměřeno 499,996 / 499,996 / 100,537 Hz; drobná odchylka magnetometru vychází z jeho vlastních hodin. Protokol měření (lokální archiv zkoušek). USB na stejném finálním firmwaru prošlo všemi 12 zrušeními zápisu s okamžitým dalším čtením i zápisem v jediné WPD relaci bez odpojování, včetně přerušeného čtení a práce se složkami. Samostatný přenos 16 MiB byl ověřen v bootu 128. [Podrobný protokol USB](docs/usb-cancel-fix.md). Po testu běží nový záznam 500 / 500 / 100 Hz.

**Známé síťové omezení:** LAB-WIFI je hotspot telefonu. Po přibližně dvou minutách přestanou multicastové dotazy `.local` docházet k mDNS responderu ESP32, zatímco přímé dotazy i HTTP přes IP fungují. Neúčinné pokusy s pravidelnými oznámeními byly odstraněné. Použij IP z displeje (při ověření **http://10.32.176.138/**), případně vlastní hotspot desky **http://192.168.4.1/**. [Diagnostika a její hranice](docs/mdns-fix.md).

Jednoúčelový záznamník pro **Waveshare ESP32-S3-LCD-1.47 s USB-A**, 16 MB flash / 8 MB PSRAM, LCD 172 × 320. Varianta 1.47B s USB-C má jiný pin podsvícení a není tímto sestavením podporována.

**Předchozí vydání (boot 123, OTA):** firmware obnovuje registraci aliasu `.local` po získání IP, opětovném připojení a změně adresy. Překlad názvu i HTTP byly fyzicky ověřeny po restartu a dvou připojeních ([protokol mDNS](docs/mdns-fix.md)). Obsahuje také opravu restartovací smyčky při obnově CSV po odpojení napájení, ověřenou v bootu 122. Příčinou byl překročený zásobník SD úlohy, kvůli kterému zůstával displej černý. Po úplné záloze flash byla přes USB nahrána pouze opravená aplikace, se zachováním nastavení; uživatel potvrdil funkční displej. Kontrola skutečného nedokončeného CSV zachovala všech 495 900 platných řádků a automaticky se spustilo nové měření. [Protokol opravy](docs/recovery-stack-fix.md). Aktuální obraz je release/firmware.bin (lokální archiv zkoušek), kontrolní součet a stav ověření v release/firmware.json (lokální archiv zkoušek). Původní zálohy zůstávají zachované.

**Senzor je nyní připojený přes SPI a fyzicky otestovaný.** Opravené časování, čtení FIFO, zpracování magnetometru a souběh webu/USB odstranily reprodukované ztráty. Pětiminutový zátěžový test prošel s nulovými ztrátami; celý CSV má 227 429 ověřených řádků a průměr 500,000 / 500,000 / 100,316 Hz. [Příčiny, opravy a naměřené výsledky](docs/sampling-validation.md).

Po doplnění Wi-Fi klienta prošel další dvouminutový test přímo na LAB-WIFI při načítání stavu a grafů: **0 ztrát, 0 přetečení FIFO, 0 chyb senzoru**. Stažený CSV má **73 340 řádků**, žádnou chybu CRC ani mezeru v pořadí; průměr 499,999 / 499,999 / 100,295 Hz. Protokol (lokální archiv zkoušek). Deska zůstala po ověření v novém záznamu, připojená k LAB-WIFI.

Obnova prošla softwarovými testy přerušení zápisu i opravy a kontrolou reálného logu po odpojení napájení. To nepokrývá všechny možné poruchy FAT ani opakované výpadky během samotné opravy. Windows MTP bylo fyzicky ověřeno až do 16 MiB; po jednom zrušeném zápisu selhalo navazující čtení a pomohlo nové otevření USB relace. Tuto závadu následně opravila verze ověřená v bootu 128; aktuální výsledky jsou v [USB po zrušení přenosu](docs/usb-cancel-fix.md). [Protokol USB](docs/usb-verification.md), [obnova a PDF reporty](docs/recovery-and-reports.md).

## Připojení a první měření

1. Vlož SD kartu s FAT32. Firmware kartu automaticky neformátuje.
2. Při vypnutém napájení připoj IMU podle tabulky níže.
3. Zapni desku. S dostupnou kartou a senzorem automaticky vznikne nový `/logs/boot_XXXXXX_run_XXX.csv`.
4. Připoj telefon k Wi-Fi **IMU-Test**, heslo **IMU-DEMO-CHANGE-ME** (osm znaků).
5. Otevři **http://192.168.4.1/** v běžném prohlížeči. Telefon může upozornit, že síť nemá internet; zůstaň připojený. Pro nahrávání souborů a OTA používej plný prohlížeč, nikoli omezené okno přihlášení k Wi-Fi.

Výchozí logování: **akcelerometr 500 Hz, gyroskop 500 Hz, magnetometr 100 Hz**, I²C, adresa 0x69, ±16 g, ±2000 °/s, dolní propust přibližně 50 Hz. Každá skupina má vlastní nastavitelnou frekvenci. Akcelerometr a gyroskop: 50 / 100 / 200 / 500 Hz; magnetometr: 10 / 20 / 50 / 100 Hz. Magnetometr AK09916 má **pevný rozsah přibližně ±4912 µT**, žádný přepínatelný rozsah.

Pokud senzor nebo SD chybí, web i displej zůstávají dostupné a ukazují chybu. Firmware nevytváří smyšlená měření. Po připojení senzoru / vložení karty desku restartuj, případně ulož nastavení z webu.

**Orientace LCD:** v **Nastavení → Displej ESP32** zvol 0°, 90°, 180° nebo 270° a stiskni **Uložit orientaci**. Změna se projeví hned, i během záznamu, bez restartu. Ukládá se samostatně do NVS a zůstane zachovaná po vypnutí; nastavení senzoru se nemění. Na šířku se aktuální hodnoty a minima/maxima zobrazují vedle sebe. Obě rozložení zachovávají vykreslování po připravených blocích bez průběžného mazání textu. Hardwarové ověření všech poloh za běžícího záznamu a zachování 90° po restartu: protokol (lokální archiv zkoušek).

## Zapojení

Všechny údaje jsou **čísla GPIO**, nikoli pořadí kontaktů konektoru. I²C lze díky ESP32 GPIO matrix používat i na vyvedených GPIO8 a GPIO9; není nutné používat zvláštní konektor na desce.

| ESP32-S3 | Adafruit IMU – I²C (výchozí) |
| --- | --- |
| 3V3 | VIN |
| GND | GND |
| GPIO8 | SDA |
| GPIO9 | SCL |
| 3V3 / pull-up na modulu | CS musí být v logické 1 |

| ESP32-S3 | Adafruit IMU – SPI |
| --- | --- |
| 3V3 | VIN |
| GND | GND |
| GPIO12 | SCL / SCK |
| GPIO11 | SDA / MOSI |
| GPIO13 | SDO / MISO |
| GPIO10 | CS |

STEMMA QT/Qwiic přenáší pouze I²C a napájení. SPI vyžaduje navíc SDO a CS z pájecích kontaktů IMU. Nepřipojuj ESP32 k pinům **1V8, AC, AD nebo FS**. INT není potřebný. I²C pracuje na 400 kHz; SPI na 4 MHz, na samostatném řadiči vedle LCD. Použij krátké vodiče a spolehlivé společné zemnění.

Vestavěný LCD: MOSI45, SCK40, CS42, DC41, RST39, BL48. SD používá samostatné SDMMC ve 4bit režimu: CLK14, CMD15, D0=16, D1=18, D2=17, D3=21.

## Ovládání

- **Nový záznam:** nový soubor, nové minimum/maximum, nová živá historie.
- **Pozastavit:** přestane přidávat vzorky, dopíše frontu, synchronizuje a zavře CSV. SD se tím uvolní pro prohlížení, stahování a nahrávání.
- **Pokračovat:** otevře stejné CSV pro přidávání. Časová osa zachová mezeru vzniklou pauzou.
- **Ukončit:** dopíše a zavře soubor. Příští start vytvoří nový soubor.
- **Nastavení:** změna rozsahů, frekvencí, filtru a sběrnice se uloží do NVS a restartuje desku. Rozběhnutý i pozastavený záznam je nutné nejdříve ukončit.
- **SD karta:** navigace po celé cestě, hledání, řazení, hromadný výběr, přejmenování a přesuny souborů i neprázdných složek. Obrázky včetně JPG a PDF se otevírají na celou obrazovku. Přenosy po blocích mají průběh a pokračování po výpadku. [Podrobný popis](docs/file-manager.md).
- **PDF report:** v nabídce CSV nebo u načtených grafů. Čtyři stránky s extrémy, počty platných odečtů, clippingem a grafy devíti os. Vzniká offline přímo v prohlížeči. [Obnova a reporty](docs/recovery-and-reports.md).
- **Grafy:** společná časová osa, přiblížení, posun, pinch dvěma prsty, přímé zadání časového intervalu a klepnutí pro odečet.

Na LCD je při připojení k uložené Wi-Fi její SSID a skutečná IP adresa. Bez připojení ukazuje údaje hotspotu IMU-Test, jeho heslo a IP. Po dvou sekundách se střídají akcelerometr, gyroskop a magnetometr. Každá osa ukazuje živou hodnotu, minimum a maximum; dole je stav SD, senzoru a záznamu. Žádné tlačítko desky neslouží k ovládání aplikace.

## Síťová nastavení

V **Nastavení → Síťová nastavení** lze uložit až šest sítí, přidat nebo odebrat síť a šipkami změnit pořadí. Deska zkouší sítě od první; po 15 s přejde na další. Fungující spojení zbytečně nepřerušuje kvůli vyšší prioritě. Na připojené desce je první **LAB-WIFI**, její heslo je pouze v NVS desky, nikoli ve zdrojích nebo distribuovaném firmware.

Stejný formulář nastavuje alias (výchozí **imu-test**, tedy **http://imu-test.local/**), IP hotspotu (výchozí **192.168.4.1**) a DHCP nebo pevnou IP ve Wi-Fi včetně masky, brány a DNS. Hotspot zůstává dostupný i při připojení k routeru. Alias .local vyžaduje podporu mDNS v síti a klientovi; přímá IP je vždy na displeji. Uložená hesla se do prohlížeče nevracejí: prázdné pole ponechá dosavadní heslo, otevřenou síť je nutné zvolit výslovně.

Nastavení se uloží do NVS jako jeden celek. Přepnutí sítě je odložené až po HTTP odpovědi; během přenosu souboru je změna odmítnutá. Měření pokračuje. API: `GET/POST /api/wifi`, stav připojení také v `GET /api/status` pod `wifi`. Ověření priorit, alternativní IP/aliasu, statické konfigurace a zachování po restartu: docs/hardware-wifi.json (lokální archiv zkoušek).

## CSV a interpretace dat

CSV má jeden běžný hlavičkový řádek, čárku jako oddělovač a desetinnou tečku. V českém Excelu použij **Data → Z textu/CSV**, oddělovač čárka, místní nastavení pro desetinnou tečku. Nejsou v něm komentáře před hlavičkou. Sousední `.csv.json` obsahuje souhrn při zastavení / pauze.

- `time_us`: monotónní čas řádku od začátku záznamu v mikrosekundách. Nejde o UTC; hotspot nemá přístup k NTP.
- `seq`: pořadí řádku před zařazením do zapisovací fronty. Mezery odhalí ztráty při zaplnění fronty.
- `ax_g,ay_g,az_g`: zrychlení v g, **včetně gravitace**.
- `gx_dps,gy_dps,gz_dps`: úhlová rychlost ve stupních za sekundu.
- `mx_uT,my_uT,mz_uT`: magnetická indukce v µT v nativních osách magnetometru; nejde o kalibrovaný azimut ani sloučenou orientaci vozidla.
- `temp_C`: teplota čipu, nikoli okolního vzduchu.
- `accel_new,gyro_new,mag_new`: 1 pouze při novém odečtu dané skupiny. **Při rozdílných frekvencích se poslední hodnoty ostatních skupin opakují.** Pro statistiku konkrétního senzoru vybírej jeho řádky s příznakem 1.
- `accel_age_us,gyro_age_us,mag_age_us`: stáří posledního odečtu dané skupiny vůči času řádku. Čas magnetometru je okamžik zahájení čtení, nikoli hardwarový timestamp převodu.
- `mag_valid`: 0 při chybě, přetečení či zastarání magnetometru; hodnoty jsou pak `nan`. `mag_overflow` přenáší hardwarový HOFL.
- `crc32`: kontrolní součet nového formátu CSV (schema 3); osm hexadecimálních číslic, CRC-32/ISO-HDLC.
- `clip_mask`: bity 0–2 pro A XYZ, 3–5 pro G XYZ, 6–8 pro M XYZ. Označuje dosažení **98 % rozsahu** nebo magnetický overflow. Senzor skutečnou velikost signálu za saturací nezměří; červená je indikace blízkosti limitu / overflow, nikoli rekonstrukce překročené hodnoty.
- `accel_range_g,gyro_range_dps,accel_rate_hz,gyro_rate_hz,mag_rate_hz,dlpf`: nastavení platné pro záznam.

Řádky vznikají, když přijde nová hodnota některé skupiny. Při odlišných periodách tedy počet řádků za sekundu nemusí být roven jediné zadané frekvenci. Web proto ukazuje zvlášť skutečnou rychlost A/G/M. Nativní ODR A/G je 1125 Hz; firmware vybírá skutečné vzorky z hardwarového FIFO podle požadovaných termínů. Neslibuje hardwarově synchronní převody přesně 500 Hz ani uložení všech 1125 interních vzorků.

## Úplnost, výkon a testování

Měření běží na samostatné FreeRTOS úloze. Zapisovač vlastní SD během záznamu a používá frontu 2048 vzorků v PSRAM a 16KB bloky CSV. Synchronizace probíhá každých 250 ms. Nové řádky mají CRC32 a nedokončený záznam se po zapnutí automaticky kontroluje. Poškozený originál zůstane zachovaný a platná část se obnoví do CSV. Při náhlém odpojení lze stále ztratit poslední buffer/frontu nebo data v cache karty; samotný FAT a elektroniku SD nelze softwarově ochránit před každým výpadkem. [Postup, omezení a testy](docs/recovery-and-reports.md).

Živé grafy vycházejí z RAM: až 4096 časových úseků, každý uchovává minima, maxima a clipping všech devíti os. Po zaplnění se sousední úseky sloučí. **Začátek záznamu ani špičky se neodřezávají**, postupně ale klesá časové rozlišení. Živý odečet proto ukazuje interval a jeho obálku, nikoli předstíraný přesný vzorek. Úplné vzorky jsou v CSV na SD.

CSV prohlížeč čte data postupně do polí v paměti telefonu a umožňuje přesný odečet. Limit jsou 2 miliony vzorků, přibližně 240 MB číselných polí plus režie prohlížeče. Na slabších telefonech používej kratší záznamy. Delší CSV stáhni a analyzuj v počítači. Poškozené řádky parser oznámí a vynechá.

Před jízdou ověř:

1. V klidu: velikost vektoru A přibližně 1 g; G blízko nule. Zapiš teplotu a klidový offset.
2. Otoč každou osu o 90° a ověř znaménka. Magnetometr má vlastní nativní orientaci os; firmware neprovádí fúzi ani převod do souřadnic auta.
3. Vyzkoušej 500/500/100 Hz alespoň deset minut současně s živým webem. Sleduj A/G/M Hz, časové výpadky, ztráty fronty a I/O chyby. Dosažitelnou frekvenci ovlivňuje skutečné zapojení a SD karta.
4. Udělej krátký záznam s úmyslným dosažením nízkého rozsahu a ověř červené úseky CSV grafu.
5. Ve vozidle ověř vibrace, rigidní montáž, připojení a magnetické rušení od proudů a oceli. Magnetometr není bez kalibrace spolehlivý kompas ve vozidle. Tento projekt měří surová fyzikální data, neprovádí kalibraci hard/soft iron ani odečítání gravitace.

## Sestavení, záloha a první instalace

Všechny nástroje, zálohy, buildy a cache zůstávají uvnitř tohoto projektu. Z kořene spusť PowerShell:

```powershell
./scripts/setup.ps1                    # pouze pokud lokální nástroje chybí
./scripts/project.ps1 build
./scripts/project.ps1 test
./scripts/project.ps1 ports
./scripts/project.ps1 backup -Port COM29
./scripts/project.ps1 upload -Port COM29
```

Číslo COM se může změnit. Příkaz `upload` nejdříve sestaví projekt, přečte **celých 16 MB původní flash**, ověří ji příkazem `verify_flash`, uloží SHA-256 a MAC do JSON a teprve potom zapisuje firmware. Neúspěšná záloha nahrání zablokuje. Záloha obsahuje také NVS a existující oddíly. SD se tím nezálohuje ani nepřepisuje.

První vstup do zaváděcího režimu může vyžadovat držet BOOT při připojení USB, pokud předchozí firmware vystupuje pouze jako HID. Verze s MTP používá USB OTG pro přenosné zařízení; původní USB Serial/JTAG port COM se v běžném provozu již nezobrazuje. OTA zůstává dostupná. Běžné další aktualizace se provádějí bez BOOT přes web.

Obnovení původního firmwaru:

```powershell
./scripts/project.ps1 restore -Port COM29 -Backup './backups/original_...bin'
```

Vedle BIN musí být ověřovací JSON. Skript kontroluje MAC desky, velikost a SHA-256. Před obnovou ještě uloží aktuální firmware. Obnova původního firmware zároveň vrátí jeho původní chování USB a případně odstraní dostupnost této OTA aplikace.

## OTA bez BOOT

1. Sestav novou verzi příkazem `./scripts/project.ps1 build`.
2. Na webu ukonči záznam, případně klikni na **Přestat používat USB**, a otevři **Nastavení → Aktualizace firmwaru přes Wi-Fi**.
3. Vyber **`.build/imu/firmware.bin`**. Nenahrávej zálohu celé flash, bootloader ani partitions.bin.
4. Počkej na dokončení a restart. Znovu se připoj k hotspotu.

Partice obsahují dvě aplikační oblasti po 7 MiB. Během přenosu se zapisuje neaktivní oblast a nová aplikace se vybere až po úspěšném dokončení a ověření obrazu. Nejde o automatický návrat při funkčně vadné nové aplikaci; firmware, který po startu nefunguje, může vyžadovat USB obnovu. Přístup k ovládání, souborům i OTA mají klienti připojení k hotspotu. Web nepoužívá externí CDN ani internetové služby.

## Lokální náhled a zdroje

```powershell
./scripts/project.ps1 preview
```

Náhled: http://127.0.0.1:18765/ — má viditelný štítek **simulovaná data** a nemá přístup k desce ani její SD. QA náhledy: `/qa?width=320&panel=dashboard`, `/qa?width=390&panel=settings`, `/qa?width=1280&panel=dashboard`. Souborové operace simulátoru pracují pouze v `.cache/preview-sd`; OTA do desky neprovádí.

- [Waveshare: zapojení ESP32-S3-LCD-1.47](https://www.waveshare.com/wiki/ESP32-S3-LCD-1.47)
- [Waveshare: schéma varianty USB-A](https://files.waveshare.com/wiki/ESP32-S3-LCD-1.47/ESP32-S3-LCD-1.47_schematic_diagram.pdf)
- [Adafruit: piny ICM-20948](https://learn.adafruit.com/adafruit-tdk-invensense-icm-20948-9-dof-imu/pinouts)
- [TDK: ICM-20948 datasheet v1.6](https://invensense.tdk.com/wp-content/uploads/2024/03/DS-000189-ICM-20948-v1.6.pdf)
- [SparkFun: ovladač ICM-20948](https://github.com/sparkfun/SparkFun_ICM-20948_ArduinoLibrary)

Zdrojový firmware: `src/main.cpp`, nastavení/pomocné struktury: `include/model.h`. Web: `web/`. Zabalený web se generuje do flash při sestavení, není potřeba žádný další upload souborového systému.
