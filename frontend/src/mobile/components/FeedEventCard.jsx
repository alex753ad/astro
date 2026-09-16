/**
 * FeedEventCard.jsx — карточка события в потоке ленты (§8 спецификации).
 *
 * В карточке: заголовок, знаки, орб (точность — заливкой того же чипа, без
 * отдельной строки). Время не дублируется — оно уже в колонке слева на
 * линии (FeedTimelineNode.jsx, FeedScreen.jsx), карточка его не показывает
 * вообще ни для одного вида событий.
 *
 * ⚠️ Тизера здесь нет намеренно, и это правка спецификации от 05.09.2026.
 * Первый заход показывал intro/outro прямо в карточке — на боевых данных
 * текст оказался ОДИНАКОВЫМ на всех ~700 закрытых карточках (он общий для
 * тарифа, а не для события) и из подсказки превращался в шум, заодно
 * съедая высоту в ленте, где высота значит длительность. Полный тизер и
 * кнопка доступа живут в панели по тапу (FeedEventPanel.jsx) — как на вебе,
 * где разбор тоже открывается отдельной панелью, а не лежит в списке.
 *
 * ⚠️ Помечается ОТКРЫТОЕ, а не закрытое (решение владельца 05.09.2026).
 * Сначала стоял замок на закрытых — и он оказался на 689 карточках из 718:
 * пометка, которая стоит почти везде, не сообщает ничего, кроме шума.
 * Открытых на free всего два (топ-2 значимых транзита, их выбирает
 * бэкенд) — вот их и видно.
 *
 * Карточка одна на все семь видов событий, остающихся в потоке. Отдельных
 * вёрсток по kind нет: у не-транзитов просто нет части полей (знаков, орба),
 * и строки не рисуются. Развилка на каждый вид дала бы семь почти
 * одинаковых блоков, которые разойдутся при первой же правке.
 */

import React from 'react';
import BlurredHint from './BlurredHint';
import FeedLockMark from './FeedLockMark';
import FeedOrbChip from './FeedOrbChip';
import { aspectColor, aspectSymbol, glyph, glyphStyle } from '../lib/feedGlyphs';
import { daysBetween, eventTitle, localToday, periodRangeFull, planetRu, signRu } from '../lib/feedTime';
import { planetDotColor } from '../lib/feedTimelineDot';
import { splitItemLabel } from '../lib/plannerItemLabel';

// Высота блока пропорциональна длительности (§8). Коэффициент подобран под
// то, что реально остаётся в потоке после изъятия долгосрочных периодов:
// самый длинный — месячный период Солнца, 30 суток, то есть +75px к базовой
// высоте. Потолок НЕ вводится (решение владельца, §12.2): пропорция должна
// остаться честной.
const PX_PER_DAY = 2.5;

/** Точка на шкале (транзит, фаза, станция) против периода с длительностью. */
function durationHeight(event) {
  if (!event.ends_at || !event.duration_days) return undefined;
  return Math.round(event.duration_days * PX_PER_DAY);
}

/**
 * Закрыто ли событие.
 *
 * `teaser != null` — единственный признак «закрыто» для транзита (§8):
 * бэкенд уже учёл free_unlocked, и топ-2 значимых транзита на free открыты.
 * Выводить это из тарифа на клиенте нельзя — получилась бы вторая копия
 * тарифного правила, которая разойдётся с серверной. `locked` закрывает
 * периоды планера, у которых тизера нет вовсе.
 */
export function isLocked(event) {
  return Boolean(event.teaser || event.locked);
}

/**
 * Открывается ли карточка тапом.
 *
 * Вынесено отдельно и покрыто тестом после дефекта 09.09.2026: условие
 * «открывается только закрытое» пережило появление разбора транзита и
 * оставило нажимаемыми ровно те карточки, у которых разбора нет, — а те, у
 * которых он есть, перестали открываться совсем. Заметить это можно было
 * только на устройстве и только на платном тарифе, где тизеров нет вовсе.
 */
export function isOpenable(event) {
  return isLocked(event) || event?.kind === 'transit' || isPlannerEvent(event);
}

/**
 * Событие планера — месячный период, проход Луны по дому или долгосрочный.
 *
 * У всех трёх одинаковый набор полей (одна функция `add()` в
 * backend/feed/builder.py), и все три открываются панелью: там срок,
 * тема и рекомендации. До 16.09.2026 открывалось только ЗАКРЫТОЕ — то есть
 * человек с платным тарифом не мог открыть ничего, хотя открыто было всё.
 * Ровно тот же дефект уже ловили на транзитах 09.09.2026.
 */
export function isPlannerEvent(event) {
  return typeof event?.kind === 'string' && event.kind.startsWith('planner_');
}

const rowStyle = {
  fontSize: 13,
  fontFamily: 'var(--font-body)',
  color: 'var(--text-secondary)',
  lineHeight: 1.5,
};

export default function FeedEventCard({ event, onOpen, major = false, collapsed = false, onToggle }) {
  const meta = event.meta || {};
  const locked = isLocked(event);
  const extraHeight = durationHeight(event);

  // Витрина под блюром — только у закрытого МЕСЯЧНОГО периода: у него есть
  // высота (она значит длительность), но нечего в ней показать, потому что на
  // free сервер отдаёт пустые theme и groups.
  //
  // ⚠️ Проход Луны по дому сюда не входит намеренно (решение владельца
  // 16.09.2026): вид события не должен зависеть от тарифа. Блюр давал бы free
  // рамку с витриной там, где у платного просто строка, — и лента читалась бы
  // по-разному у разных людей. Закрытость несёт значок (FeedLockMark).
  const showFiller = !collapsed && locked && Boolean(extraHeight) && event.kind === 'planner_period';

  // ⚠️ Высота по длительности идёт В ПАРЕ с витриной, а не сама по себе.
  // Растянутая карточка без содержимого — это пустая коробка, и владелец
  // просил такие не тянуть: у них высота по контенту. Поэтому minHeight
  // ставится ровно тогда, когда есть чем его заполнить.
  const minHeight = showFiller ? 64 + extraHeight : undefined;

  // Строка знаков — только когда пришли оба знака: у не-транзитов их нет.
  const hasSigns = meta.transit_sign && meta.natal_sign;
  const degree = typeof meta.transit_degree === 'number'
    ? `${meta.transit_degree.toFixed(1)}° `
    : '';

  // Орб приходит только у транзита; вид чипа (и правило «точный») живут в
  // FeedOrbChip.jsx — он же рисует этот чип в сжатой строке дня
  // (FeedEventRow.jsx), поэтому правило здесь не повторяется.
  const hasOrb = typeof meta.peak_orb === 'number';

  // Формула («☽ △ ♆   Луна — Нептун», §4 SPEC_FEED_VISUAL.md) заменяет
  // словесный заголовок только у транзита и только когда есть чем её
  // собрать — у остальных шести видов событий этих трёх полей нет вовсе,
  // и для них заголовок остаётся текстом из eventTitle(), как раньше.
  const formula = event.kind === 'transit' && meta.transit_planet && meta.natal_planet && meta.aspect_type
    ? meta
    : null;

  // ⚠️ У транзита нет словесного заголовка — заголовок это формула, и поднять
  // его «важность» кеглем h3 нельзя, потому что h3 у него нет вовсе. Крупный
  // транзит (feedRank.js) отличается от рядового РАЗМЕРОМ САМОЙ ФОРМУЛЫ, а не
  // новой строкой текста: выдать ему `event.text` словами — это уже правка
  // содержимого, и ровно по этой причине владелец 15.09.2026 отклонил
  // соответствующий вариант ритма. Не «улучшать» это подстановкой заголовка.
  const glyphSize = major ? 18 : 15;
  const wordSize = major ? 14.5 : 13;

  // Открытый разбор помечается только у транзитов: у фазы, затмения,
  // равноденствия и станции разбора нет в принципе, и «открыто» на них
  // значило бы «доступно то, чего не существует».
  const openInterpretation = event.kind === 'transit' && !locked;

  // Тапом открывается только то, что есть чем открыть.
  //
  // ⚠️ До 09.09.2026 условием было одно `locked`, и это было верно: в панели
  // показывался лишь тизер, а у открытого события тизера нет. С появлением
  // разбора транзита условие устарело и стало дефектом: у тарифа выше
  // бесплатного сервер не отдаёт тизеры ВООБЩЕ, поэтому ни один транзит не
  // открывался — приёмка это и поймала («тапаю на транзиты, ничего не
  // открывается»). На free не открывались ровно те два, ради которых разбор
  // и делался.
  //
  // Теперь у транзита всегда есть что показать: либо разбор, либо отказ с
  // объяснением. У лунных событий и станций разбора нет в принципе — они
  // остаются нажимаемыми только когда закрыты.
  const openable = isOpenable(event) && typeof onOpen === 'function';

  // Рамка и фон — только у карточки периода (§9 SPEC_FEED_VISUAL.md, «до
  // захода Б»: точка и линия слева уже показывают, что это событие, рамка
  // с ними спорит). showFiller — исключение: витрине под блюром нужна
  // видимая граница, иначе непонятно, где она заканчивается.
  const isPeriodCard = event.kind === 'planner_period';
  /**
   * ⚠️ Рамка — у ВСЕХ периодов планера и в обоих состояниях (решение владельца
   * 16.09.2026). Раньше она была только у месячного и только у раскрытого:
   * на одном экране Меркурий стоял в рамке, а Луна под ним — без, хотя это
   * одна и та же сущность. Свёрнутый и раскрытый вид отличаются ОБЪЁМОМ, а не
   * оформлением.
   */
  const boxed = isPlannerEvent(event) || showFiller;

  // Цвет планеты — та же таблица, что у точки на линии и у полосы в шапке
  // (feedTimelineDot.js): один источник на всё приложение, не вторая копия.
  const periodColor = isPlannerEvent(event) ? planetDotColor(meta.planet) : null;

  // Список рекомендаций периода (§5). Только у открытого: у закрытого
  // сервер отдаёт пустые theme/groups.
  //
  // ⚠️ Условие было `isPeriodCard`, то есть буллеты видел только МЕСЯЧНЫЙ
  // период. Проход Луны по дому приезжал с бэкенда с тем же непустым
  // `groups` — и молча не рисовался: недельная вкладка планера существовала в
  // ответе и не существовала на экране.
  const groups = !collapsed && isPlannerEvent(event) && !locked && Array.isArray(meta.groups) ? meta.groups : [];

  // Срок ЛЮБОГО периода — одним форматом (periodRangeFull). В свёрнутом виде
  // скрыт: решение владельца 16.09.2026 оставляет там заголовок и тему.
  const periodRangeText = !collapsed && isPlannerEvent(event) && event.ends_at
    ? periodRangeFull(event.at, event.ends_at)
    : '';

  // Прогресс периода (§5, полоса внизу) — доля прошедшего от всего срока,
  // по календарным дням. today во всех расчётах ленты — локальная дата
  // устройства (см. localToday в feedTime.js), не UTC.
  const progressPct = isPeriodCard && !collapsed && event.ends_at
    ? Math.min(100, Math.max(0, Math.round(
      (daysBetween(event.at.slice(0, 10), localToday()) /
        Math.max(1, daysBetween(event.at.slice(0, 10), event.ends_at.slice(0, 10)))) * 100,
    )))
    : null;

  /**
   * Тап по периоду: раскрыть/свернуть прямо в ленте (решение владельца
   * 16.09.2026) — это исключение из §5 «сжатый день не раскрывается», и оно
   * записано в DESIGN_SYSTEM как решение, а не как случайность.
   *
   * ⚠️ Переключение работает только у ОТКРЫТОГО периода. У закрытого тарифом
   * раскрывать нечего: сервер отдаёт пустые theme и groups, и «полный вид»
   * оказался бы тем же самым заголовком. Такой период по-прежнему открывает
   * панель — там каркас и «Открыть доступ» по правилу plannerAccess.js.
   * Иначе платный путь исчез бы из потока вовсе.
   *
   * ⚠️ Высота НЕ анимируется. Раскрытие меняет высоту блока, а анимация
   * высоты под липкой полосой уводит прокрутку — дефект этого класса в ленте
   * уже ловили (§5 DESIGN_SYSTEM.md, три попытки прокрутки к якорю). Рост
   * идёт ВНИЗ от тапнутого элемента, поэтому сам он с места не двигается и
   * компенсировать прокрутку не нужно.
   */
  const togglable = typeof onToggle === 'function' && isPlannerEvent(event) && !locked;
  const handleClick = togglable
    ? () => onToggle(event)
    : (openable ? () => onOpen(event) : undefined);

  return (
    <article
      onClick={handleClick}
      style={{
        position: 'relative',
        background: boxed ? 'var(--bg-card)' : 'transparent',
        // ⚠️ Цвет рамки у периода — цвет ПЛАНЕТЫ. Он же несёт опознание, и
        // поэтому цветной полосы слева больше нет: две приметы одного и того
        // же на одной карточке — это не «надёжнее», а шумнее.
        border: boxed
          ? `1px solid ${periodColor || (openInterpretation ? 'var(--accent)' : 'var(--border)')}`
          : 'none',
        borderRadius: boxed ? 'var(--radius-xl)' : 0,
        // Единственное различие свёрнутого и раскрытого — ОБЪЁМ: те же рамка,
        // фон и радиус, меньше воздуха внутри.
        padding: boxed ? (collapsed ? '10px 14px' : 16) : 0,
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
        cursor: (togglable || openable) ? 'pointer' : 'default',
        // minHeight, а не height: длительность задаёт нижнюю границу, но
        // длинный заголовок не должен обрезаться.
        minHeight,
      }}
    >
      {/*
        Цветная полоса периода (§5) — отдельный элемент, а не борт `border`.
        Утолщённый `border-left` держит скругление УГЛОВОЙ ДУГИ card'а, но не
        собственное: на стыке с 1px border остальных сторон дуга съезжает по
        радиусу иначе и торчит поверх скругления сверху/снизу. Прямоугольник
        без своего radius, вырезанный по форме card'а через `overflow:hidden`
        + `borderRadius` родителя (уже стоят на article), даёт ровно те же
        3px спецификации без этого эффекта.
      */}
      {formula ? (
        // alignItems: flex-start — строка формулы может стать двухрядной
        // (перенос вместо обрезки), значки остаются у ПЕРВОГО ряда.
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
          <span style={{ ...glyphStyle, fontSize: glyphSize }}>{glyph(formula.transit_planet)}</span>
          <span style={{ ...glyphStyle, fontSize: glyphSize, color: aspectColor(formula.aspect_type) }}>
            {aspectSymbol(formula.aspect_type)}
          </span>
          <span style={{ ...glyphStyle, fontSize: glyphSize }}>{glyph(formula.natal_planet)}</span>
          <span
            style={{
              fontSize: wordSize,
              fontWeight: major ? 600 : 400,
              fontFamily: 'var(--font-body)',
              color: 'var(--text-secondary)',
              // ⚠️ Свободное место строки принадлежит ЗАГОЛОВКУ, а не отступу
              // перед чипом (приёмка 15.09.2026). Подробнее — тот же разбор в
              // FeedEventRow.jsx.
              flex: '1 1 auto',
              minWidth: 0,
              // ⚠️ ПЕРЕНОС, а не многоточие. Первый заход 16.09.2026 поправил
              // только сжатую строку (FeedEventRow) и пропустил КАРТОЧКУ — а
              // именно ею транзит рисуется в раскрытом дне, то есть на том
              // самом экране, где обрезку и увидели («Меркурий — Ме…»).
              // Обрезка съедает вторую планету целиком, то есть половину
              // содержания аспекта.
              overflowWrap: 'anywhere',
            }}
          >
            {planetRu(formula.transit_planet)} — {planetRu(formula.natal_planet)}
          </span>
          {(openInterpretation || hasOrb) && (
            <span style={{ marginLeft: 'auto', flexShrink: 0, display: 'flex', alignItems: 'center', gap: 6 }}>
              {/* Рамки нет (см. boxed выше), поэтому «разбор открыт» переехал
                  сюда — раньше эта точка объясняла подсвеченную рамку
                  карточки, теперь она единственный носитель признака. */}
              {openInterpretation && (
                <span
                  aria-label="Разбор открыт"
                  title="Разбор открыт"
                  style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--accent)', display: 'inline-block' }}
                />
              )}
              {hasOrb && <FeedOrbChip meta={meta} />}
            </span>
          )}
        </div>
      ) : (
        /*
         * Заголовок ЛЮБОГО периода планера — один вид на все три горизонта
         * (решение владельца 16.09.2026). Раньше их было два: месячный период
         * показывал только имя планеты («Солнце») и срок в строке заголовка, а
         * проход Луны — «Луна в 3 доме» и срок отдельной строкой. Один экран,
         * два разных способа сказать одно и то же.
         *
         * Значок цветной (`--planet-*`, один источник с точкой на линии) —
         * опознавательный знак, как формула у транзита. Цвет при этом вторая
         * примета, не единственная: сам значок остаётся всегда.
         */
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
          {isPlannerEvent(event) && (
            <span style={{ ...glyphStyle, fontSize: 16, color: periodColor, flexShrink: 0 }}>
              {glyph(meta.planet)}
            </span>
          )}
          <h3
            style={{
              margin: 0,
              fontSize: collapsed ? 15 : 18,
              fontWeight: 600,
              fontFamily: 'var(--font-display)',
              color: 'var(--text-primary)',
              lineHeight: 1.3,
              flex: '1 1 auto',
              minWidth: 0,
            }}
          >
            {eventTitle(event)}
          </h3>
          {locked && isPlannerEvent(event) && !showFiller && <FeedLockMark />}
        </div>
      )}

      {/* Срок прохода — ОТДЕЛЬНОЙ строкой, а не рядом с заголовком: обе
          границы записаны полностью («16.09 Ср 19:33 – 19.09 Сб 23:47»), и в
          одну строку с заголовком это не влезает ни на одном телефоне.
          Переносится, не обрезается. */}
      {periodRangeText && <div style={rowStyle}>{periodRangeText}</div>}

      {/* Тема периода — вторая строка, если пришла. На free она пустая
          (сервер отдаёт `theme: ""` вместе с locked), и строки не будет. */}
      {meta.theme && <div style={rowStyle}>{meta.theme}</div>}

      {hasSigns && (
        <div style={rowStyle}>
          {degree}{signRu(meta.transit_sign)} → {signRu(meta.natal_sign)}
        </div>
      )}

      {/* Рекомендации периода (§5) — только у открытого, с непустым
          содержимым: у закрытого их место занимает showFiller ниже.

          ⚠️ Гротеск, а не антиква, и это по правилу, а не по недосмотру
          (§3 DESIGN_SYSTEM.md). Антиква положена прозе модели, читаемой
          подряд; здесь ни того, ни другого: строки приходят из статического
          справочника backend/transit/methodology.json, а список императивов
          с буллетами читают СКАНИРОВАНИЕМ — «что делать», — а не подряд.
          Засечки такое чтение замедляют. Спрашивали уже один раз: блок
          похож на тело разбора, потому что стоит в той же карточке. */}
      {groups.map((group, gi) => (
        <div key={gi} style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          {/* Метка группы («Обучение:», «Быт:») — жирным, как в веб-планере.
              Она не заголовок раздела, а подпись к списку, поэтому остаётся
              гротеском того же кегля: антиква здесь превратила бы список
              императивов в прозу (§3 DESIGN_SYSTEM.md). Приходит пустой у
              большинства домов — тогда строки нет вовсе. */}
          {group.heading && (
            <div style={{ ...rowStyle, fontWeight: 600, color: 'var(--text-primary)' }}>
              {group.heading}
            </div>
          )}
          {(group.items || []).map((item) => {
            // Метка Луны («Работа:») вшита в сам пункт, у Меркурия она
            // приходит отдельным `heading` — разбор в lib/plannerItemLabel.js.
            // Выделяем одинаково, иначе на одном экране подписи у разных
            // планет выглядят по-разному.
            const { label, rest } = splitItemLabel(item);
            return (
              <div key={item} style={{ display: 'flex', alignItems: 'flex-start', gap: 8, ...rowStyle }}>
                <span
                  aria-hidden="true"
                  style={{
                    marginTop: 6,
                    flexShrink: 0,
                    width: 5,
                    height: 5,
                    borderRadius: '50%',
                    border: `1px solid ${periodColor || 'var(--accent)'}`,
                  }}
                />
                <span>
                  {label && (
                    <strong style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{label} </strong>
                  )}
                  {rest}
                </span>
              </div>
            );
          })}
        </div>
      ))}

      {/*
        flex:1 + overflow:hidden — обязательная часть, а не оформление.
        Витрина ЗАПОЛНЯЕТ оставшееся место, но не добавляет своего: иначе
        двухдневный проход Луны с тремя строками витрины стал бы ВЫШЕ
        тридцатидневного периода Солнца, и пропорция длительности — главный
        приём ленты — начала бы врать в обратную сторону.
      */}
      {showFiller && (
        <div style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}>
          <BlurredHint />
        </div>
      )}

      {/* Полоса прогресса (§5) — во всю ширину карточки, поэтому отрицательные
          отступы гасят padding родителя; overflow:hidden на article (см. выше)
          подрезает её углы по общему borderRadius. */}
      {progressPct !== null && (
        <div style={{ margin: '4px -16px -16px', height: 3, background: 'var(--border)' }}>
          <div style={{ width: `${progressPct}%`, height: '100%', background: periodColor }} />
        </div>
      )}
    </article>
  );
}
