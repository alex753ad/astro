# Астрологические глифы — Noto Sans Symbols / Symbols 2 (сабсет)

Используются в `NatalChart.jsx` для символов планет, знаков зодиака и узлов
(вместо системных шрифтов — см. пункт 2 задания «навигация/шрифт/планер»:
на iOS/Android системный фолбэк для этих Unicode-символов часто отсутствует
или подменяется цветным emoji-шрифтом, который игнорирует `fill`).

## Источник — важно

Файлы скачаны **с `fonts.googleapis.com/css2`, не с зеркала google/fonts на
GitHub**. У зеркала (`raw.githubusercontent.com/google/fonts/...`) на момент
загрузки было расхождение в покрытии кодпоинтов с тем, что реально отдаёт
Google по CSS API, — если понадобится перекачать файлы заново, качать нужно
через тот же CSS-эндпоинт, а не напрямую из репозитория:

```bash
curl -sSL -A "Mozilla/5.0" \
  "https://fonts.googleapis.com/css2?family=Noto+Sans+Symbols&family=Noto+Sans+Symbols+2&display=swap" \
  -o google_css.css
# в google_css.css — актуальные url(...) на fonts.gstatic.com для каждого шрифта
```

На момент загрузки (2026-08-13) это были:
- `https://fonts.gstatic.com/s/notosanssymbols/v47/rP2up3q65FkAtHfwd-eIS2brbDN6gxP34F9jRRCe4W3gfQ8gag.ttf`
- `https://fonts.gstatic.com/s/notosanssymbols2/v25/I_uyMoGduATTei9eI8daxVHDyfisHr71ypM.ttf`

(версии `v47`/`v25` со временем сменятся — брать актуальные url из
`google_css.css`, а не эти константы).

## Покрытие: зачем два файла

Нужных кодпоинтов — 25 (12 знаков зодиака, 10 планет, 2 узла, 1 ретро).
Покрытие между двумя шрифтами Noto устроено не так, как можно было бы
ожидать: почти всё лежит в **Noto Sans Symbols** (первом), а ☉ Солнце —
**только** в Noto Sans Symbols 2. Один файл не покрывает всё. Ретроградный
℞ (U+211E) отсутствует в обоих — в коде он не берётся из этого шрифта,
рисуется как обычная латинская `R` тем же `fill`/`fontWeight`.

## Пересборка сабсетов

Требуется `fonttools` (уже используется в backend, `pip show fonttools`) и
модуль `brotli` для woff2-энкодера:

```bash
pip install brotli
```

Команды (относительно скачанных `NotoSansSymbols.ttf` / `NotoSansSymbols2.ttf`):

```bash
python3 -m fontTools.subset NotoSansSymbols.ttf \
  --unicodes=2648-2653,263D,263F,2640,2642-2647,260A,260B \
  --flavor=woff2 --output-file=NotoSansSymbols-subset.woff2 \
  --no-hinting --desubroutinize --layout-features=''

python3 -m fontTools.subset NotoSansSymbols2.ttf \
  --unicodes=2609 \
  --flavor=woff2 --output-file=NotoSansSymbols2-subset.woff2 \
  --no-hinting --desubroutinize --layout-features=''
```

Результат: `NotoSansSymbols-subset.woff2` (23 кодпоинта, ~3 КБ),
`NotoSansSymbols2-subset.woff2` (1 кодпоинт — Солнце, ~0.7 КБ).

## Лицензия

SIL Open Font License 1.1, Copyright 2022 The Noto Project Authors. Текст —
`OFL-NotoSansSymbols.txt` и `OFL-NotoSansSymbols2.txt` (по одному на
исходный шрифт, оба сабсета из них происходят).

## Единственный источник — эти два .woff2, инлайнятся Vite на сборке

Раньше здесь была вторая копия: тот же шрифт ещё раз, base64-литералом
внутри `NatalChart.jsx` (нужен был для захвата PNG — см. ниже). Проблема —
две копии одного и того же байткода рано или поздно разъедутся, если
обновить сабсет и забыть про вторую. При первой же ручной вставке литерала
уже словили испорченный символ в base64 (нашли только сверкой sha256).

Теперь копия одна — эти файлы. `NatalChart.jsx` импортирует их напрямую:

```js
import astroSymbolsSrc  from '../assets/fonts/NotoSansSymbols-subset.woff2?inline';
import astroSymbols2Src from '../assets/fonts/NotoSansSymbols2-subset.woff2?inline';
```

`?inline` — модификатор Vite (с 4.5+, тут используется 5.4.21): импорт
всегда даёт готовую `data:` URI строку с base64 самого файла, независимо от
размера, без ручного кодирования. `NatalChart.jsx` подставляет её в
`@font-face` внутри собственного `<style>` SVG.

Почему именно так, а не `@font-face` в `index.css`: `captureSvgPng` в
`ChartPage.jsx` (PNG-экспорт для карточки/PDF) клонирует SVG и рендерит его
через `<img src="blob:...svg">` — в этом режиме браузер не подгружает
внешние `@font-face` по `url()` (та же причина, по которой уже понадобился
`resolveSvgVarColors` для CSS-переменных). `@font-face` с `data:` URI внутри
самого SVG работает в обоих контекстах — и на странице, и в захваченном
изображении — без второй копии и без риска, что объявления разойдутся.

Раньше `@font-face` дублировался и в `index.css` — с тем же именем семейства
`AstroSymbols` и тем же `unicode-range`, что создавало два конкурирующих
объявления для единственного потребителя (сам `NatalChart.jsx`, который
всегда несёт свой `<style>` с этим же шрифтом). Убрали: `AstroSymbols`
используется только этим компонентом, второе объявление было чистой
избыточностью, а не разделением ролей.

Файлы лежат в `src/`, а не в `public/` — только так их можно импортировать
как модуль и использовать `?inline`; `public/` Vite копирует как есть, без
доступа к сборке.

---

# UI-шрифты мобильной сборки — Space Grotesk / Inter (сабсет по начертаниям)

`SpaceGrotesk-600.woff2`, `SpaceGrotesk-700.woff2`,
`Inter-{400,500,600}-{cyrillic,latin}.woff2` — используются
`frontend/src/mobile/` (Capacitor-приложение) через `@font-face` в
`frontend/src/mobile/fonts.css`.

## Зачем локально, а не как в вебе

Веб (`index.html`) подключает оба шрифта с `fonts.googleapis.com` —
`<link rel="preconnect">` + `<link rel="stylesheet" href="...css2?family=...">`.
Мобильное приложение открывается из `file://`/`https://localhost` и обязано
работать без сети сразу после установки (см. `CAPACITOR.md`) — внешний
`<link>` на Google Fonts недопустим тем же способом, каким недопустим
инлайновый `<script>` в `index.html` (см. комментарий там же). Поэтому здесь
— не ссылка, а сами файлы, byte-for-byte из официального источника, тем же
способом, каким уже собраны сабсеты Noto Sans Symbols выше.

## Источник и как перекачать заново

Файлы взяты из npm-пакетов `@fontsource/space-grotesk@5.3.0` и
`@fontsource/inter@5.3.0` (`node_modules/@fontsource/*/files/*.woff2` после
`npm install @fontsource/space-grotesk @fontsource/inter`, пакеты после
копирования удалены — они нужны были только как источник файлов, не как
зависимость времени сборки). Fontsource публикует те же файлы, что отдаёт
`fonts.gstatic.com`, с тем же байткодом — распаковка их npm-пакета проще и
воспроизводимее, чем ручной `curl` по `fonts.googleapis.com/css2`.

## Почему не все начертания и не все сабсеты Google-версии

Google Fonts на вебе грузит Space Grotesk `400;500;600;700` и Inter
`400;500;600` — калька с `index.html`. Мобильный экран входа использует
только то, что реально требует DESIGN_SYSTEM.md для заголовков/кнопок
(`text-lg`+, `font-weight: 600–700`) и текста (`text-base`, `400`; подписи
полей, `text-xs` — тоже 700, но уже покрыто); `500` для Inter взят с запасом
под будущие экраны, не используется сегодняшним экраном входа впрямую.
Тянуть весь набор весов ради двух экранов — лишний вес в офлайн-бандл без
видимого эффекта.

Сабсеты — по языку глифов, а не «как у Google»: **Inter** взят в
`cyrillic` + `latin` (UI полностью на русском, плюс email/версия — латиница).
**Space Grotesk** взят только в `latin` — **у него нет кириллического
покрытия вовсе** (`metadata.json` пакета: `"subsets": ["latin", "latin-ext",
"vietnamese"]`). Это не ограничение сабсетирования, а факт исходного шрифта:
то же самое уже происходит и в вебе — `font-family: 'Space Grotesk', ...` на
русском тексте молча не находит ни одного кириллического глифа и рендерится
шрифтом, стоящим в стеке следующим. Стек в `mobile/fonts.css` — намеренно
`'Space Grotesk', 'Inter', system-ui, sans-serif` (не как в `index.css`,
где после Space Grotesk сразу `system-ui`): для кириллицы это даёт
последовательный Inter вместо шрифта ОС, ближе по рисунку к дизайн-системе.
Латиница (сам бренд «Aristea Timeline», версия сборки) рендерится Space
Grotesk по-настоящему.

## Лицензия

SIL Open Font License 1.1 для обоих — `OFL-SpaceGrotesk.txt` (Copyright 2020
The Space Grotesk Project Authors) и `OFL-Inter.txt` (Copyright 2020 The
Inter Project Authors). Тексты — из тех же npm-пакетов.

## Пересборка (другие веса/сабсеты)

```bash
npm install @fontsource/space-grotesk@5 @fontsource/inter@5
# нужные файлы лежат в node_modules/@fontsource/<name>/files/
#   <name>-<subset>-<weight>-normal.woff2
npm uninstall @fontsource/space-grotesk @fontsource/inter
```
