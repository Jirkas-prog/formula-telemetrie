# Reprodukce na Raspberry Pi 5

Prototyp používá Raspberry Pi 5 s 2 GB RAM, Raspberry Pi OS Lite 64-bit (Trixie), systémový disk NVMe a simpleRTK3B Pro s modulem Septentrio mosaic-X5 na USB. Během instalace je potřeba síť s přístupem k repozitářům balíčků. Běžný záznam vyžaduje pouze Pi, přijímač a jejich napájení. [Raspberry Pi, instalace OS a vzdálené připojení](https://www.raspberrypi.com/documentation/computers/getting-started.html) · [Uživatelská příručka desky](https://www.ardusimple.com/user-guide-simplertk3b-pro/)

1. V Raspberry Pi Imageru vyber Raspberry Pi 5, Raspberry Pi OS Lite (64-bit) a správný cílový disk. V nastavení zadej jméno počítače `formula-logger`, účet `formula69`, vlastní heslo nebo SSH klíč, vlastní Wi-Fi, zemi CZ, časovou zónu Europe/Prague a povol SSH. Pro přímou instalaci lze NVMe zapsat přes USB čtečku. Pro cestu použitou na prototypu se nejprve zavede systém z microSD a pomocí [rpi-clone, použitá revize](https://github.com/geerlingguy/rpi-clone/tree/e640eff1caa29e70bb3beaea21afb36ad6311313) se naklonuje na NVMe. Zápis obrazu nebo klonování přepíše cílové médium.
2. Po vypnutí vyjmi instalační kartu, zapni desku a přihlas se přes `ssh formula69@formula-logger.local`. Pomocí `findmnt -no SOURCE /` a `lsblk -o NAME,SIZE,MOUNTPOINTS` ověř, že kořenový systém běží z NVMe. Připoj přijímač na USB a ověř jeho přítomnost příkazem `ls -l /dev/serial/by-id/`.
3. Z důvěryhodného místního spojení s vlastním přijímačem zjisti otisk SHA-256 jeho veřejného certifikátu HTTPS (v prohlížeči v podrobnostech certifikátu). Přenos certifikátu ze samotného Pi lze později ověřit proti tomuto otisku. Na Pi připrav software:

   ```sh
   sudo apt-get update
   sudo apt-get install -y git
   git clone https://github.com/Jirkas-prog/formula-telemetrie.git
   cd formula-telemetrie/Formula_Manager
   read -r -p 'Ověřený SHA-256 přijímače: ' RECEIVER_SHA256
   export RECEIVER_SHA256
   sudo --preserve-env=RECEIVER_SHA256 bash deploy/install.sh
   ```

   Při první instalaci zvol vlastní heslo webu. Při opakované instalaci se již uložený certifikát přijímače a ověřovací údaj webu zachovají. Instalátor získá DNS jméno přijímače z ověřeného certifikátu. U nového vydání či změny přijímače ověř jeho kompatibilitu a identitu.
4. V přihlášeném SSH terminálu zobraz otisk certifikátu **webu Raspberry Pi** příkazem `openssl x509 -in /etc/formula-manager/web.crt -noout -fingerprint -sha256`. V počítači otevři `https://formula-logger.local/` a porovnej jej s certifikátem zobrazeným prohlížečem. Otisk webu Pi a otisk webu přijímače patří dvěma různým zařízením.
5. Ověř běh příkazem `systemctl is-active formula-manager nginx`. Případnou příčinu chyby hledej v `journalctl -u formula-manager -b`. Při první zkoušce připoj GNSS anténu, zkontroluj čerstvou polohu, ulož krátkou jízdu a porovnej počty vzorků v detailu a CSV. Podrobný [návod k obsluze](../Formula_Manager/README.md) popisuje i laboratorní záznam bez antény.
6. Volitelný hotspot vyžaduje nástroje `iw`, `dnsmasq` (balík `dnsmasq-base`) a Avahi. Po jejich instalaci spusť `sudo bash deploy/wifi-fallback.sh`, zadej vlastní heslo hotspotu a v nastavení webu seřaď profily. Pro Tailscale, sdílení SMB a výpočet použij [návod PPK](../Formula_Manager/PPK.md).
7. K přejímce záznamu lze použít `python deploy/check_live.py formula-logger.local --cafile web.crt` na počítači v místní síti. Nejdřív zkopíruj ověřený veřejný `/etc/formula-manager/web.crt` z Pi do uvedené cesty. Test zakládá pokusnou jízdu; varianta `--inspect` pouze kontroluje stav. Referenční zkouška PPK má samostatný [postup](overeni.md).

Při opakování přímo z verze citované v práci použij po klonování `git checkout --detach IDENTIFIKATOR_REVIZE` s úplným identifikátorem z bibliografického záznamu.
