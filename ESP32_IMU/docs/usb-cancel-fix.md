# USB po zrušení přenosu — ověřená oprava, 21. 10. 2026

## Příčina a změna

Původní firmware boot 123 selhal ve stejné Windows WPD relaci při druhém zrušeném zápisu deklarovaného 16MiB souboru, po 63 skutečně zapsaných bajtech. Následující GetStream vrátil 0x8007001f. Diagnostický boot 124 chybu zopakoval: Cancel přeznačil částečně naplněný OUT přenos na příjem příkazu, ale starý buffer TinyUSB 0.16 stále obsahoval data zrušeného souboru. Viz `usb-failure-usb-trace.json`.

Oprava při Cancel zápisu interně ukončí OUT přenos a zachová jeho USB datový přepínač DATA0/DATA1. Po vyprázdnění již zařazených dokončovacích událostí znovu připraví čistý příjem příkazu. Do té doby vrací DeviceBusy. Nevyžaduje zavření relace ani fyzické připojení.

Směr IN má jiný postup: jeho nedokončený přenos se ukončuje až při dalším příkazu, kdy host opět posílá IN tokeny. Plošné zakazování obou endpointů při Cancel v diagnostickém bootu 125 uvázlo v čekání DCD na IN token. Varianta s hostem viditelným HALT (boot 127) také nevyhověla: Windows po vlastním Cancel čekaly na Ready a ClearFeature poslaly až po timeoutu. Obě neúspěšné varianty jsou nahrazené interním ukončením OUT se zachováním datového přepínače.

Zdroj protokolu: [USB Still Image Capture 1.0, §7.2.1](https://www.pjrc.com/tmp/usb_still_img10.pdf). Řadič: [TinyUSB 0.16 DWC2](https://github.com/hathach/tinyusb/blob/0.16.0/src/portable/synopsys/dwc2/dcd_dwc2.c).

## Fyzické ověření — boot 128

`usb-cancel-verified.json` uchovává úspěšný test z 21:24, `.cache/USB_overeni_fb4c52/wpd.log` jeho nativní WPD protokol.

- Jedna WPD relace, bez odpojení, resetu, nového otevření zařízení, opakování neúspěšné operace nebo čekání mezi Cancel a dalším přenosem.
- 12 zrušení zápisu po 1, 63, 64, 511, 512, 4096, 65535, 65536, 65537, 131072, 262144 a 1048576 bajtech. Střídá se okamžité čtení a okamžitý nový zápis.
- Po každém zrušení úspěšné čtení 1 MiB, zápis 64 KiB a úplná kontrola zpětně přečtených bajtů. Zrušený soubor není viditelný.
- Úspěšné přerušení čtení po 64 KiB a okamžité další čtení. Také vytvoření složky, přesun tam/zpět, přejmenování a smazání vlastní testovací složky.
- Současně 205 HTTP kontrol stavu; web zůstal dostupný. Návrat USB → web a kontrola obsahu přes HTTP prošly.
- Testovací složka byla uklizena; uložená měření se nemažou. Kompletní softwarové testy včetně zásobníku obnovy CSV prošly.

Také samostatný test 16 MiB prošel: čtení, zápis, přejmenování, zpětné čtení přes USB i následné stažení obou souborů přes HTTP mají shodu všech bajtů (`usb-large-verified.json`). Během USB web zůstal dostupný. Vlastní testovací složka i zbytky dvou známých neúspěšných pokusů byly odstraněné; uživatelská data se neměnila.

## Opakování

Finální firmware s limitem 500 / 500 / 100 Hz zopakoval celý rozšířený test v bootu **139**: všech 12 zrušení s okamžitým čtením/zápisem v jedné relaci, přerušené čtení, operace se složkami i předání USB → web. Protokol: `usb-cancel-final.json`, nativní výpis `.cache/USB_overeni_67df20/wpd.log`. Deska se neodpojovala ani během této zkoušky. Obraz a SHA-256 jsou v `release/firmware.json`.

```powershell
./.tools/venv/Scripts/python.exe -X utf8 -B scripts/hardware_check.py --base http://10.32.176.138 --usb-copy --usb-api --usb-extended --usb-mib 1
```

Test řádně zastaví záznam, používá pouze svou novou složku `USB_overeni_*` a zachová protokol v `docs/hardware-runs`. Po testu je potřeba spustit další záznam. Předchozí vydaná aplikace je v `backups/imu_before_usb_cancel_fix_app.*`.
