# Protokol ověření záznamu a výpočtu

| Zkouška | Vstup a postup | Výsledek a rozsah závěru |
|---|---|---|
| Integrita SBF a pořadí CSV | Vlastní archiv projektu z 18. 11. 2026, soubory `test-jizda.sbf` a `test-jizda.csv`. Při přípravě vydání byl proud znovu projit podle délek rámců a v každém rámci se přepočetlo CRC. V CSV bylo ověřeno pořadové číslo a platnost každé polohy. | 117 776 bajtů, 858 řádků CSV, posloupnost 1–858. Bloky 4007, 4000 a 4027 každý po 858 kusech, blok 4014 celkem 17krát. Každý rámec prošel kontrolou CRC a na konci nezůstaly přebytečné bajty. Všech 858 poloh bylo neplatných. [Výpis původní kontroly](../overeni/integrita_exportu.json) |
| Časování výše uvedené série | Krajní časy příjmu na Pi, 857 mezilehlých intervalů | Rozpětí 17,140 s, průměr 20,0 ms neboli 50,0 Hz. Jde o frekvenci doručených polohových zpráv v tomto úseku. Bez platných souřadnic z něj nelze určit polohovou chybu. |
| Výpočet PPK na referenčních datech | [Tři soubory RINEX projektu RTKLIB](https://github.com/tomojitakasu/RTKLIB/tree/rtklib_2.4.3/test/data/rinex), SHA-256 kontroluje [test](../Formula_Manager/deploy/check_ppk.py). Výpočet při vydání opakován v Ubuntu/WSL pomocí RTKLIB 2.4.3.b34 z distribuce Ubuntu. | 115 výsledných epoch, 115 Fix, 0 Float. Test znovu otevřel databázi, zkontroloval export CSV a odmítnutí vstupů bez navigace nebo bez měřicích epoch. Výsledek dokládá činnost zpracovatelského řetězce na referenční dvojici. |
| Bezdrátové připojení | Uživatelem doložené hlášení Formula Manageru z Pi, 23. 11. 2026 ve 22:10:38, zkouška uloženého profilu eduroamu | Ověřeno přihlášení, přidělení IPv4 a návrat na původní Wi-Fi. Test dokládá správu spojení v daném místě a čase. |

## Jak zopakovat výpočet

Na Linuxu s nástroji `convbin` a `rnx2rtkp` spusť z adresáře `Formula_Manager` příkaz `python3 deploy/check_ppk.py`. Test pracuje v dočasném adresáři. Pro zkoušku bez internetu lze předat `--fixtures ADRESAR` se třemi nezměněnými soubory uvedenými na začátku skriptu. Jména souborů a jejich očekávané kontrolní součty jsou součástí stejné revize jako výpočet.

## Co zbývá změřit ve vozidle

Při přípravě veřejného vydání 24. 11. 2026 byl rovněž sestaven firmware ESP32-S3 s profilem `imu` v PlatformIO Core 6.2.0 a s lokálním heslem z příkladu. Výstupem byl obraz `firmware.bin`. Na Windows proběhl překlad v krátké pracovní cestě. U pomocného editoru O-Leaf proběhlo 25 testů Node.js, z nichž 24 prošlo a jeden byl přeskočen. Tyto kontroly ověřují sestavitelnost firmwaru a testované funkce editoru. Funkci IMU na vozidle dokládají samostatné protokoly.

Pro ověření přesnosti, dostupnosti pevného řešení a úplnosti trajektorie je třeba vlastní souběžný venkovní záznam roveru a základny, zdokumentované ustavení antén a nezávislá reference. Pro podíl platných řešení se uvádí také jmenovatel, časové okno a počty chybějících epoch. Odolnost napájení a úplnost poslední dávky vyžadují samostatnou zkoušku s řízeným přerušením. [Technický popis](technicka-zprava.md)
