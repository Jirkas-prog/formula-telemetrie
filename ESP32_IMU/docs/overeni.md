# Ověření projektu – 21. 10. 2026

Testovaná deska: Waveshare ESP32-S3-LCD-1.47 USB-A, ESP32-S3 rev. 0.2, MAC 1c:db:d4:79:2e:18, 16 MiB flash, 8 MiB PSRAM. Adafruit ICM-20948 nebyl během testu připojený.

Tento protokol popisuje předchozí verzi bez MTP. Stav pozdějšího rozšíření USB je v [usb-mtp.md](usb-mtp.md); jeho nahrání a fyzický test zatím blokuje odpojená deska.

## Záloha a instalace

- Před prvním přepsáním byla přečtena a příkazem `verify_flash` porovnána celá původní 16MiB flash.
- Záloha: `backups/original_1cdbd4792e18_20261021T095932Z.bin`; ověřovací manifest je vedle ní jako JSON.
- SHA-256 zálohy: `862db13fb0785b8030fd61cbe63ba3e23c778698619ae7b24f7467804da788e2`.
- První instalace přes USB COM29 prošla kontrolou hashů. Po watchdog resetu se spustil hotspot IMU-Test. Další aktualizace už proběhly přes OTA bez BOOT.
- Zachovaný obraz `release/firmware.bin` je totožný s obrazem této úspěšné OTA, jeho hash je v `release/firmware.json`. `docs/hardware-ota.json` obsahuje vždy poslední pokus, aktuálně neúspěšné připojení k odpojené desce před novou OTA s MTP.

## Ověřeno na skutečné desce

| Kontrola | Výsledek |
|---|---|
| Hotspot IMU-Test, WPA2, HTTP na 192.168.4.1 | Prošlo |
| Alokace historie a fronty v PSRAM | Prošlo, `memory=true` |
| SD karta | Dostupná, kapacita souborového systému 30 977 032 192 B |
| Vytvoření složky, upload CSV, download, přejmenování, výpis, odstranění testovacích souborů | Prošlo, stažené bajty totožné s nahranými |
| HTML, CSS, JS z flash | Gzip odpovědi po rozbalení totožné se zdroji |
| `/api/history` bez měření | Platná prázdná historie |
| Start záznamu bez IMU | Odmítnut HTTP 409; nevznikají smyšlená data |
| Frekvence A/G/M 100/200/20 Hz | Uloženy nezávisle, po restartu načteny stejné hodnoty |
| Nepodporovaných 500 Hz magnetometru | Odmítnuto HTTP 400 |
| Obnova výchozího nastavení | Po restartu ověřeno 500/500/100 Hz, I²C, ±16 g, ±2000 °/s, autostart |
| OTA přes hotspot | Upload, restart a nový běh aplikace prošly; nastavení zůstalo zachované |

Strojové výsledky: `hardware-check.json`, `hardware-settings.json`, `hardware-ota.json`. Testy používaly dočasné připojení Windows k hotspotu; počítač byl potom vrácen na původní eduroam. Vlastní testovací složky na SD byly odstraněny, uživatelské soubory zůstaly zachované.

## Sestavení a prohlížeč

- PlatformIO sestavení úspěšné; oba aplikační oddíly mají po 7 MiB, kontrola hranic 16MiB flash prošla.
- Regresní testy CSV parseru: rozdělení streamu mezi bloky, BOM/CRLF, příznaky nových vzorků, stáří magnetometru, clipping, poškozené řádky, neplatná hlavička, prázdný soubor a paměťový limit.
- Regresní kontrola: selhání zálohy blokuje USB upload; úspěšné ověření předchází zápisu.
- UI zkontrolováno v prohlížeči při šířkách 320, 390 a 1280 px. Ověřeny samostatné volby frekvencí, změna pinoutu podle sběrnice, CSV grafy, přiblížení a výběr bodu. Snímky jsou v `tests/screenshots/`.
- Lokální náhled obsahuje výslovně označená simulovaná data. Screenshoty nejsou důkazem měření z fyzického senzoru.

## Zbývá po zapojení IMU

Skutečná komunikace s ICM-20948 přes I²C i SPI, nové vzorky magnetometru do 100 Hz, stabilita 500Hz záznamu a ztráty při souběhu s webem. Rovněž fyzický obraz LCD a jeho orientace nejsou z počítače vizuálně ověřitelné. Postup měření, kontroly znamének/gravitace a desetiminutového zátěžového testu je v README.

Bez těchto měření nelze rozhodnout, zda senzor a nastavené filtry vyhovují použití na formuli.
