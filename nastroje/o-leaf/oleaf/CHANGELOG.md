# Changelog

## 0.8.0

- WorkFlow Angular: modrošedé pozadí, limetkové akce, ostré rohy a jemné diagonály.
- Přehled posledních projektů s hledáním a zobrazením skutečného umístění.
- Otevírání existujících složek v `/media` a `/share` přímo, bez importu ZIP.
- Prohlížeč složek s výchozím umístěním, navigací po cestě, filtrem a vytvářením podsložek.
- Trvale uložená výchozí složka projektů pro každý pracovní prostor.
- Nový projekt lze vytvořit ve vybrané sdílené složce nebo v soukromém prostoru addonu.
- Vlastní dialogy namísto generických promptů a potvrzení prohlížeče.
- Jednotné SVG ikony, hledání souborů a výběr hlavního TeX souboru s uložením k projektu.
- Sdílené soubory se upravují na místě se zachováním oprávnění; kompilace běží pod odděleným UID v soukromé kopii.
- Kontrola připojených cest a symbolických odkazů; export vynechává interní data a odkazy.
- Oprava čekání na automatické uložení při přechodu do jiného souboru nebo projektu.
- Aktualizace závislostí pro ZIP upload a HTTP požadavky.

## 0.7.0

- Univerzální otevírání projektových souborů v levém pracovním panelu.
- UTF-8 texty bez ohledu na příponu zůstávají editovatelné; velké a binární
  soubory se otevírají bezpečně pouze pro čtení.
- PDF se zobrazuje jako plynule svisle posouvaný dokument vykreslený lokálním
  Popplerem, nezávisle na kompilovaném PDF v pravém panelu.
- Obrázky mají přímý náhled, zvuk a video vestavěný přehrávač.
- Neznámé binární formáty mají informační kartu, hex náhled prvních bajtů a
  možnost stáhnout originál bez změny.
- Náhledy zachovávají projektovou izolaci, blokují aktivní spuštění neznámých
  souborů a tlačítko Uložit povolují jen pro text.

## 0.6.0

- Obousměrná křížová navigace pomocí SyncTeXu.
- Kliknutí na zdrojový řádek posune PDF na odpovídající místo a označí jej terčem.
- Kliknutí nebo klepnutí do PDF otevře odpovídající zdrojový soubor, řádek zvýrazní a umístí na něj kurzor.
- Navigace funguje také přes `\\input` a `\\include`, pokud je zdroj uvnitř projektu.
- Na úzké obrazovce se automaticky otevře panel s nalezeným výsledkem.
- Tažení PDF pro posun je odlišeno od kliknutí, takže navigaci omylem nespustí.
- Kompilace nově vždy vytváří mapu `.synctex.gz`; staré PDF je nutné jednou znovu zkompilovat.

## 0.5.0

- Horní lišta bez posuvníků: při dostatečné šířce ikony s textem, na mobilu pouze ikony s přístupnými názvy.
- Zatahovací navigace; na telefonu se vysouvá nad pracovní plochou.
- Posuvný předěl editor/PDF s ovládáním myší, dotykem i klávesnicí.
- Jednoduché šipky vracejí uložené rozdělení, dvojité přepínají přímo mezi PDF a editorem přes celou pracovní plochu.
- Samostatně zapamatované rozložení pro úzkou a širokou obrazovku.
- Tmavý kurzor se světlým teplým obrysem ve všech variantách; při dotyku bez kurzoru.
- Oprava skrytí neaktivního průběhu kompilace a přizpůsobení PDF měnící se šířce panelu.
- Testy logiky rozložení a ověřované ZIP balení ze stejného zdroje jako instalační složka.

## 0.4.0

- Plynulý svislý PDF náhled se všemi stránkami místo pomalého přepínání jedné bitmapy.
- Líné přednačítání sousedních stran a serverová cache vykreslených stran PDF.
- Nezávislé měřítko editoru a PDF přes tlačítka, `Ctrl` + kolečko a pinch-to-zoom.
- Stylované svislé i vodorovné posuvníky editoru a PDF.
- Nová sada vlastních kurzorů pro běžný stav, odkaz, text, tažení a zakázané akce.
- PDF lze posouvat kolečkem, posuvníky, dotykem i tažením myší.

## 0.3.0

- Projektově oddělené připínání souborů uložené v metadatech projektu.
- Nová sekce Připnuté soubory nad úplným stromem souborů.
- Připnutí a odepnutí špendlíkem přímo ve stromu i v připnutém seznamu.
- Připnutí se automaticky přenese při přejmenování a odstraní při smazání souboru nebo složky.

## 0.2.0

- Automatické načtení a ověření PDF po dokončení kompilace.
- Živý průběh kompilace a kompletní spodní debug konzole.
- Sbalitelné podsložky a vytváření nových podsložek.
- Vlastní dropdowny ve stylu O-Leafu.
- Nastavení tématu, písma, zalamování řádků a výšky konzole.
- Stylovaný trvale viditelný scrollbar a drag/touch posouvání sidebaru.
- Responzivní přepínač Editor/PDF s automatickým otevřením náhledu po kompilaci.
- PDF náhled se vykresluje lokálně přes Poppler, funguje i bez PDF pluginu
  prohlížeče a nevyžaduje ruční obnovení.
- Addonové logo a ikona se znakem ❧.

## 0.1.0

- První funkční verze editoru.
- Anonymní a oddělené uživatelské pracovní prostory.
- Import/export projektů ZIP a import pluginů.
- XeLaTeX, BibLaTeX/Biber, náhled PDF a log kompilace.
