# Alias imu-test.local — diagnostika, 21. 10. 2026

## Aktuální ověřený výsledek

LAB-WIFI je hotspot telefonu, což potvrdil uživatel. HTTP přes IP i unicast na UDP 5353 fungují, ale multicastové dotazy po přibližně dvou minutách přestanou v této síti docházet k ESP32. Windows pak nedokážou přeložit imu-test.local. Pravidelné oznamování služby z firmwaru to nevyřešilo.

Dočasný čítač příchozích paketů lwIP předával každý paket beze změny knihovnímu responderu. Na začátku bootu 131 dorazil unicast i multicast a oba vrátily správnou adresu (`mdns-tap-first.json`). Později unicast stále vracel 10.32.176.138 a jeho čítač vzrostl z 1 na 2. Multicast nevrátil nic a čítač příjmu zůstal na 14 (`mdns-tap-expired.json`). Ztráta tedy nastává před mDNS responderem. Tato zkouška sama nerozliší implementaci telefonu od všech nižších síťových příčin.

Pravidelné IGMP reporty (booty 127/128) ani oznámení služby a IP každých 30 sekund (boot 129) výpadku nezabránily. Tyto neúčinné pokusy i dočasný čítač byly odstraněné. Zůstává obnovení mDNS po získání IP, opětovném připojení a změně adresy. Uspávání Wi-Fi je vypnuté. Soubor hosts, firewall ani DNS počítače se neměnily.

Na LAB-WIFI použij IP uvedenou na displeji, při ověření http://10.32.176.138/. DHCP ji může změnit. Samostatný hotspot IMU-Test zůstává dostupný na http://192.168.4.1/. Pro spolehlivé `.local` mezi klienty je potřeba síť, která předává mDNS multicast; samotný nastavitelný alias to na libovolném hotspotu telefonu nezaručí.

Krátké historické testy níže dokládají pouze počáteční úspěch. Oprava USB po zrušení přenosu má samostatný úspěšný protokol `usb-cancel-fix.md`.

## Pozorování a změna

HTTP na `10.32.176.138` fungovalo, ale Windows nedokázaly přeložit `imu-test.local`. Přímý UDP dotaz na mDNS responder ESP32 vracel správnou A adresu `10.32.176.138`; stejný dotaz přes multicast `224.0.0.251:5353` nedostal odpověď. Windows měly mDNS povolené. Obnovení připojení ESP32 ke stejné síti LAB-WIFI obnovilo i multicast a překlad názvu (`mdns-reconnect-check.json`). Tím je doložen projev a účinná obnova spojení; samotný test nerozlišuje všechny možné příčiny ztráty multicastového členství mezi ESP32 a přístupovým bodem.

Firmware dříve spouštěl mDNS pouze při nastavení AP/STA, před získáním adresy klienta. Nyní v `wifiTick()` znovu inicializuje responder a oznámí HTTP službu, když klient skutečně získá nenulovou IP, při opětovném připojení a při změně IP. Nastavitelný alias zůstává zachovaný. `wifi.mdnsStarted` diagnostikuje úspěšné spuštění služby; není zárukou, že libovolný router propouští multicast.

Na počítači se neměnil soubor hosts, DNS servery, firewall ani síťový profil. Síťová nastavení desky i původní alias byly po diagnostice obnoveny.

## Ověření a nasazení

- Sestavení i kompletní existující testy prošly, včetně kontroly zásobníku obnovy CSV.
- Předchozí aplikace je zachovaná v `backups/imu_before_mdns_reconnect_app.bin` a její metadata ve vedlejším JSON.
- Aktualizace přes OTA prošla, boot **123**, konfigurace senzoru zůstala zachovaná. Protokol: `hardware-ota.json`.
- `mdns-probe-20261021T201649.json`: po restartu prošel unicast, multicast, překlad jména Windows a HTTP přes alias.
- `mdns-probe-20261021T201744.json`: prošel dosud nepoužitý dočasný alias `imu-check-2018.local`, včetně načtení celé úvodní stránky a shody s HTML projektu.
- `mdns-probe-20261021T201752.json`: po dalším připojení a obnovení původního `imu-test.local` prošly stejné kontroly.
- `mdns-lifecycle-check.json` potvrzuje obnovení původních nastavení a pokračování záznamu. Záznam byl během diagnostických změn korektně pozastaven; původní soubory nebyly smazány. Závěrečné čítače ztrát a chyb jsou nulové.

Opakování fyzického testu: `scripts` runtime Python s `tests/mdns_probe.py --device-ip <IP-desky>`. Test přímo ověřuje mDNS pakety, takže úspěch není odvozen jen z DNS cache.

