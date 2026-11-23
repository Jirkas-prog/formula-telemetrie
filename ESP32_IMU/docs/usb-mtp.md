# USB přístup k SD

Implementace používá MTP. Ve Windows se zobrazuje přenosné zařízení **IMU-Test** a v něm úložiště **Měřicí data**, které přímo představuje obsah SD. Nevzniká druhá kopie SD ani disk s písmenem jednotky.

## Přepínání

1. Ukonči záznam na webu. USB přístup k souborům je blokován i při pozastaveném záznamu, aby počítač nemohl změnit soubor, do kterého by se později pokračovalo.
2. Připoj USB a v Průzkumníku otevři IMU-Test → Měřicí data. Přenos nebo změna souboru převezme SD pro USB. Výpis drží SD jen během jeho sestavení; hotový seznam se posílá z RAM. Identifikace zařízení, dotaz na kapacitu a vlastnosti již známých souborů kartu nepřebírají. Windows tyto dotazy provádí i automaticky na pozadí.
3. Web zobrazí **SD kartu používá USB**. Prohlížení, stahování a změny souborů na webu, nový záznam, změny nastavení s restartem a OTA jsou zablokované. Živý dashboard a grafy z RAM fungují dál.
4. Po skončení kopírování klikni na **Přestat používat USB**. Pokud USB ještě přenáší soubor nebo má rozpracovaný zápis, firmware předání odmítne. Nejprve dokonči nebo zruš operaci ve Windows.
5. USB zařízení zůstane připojené. Další přenos Windows si SD znovu převezme. Firmware oznamuje dokončené webové změny pomocí MTP událostí, aby se obnovila mezipaměť Windows. Události se odesílají po krátkém uklidnění změn, nikoli mezi jednotlivými kroky hromadné operace. Pokud Windows stále ukazuje starý obsah, použij **F5**. Firmware nedokáže rozlišit kliknutí uživatele od stejného USB požadavku programu na pozadí.

Odpojení/reset USB uzavře nebo zruší rozpracovaný MTP přenos a uvolní přístup webu. USB suspend sám o sobě přístup neuvolňuje, protože může znamenat pouze úsporný režim Windows. Pokud je USB zároveň jediným napájením, jeho vytažením se samozřejmě vypne celá deska.

Vlastnictví se nevztahuje na SD bloky ve Windows: FAT spravuje stále ESP32 a MTP přenáší soubory přes jeho filesystem. Ovladač podporuje výpis, čtení, zápis, složky, přejmenování, přesuny a mazání. Paměťová tabulka ovladače pojme 1024 objektů; při překročení vrací chybu místo tichého vynechání. Upstream zdroje a úpravy kompatibility jsou popsané v `lib/ImuMtp/README.md`.

## Ověření této verze

- Sestavení pro ESP32-S3 a kontrola OTA obrazu prošly.
- Automatický test skutečné funkce `updateState` ověřuje zamčení souborů, startu a nastavení při USB, blokování předání při probíhajícím přenosu, odemčení po předání, ochranu při záznamu a zachování zámku během uzavírání logu po chybě zápisu.
- V prohlížeči ověřeno rozložení na šířce 320 px a funkce tlačítka proti označenému simulátoru. Snímek: `tests/screenshots/usb-320.png`.
- Firmware s MTP je nahraný přes OTA. Windows zařízení rozpoznaly jako **IMU-Test**, stav OK (`USB\VID_303A&PID_0002\182E79D4DB1C`). Na skutečné desce bylo pozorováno převzetí SD přes USB a úspěšné předání webu.
- Nativní test `tests/mtp_check.cpp` používá Windows Portable Devices API: čte 256 KiB z SD, ověřuje každý bajt, zapisuje vlastní nový soubor, přejmenovává jej a znovu čte. HTTP monitor současně ověřuje dostupnost stavu, předání USB → web a shodu dat mezi oběma cestami. Spuštění: `scripts/build_mtp_check.ps1`, potom `scripts/hardware_check.py --base http://<IP-desky> --usb-copy --usb-api`. Protokol: `docs/hardware-usb-copy.json`. Toto je fyzický přenos přes ovladač Windows; není to automatizace okna Průzkumníku.

Dodatečné fyzické ověření 21. 10. 2026 zahrnulo 16MiB USB přenos oběma směry, přejmenování, vytvoření podsložky, přesun souboru tam a zpět, smazání složky, přerušené čtení a zrušený zápis. Běžné operace prošly se shodným obsahem. Po jednom zrušení zápisu selhalo následující USB čtení chybou Windows `0x8007001f`; nové otevření WPD relace obnovilo přístup bez restartu. Dva opakované testy zrušení prošly. Příčina tohoto nepravidelného selhání není určená a firmware nebyl při ověřování změněn. Podrobnosti a odkazy na všechny pokusy obsahují `usb-verification.md` a `usb-verification.json`. Fyzické odpojení během přenosu zůstává neověřené.

## Soubory

- `release/firmware.bin`: aktuální aplikace s MTP, obnovou CSV a PDF reporty; hash a stav ověření obsahuje vedlejší JSON.
- `release/firmware-mtp-candidate.bin`: archivní meziverze prvního MTP sestavení; pro nové nahrání použij aktuální `firmware.bin`.
- `backups/imu_before_mtp_app.bin`: další zachovaná kopie předchozí aplikace; lze použít pro návrat přes OTA. Není to obraz celé flash pro `flash.py restore`.
- `backups/original_1cdbd4792e18_20261021T095932Z.bin`: původní úplná 16MiB flash s ověřovacím JSON; obnovuje se přes USB podle README.
