# O-Leaf — offline LaTeX editor pro Home Assistant

O-Leaf poskytuje běžný pracovní postup známý z Overleafu, ale veškerá data i
kompilace zůstávají v Home Assistantu. Webové rozhraní obsahuje strom souborů,
LaTeX editor se zvýrazněním syntaxe, automatické ukládání, kompilaci XeLaTeXem,
živý průběh kompilace, automaticky obnovovaný náhled PDF a úplnou debug konzoli.

## Instalace do Home Assistant OS

Nejjednodušší instalace je z veřejného GitHub repozitáře pomocí tlačítka v
kořenovém `README.md`. Tlačítko přidá repozitář do obchodu Home Assistantu;
potom stačí otevřít O-Leaf, zvolit **Instalovat** a **Spustit**.

Pro místní instalaci bez GitHubu:

1. Nainstalujte oficiální addon **Terminal & SSH** nebo **Samba share**.
2. Zkopírujte celou složku `oleaf` do `/addons/oleaf` na zařízení s Home
   Assistant OS. Ve složce musí být přímo soubory `config.yaml`, `Dockerfile`,
   `run.sh` a `DOCS.md`.
3. Otevřete **Nastavení → Doplňky → Obchod s doplňky** a v nabídce zvolte
   **Zkontrolovat aktualizace**.
4. V části **Místní doplňky** otevřete O-Leaf, stiskněte **Instalovat** a potom
   **Spustit**.
5. Zapněte **Zobrazit v postranním panelu**. O-Leaf má současně nastavené
   `panel_title` a `panel_icon`, takže jej Supervisor může nabídnout přímo v
   navigaci.

První sestavení je pomalejší a vyžaduje připojení k internetu, protože Home
Assistant sestaví obraz s TeX Live a Node.js. Po sestavení běží editor i
kompilace plně offline.

Podporované architektury jsou `amd64` a `aarch64`. Pro Raspberry Pi je kvůli
velikosti TeX Live a rychlosti kompilace doporučen Raspberry Pi 4/5 se 4 GB RAM
nebo více a SSD místo SD karty.

## Ukládání dat

Addon mapuje svůj adresář `addon_config` pro zápis. U instalace z GitHubu jsou
soubory z pohledu ostatních správcovských nástrojů Home Assistantu v adresáři
`/addon_configs/<id-repozitare>_oleaf/`. U místní instalace je tato cesta
`/addon_configs/local_oleaf/`:

```text
/addon_configs/local_oleaf/
├── account-recovery.json
├── auth/
│   ├── users.json
│   └── sessions.json
├── plugins/
└── workspaces/
    ├── guest/projects/
    └── users/<interní-id>/projects/
```

Anonymní návštěva používá jediný oddělený prostor `guest`. Přihlášený uživatel
vidí jen své projekty. Dokumenty nejsou šifrované, takže je správce může
zálohovat a obnovit běžnými souborovými nástroji. Home Assistant záloha addonu
zahrne data automaticky; addon používá studenou zálohu (`backup: cold`).

Prohlížečová cookie obsahuje pouze náhodný token relace. Hesla nejsou uložena
čitelně — `users.json` obsahuje scrypt hash se samostatnou solí. Ukládání
plaintext hesel by umožnilo jejich přečtení každému procesu nebo záloze s
přístupem k addonovým souborům.

## Obnova hesla správcem

Vytvořte nebo přepište soubor
`/addon_configs/<id-repozitare>_oleaf/account-recovery.json`. U místní instalace
použijte `/addon_configs/local_oleaf/account-recovery.json`:

```json
{
  "username": "uzivatel",
  "new_password": "nove-dostatecne-dlouhe-heslo"
}
```

O-Leaf soubor nejpozději během pěti sekund načte, nové heslo zahashuje a
plaintext nahradí potvrzením o provedení. Není nutné znát původní heslo a
dokumenty uživatele zůstanou beze změny.

## Projekty

- **Otevřít projekt** zobrazí nedávné projekty, hledání a volbu **Složka v Home Assistantu**.
- **Složka v Home Assistantu** prochází připojená úložiště `/media` a `/share`.
  Navigace začne ve výchozí složce z nastavení; můžete psát cestu, klikat na
  její části, filtrovat složky, přejít o úroveň výš nebo vytvořit podsložku.
  Tlačítkem **Otevřít tuto složku** ji připojíte jako projekt. Soubory se
  nekopírují do soukromého prostoru: úpravy i mazání souborů mění originály.
- **Nastavení → Složky projektů** ukládá výchozí cestu na server, samostatně
  pro hosta a každý lokální účet. Složka musí existovat a být zapisovatelná.
  Pokud chybí, použijte **Procházet**, přejděte do `/media` nebo `/share` a
  vytvořte potřebné podsložky. Výchozí návrh je `/media/projekty/latex`.
  Volba `projects_directory` v konfiguraci doplňku platí, dokud pracovní
  prostor neuloží vlastní volbu v aplikaci. Změna výchozí složky nepřesouvá projekty.
- **Nový projekt** otevře vlastní formulář s názvem a umístěním. Vytvoří novou
  složku se souborem `main.tex`; existující složku nikdy nepřepíše. Volba
  **Uložit do soukromého prostoru addonu** zachovává původní způsob ukládání.
- **Import ZIP** přijímá běžný Overleaf ZIP a vytvoří nový projekt.
- **Export ZIP** stáhne zdrojové soubory bez interních sestavovacích artefaktů.
- Výběr **Hlavní soubor** nabízí skutečné `.tex` soubory a pamatuje si volbu
  v projektu. Při prvním otevření složky upřednostní `main.tex`.
- Pole **Najít soubor** filtruje celý strom včetně podsložek. Složky i typy
  souborů mají sjednocené SVG ikony; připnuté soubory se zobrazí nad stromem.
- Kompilace používá XeLaTeX, Biber/BibLaTeX a vypnutý shell escape.
- Podsložky ve stromu lze sbalit, rozbalit a vytvářet přímo v levém panelu.
- Jednotlivé soubory lze připnout špendlíkem. Každý projekt si pamatuje vlastní
  seznam a zobrazuje jej v sekci **Připnuté soubory** nad úplným stromem.
- V levém pracovním panelu lze otevřít všechny soubory projektu. Platný UTF-8
  text (například `.tex`, `.txt`, `.md`, `.csv`, `.json`, `.yaml`, `.sty` nebo
  log) lze upravovat i bez známé přípony. PDF se zobrazí jako souvislý dokument,
  obrázky přímo a zvuk či video ve vestavěném přehrávači. Neznámé binární
  soubory se nikdy nepřepisují jako text: zobrazí se jejich velikost, typ, krátký
  hex náhled a tlačítko pro stažení originálu. Text nad 5 MB se z bezpečnostních
  důvodů otevírá pouze pro čtení.
- Levý panel má vlastní stále viditelný posuvník; posouvat lze kolečkem, tažením
  jezdce, tažením volné plochy myší i dotykovým tažením.
- Šipka na hraně navigace panel zatahuje a vysouvá. Na telefonu se navigace
  otevře nad obsahem; zavře ji i klepnutí mimo panel nebo klávesa `Escape`.
- Horní lišta nikdy není scrollovací. Na úzké obrazovce zobrazuje pouze ikony,
  na široké i popisky. Názvy akcí jsou dostupné přes tooltip a čtečky obrazovky.
- Předěl editor/PDF lze táhnout myší nebo dotykem. V rozděleném režimu šipka
  doleva otevře pouze PDF, šipka doprava pouze editor. V krajním režimu
  jednoduchá šipka obnoví uložený poměr a dvojitá otevře opačný panel.
  Předěl ovládají také klávesy `←`/`→`, `Shift` pro větší krok, `Home` pro PDF,
  `End` pro editor a `Enter` pro návrat k rozdělení.
- Prohlížeč si pamatuje poměr, režim panelů a stav navigace zvlášť pro úzké
  (do 700 px) a široké zobrazení. U velmi úzkého rozdělení se poměr dočasně
  omezí tak, aby ovládací prvky zůstaly uvnitř panelů.
- Kurzor používá standardní systémový vzhled a mění se podle druhu ovládání.
- Na užším panelu tlačítko **PDF/Editor** přepíná pracovní plochu. Po úspěšné
  kompilaci se aktuální PDF otevře automaticky bez ručního obnovení. Všechny
  strany jsou v jednom plynule svisle posouvaném dokumentu; sousední strany se
  přednačítají a server si vykreslené bitmapy ukládá do cache.
- Editor i PDF mají vlastní nezávislé měřítko. Lze je měnit tlačítky `−`/`+`,
  pomocí `Ctrl` + kolečka nad příslušnou plochou nebo gestem pinch-to-zoom.
  Obě hodnoty si prohlížeč pamatuje. Svislé i vodorovné posuvníky editoru a PDF
  používají vzhled O-Leafu; PDF lze navíc posouvat tažením myší a dotykem.
- Strany PDF vykresluje lokální Poppler, takže náhled není závislý na PDF pluginu
  prohlížeče.
- Editor a PDF jsou obousměrně propojené přes SyncTeX. Kliknutí do zdrojového
  textu otevře odpovídající stránku PDF a označí místo terčem. Kliknutí nebo
  klepnutí do PDF otevře příslušný zdrojový soubor a na několik sekund zvýrazní
  nalezený řádek. Na telefonu se automaticky zobrazí panel s výsledkem.
- Křížová navigace vyžaduje mapu `.synctex.gz`. Po aktualizaci ze starší verze
  proto každý projekt jednou znovu zkompilujte. Pokud se zdroje od poslední
  kompilace změnily, může poloha odpovídat předchozímu sestavení.
- Spodní konzole průběžně vypisuje celý stdout/stderr kompilátoru i diagnostiku
  načítání PDF. Tlačítkem lze její obsah zkopírovat.
- V dialogu **Nastavení** lze přepnout barevné téma, velikost písma, zalamování
  řádků a výšku konzole.

### Sdílené složky, oprávnění a zálohy

`/media` a `/share` jsou společná úložiště dostupná uživatelům addonu přes
Home Assistant Ingress. Nejsou oddělené podle lokálních O-Leaf účtů.
Soukromé projekty, nastavení a seznam připojených složek zůstávají oddělené.
Původní soukromé projekty se aktualizací nepřesouvají.

Při kompilaci připojeného projektu O-Leaf vytvoří soukromou pracovní kopii
zdrojů a v ní spustí TeX pod UID pracovního prostoru. Nemění vlastníka ani
oprávnění původních sdílených složek. Výsledné PDF a SyncTeX patří k této
kompilaci; další kompilace načte aktuální obsah původní složky. Symbolické
odkazy se neotevírají a kompilace projektu s odkazy vypíše chybu.

Pro zálohu zdrojů z `/media` a `/share` zahrňte tato úložiště do příslušné
zálohy Home Assistantu. Samotná záloha dat O-Leafu nenahrazuje zálohu externího
úložiště. Odpojení projektu přes API maže pouze jeho registraci a pracovní
kopii; mazání jednotlivého souboru v editoru naopak odstraní originál.

### Aktualizace na 0.8

Zkopírujte nové zdroje do stávající složky `/addons/oleaf`, obnovte seznam
místních doplňků a aktualizujte či přestavte O-Leaf. Je potřeba sestavit nový
obraz kvůli připojení úložišť i serverovým změnám; samotný restart starého
obrazu nestačí. Zachovejte existující slug `oleaf` a data v `addon_config`.

## Pluginy

Plugin je ZIP s následující strukturou:

```text
oleaf-plugin.json
template/
  main.tex
  další-soubory...
```

Minimální manifest:

```json
{
  "schemaVersion": 1,
  "id": "moje-sablona",
  "name": "Moje šablona",
  "version": "1.0.0",
  "description": "Popis pluginu",
  "contentRoot": "template",
  "entrypoint": "main.tex"
}
```

Plugin se importuje v levém panelu. Po importu jej vyberte, otevřete cílový
projekt a stiskněte **Použít**. Lze pouze doplnit chybějící soubory nebo potvrdit
přepsání shodných názvů.

## Bezpečnostní model

- Webové rozhraní není vystaveno portem do LAN; je dostupné jen přes Home
  Assistant Ingress.
- Přístup k samotnému panelu nejdřív ověří Home Assistant.
- O-Leaf účet je volitelná druhá vrstva pro oddělení dokumentů více lidí.
- Jednotlivé kompilace běží pod rozdílnými linuxovými UID a shell escape je
  zakázán. Uživatelský TeX proto nemá přístup k heslovým hashům ani dokumentům
  jiného účtu.
- ZIP import odmítá absolutní cesty, `..`, symbolické odkazy a nadměrně velký
  rozbalený obsah.

O-Leaf nepouštějte přímo na veřejný internet. Vzdálený přístup řešte přes
zabezpečený Home Assistant, VPN nebo Home Assistant Cloud.

## Rozsah verze 0.5

Jde o funkční první verzi zaměřenou na samostatné psaní: chybí současná
kolaborace více kurzorů, komentáře, historie podobná Gitu a cloudová synchronizace
Overleafu. Dokumenty, účty, pluginy, kompilace a PDF náhled jsou lokální a na
online Overleafu nezávislé.
