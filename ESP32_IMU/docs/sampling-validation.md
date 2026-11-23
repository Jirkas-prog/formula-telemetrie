# Skutečný senzor: odstranění ztrát při zátěži

Ověřeno 21. 10. 2026 na připojeném Adafruit ICM-20948 přes **SPI**, 500 / 500 / 100 Hz, ±16 g, ±2000 °/s, filtr 3. Výsledky I²C tímto fyzickým testem ověřené nejsou; transport zůstává podporovaný stejným ovladačem.

## Příčiny a opravy

1. Zapisovač čekal jeden RTOS tick po každém CSV řádku. CSV obsahuje také samostatné řádky magnetometru, takže celkový počet řádků může překročit 500 za sekundu. Při obsluze grafů a Wi-Fi se fronta nestíhala vyprázdnit. Nyní se vyprazdňuje po dávkách až 32 řádků a zapisovací úloha má vyšší prioritu. Fronta se nezvětšovala, stále má 2048 položek.
2. Kopírování a slučování grafové historie používalo stejný zámek jako vzorkování. Historii nyní zpracovává zapisovač pod samostatným zámkem. Web odesílá JSON po větších blocích místo samostatného síťového zápisu pro každý bod.
3. Hlavní webová úloha držela mutex sdílený s USB po celou dobu HTTP odpovědi. Čekající USB úloha jí mohla přes dědění priority zvýšit prioritu nad vzorkování. Nyní se pod mutexem pouze krátce nastaví atomický příznak vlastnictví webem. Dlouhé HTTP zpracování mutex nedrží; USB po tu dobu nemůže nově získat SD. Probíhající USB operace a předání zůstávají chráněné kontrolami vlastnictví a rozpracovaných přenosů.
4. Akcelerometr, gyroskop a teplota se nyní čtou po dávkách z hardwarového FIFO. Krátké zdržení CPU proto nepřepisuje nevyzvednuté odečty. Přetečení FIFO se hlásí samostatně, protože jeho ztrátu nelze vždy vyjádřit přesným počtem řádků.
5. Magnetometr má vlastní připravenost výsledku. Firmware kontroluje ST1 každé 2 ms a přečte HXL až ST2 pouze po DRDY. Původní čekání na další hostitelský 10ms termín mohlo nechat připravená data přepsat. Průběžné čtení celého datového bloku bez DRDY se při fyzickém testu ukázalo jako nevhodné: čtení chrání stará data proti přepsání a může zahodit právě dokončenou konverzi. Tato meziverze byla nahrazena řízeným čtením po DRDY.

## Výsledky

| Kontrola | Původní firmware, přibližně 65 s zátěže | Opravený firmware, přibližně 300 s zátěže |
| --- | ---: | ---: |
| Ztracené řádky ve frontě | 12 835 | **0** |
| Vynechané termíny A/G | 52 | **0** |
| Chyby komunikace se senzorem | 0 | **0** |
| Přepsané výsledky magnetometru | 45 | **0** |
| Přetečení hardwarového FIFO | nepoužívalo se | **0** |

Zátěž opakovaně načítala stav a kompletní rostoucí historii při běžícím záznamu, LCD a připojeném USB. Během testu se počítač jednou musel znovu připojit k AP; lokální logování pokračovalo bez ztrát.

Celý stažený soubor `/logs/boot_000019_run_001.csv` obsahuje **227 429 řádků**, 32 823 747 bajtů a přibližně 379 s měření:

- 189 445 nových odečtů akcelerometru a gyroskopu, průměr **499,99998 Hz** pro každou skupinu.
- 38 009 nových odečtů magnetometru, průměr **100,31565 Hz**.
- **0 chybných CRC, 0 mezer v pořadových číslech**. Současně nulové čítače ztrát při akvizici; samotná souvislá sekvence CSV by ztráty před vložením do fronty nevylučovala.
- Maximum zapisovací fronty **62 / 2048 položek**, maximum FIFO **84 bajtů**.
- Nejdelší sledovaný zápis/flush na SD **97,312 ms**; fronta ho absorbovala.
- Nejdelší probuzení vzorkovací úlohy **4,687 ms**, nejdelší sledovaný průchod čtením FIFO **3,105 ms**.

Strojové protokoly: `hardware-sampling-before.json`, `hardware-sampling-priority.json`, `hardware-ota.json`. Stažený skutečný CSV: `measurement-sampling-priority.csv`. Testovací záznam zůstává i na SD. Po jeho ověření skript spustil další nový záznam.

## Co znamená kolísání Hz

### Doplnění při zavedení Wi-Fi klienta

Připojování k LAB-WIFI zdrželo úlohu `esp_timer` na jádře 0 přibližně o 330–350 ms. Vzorkovač na jádře 1 původně čekal bez časového omezení na její notifikaci, takže se také zastavil a FIFO přeteklo. Nyní čeká nejvýše 2 ms a vyčítá FIFO i bez notifikace. Během OTA se samostatné čtení výslovně pozastavuje. V ověřeném startu boot 35 zůstala prodleva časovače 353,239 ms, ale prodleva vzorkovače byla jen 3,407 ms a přetečení FIFO, vynechané termíny i přepsané výsledky magnetometru byly nulové.

Čítače vynechaných termínů, přetečení FIFO a přepsaných výsledků magnetometru se nyní vztahují k aktivnímu záznamu. Prodleva při zápisu NVS po zastavení nebo během pauzy už dodatečně nezhoršuje výsledek ukončeného měření. Čítače se neresetují uprostřed běžícího záznamu.

Finální sestavení, boot 36, bylo ověřené 120 s opakovaných požadavků na stav a grafy přes LAB-WIFI. Všechny kontrolované stavy mají nulové `missed`, `dropped`, `ioErrors`, `magOverruns` a `fifoOverflows`. Následně stažený celý `/logs/boot_000036_run_002.csv` má 73 340 řádků / 10 484 316 bajtů, 0 chybných CRC a 0 mezer v sekvenci. Průměrné frekvence jsou 499,99925 / 499,99925 / 100,29501 Hz, nejdelší intervaly nových hodnot 3,544 / 3,544 / 13,992 ms. Protokol: hardware-network-final.json (lokální archiv zkoušek), data: `measurement-network-final.csv`. Síťové prodlevy při dotazech nepřerušily místní záznam.

Dashboard počítá počet skutečně převzatých nových hodnot v přibližně sekundovém okně. Posun jediného vzorku přes hranici tohoto okna změní údaj asi o 1 Hz. Výsledek 499–501 Hz s nulovými čítači ztrát proto sám o sobě neznamená ztrátu dat. Naměřený magnetometr na tomto kusu běžel průměrně 100,316 Hz při nominálním nastavení 100 Hz.

ICM-20948 v použitém režimu interně vzorkuje A/G nominálně na 1125 Hz. Výběr pro 500 Hz tak používá různé rozestupy mezi skutečnými konverzemi; není to hardwarově synchronizovaný 2ms zdroj. Firmware nezaplňuje mezery vymyšlenými odečty. Čas FIFO vzorků je odhadnutý z okamžiku přečtení, počtu čekajících vzorků a nominální ODR; jednotlivá časová značka není samostatný hardwarový timestamp. Maximální interval mezi označenými novými hodnotami v testovacím CSV byl 3,163 ms pro A/G a 14,023 ms pro magnetometr.

Register map a vlastnosti FIFO: [datasheet TDK ICM-20948](https://product.tdk.com/system/files/dam/doc/product/sensor/mortion-inertial/imu/data_sheet/ds-000189-icm-20948-v1.5.pdf). Kontrola průběhu čtení magnetometru vychází také z AKM AK09916, části 9.4.3 a 11.3.3.

## Opakování testu

`scripts/project.ps1 test` ověřuje i rozvrhování nezávislých frekvencí, pořadí bajtů a monotónnost časů FIFO. Fyzický test vyžaduje již běžící záznam:

```powershell
.\.tools\venv\Scripts\python.exe -X utf8 -B scripts/hardware_check.py --base http://imu-test.local --sample-seconds 300 --sample-label moje-mereni --capture
```

`--capture` záznam řádně uzavře, stáhne a zkontroluje CSV, pak spustí nový. Nemaže měření na SD. Závěr platí pro provedenou zátěž a zapojení; není to záruka proti odpojení senzoru, poruše SD, libovolně dlouhému blokování nebo výpadku napájení.
