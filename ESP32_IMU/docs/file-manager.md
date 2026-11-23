# Práce se soubory

Správce má cestu s klikacími nadřazenými složkami, návrat do předchozí složky, krok nahoru, hledání v aktuální složce, řazení, hromadný výběr, přejmenování a přesun přes výběr cílové složky. Přesouvat lze i neprázdné složky. Přesun do vlastního podstromu a přepsání existujícího cíle jsou odmítnuté. Mazání složek vyžaduje prázdnou složku; potvrzovací dialog uvádí položky.

PNG, JPG/JPEG, GIF, WebP, BMP a AVIF se otevírají v náhledu, pokud je daný formát podporovaný prohlížečem. PDF používá přibalený PDF.js, bez internetu a externích služeb. Náhled vyplňuje obrazovku, nahoře má 48px lištu se šipkou zpět, názvem na jednom řádku a ikonami stažení / samostatného otevření. Stránkování a zoom zabírají dalších 40 px. Dokument nemá boční rámeček ani výplň. Podrobnosti o PDF reportech jsou v [recovery-and-reports.md](recovery-and-reports.md).

## Velké soubory

Nahrávání přijímá více souborů do fronty. Každý soubor se odesílá v blocích do 64 KiB s potvrzenou pozicí; celý soubor se do RAM desky nenačítá. Vidíš procenta, přenesená data, rychlost a odhad zbývajícího času. Ztracené potvrzení nezpůsobí zdvojení bloku. Po výpadku lze ve stejné kartě prohlížeče zvolit **Pokračovat v přenosu**. Tato karta musí zůstat otevřená, protože drží vybraný lokální soubor.

Při zavření / obnovení stránky se automaticky neodhaduje shoda jiného souboru pouze podle názvu a velikosti. Web ukáže rozpracovaný přenos a možnost zrušení. Po restartu desky nebo deseti minutách nečinnosti může zůstat `.upload-part`, který lze odstranit ve správci. Hotový název vzniká teprve po přijetí celé očekávané délky. Existující soubory se nepřepisují.

Download používá malé neblokující bloky. Běžné stahování má jedinou rezervaci pro celou desku: opakované kliknutí se zablokuje hned v prohlížeči a duplicitní požadavek odmítne také server (HTTP 409). Průběh lze sledovat a přenos zrušit. Rezervace bez zahájení přenosu vyprší po 120 s. PDF/obrázkové náhledy mají oddělené HTTP Range streamy, nejvýše tři zároveň.

Celková doba přenosu není omezená. Stream bez pokroku se po 30 sekundách uzavře; webový upload hlídá 45 sekund nečinnosti. Pomalý přenos s průběžným pokrokem nemusí skončit kvůli celkové délce. USB, změny souborů, restart a nový záznam se nesmí překrýt s otevřeným přenosem SD.

FAT32 omezuje jednotlivý soubor na 4 GiB − 1 B. Analyzátor CSV má samostatný limit 2 miliony řádků kvůli paměti prohlížeče. Velké soubory lze přenášet i bez načítání do analýzy.

Lokální simulátor provádí souborové operace pouze v `.cache/preview-sd`, nikoli na skutečné SD. `tests/storage_http.py` stejná API ověřuje proti simulátoru nebo desce a používá vlastní složku `/imu-files-check-*`.
