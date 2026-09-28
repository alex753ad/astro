# Шрифты PDF (`backend/natal_pdf.py`)

| Файл | Что | Откуда |
|---|---|---|
| `Literata-Regular.ttf`, `Literata-SemiBold.ttf` | заголовки и проза разбора | Google Fonts, статические начертания 400/600 |
| `GolosText-Regular.ttf`, `GolosText-SemiBold.ttf` | таблицы, подписи | Google Fonts, 400/600 |
| `NotoSansSymbols-astro.ttf` | значки планет, знаков, аспектов (как в приложении) | Google Fonts, Noto Sans Symbols |
| `DejaVuSans.ttf` | запасной для символов: ☉ △ □ ℞, которых нет в Noto | DejaVu |

Лицензии — `OFL-*.txt` рядом (DejaVu — своя свободная лицензия).

⚠️ **Статические TTF, а не вариативные woff2 фронтенда**: ReportLab не читает
ни woff2, ни вариативные оси. Скачивать через CSS API с НЕбраузерным
User-Agent — тогда Google отдаёт `.ttf` по каждому весу:

```bash
curl -A "Wget/1.21" "https://fonts.googleapis.com/css2?family=Literata:wght@400;600&family=Golos+Text:wght@400;600"
```

Урезаны `pyftsubset` (fontTools) 28.09.2026 до латиницы и кириллицы:
`U+0020-007E,U+00A0-00FF,U+0400-045F,U+0490-0491,U+2010-2027,U+2030-2033,U+2039-203A,U+20BD,U+2116,U+2212`,
признаки `kern,liga,lnum,tnum`. Noto — только астрозначки:
`U+2609,U+263D,U+263F,U+2640,U+2642-2647,U+260A,U+260B,U+2648-2653,U+260C,U+260D,U+25B3,U+25A1,U+26B9,U+26BB,U+26B7,U+26B8`.

Символ, которого нет в шрифте строки, `natal_pdf._runs` отдаёт первому шрифту
цепочки `SymNoto → SymDejaVu`, где он есть; нет нигде — выбрасывает.
Квадратиков не должно быть — держит `tests/test_natal_pdf_layout.py`.
Расширяешь набор символов в PDF — проверь покрытие этим тестом, а не глазами.
