# Formula Manager · síťový disk a výpočet PPK

Po jízdě nahraješ měření stacionární základny na Raspberry Pi, vybereš jízdu a spustíš výpočet. Karta **Výpočet PPK** uloží novou trasu se souřadnicí a kvalitou řešení pro každý vypočtený okamžik. Původní měření z jízdy zůstává pod stejným číslem a výpočet můžeš zopakovat třeba s přesnější polohou základny.

## 1. Jednorázové nasazení na stávající Pi

1. Pro první instalaci připrav ověřený otisk přijímače podle [instalačního návodu](../docs/instalace.md). Připoj Pi a počítač ke stejné Wi-Fi. Pro instalaci balíčků a první přihlášení do Tailscale potřebuje Pi internet. Dokonči probíhající záznamy, test přesnosti a export. Při první instalaci na čistý systém připoj i příslušný přijímač mosaic-X5 kvůli ověření certifikátu.
2. Na Windows otevři PowerShell **ve složce obsahující adresář `Formula_Manager`** a přenes jeho obsah do domovského adresáře na Pi.

   ```powershell
   scp -r .\Formula_Manager formula69@formula-logger.local:~/
   ssh formula69@formula-logger.local
   ```

3. V otevřeném SSH spojení spusť následující příkazy. První instalační skript aktualizuje aplikaci a nainstaluje RTKLIB. Druhý nastaví sdílenou složku a vzdálené připojení.

   ```bash
   cd ~/Formula_Manager
   sudo apt-get update
   sudo --preserve-env=RECEIVER_SHA256 bash deploy/install.sh
   sudo bash deploy/network-drive.sh
   ```

4. Při první konfiguraci zadej heslo sdílení pro účet **formula69** dvakrát. Po přihlášení do webu otevři **Síťový disk**. Najdeš tu návod pro Windows a Linux a tlačítka pro zobrazení a zkopírování hesla. Při pozdější změně použij z adresáře projektu `sudo python3 deploy/samba-password.py`, který aktualizuje účet Samby i údaj pro web.
5. Pokud Tailscale vypíše přihlašovací odkaz, otevři ho na počítači a autorizuj Pi ve své síti Tailscale. Na vzdáleném počítači nainstaluj klienta a přihlas jej do stejné sítě. Pro přístup podle názvu musí být zapnuté MagicDNS a pravidla této sítě musí povolovat přístup počítače na Pi přes TCP 445. Poznamenej si obě cesty, které skript vypíše. [Instalace Tailscale](https://tailscale.com/docs/install/linux) · [MagicDNS](https://tailscale.com/docs/features/magicdns)

## 2. Připojení síťového disku ve Windows

- **Na stejné Wi-Fi nebo hotspotu** otevři v adresním řádku Průzkumníka `\\formula-logger.local\PPK`. Místní přenos funguje také bez internetu. Počítač a Pi musí mít povolenou vzájemnou komunikaci. Pokud síť blokuje mDNS, použij místní IP adresu Pi ve stejné cestě.
- **Odkudkoliv přes Tailscale** zapni klienta a otevři cestu vypsanou jako **Sdílení přes Tailscale**. Má tvar `\\formula-logger.<tvoje-síť>.ts.net\PPK`. Skutečnou doménu přidělí Tailscale. Výchozí nastavení využívá privátní propojení a nevyžaduje přesměrování portu na routeru.
- **Pro trvalé písmeno disku** spusť v běžném PowerShellu níže uvedený příkaz. Hvězdička vyvolá skrytou výzvu k zadání hesla. Chceš-li používat stejné písmeno disku i mimo místní síť, použij ve stejném příkazu vypsanou cestu Tailscale a nech klienta připojeného.

  ```powershell
  net use P: \\formula-logger.local\PPK /user:formula69 * /persistent:yes
  ```

Do tohoto disku můžeš kopírovat soubory a vytvářet podsložky. Sdílení **PPK** vede do `/var/lib/formula-manager/imports` na NVMe. Aplikace spravuje databáze v nadřazeném adresáři. [Konfigurace sdílení Samba](https://www.samba.org/samba/docs/current/man-html/smb.conf.5.html)

## 3. Příprava měření

1. Na roveru před jízdou zapni **RAW měření pro PPK** v nastavení ručně spouštěného záznamu nebo v profilu **Záznam po spuštění**. Zaznamenej jízdu a ukonči ji. V jejím detailu zkontroluj nenulový počet měřicích epoch.
2. Na základně upevni anténu na známý bod. Začni logovat před jízdou a skonči po ní. Oba přijímače potřebují současná měření fáze nosné ze společných družic. Ulož i navigační zprávy družic nebo si připrav navigační RINEX pokrývající stejné období. Soubor obsahující jen polohy, například NMEA GGA nebo GPX, pro tento výpočet nestačí.
3. Připrav si šířku, délku a **elipsoidickou výšku** referenčního bodu antény základny ve WGS 84 nebo odpovídajícím rámci. Pokud znáš souřadnice geodetické značky pod anténou, zohledni výšku a případné vodorovné odsazení antény. Nadmořská výška v Bpv a elipsoidická výška se liší. Chyba polohy základny se přenese do absolutní polohy celé trasy.
4. Pro základnu i externí rover aplikace přijímá observační **RINEX 2/3**, **Septentrio SBF**, **u-blox UBX** a **RTCM 3** s měřicími zprávami. Navigaci lze importovat jako samostatný RINEX. Podporované jsou i soubory komprimované pomocí gzip (`.gz`). Kompaktní RINEX Hatanaka (`.crx`, `.YYd`) napřed převeď na běžný observační RINEX. Pro RTCM 3 si poznamenej skutečné datum začátku měření. [Dokumentace RTKLIB](https://www.rtklib.com/rtklib_document.htm) · [Příručka přijímače mosaic-X5](https://www.ardusimple.com/wp-content/uploads/2024/10/mosaic-X5-Firmware-v4.14.10-Reference-Guide.pdf)

## 4. Import a výpočet ve webu

1. Při přenosu přes Sambu nejprve dokonči kopírování souborů na disk **PPK**. Pro import z flash disku připoj médium FAT, exFAT nebo NTFS přímo k Raspberry Pi.
2. Na stejné místní síti otevři v prohlížeči `https://formula-logger.local`. Přihlas se a zvol **Výpočet PPK → Import ze Samby nebo USB**. Průzkumník otevře příchozí složku na NVMe. Pro flash disk přepni **Jednotku** na příslušné USB a podle potřeby klikni na **Připojit**.
3. U souboru základny klikni na **Importovat pro PPK**. Počkej na **Hotovo**. Stejně přidej potřebné navigační soubory, případně externí rover. Soubor se uloží do databáze na NVMe. Po dokončení všech importů můžeš USB v kartě **Soubory** odpojit. Opětovný import shodného obsahu rozpozná kontrolní součet SHA-256.
4. V kartě **Výpočet PPK** vyber **Rover nebo jízda** a **Stacionární základna**. Pokud používáš samostatný navigační RINEX, označ jej v seznamu navigace. Na Windows přidáš další položky podržením Ctrl. Navigace získaná při převodu surového záznamu vstupuje do výpočtu automaticky.
5. U **Referenčních souřadnic základny** vyber **Zaměřená poloha antény** a zadej šířku, délku a elipsoidickou výšku. Možnost **Použít APPROX POSITION XYZ z hlavičky základny** použij, pokud znáš původ a přesnost zapsaných souřadnic. U souboru RTCM 3 vyplň datum měření.
6. Klikni na **Spočítat souřadnice**. Výpočet běží na Pi a můžeš zavřít prohlížeč. Po dokončení vyber výpočet v seznamu **Uložený výpočet**. Zobrazí se počet epoch **RTK Fix**, **RTK Float** a dalších řešení, konkrétní souřadnice základny, verze výpočetního programu a tabulka výsledků. Tlačítko **Stáhnout CSV** stáhne všechny vypočtené epochy. Vlastní import a výpočet běží i bez internetu.

## 5. Jak číst a uchovat výsledky

**RTK Fix** znamená, že řešič určil celočíselné ambiguity nosné fáze. **RTK Float** znamená, že ambiguity zůstaly odhadnuté jako reálná čísla. U každého vzorku sleduj také počet družic a odhad směrodatné odchylky v severním, východním a svislém směru. Tyto hodnoty popisují odhad řešiče. Absolutní přesnost ověř opakovaným měřením na nezávisle zaměřeném bodě. [Příručky RTKLIB](https://www.rtklib.com/rtklib_document.htm)

Vypočtené souřadnice a importované zdrojové soubory jsou v `/var/lib/formula-manager/ppk.sqlite3`. Vstupy jsou uložené po částech a každému výpočtu patří vlastní sada epoch. U jízdy se zachová vazba na původní záznam v `logger.sqlite3`. CSV obsahuje GPS týden a milisekundy od začátku GPS týdne, šířku a délku ve stupních, elipsoidickou výšku v metrech, číselnou kvalitu (1 = Fix, 2 = Float), počet družic, odhady odchylek N/E/U, stáří diferenciálních dat a poměr pro test ambiguit. Čas GPS se od UTC liší o přestupné sekundy. Pro konzistentní kopii databáze zvol **Soubory → Data loggeru na NVMe → ppk.sqlite3**. Pro opakování výpočtů z jízd uchovej také `logger.sqlite3`.

Výchozí profil používá kinematické relativní řešení, dvě frekvence, elevační masku 15° a poměrový práh 3. Zpracovává dostupná pozorování GPS, GLONASS, Galileo a BeiDou. Na dvougigabajtovém Pi běží vždy jedna úloha PPK. Externí řešič má nižší prioritu CPU a limit adresního prostoru 768 MiB. Dlouhé relace plánuj po jízdě. Při chybě si v seznamu úloh přečti důvod. Nejčastěji jde o chybějící efemeridy, nulové měřicí epochy nebo nesouběžné záznamy. Poté můžeš spustit nový výpočet se stejnými importovanými vstupy.

## 6. Ověření po nasazení

Na Pi lze následujícími příkazy zkontrolovat služby, konfiguraci sdílení a skutečný výpočet. Poslední příkaz stáhne tři malé referenční soubory RTKLIB, ověří jejich kontrolní součty a použije dočasnou databázi.

```bash
cd ~/Formula_Manager
systemctl is-active formula-manager smbd avahi-daemon tailscaled
testparm -s --section-name=PPK --parameter-name=path
tailscale status
python3 deploy/check_ppk.py
```

Na referenční dvojici měření a navigaci vyšlo lokálně **115 epoch, všechny RTK Fix**. V prohlížeči byl ověřen přenos tří souborů přes Sambu, import, uložení výsledku, stránkování a stažení CSV. Tyto hodnoty patří referenčním datům. První test na vlastním Pi proveď při venkovním příjmu se souběžným záznamem základny a roveru. [Referenční měření projektu RTKLIB](https://github.com/tomojitakasu/RTKLIB/tree/rtklib_2.4.3/test/data/rinex)

