/**
 * FeedEventCard.jsx — карточка события в потоке ленты (§8 спецификации).
 *
 * В карточке: время, заголовок, знаки, точность и орб.
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
import { aspectColor, aspectSymbol, glyph, glyphStyle } from '../lib/feedGlyphs';
import { dateRangeShort, daysBetween, eventTitle, localToday, planetRu, signRu, timePart } from '../lib/feedTime';
import { planetDotColor } from '../lib/feedTimelineDot';

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

const rowStyle = {
  fontSize: 13,
  fontFamily: 'var(--font-body)',
  color: 'var(--text-secondary)',
  lineHeight: 1.5,
};

export default function FeedEventCard({ event, onOpen }) {
  const meta = event.meta || {};
  const locked = isLocked(event);
  const extraHeight = durationHeight(event);

  // Витрина под блюром — только у закрытого периода: у него есть высота
  // (она значит длительность), но нечего в ней показать, потому что на free
  // сервер отдаёт пустые theme и groups.
  const showFiller = locked && Boolean(extraHeight);

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

  // Орб и точность приходят вместе и только у транзита.
  const hasOrb = typeof meta.peak_orb === 'number';
  const precision = typeof meta.applying === 'boolean'
    ? (meta.applying ? 'точный' : 'отходит')
    : null;

  // Формула («☽ △ ♆   Луна — Нептун», §4 SPEC_FEED_VISUAL.md) заменяет
  // словесный заголовок только у транзита и только когда есть чем её
  // собрать — у остальных шести видов событий этих трёх полей нет вовсе,
  // и для них заголовок остаётся текстом из eventTitle(), как раньше.
  const formula = event.kind === 'transit' && meta.transit_planet && meta.natal_planet && meta.aspect_type
    ? meta
    : null;

  // Открытый разбор помечается только у транзитов: у фазы, затмения,
  // равноденствия и станции разбора нет в принципе, и «открыто» на них
  // значило бы «доступно то, чего не существует».
  const openInterpretation = event.kind === 'transit' && !locked;

  // Тапом открывается только то, что есть чем открыть: у события без тизера
  // и без locked панели показать нечего, и «нажимаемая» карточка, которая
  // ничего не делает, читается как поломка.
  const openable = locked && typeof onOpen === 'function';

  // Рамка и фон — только у карточки периода (§9 SPEC_FEED_VISUAL.md, «до
  // захода Б»: точка и линия слева уже показывают, что это событие, рамка
  // с ними спорит). showFiller — исключение: витрине под блюром нужна
  // видимая граница, иначе непонятно, где она заканчивается.
  const isPeriodCard = event.kind === 'planner_period';
  const boxed = isPeriodCard || showFiller;

  // Цветная полоса периода (§5) — та же таблица «планета → токен», что и у
  // точки на линии (feedTimelineDot.js): один источник, не вторая копия.
  const periodColor = isPeriodCard ? planetDotColor(meta.planet) : null;

  // Список рекомендаций периода (§5). Только у открытого: у закрытого
  // сервер отдаёт пустые theme/groups и показывает вместо них showFiller.
  const groups = isPeriodCard && !locked && Array.isArray(meta.groups) ? meta.groups : [];

  // Прогресс периода (§5, полоса внизу) — доля прошедшего от всего срока,
  // по календарным дням. today во всех расчётах ленты — локальная дата
  // устройства (см. localToday в feedTime.js), не UTC.
  const progressPct = isPeriodCard && event.ends_at
    ? Math.min(100, Math.max(0, Math.round(
      (daysBetween(event.at.slice(0, 10), localToday()) /
        Math.max(1, daysBetween(event.at.slice(0, 10), event.ends_at.slice(0, 10)))) * 100,
    )))
    : null;

  return (
    <article
      onClick={openable ? () => onOpen(event) : undefined}
      style={{
        position: 'relative',
        background: boxed ? 'var(--bg-card)' : 'transparent',
        border: boxed ? `1px solid ${openInterpretation ? 'var(--accent)' : 'var(--border)'}` : 'none',
        borderRadius: boxed ? 20 : 0,
        padding: boxed ? 16 : 0,
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
        cursor: openable ? 'pointer' : 'default',
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
      {periodColor && (
        <span style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: 3, background: periodColor }} />
      )}
      {/* Время дублировало бы колонку слева на линии (§3) — убрано у
          формулы транзита. У остальных видов колонка не даёт точного
          времени (период там — датой начала), поэтому строка остаётся. */}
      {!formula && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span
            style={{
              fontSize: 11,
              fontWeight: 700,
              letterSpacing: '0.09em',
              fontFamily: 'var(--font-display)',
              color: 'var(--text-secondary)',
            }}
          >
            {timePart(event.at)}
          </span>
          {openInterpretation && (
            <span
              // Точка объясняет рамку: одна рамка без подписи читается как
              // «выделено», но не говорит чем.
              aria-label="Разбор открыт"
              title="Разбор открыт"
              style={{
                width: 6,
                height: 6,
                borderRadius: '50%',
                background: 'var(--accent)',
                display: 'inline-block',
              }}
            />
          )}
        </div>
      )}

      {formula ? (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ ...glyphStyle, fontSize: 15 }}>{glyph(formula.transit_planet)}</span>
          <span style={{ ...glyphStyle, fontSize: 15, color: aspectColor(formula.aspect_type) }}>
            {aspectSymbol(formula.aspect_type)}
          </span>
          <span style={{ ...glyphStyle, fontSize: 15 }}>{glyph(formula.natal_planet)}</span>
          <span
            style={{
              fontSize: 13,
              fontFamily: 'var(--font-body)',
              color: 'var(--text-secondary)',
              minWidth: 0,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
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
              {hasOrb && (
                <span
                  style={{
                    padding: '2px 7px',
                    border: '1px solid var(--border)',
                    borderRadius: 7,
                    fontSize: 10.5,
                    color: 'var(--text-secondary)',
                    fontFamily: 'var(--font-body)',
                  }}
                >
                  {meta.peak_orb.toFixed(1)}°
                </span>
              )}
            </span>
          )}
        </div>
      ) : isPeriodCard ? (
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
          <span style={{ ...glyphStyle, fontSize: 17, color: periodColor, flexShrink: 0 }}>
            {glyph(meta.planet)}
          </span>
          <h3
            style={{
              margin: 0,
              fontSize: 18,
              fontWeight: 600,
              fontFamily: 'var(--font-display)',
              color: 'var(--text-primary)',
              lineHeight: 1.3,
              minWidth: 0,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {meta.planet_name}
          </h3>
          {event.ends_at && (
            <span
              style={{
                marginLeft: 'auto',
                flexShrink: 0,
                fontSize: 12,
                color: 'var(--text-secondary)',
                fontFamily: 'var(--font-body)',
              }}
            >
              {dateRangeShort(event.at, event.ends_at)}
            </span>
          )}
        </div>
      ) : (
        <h3
          style={{
            margin: 0,
            fontSize: 18,
            fontWeight: 600,
            fontFamily: 'var(--font-display)',
            color: 'var(--text-primary)',
            lineHeight: 1.3,
          }}
        >
          {eventTitle(event)}
        </h3>
      )}

      {/* Тема периода — вторая строка, если пришла. На free она пустая
          (сервер отдаёт `theme: ""` вместе с locked), и строки не будет. */}
      {meta.theme && <div style={rowStyle}>{meta.theme}</div>}

      {hasSigns && (
        <div style={rowStyle}>
          {degree}{signRu(meta.transit_sign)} → {signRu(meta.natal_sign)}
        </div>
      )}

      {/* Орб теперь в чипе формулы выше (§4) — здесь он был бы вторым
          показом того же числа. Точность остаётся: у неё нет второго места. */}
      {precision && <div style={rowStyle}>{precision}</div>}

      {/* Рекомендации периода (§5) — только у открытого, с непустым
          содержимым: у закрытого их место занимает showFiller ниже. */}
      {groups.map((group, gi) => (
        <div key={gi} style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          {(group.items || []).map((item) => (
            <div key={item} style={{ display: 'flex', alignItems: 'flex-start', gap: 8, ...rowStyle }}>
              <span
                aria-hidden="true"
                style={{
                  marginTop: 6,
                  flexShrink: 0,
                  width: 5,
                  height: 5,
                  borderRadius: '50%',
                  border: '1px solid var(--accent)',
                }}
              />
              <span>{item}</span>
            </div>
          ))}
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
