# Ověření 21. 10. 2026

## Skutečná deska a SD

- Waveshare ESP32-S3-LCD-1.47 USB-A, USB identifikace IMU-Test, SD připojená; ICM-20948 zatím není zapojená.
- Uživatel fyzicky potvrdil odstranění problikávání LCD.
- OTA přes hotspot IMU-Test funguje. Finální obraz má 3 956 960 bajtů, SHA-256 `8f1dd83747fb47562f27d8a22e2cdde87c209fb99b28069279097ae839919adf`, po nahrání byl ověřen boot 12. Běh `hardware-ota.json` zachytil úspěšné přijetí obrazu a restart, následný síťový výpadek ale přerušil kontrolu nastavení. Proto byl samostatně spuštěn `hardware-check.json`: prošla shoda všech kontrolovaných webových souborů, stav a SD operace. Při vytvoření release byla navíc porovnána zachovaná konfigurace a číslo bootu obou běhů. Původní výsledky nejsou přepsané na úspěch; archiv je v `hardware-runs/`.
- Skutečný webový přenos 16 777 228 bajtů (16 MiB + 12 bajtů): pokračování uploadu po výpadku sítě, úplný download a porovnání SHA-256. Dále ověřené HTTP Range, MIME PNG/PDF, přejmenování s diakritikou, přesun neprázdné složky a odmítnutí přesunu složky do sebe.
- Samostatný pomalý download trval **78,08 s**, zachoval všechny bajty a během něj `/api/status` odpovídal nejdéle za **0,469 s**. Vlastní testovací soubory byly odstraněné. Výsledek: `files-http-20261021T141608.json`.
- První kombinovaný běh `files-http-20261021T134115.json` má celkový výsledek false kvůli pozdějšímu přerušení sítě. Jeho úspěšné dílčí kontroly nejsou vydávané za úplný úspěch; pomalý přenos byl následně ověřen samostatně.

## Software a rozhraní

- `scripts/project.ps1 test`: CSV parser a CRC, zamykání SD, obnovení uploadu po ztraceném potvrzení, statistiky PDF, ochrana záloh a kontrola obrazu/oddílů.
- Produkční C++ validátor testovaný při přerušení CSV na každé bajtové pozici testovacího souboru a při poškození jednotlivých bajtů.
- Produkční postup obnovy testovaný s přerušeními při přejmenování, zápisu, flush, ukládání protokolu a mazání značky v NVS. Ověřené opakování obnovy, nedostatek místa a zachování originálu.
- PDF report se čtyřmi stránkami vytvořený testem a prohlédnutý po rasterizaci. Také vytvořený přímo tlačítkem ve webovém správci souborů.
- Rozhraní prohlédnuté v prohlížeči při šířce 320 a 1280 px. Dokument zabírá celou šířku, hlavička má 48 px, PDF ovládání 40 px; název je maximálně na jednom řádku. Ověřená změna velikosti okna, stránkování a návrat.
- Snímky v `tests/screenshots/` pocházejí z označeného místního simulátoru. `report-fullscreen-320.png` ukazuje report simulovaného CSV, nikoli skutečné měření senzoru.

## Co zatím není fyzicky ověřené

- Skutečná data IMU, dlouhodobý běh při 500/500/100 Hz a odpojení napájení během takového měření; senzor není zapojený.
- Kompletní kopírovací test MTP přes Průzkumník s kontrolním součtem. Rozpoznání zařízení ve Windows a předání vlastnictví SD byly pozorované; velké přenosy výše proběhly přes HTTP.
- Aplikační oprava CSV neodstraňuje riziko poškození FAT nebo interního řadiče SD při výpadku. Podrobnosti jsou v `recovery-and-reports.md`.
