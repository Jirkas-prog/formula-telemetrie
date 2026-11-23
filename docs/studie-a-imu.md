# Související studie a inerciální experiment

## Jak číst studie

Jednotlivé studie dokumentují rozhodování v různých fázích bakalářské práce. Výchozí návrhy používají i jiné součásti nebo nástroje než realizovaný palubní logger. Pro popis vydaného palubního programu je určující [technická zpráva](technicka-zprava.md).

| Samostatný podklad | Otázka, kterou řeší |
|---|---|
| [Původní rešerše](../studie/00_Puvodni_reserse/) | Varianty sestavy, rozpočet, integrace a výchozí požadavky |
| [Přesnost RTK](../studie/01_presnost_RTK/) | Podmínky interpretace přesnosti a význam referenční polohy |
| [Přenos RTCM](../studie/02_prenos_RTCM/) a [NTRIP](../studie/03_NTRIP_a_referencni_stanice/) | Přenos korekcí a varianty referenční stanice |
| [ELRS](../studie/04_ELRS_prenos_RTK/) a [rychlosti rozhraní](../studie/05_rychlosti_komunikacnich_rozhrani/) | Možnosti rádiového a vodičového přenosu |
| [OS a spolehlivý záznam](../studie/06_OS_a_spolehlive_logovani/) a [infrastruktura Pi](../studie/07_Infrastruktura_RPi_pruvodce/) | Varianty záznamu, výukové příklady Dockeru, InfluxDB a Grafany |
| [Stacionární základna F9P](../studie/08_Stacionarni_zakladna_F9P/) | Návrh vlastní základny, napájení, výstupní data a plán přejímky |
| [Instalace OS přes Wi-Fi a migrace na NVMe](../studie/instalace-nvme/) | Postup instalace na čistý systém, včetně citované verze rpi-clone |
| [Český výukový podcast](../studie/podcast/) | Zvukový výklad, scénář, navigace po kapitolách a původ syntetického hlasu |

Každá studie obsahuje vlastní literaturu a její text je pro příslušné tvrzení primárním rozcestníkem. Historická rešerše má i sdílenou bibliografii [references.bib](../studie/00_Puvodni_reserse/Zdrojovy_projekt/references.bib). Studie F9P uvádí zdroje také v [generátoru PDF](../studie/08_Stacionarni_zakladna_F9P/vytvor_studii.py), který používá [ReportLab](https://docs.reportlab.com/). Instalace je doložena [repozitářem rpi-clone](https://github.com/geerlingguy/rpi-clone). Původ syntetického zvuku, hlas a podklady jsou uvedeny v [poznámkách k podcastu](../studie/podcast/Zdroje_a_poznamky.txt).

## Inerciální experiment na ESP32-S3

Samostatný firmware ukládá průběh měření IMU a obsluhuje lokální web a USB. Patří k volitelné inerciální části. [README firmwaru](../ESP32_IMU/README.md), [parametry sestavení](../ESP32_IMU/platformio.ini), [historické ověření vzorkování](../ESP32_IMU/docs/sampling-validation.md).

1. Před sestavením v adresáři `ESP32_IMU` zkopíruj `include/local_wifi.example.h` do `include/local_wifi.h` a nastav vlastní heslo přístupového bodu (8–63 znaků). Soukromý soubor ignoruje Git.
2. V prostředí PlatformIO spusť `pio run -e imu`. Profil připíná platformu espressif32 6.12.0, knihovnu ICM-20948 1.3.2, knihovnu displeje 1.11.0 a ArduinoJson 7.4.2. Webové prostředky pro flash vytvoří před sestavením `scripts/embed_web.py`. [PlatformIO Espressif 32](https://github.com/platformio/platform-espressif32) · [Arduino ESP32](https://github.com/espressif/arduino-esp32)
3. Historické postupy a záznamy přejímky jsou v [docs](../ESP32_IMU/docs/). V [analytických skriptech](../ESP32_IMU/analysis_20261026/) jsou čtečky, kontrola posloupnosti a nástroje pro vyhodnocení vlastních záznamů. Vstupní datové soubory k jízdám zajišťuje měřicí tým. Historické obslužné a balicí skripty mohou vyžadovat přizpůsobení umístění nástrojů konkrétnímu počítači.

| Část | Původ a doklad |
|---|---|
| `src`, `include`, základní `web`, `scripts`, `tests`, `analysis_20261026` | Projektový firmware, uživatelské rozhraní, kontrolní a analytické skripty. Původ a meze spolupráce s AI popisuje [registr](zdroje.md). Rozhraní akcelerometru, displeje a JSON vycházejí z [knihovny SparkFun ICM-20948](https://github.com/sparkfun/SparkFun_ICM-20948_ArduinoLibrary), [Adafruit ST7735/ST7789](https://github.com/adafruit/Adafruit-ST7735-Library) a [ArduinoJson](https://github.com/bblanchon/ArduinoJson). |
| `lib/ImuMtp` | Integrace a úpravy kódu Espressif esp-usb (Apache-2.0) a MTP třídy TinyUSB (MIT). [Soupis přejatých cest, revizí a úprav](../ESP32_IMU/lib/ImuMtp/README.md), [licence Espressif](../ESP32_IMU/lib/ImuMtp/LICENSE-ESPRESSIF), [licence TinyUSB](../ESP32_IMU/lib/ImuMtp/LICENSE-TINYUSB). |
| `web/pdfjs`, `web/vendor` | Distribuce Mozilla PDF.js, vložené mapy znaků a fonty s přiloženými licencemi a jsPDF. Původ, verze a integrita jsou v [manifestu PDF.js](../ESP32_IMU/web/pdfjs/SOURCE.json) a [manifestu jsPDF](../ESP32_IMU/web/vendor/SOURCE.json). [Mozilla PDF.js](https://github.com/mozilla/pdf.js) · [jsPDF](https://github.com/parallax/jsPDF) |
| Statistika, filtrace a grafy v analýze | Použitá vědecká rozhraní dokumentují [NumPy](https://numpy.org/doc/), [pandas](https://pandas.pydata.org/docs/), [SciPy](https://docs.scipy.org/doc/scipy/) a [Matplotlib](https://matplotlib.org/stable/). |
