# Formát O-Leaf pluginu 1

O-Leaf plugin je ZIP archiv obsahující v kořeni soubor
`oleaf-plugin.json`. Manifest musí obsahovat:

- `schemaVersion`: číslo `1`,
- `id`: stabilní identifikátor tvořený písmeny, čísly, tečkou, pomlčkou nebo
  podtržítkem,
- `name`: zobrazovaný název,
- `version`: verze pluginu,
- `contentRoot`: relativní cesta ke složce kopírované do projektu.

Volitelně lze přidat `description`, `entrypoint` a `homepage`. Archiv nesmí
obsahovat symbolické odkazy ani cesty opouštějící jeho kořen.

