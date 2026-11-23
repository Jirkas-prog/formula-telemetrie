# Telemetrie studentské formule

**Elektronická příloha bakalářské práce Jiřího Buršíka „Využití RTK systému pro telemetrii studentské formule“, Technická univerzita v Liberci.** Vydání z 23. listopadu 2026 spojuje zdrojový kód palubního GNSS loggeru, postup jeho sestavení a výsledky, které lze reprodukovat.

| Chci… | Kde začít |
|---|---|
| Porozumět měřicímu řetězci a datovému modelu | [Technická zpráva](docs/technicka-zprava.md) · [Úplná technická dokumentace pro tisk (PDF)](docs/technicka-dokumentace.pdf) |
| Nainstalovat Raspberry Pi a aplikaci | [Postup nasazení](docs/instalace.md) |
| Zaznamenat jízdu, porovnat stacionární měření nebo exportovat data | [Návod k obsluze Formula Manageru](Formula_Manager/README.md) |
| Importovat základnu a zopakovat výpočet PPK | [Postup PPK a síťový disk](Formula_Manager/PPK.md) |
| Prověřit, co bylo skutečně změřeno | [Protokol a podmínky zkoušek](docs/overeni.md) |
| Najít firmware ESP32 a studie, z nichž návrh vyšel | [Studie a inerciální experiment](docs/studie-a-imu.md) |
| Najít analytické zprávy, podklady k senzorice a související programy | [Doplňující autorské podklady](docs/dalsi-podklady.md) |
| Dohledat autorství, převzatý kód, licence a využití AI | [Registr zdrojů](docs/zdroje.md) a [soupis souborů s SHA-256](SOUBORY.tsv) |

Zdrojové kódy jsou v adresářích [Formula_Manager](Formula_Manager/) a [ESP32_IMU](ESP32_IMU/). Pro citaci použij konkrétní revizi Git. K reprodukci jízdy navíc patří nastavení receiveru, použitá anténa, původní měření roveru a základny, konfigurace řešiče a jeho verze. Terénní měření má vlastní datovou evidenci oddělenou od tohoto vydání softwaru.
