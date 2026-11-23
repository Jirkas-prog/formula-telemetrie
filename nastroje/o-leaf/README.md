# O-Leaf pro Home Assistant

O-Leaf je plně lokální LaTeX editor pro Home Assistant OS. Nabízí strom
projektu, zvýraznění syntaxe, automatické ukládání, kompilaci XeLaTeXem,
průběžný náhled PDF, SyncTeX, import a export ZIP a šablonové pluginy.

> [!IMPORTANT]
> Před prvním nahráním na GitHub jednou spusťte následující příkaz a dosaďte
> adresu nového veřejného repozitáře. Příkaz doplní adresu repozitáře i do
> instalačního tlačítka níže.
>
> ```powershell
> .\tools\set-repository-url.ps1 -RepositoryUrl "https://github.com/UZIVATEL/oleaf-homeassistant"
> ```

## Instalace

[![Přidat repozitář O-Leaf do Home Assistantu](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=__REPOSITORY_URL_ENCODED__)

1. Klikněte na tlačítko **Přidat repozitář do Home Assistantu** a potvrďte
   přidání repozitáře.
2. V obchodě s doplňky otevřete **O-Leaf** a zvolte **Instalovat**.
3. Po sestavení doplněk spusťte a zapněte **Zobrazit v postranním panelu**.

Ruční instalace repozitáře: v Home Assistantu otevřete **Nastavení → Doplňky →
Obchod s doplňky → Repozitáře** a vložte tuto adresu:

```text
__REPOSITORY_URL__
```

První sestavení může trvat déle, protože Home Assistant stáhne Node.js, TeX
Live a další závislosti. Po sestavení funguje editor i kompilace bez externí
cloudové služby.

## Požadavky

- Home Assistant OS nebo Home Assistant Supervised
- architektura `amd64` nebo `aarch64`
- pro Raspberry Pi je doporučen Raspberry Pi 4/5, alespoň 4 GB RAM a SSD

## Soukromí a data

Tento repozitář obsahuje jen zdrojový kód addonu. Neobsahuje uživatelské
dokumenty, účty, relace, hesla, importované pluginy ani sestavené PDF soubory.
Závislosti `node_modules` se na GitHub také neukládají; při sestavení se obnoví
z uzamčeného `package-lock.json`.

Po instalaci ukládá O-Leaf data do samostatného adresáře `addon_config`, který
Home Assistant připojí jako `/config`. Tato data zůstávají na zařízení a jsou
součástí zálohy addonu.

## Dokumentace

- [Instalace, používání a bezpečnost](oleaf/DOCS.md)
- [Historie změn](oleaf/CHANGELOG.md)
- [Formát šablonových pluginů](PLUGIN_FORMAT.md)

## Vývoj a vydání

```powershell
cd oleaf\app
npm ci
npm test
```

Home Assistant čte addon přímo z výchozí větve repozitáře. GitHub Release není
pro instalaci nutný; pro zveřejnění konkrétní verze lze navíc vytvořit tag
`v0.7.0` a připojit ZIP vytvořený skriptem `tools/package-addon.ps1`.
