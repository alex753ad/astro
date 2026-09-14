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

Исходных кодпоинтов было 25 (12 знаков зодиака, 10 планет, 2 узла, 1 ретро).
Покрытие между двумя шрифтами Noto устроено не так, как можно было бы
ожидать: почти всё лежит в **Noto Sans Symbols** (первом), а ☉ Солнце —
**только** в Noto Sans Symbols 2. Один файл не покрывает всё. Ретроградный
℞ (U+211E) отсутствует в обоих — в коде он не берётся из этого шрифта,
рисуется как обычная латинская `R` тем же `fill`/`fontWeight`.

⚠️ **05.09.2026: в `NotoSansSymbols-subset.woff2` добавлены ещё два —
☌ U+260C (соединение) и ☍ U+260D (оппозиция), для формулы транзита в
мобильной ленте (§4 SPEC_FEED_VISUAL.md, «значки планет вместо слов, аспект
цветом»). Тот же риск тофу, что у планет: оба знака лежат в блоке Misc
Symbols, а не в Dingbats/Geometric Shapes, где сидят остальные три символа
аспектов (□ △ ✶) — те системный шрифт покрывает почти всегда, эти два —
нет. Веб (`TransitTimeline.jsx`) рисует ☌/☍ системным шрифтом без этой
защиты — это не тронуто и остаётся открытым риском там же, где было.
Сейчас 27 кодпоинтов.

## Пересборка сабсетов

Требуется `fonttools` (уже используется в backend, `pip show fonttools`) и
модуль `brotli` для woff2-энкодера:

```bash
pip install brotli
```

Команды (относительно скачанных `NotoSansSymbols.ttf` / `NotoSansSymbols2.ttf`):

```bash
python3 -m fontTools.subset NotoSansSymbols.ttf \
  --unicodes=2648-2653,260C,260D,263D,263F,2640,2642-2647,260A,260B \
  --flavor=woff2 --output-file=NotoSansSymbols-subset.woff2 \
  --no-hinting --desubroutinize --layout-features=''

python3 -m fontTools.subset NotoSansSymbols2.ttf \
  --unicodes=2609 \
  --flavor=woff2 --output-file=NotoSansSymbols2-subset.woff2 \
  --no-hinting --desubroutinize --layout-features=''
```

Результат: `NotoSansSymbols-subset.woff2` (25 кодпоинтов, ~3.1 КБ),
`NotoSansSymbols2-subset.woff2` (1 кодпоинт — Солнце, ~0.7 КБ).

⚠️ При пересборке — не забыть раздвинуть `unicode-range` в ОБОИХ
потребителях (`mobile.css` и `NatalChart.jsx`), а не только пересобрать
файл: диапазон в CSS — это отдельное объявление, браузер решает по нему,
покрывает ли шрифт кодпоинт, независимо от того, что реально лежит внутри
файла. Разойдутся — новый глиф в файле есть, а браузер его не запросит.

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

# UI-шрифты — Literata / Golos Text (переменные, сабсет по языку)

`Literata-{cyrillic,latin}.woff2`, `GolosText-{cyrillic,latin}.woff2` —
подключаются `@font-face` в `frontend/src/mobile/mobile.css` (приложение).
Веб те же гарнитуры тянет с `fonts.googleapis.com` через `<link>` в
`index.html`.

**Четыре файла, а не восемь.** Обе гарнитуры переменные по весу, поэтому на
семейство нужен один файл на языковой сабсет. Прежняя пара занимала восемь
файлов (Inter в трёх начертаниях × два сабсета + Space Grotesk в двух).

## Зачем локально, а не как в вебе

Приложение открывается из `file://`/`https://localhost` и обязано работать
без сети сразу после установки (`CAPACITOR.md`) — внешний `<link>` на Google
Fonts недопустим тем же способом, каким недопустим инлайновый `<script>` в
`index.html`. Поэтому здесь не ссылка, а сами файлы — как и сабсеты Noto Sans
Symbols выше.

## Почему Literata и почему не две другие

Решение владельца 14.09.2026 по образцу на реальном тексте приложения
(`frontend/font-specimen.html` — открыть в браузере; снимки не
коммитились). Полная запись — `DESIGN_SYSTEM.md` §3,
здесь коротко, потому что спрашивают обычно у файлов шрифтов:

* **Literata** держит заголовок дня ленты на **13px** — сегодняшнем размере
  из `FeedDayHeader.jsx` — не теряя читаемости, и даёт плотную ровную строку
  на длинном русском абзаце.
* **Cormorant отклонён:** низкий рост строчных. При равном кегле мельче
  примерно на два пункта — абзац на 16px читается как 14px. Принять его
  значило бы поднимать кегли по всей ленте, то есть менять вёрстку ради
  шрифта. ⚠️ Это тот отказ, который тянет пересмотреть словами «он же
  красивее»: красивее он на витрине, а не на 13px в плотном списке.
* **Source Serif 4 отклонён:** ширина строки. Тот же абзац занимает заметно
  больше строк — на ширине телефона это лишняя прокрутка на каждой
  интерпретации.

⚠️ **Space Grotesk ушёл не по вкусу.** Кириллицы у него нет вовсе — Google
отдаёт три сабсета (`latin`, `latin-ext`, `vietnamese`). Русский заголовок
всегда проваливался на следующий шрифт стека: на вебе в системный, в
приложении в Inter. То есть выбранного display-шрифта русский пользователь
не видел никогда. **Требование к любому будущему кандидату на display:
кириллица проверяется до всего остального.**

## ⚠️ Ось `opsz` у Literata удалена физически — это намеренно

У исходной Literata **две** переменные оси: `wght` 400–900 и `opsz`
(оптический размер) 7–72. В лежащих здесь файлах оси `opsz` НЕТ — она
инстансирована в значение **14** при подготовке (команда ниже).

Причина: поведение `font-optical-sizing` в Android WebView проверить на
устройстве не удалось, а цена ошибки несимметрична. Ось, молча ушедшая в
крайнее значение (7 или 72), меняет рисунок шрифта **на всех экранах
разом** — и выглядит это не как поломка, а как «шрифт какой-то не такой».
Искать причину в оси оптического размера никто не станет.

Поэтому ось не настроена, а **удалена**: значения, которого нет в файле,
не может выбрать ни браузер, ни WebView, ни будущая правка CSS. Это сильнее
`font-optical-sizing: none`, который полагается на то, что движок его
уважает.

Значение 14 выбрано по нашим кеглям: display-шрифт работает на 13–28px
(на вебе ещё hero до 58px), 14 — середина основного диапазона. Если
понадобится другое — переинстансировать файл, а не добавлять CSS-правило.

## Источник и как перекачать заново

Файлы — сабсеты `cyrillic` и `latin` с `fonts.gstatic.com`, после чего
`opsz` инстансирована, а `wght` обрезана до 400–700 (веса выше 700 в
проекте не используются, а диапазон 400–900 весит больше).

```bash
python - <<'EOF'
import re, urllib.request
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'}
URL = ("https://fonts.googleapis.com/css2?family=Golos+Text:wght@400..600"
       "&family=Literata:opsz,wght@7..72,400..600&display=swap")
css = urllib.request.urlopen(urllib.request.Request(URL, headers=UA)).read().decode()
names = {'Golos Text': 'GolosText', 'Literata': 'Literata'}

for sub, block in re.findall(r"/\* ([a-z-]+) \*/\s*@font-face \{(.*?)\}", css, re.S):
    if sub not in ('cyrillic', 'latin'):
        continue
    fam = re.search(r"font-family: '([^']+)'", block).group(1)
    url = re.search(r'url\((https://[^)]+)\)', block).group(1)
    data = urllib.request.urlopen(urllib.request.Request(url, headers=UA)).read()
    path = f"{names[fam]}-{sub}.woff2"
    open(path, 'wb').write(data)

    f = TTFont(path)
    limits = {'wght': (400, 700)}
    if any(a.axisTag == 'opsz' for a in f['fvar'].axes):
        limits['opsz'] = 14           # см. раздел про opsz выше
    f = instancer.instantiateVariableFont(f, limits, inplace=False)
    f.flavor = 'woff2'
    f.save(path)
EOF
```

Нужен `fontTools` с поддержкой brotli (`pip install fonttools brotli`).
После перекачки сверить `unicode-range` в `mobile/mobile.css` с теми, что
отдаёт CSS Google: они задают, какой файл когда скачивается, и разъехавшись,
заставят тянуть латинский сабсет на русской странице.

## Лицензия

SIL Open Font License 1.1 для обеих — `OFL-Literata.txt` (Copyright 2017 The
Literata Project Authors) и `OFL-GolosText.txt` (Copyright 2019 The Golos
Text Project Authors). Тексты — из репозитория `google/fonts`.
