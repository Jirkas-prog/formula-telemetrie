# Ověření USB — 21. 10. 2026

> Historický test před opravou. Aktuální oprava a úspěšný test 12 zrušení bez nového otevření relace: [usb-cancel-fix.md](usb-cancel-fix.md).

Test skutečné desky přes Windows Portable Devices / USB MTP. Nejde o simulátor ani automatizaci okna Průzkumníku. Firmware nebyl změněn ani znovu nahrán; po celou dobu boot 36, SHA-256 vydaného obrazu `c928b596bb38d17b3649ffe0111070a78ccebbf56c0678d4ea4ebd00ff713998`.

## Výsledek

Běžné USB operace fungují. Při zrušení zápisu se jednou projevil problém navazujícího čtení; nelze proto USB označit za bezchybné ve všech testovaných situacích.

| Kontrola | Výsledek |
|---|---|
| Rozpoznání zařízení IMU-Test ve Windows | OK |
| Výpis úložiště a podsložek | OK |
| Čtení 256 KiB a 16 MiB | Shoda všech bajtů |
| Zápis přes USB, přejmenování a zpětné čtení 16 MiB | Shoda všech bajtů |
| Vytvoření podsložky, přesun souboru do ní a zpět | OK, obsah zachován |
| Smazání prázdné složky přes USB | OK, obnovený výpis ji neobsahuje |
| Uzavření čtecího streamu po 64 KiB a nové úplné čtení | OK |
| Zrušení zápisu po 64 KiB | Bez neúplného souboru, ale jednou selhalo následující čtení |
| Předání USB → web a stažení souboru vytvořeného přes USB | OK, 16 MiB se shodným SHA-256 |
| Webové soubory během USB přenosu | Správně blokované odpovědí 409 |
| Stavové API během přenosů | Dostupné; maximum v dlouhém testu 4,594 s včetně opětovného připojení požadavku |

## Otevřený problém

V dlouhém testu byl zápis plánovaného 16MiB souboru zrušen metodou WPD `IStream::Revert` po odeslání 64 KiB. Zrušení se vrátilo úspěšně a neúplný soubor nebyl ve výpisu. Následné otevření existujícího souboru pro čtení ale selhalo chybou `0x8007001f`.

Po ukončení testovacího procesu a novém otevření WPD relace šlo všech 16 MiB znovu přečíst bez chyby. Deska se nerestartovala, web odpovídal. Následné stažení souboru vytvořeného přes USB přes HTTP potvrdilo shodu dat:

`341aacac661ccb210720bedaa9ead5d668fe5ea41a73532fc147c71e34040df1`

Dva další testy prošly včetně zrušení zápisu a okamžitého navazujícího čtení. Jeden používal soubor o velikosti 256 KiB, druhý deklaroval 16MiB zápis a zrušil jej po 64 KiB. Jde zatím o nepravidelné selhání; nelze z těchto výsledků určit, zda je příčina ve firmware, stavu ovladače Windows nebo jejich souhře. Nebyla provedena oprava firmware.

## Doklady a stav po testu

- `hardware-runs/20261021T190035-hardware-usb-copy.json`: základní 256KiB test, úspěch.
- `hardware-runs/20261021T190934-hardware-usb-copy.json`: dlouhý 16MiB test, selhání po zrušeném zápisu.
- `hardware-runs/20261021T191333-hardware-usb-copy.json`: opakování s 256 KiB, úspěch.
- `hardware-runs/20261021T191421-hardware-usb-copy.json`: opakování zrušení deklarovaného 16MiB zápisu, úspěch.
- `usb-verification-recovery.json`: nové USB čtení, shoda HTTP dat a úklid velkého souboru.
- `usb-verification.json`: souhrn pokusů a konečný stav zařízení.

Všechny čtyři vlastní testovací složky byly odstraněny. Původní záznam byl před testem řádně uzavřen. Po testu běží nový `/logs/boot_000036_run_004.csv` s nastavením 500/500/100 Hz; při závěrečné kontrole byly čítače ztrát a chyb nulové. Uživatelovy soubory zůstaly zachované.

Fyzické vytažení USB během přenosu ani chování samotného okna Průzkumníku tímto ověřením nejsou pokryté. Firmware zůstal beze změny.

Opakování rozšířeného testu: sestavit `scripts/build_mtp_check.ps1`, potom spustit `scripts/hardware_check.py --base http://<IP> --usb-copy --usb-api --usb-mib 16 --usb-extended`. Skript zastaví aktivní záznam; po dokončení jej znovu spusť na webu. Při chybě uchovává testovací složku pro diagnostiku.
