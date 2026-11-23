# Černý displej po odpojení napájení — oprava 21. 10. 2026

## Příčina a oprava

Deska opakovaně padala při startu, nikoli při samotném vykreslování LCD. Sériový výpis `usb-boot-current.txt` obsahuje `Stack canary watchpoint triggered (sd-writer)`. K pádu docházelo ještě před spuštěním úlohy displeje.

Úloha SD měla zásobník 8192 bajtů. Obnova nedokončeného CSV obsahovala současně lokální kopírovací blok 4096 bajtů a další 4096bajtový blok ve vnořené funkci kontroly. Disassemblace původního sestavení ukázala:

| Funkce | Před opravou | Po opravě |
|---|---:|---:|
| `loggerTask` | 160 B | 160 B |
| `recoverInterruptedLog` | 5488 B | 1408 B |
| `scanLog` | 4176 B | 80 B |
| Součet těchto rámců | **9824 B** | **1648 B** |

Původní součet překračoval celý zásobník ještě před započtením FAT/VFS a dalších volání. Obnova nyní používá první 4 KiB existujícího globálního CSV bufferu. Běží pouze v SD úloze před zahájením logování, takže tento buffer v tu dobu nemá jiného uživatele. Formát CSV ani postup zachování originálu se neměnily.

Hostitelské testy kontrolovaly správnost dat a opakovatelnost opravy po výpadku, ale neomezený zásobník PC tuto chybu neodhalil. Nová kontrola v `tests/check.py` čte rámce přímo ze sestaveného ESP32 ELF a omezuje součet na 3072 B. Integrační test navíc ověřuje sdílený buffer při obnově přes více bloků.

## Nasazení a skutečný výsledek

- Před změnou vznikla úplná ověřená 16MiB záloha `backups/original_1cdbd4792e18_20261021T173709Z.bin`, SHA-256 `ed5396f6cf2a8b53b808dc18d40181d83406fe03e12a4b9a46821b65722b01b7`. Jde o stav před touto opravou, nikoli o původní tovární firmware. Původní záloha z 09:59 UTC zůstává zachovaná.
- Samostatně se zachovala předchozí aplikace v `backups/imu_before_recovery_stack_fix_app.bin`.
- Kvůli restartovací smyčce nebylo dostupné OTA. USB umožnilo vstup do zaváděcího režimu bez ručního BOOT. Změnil se pouze aktivní oddíl aplikace na `0x710000`; NVS, bootloader, výběr OTA oddílu, druhý oddíl i SD zůstaly zachované.
- Nová aplikace: 4 007 072 bajtů, SHA-256 `fbcc81dd31a51309b6f080d53ff6d543ab9ab01ed57efabd3e7c293a15267ecd`. Shodu nahraných dat ověřil flasher.
- Boot 122 se připojil na LAB-WIFI. Obnova postupovala při dostupném webu a uživatel potvrdil fungující displej.
- Původní `/logs/boot_000036_run_004.csv` prošel kontrolou: **70 994 694 bajtů, 495 900 platných řádků, 0 odstraněných bajtů**. Soubor nevyžadoval kopírování ani zkrácení.
- Po kontrole se automaticky spustil nový záznam. Nastavení SPI, 500/500/100 Hz a Wi-Fi zůstala zachovaná.
- Následný krátký test s načítáním stavu a historie: žádné ztráty ani chyby senzoru; stažených 20 631 řádků nového CSV bez chyby CRC nebo mezery v pořadí. Po ověření běží čerstvý `/logs/boot_000122_run_003.csv`.

Doklady: `recovery-stack-flash.json`, `recovery-stack-boot.json`, `recovery-stack-result.json`; následné ověření nového CSV je v `hardware-recovery-stack.json`. Logy sestavení a testů jsou `.cache/recovery-stack-build.log` a `.cache/recovery-stack-tests.log`.

Oprava řeší potvrzené přetečení zásobníku. Není důkazem odolnosti FAT32 proti každému výpadku ani opravou dříve zjištěného nepravidelného selhání USB po zrušeném zápisu.
