/**
 * FeedNowStrip.jsx — полоса «сейчас»: три строки заголовка (§6) + чипы
 * долгосрочных периодов (§4).
 *
 * Строки 1-2 добавлены заходом Б (§6 SPEC_FEED_VISUAL.md) — период Солнца и
 * состояние Луны.
 *
 * ⚠️ С 15.09.2026 недостижимость этой полосы при прокрутке ЗАКРЫТА, но не
 * здесь: наверху появилась её компактная копия (FeedNowCompact.jsx), а сама
 * полоса осталась в потоке и по-прежнему уезжает вверх. Ниже — прежний
 * разбор, почему липкой не сделали именно её.
 *
 * Полоса НЕ липкая (`position: sticky`),
 * хотя §6 явно просит `top: 0`. Причина — заголовки дней (`FeedDayHeader.jsx`)
 * уже липкие на том же `top: 0` того же скроллера, а высота этой полосы
 * плавает (строки 1-2 пропадают при нехватке данных) — без измерения фактической высоты и проброса её как
 * `top`-отступа в заголовки дней они наедут друг на друга или полоса
 * перекроет часть контента. Сделать правильно — отдельная, самостоятельная
 * задача (ResizeObserver + проброс отступа), не путать с содержимым строк.
 *
 * Чипы долгосрочных периодов — пять медленных планет (Юпитер, Сатурн,
 * Уран, Нептун, Плутон), по одному текущему периоду на планету, структурная
 * константа бэкенда. Из хронологического потока они изъяты полностью, и
 * это главное, ради чего полоса изначально была заведена.
 *
 * ⚠️ Высота полосы ФИКСИРОВАННАЯ, приём «высота ∝ длительности» к ней не
 * применяется — именно поэтому долгосрочные и вынесены. Период Плутона идёт
 * 19 лет; в потоке, где высота значит длительность, он растянулся бы на
 * тысячи пикселей и сломал бы шкалу для всего остального. После изъятия
 * самое длинное в потоке — месячный период Солнца, и приём снова честен.
 *
 * ⚠️ Что потеряно вместе с изъятием: привязка к шкале. «Сатурн выйдет из 7
 * дома через полгода» на таймлайне больше не видно, и §4 требовал
 * компенсировать это словами — срок писался текстом («с ноября 2012 по март
 * 2032») в карточке, раскрывавшейся по нажатию чипа.
 *
 * ⚠️ С 15.09.2026 раскрытия нет: чипы стали подписями (разбор — у Chip ниже),
 * и вместе с ним ушёл срок словами. Компенсация §4 сейчас НЕ выполняется —
 * это известный долг, а не недосмотр, и закрывается он переносом планера в
 * приложение целиком (пункт в TASKS.md), а не возвратом раскрытия.
 *
 * Порядок чипов — от самого короткого периода к самому длинному
 * (Юпитер → Плутон), НЕ по дате начала: периоды идут одновременно, и
 * хронология между ними бессмысленна.
 */

import React from 'react';
import HintButton from './HintButton';
import { glyph, glyphStyle } from '../lib/feedGlyphs';
import { daysBetween } from '../lib/feedTime';
// Отбор — общий с компактной полоской (FeedNowCompact.jsx): один факт,
// два вида. Разбор, почему вынесено, — в шапке lib/feedNow.js.
import { findMoonState, findSunPeriod, longtermChips, pluralDays } from '../lib/feedNow';
import { signInRu } from '../lib/ruDeclension';

/**
 * Планета и её дом — ПОДПИСЬ, а не кнопка.
 *
 * ⚠️ Рамку, фон и состояние «нажато» сняли 15.09.2026 по решению владельца, и
 * вернуть их без нового экрана нельзя. Причина в том, куда ведут осмысленные
 * действия всех трёх элементов этой полосы (период Солнца, знак Луны, дома):
 * они ведут В ПЛАНЕР, которого в приложении НЕТ.
 *
 * В вебе планер — три горизонта: месяц, неделя, долгосрочно. В приложение
 * попал только «долгосрочно», и попал вырванным куском — вот этими чипами.
 * Поэтому:
 *
 *   • у чипа дома раскрывать нечего: на free сервер отдаёт пустые theme и
 *     groups, то есть за нажатием стояла витрина под блюром с кнопкой,
 *     которая и так ничего не делала (onUpgrade сюда никто не передавал);
 *   • период Солнца — один из МНОГИХ периодов месячного планера, и делать
 *     нажимаемым его одного бессмысленно: остальных в приложении не
 *     существует;
 *   • знак Луны ведёт к прогнозу на день, а такого экрана в приложении тоже
 *     нет.
 *
 * Пока планер не перенесён целиком (пункт в TASKS.md), элемент, который
 * выглядит нажимаемым и не нажимается, хуже честной подписи: на это уже
 * споткнулись — тап по чипу уводил ленту на месяц назад, потому что
 * обработчик висел на всей полосе.
 */
function Chip({ event }) {
  const meta = event.meta || {};
  return (
    <div
      style={{
        flex: '1 1 0',
        minWidth: 0,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 2,
        padding: '4px 2px',
        color: 'var(--text-primary)',
      }}
    >
      <span style={{ ...glyphStyle, fontSize: 17 }}>{glyph(meta.planet)}</span>
      {/* «11 дом», без слова «дом» во второй строке места не хватает на
          узком экране — пять чипов делят ширину поровну (§12.3). */}
      <span style={{ fontSize: 11, fontFamily: 'var(--font-body)', fontWeight: 600, whiteSpace: 'nowrap' }}>
        {meta.house} дом
      </span>
    </div>
  );
}

export default function FeedNowStrip({ events, today, onHelp, chipsRef }) {
  const all = events || [];
  const longterm = longtermChips(all);
  const sunPeriod = findSunPeriod(all, today);
  const moonState = findMoonState(all, today);

  if (longterm.length === 0 && !sunPeriod && !moonState) return null;

  // Порядок и копия — в longtermChips() (lib/feedNow.js), общая с компактной
  // полоской.
  const chips = longterm;

  return (
    // position: relative — под кнопку «?» в правом верхнем углу
    // (SPEC_ONBOARDING.md §8). У экрана «Лента», в отличие от «Карты», нет
    // ни <header>, ни <h1> — ставить кнопку больше некуда, а заводить ради
    // неё полноценную шапку значит отъесть вертикаль там, где её и так не
    // хватает (тот же довод, по которому 06.09.2026 решено не делать
    // липкими одновременно полоску дней и заголовок дня).
    <section style={{ padding: '12px 0 4px', position: 'relative' }}>
      {onHelp && (
        <HintButton
          onClick={onHelp}
          style={{ position: 'absolute', top: 8, right: 0, zIndex: 2 }}
        />
      )}

      {/* Строка 1 (§6) — период Солнца, остаток словами. paddingRight —
          место под кнопку «?», иначе остаток дней уходит под неё. */}
      {sunPeriod && (
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 4, paddingRight: 36 }}>
          <span style={{ ...glyphStyle, fontSize: 17, color: 'var(--color-warning)' }}>☉</span>
          <h2
            style={{
              margin: 0,
              fontSize: 19,
              fontWeight: 600,
              fontFamily: 'var(--font-display)',
              color: 'var(--text-primary)',
            }}
          >
            Период Солнца
          </h2>
          <span style={{ marginLeft: 'auto', fontSize: 13, color: 'var(--text-secondary)', flexShrink: 0 }}>
            {(() => {
              const left = daysBetween(today, sunPeriod.ends_at.slice(0, 10));
              return `${left} ${pluralDays(left)}`;
            })()}
          </span>
        </div>
      )}

      {/* Строка 2 (§6) — состояние Луны. Не хватает данных — строки нет вовсе. */}
      {moonState && (
        <div style={{ margin: '0 0 8px', fontSize: 13, color: 'var(--text-secondary)' }}>
          Луна в <span style={{ color: 'var(--text-primary)' }}>{signInRu(moonState.currentSign)}</span>
          {' · до '}{moonState.phaseGenitive} в{' '}
          <span style={{ color: 'var(--text-primary)' }}>{signInRu(moonState.phaseSign)}</span>
          {' '}{moonState.daysUntil} {pluralDays(moonState.daysUntil)}
        </div>
      )}

      {chips.length > 0 && (
        <>
          <h2
            style={{
              margin: '0 0 8px',
              fontSize: 11,
              fontWeight: 700,
              letterSpacing: '0.09em',
              textTransform: 'uppercase',
              fontFamily: 'var(--font-body)',
              color: 'var(--text-secondary)',
            }}
          >
            Планеты сейчас в домах
          </h2>

          <div ref={chipsRef} style={{ display: 'flex', gap: 6 }}>
            {chips.map((event) => <Chip key={event.key} event={event} />)}
          </div>
        </>
      )}
    </section>
  );
}
