# Obnova po výpadku a PDF reporty

## Co firmware chrání

Nové CSV mají poslední sloupec `crc32`: osm hexadecimálních číslic CRC-32/ISO-HDLC z bajtů celého řádku před poslední čárkou, bez konce řádku. Soubory zůstávají běžným CSV pro Excel. Web ověřuje CRC při importu a poškozené řádky nepoužije v grafech ani statistikách PDF. Starší CSV bez CRC jsou nadále čitelná a report tento rozdíl uvede.

Před zahájením zápisu uloží ESP32 do vlastní NVS cestu otevřeného záznamu. NVS se nezapisuje s každým vzorkem. Při řádném uzavření nebo pauze se značka smaže; před pokračováním se znovu vytvoří. SD se při záznamu synchronizuje každých 250 ms a při uzavření.

Po nečistém vypnutí firmware před dalším záznamem automaticky zkontroluje označený soubor: hlavičku, kontrolní součty, celé řádky a rostoucí sekvenční čísla. Na webu a LCD ukazuje průběh. SD je během obnovy vyhrazená této kontrole, USB ani web ji nemohou měnit.

- Pokud je celý soubor platný, zůstane beze změny.
- Pokud je konec poškozený nebo neúplný, původní soubor se zachová jako `název.csv.recovery-source`.
- Platný začátek se zkopíruje přes `název.csv.repair-part`. Kopie se znovu přečte a ověří, teprve potom dostane původní název CSV.
- Pokud výpadek nastane i během opravy, další start opravu zopakuje z uchovaného originálu.
- `název.csv.recovery.json` popisuje zachráněné řádky, platnou délku a odstraněný konec. Zdroj obnovy se automaticky nemaže.
- Při nedostatku místa nebo I/O chybě zůstane původní soubor zachovaný a automatické nové měření se nespustí. Obnova kopírováním potřebuje volné místo pro platnou část záznamu.

To chrání integritu dat na úrovni aplikace, **nezaručuje odolnost samotného FAT32 ani elektroniky SD vůči libovolnému výpadku**. Poslední data v RAM, frontě nebo interní cache karty mohou chybět. Perioda 250 ms není garantovaný horní limit ztráty. Při poškození FAT, kvůli kterému kartu nelze připojit, firmware kartu neformátuje; je potřeba záloha a oprava na počítači. Pro garantované dokončení zápisu je nutné zálohované napájení a detekce výpadku, případně karta s ochranou proti ztrátě napájení.

## PDF z CSV

Ve správci souborů otevři nabídku `••• → PDF report`, nebo načti CSV a na stránce Grafy zvol **PDF report**. Vznikne lokálně v prohlížeči a otevře se na celé obrazovce; šipka dolů jej stáhne. Funguje i pro CSV z telefonu nebo počítače a nepotřebuje internet.

Report má čtyři stránky:

1. Zdroj, relativní čas, počet řádků, dostupné nastavení, minima, maxima, maximální absolutní hodnoty, počet čerstvých platných vzorků a počet dosažení limitu pro všech devět os.
2. Akcelerometr: tři samostatné grafy.
3. Gyroskop: tři samostatné grafy.
4. Magnetometr: tři samostatné grafy.

Počty a extrémy používají pouze nové platné odečty (`accel_new`, `gyro_new`, `mag_new`, `mag_valid`). Opakované hodnoty pomalejších skupin nezkreslují počty. Grafy pokrývají celý načtený CSV záznam, nezávisle na aktuálním přiblížení webového grafu. Zobrazení používá obálku min/max v 900 časových úsecích; špičky se zachovají, přesné řádky zůstávají v CSV. Červená vychází z uloženého `clip_mask`.

U reportu se uvádí vynechané neplatné řádky, mezery v sekvenčních číslech a přítomnost kontroly CRC. Bez připojeného senzoru nelze vytvořit skutečný naměřený záznam; místní náhled používá označená simulovaná data.

## Ověření

- `tests/recovery_native.cpp`: skutečný produkční validátor, všechny možné bajtové pozice výpadku v testovacím CSV, poškození bajtů, duplicity, zpětná sekvence a neplatné hlavičky.
- `tests/recovery_integration.cpp`: skutečný produkční postup obnovy nad soubory, s výpadky během přejmenování, kopírování, flush, protokolu a změny NVS; kontrola zachování originálu, dalšího startu, plné karty a částečné hlavičky.
- `tests/parser.cjs`: poškozené CRC řádky se nedostanou do analýzy.
- `tests/report.cjs`: čerstvost, validita magnetometru, extrémy a clipping; `--render` vytvoří čtyřstránkové zkušební PDF do `.cache`.
- `scripts/test_recovery.ps1`: kompiluje hostitelské C++ testy přes Visual Studio Build Tools. Je součástí `scripts/project.ps1 test`.
- `tests/check.py`: kontroluje i skutečné rámce zásobníku v sestaveném ESP32 ELF. Součet `loggerTask → recoverInterruptedLog → scanLog` musí nechat dostatečnou rezervu v 8KiB zásobníku. Obnova sdílí existující CSV buffer; nevytváří velké lokální kopírovací bloky.

Simulované výpadky testují software. IMU už je připojená a běh 500 / 500 / 100 Hz byl fyzicky ověřený (viz `sampling-validation.md`). Po skutečném odpojení uživatelem se 21. 10. 2026 odhalilo přetečení zásobníku obnovy; po opravě se celý 70 994 694bajtový nedokončený záznam zkontroloval, obsahoval 495 900 platných řádků a nevyžadoval zkrácení. Uživatel potvrdil funkční LCD. Další fyzický výpadek během samotného kopírování opravy testovaný není. Viz `recovery-stack-fix.md`.
