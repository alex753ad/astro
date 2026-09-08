/**
 * ChartScreen.jsx — экран «Карта» (SPEC_CHART_SCREEN.md).
 *
 * Шапка, колесо на всю ширину, шторка с тремя таблицами. Данных ровно
 * два запроса (§2), тарифных состояний нет вовсе: на free карта приходит
 * полной, блюрить нечего (CHART_API_RECON.md §3).
 *
 * ⚠️ Колесо — ВЕБОВСКИЙ компонент `components/NatalChart.jsx`, а не своя
 * реализация. В нём уже сделаны тригонометрия, щипковый зум с поворотом,
 * сброс по двойному тапу и подключение шрифта значков, а CSS-токены, на
 * которых он стоит, совпадают с мобильными до имени. Довод и разбор
 * альтернативы — CHART_API_RECON.md §6.
 *
 * ⚠️ Прокрутки у этого экрана нет: колесо и шторка делят высоту, список
 * внутри шторки прокручивается сам. Поэтому здесь, в отличие от ленты,
 * `overflow` внутри безопасен — ломать `position: sticky` нечего.
 */

import React, { useCallback, useEffect, useRef, useState } from 'react';
import NatalChart from '../../components/NatalChart';
import ChartSheet from '../components/ChartSheet';
import HintButton from '../components/HintButton';
import HintOverlay from '../components/HintOverlay';
import useTheme from '../useTheme.jsx';
import { fetchChart, resolvePrimaryChartId } from '../lib/chartApi';
import { birthDateWords, shortPlace } from '../lib/chartFormat';
import { CHART_HINTS } from '../lib/onboardingCopy';
import useHints from '../lib/useHints';
import useAuth from '../../hooks/useAuth.jsx';

function CenteredNotice({ title, text, action, onAction, secondary, onSecondary }) {
  return (
    <div
      style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 10,
        padding: '48px 24px',
        textAlign: 'center',
      }}
    >
      <p style={{ margin: 0, fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 600, color: 'var(--text-primary)' }}>
        {title}
      </p>
      {text && <p style={{ margin: 0, fontSize: 14, lineHeight: 1.6, color: 'var(--text-secondary)' }}>{text}</p>}
      {action && (
        <button type="button" className="mobile-link" onClick={onAction} style={{ marginTop: 4 }}>
          {action}
        </button>
      )}
      {secondary && (
        <button
          type="button"
          className="mobile-link"
          onClick={onSecondary}
          style={{ marginTop: 2, fontSize: 13, color: 'var(--text-secondary)' }}
        >
          {secondary}
        </button>
      )}
    </div>
  );
}

/** Скелет: круг на месте колеса и три полосы на месте списка (§8). */
function ChartLoading() {
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 20, padding: 24 }}>
      <div
        className="mobile-skeleton"
        style={{ width: '78%', aspectRatio: '1 / 1', borderRadius: '50%', background: 'var(--bg-deeper)', marginTop: 24 }}
      />
      <div style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: 10 }}>
        {[0, 1, 2].map((i) => (
          <div key={i} className="mobile-skeleton" style={{ height: 14, borderRadius: 7, background: 'var(--bg-deeper)' }} />
        ))}
      </div>
    </div>
  );
}

export default function ChartScreen({ active = true, onHintsToggle }) {
  // 'loading' | 'ready' | 'error' | 'no-chart'
  const [status, setStatus] = useState('loading');
  const [chart, setChart] = useState(null);
  const [error, setError] = useState('');
  const { logout } = useAuth();
  const { dark } = useTheme();

  // Якоря подсветки подсказок (SPEC_ONBOARDING.md §10).
  //
  // ⚠️ Шаги 1-3 («колесо», «дома», «аспекты») указывают на ОДИН И ТОТ ЖЕ
  // элемент — обёртку колеса, — хотя §10 спецификации описывает подсветку
  // кольца домов и слоя аспектов по отдельности. Так сделано намеренно:
  // внутри SVG (`components/NatalChart.jsx`) у этих слоёв нет ни общих
  // групп, ни классов, за которые можно зацепиться, — дома нарисованы
  // отдельным `<g>` на каждый, аспекты просто набором `<line>`. Подсветить
  // их точно можно было бы двумя способами, и оба хуже: править вебовский
  // NatalChart (он общий с сайтом, и правка ради подсказки мобильного
  // приложения задела бы веб) или продублировать здесь его внутренние
  // радиусы (второй источник истины для геометрии, который разъедется при
  // первой же правке колеса). Текст шага при этом говорит, куда смотреть.
  const wheelRef = useRef(null);
  const zoomHintRef = useRef(null);
  const hintAnchors = { wheel: wheelRef, zoomHint: zoomHintRef };

  const hints = useHints('chart', active && status === 'ready');

  // Кнопка чата прячется на время подсказок — этим ведает TabShell.
  useEffect(() => {
    onHintsToggle?.('chart', hints.open);
  }, [onHintsToggle, hints.open]);

  /**
   * `silent` — обновление жестом, без смены состояния на 'loading'.
   * Полное «почему» — в шапке lib/usePullToRefresh.js; здесь то, что
   * ломается именно на этой вкладке:
   *
   * ⚠️ Ветка `status === 'loading'` возвращает скелет ВМЕСТО экрана, то
   * есть размонтирует колесо. Зум и поворот — локальное состояние
   * NatalChart.jsx: после размонтирования они сбросятся, и обновление
   * данных выглядело бы как «сбросило мне карту».
   *
   * Ошибка при `silent` обязана улететь наверх: увести экран в 'error'
   * нельзя (за полноэкранным отказом спрячется уже показанная карта),
   * проглотить молча — тем более. Её показывает полоска жеста.
   */
  const load = useCallback(async ({ silent = false } = {}) => {
    if (!silent) {
      setStatus('loading');
      setError('');
    }
    try {
      const chartId = await resolvePrimaryChartId();
      if (!chartId) {
        setStatus('no-chart');
        return;
      }
      setChart(await fetchChart(chartId));
      setStatus('ready');
    } catch (err) {
      if (silent) throw err;
      // Текст уже человеческий: chartApi подменяет и «Chart not found»,
      // и сетевой сбой. Сюда попадает то, что можно показать как есть.
      setError(err?.message || 'Не удалось загрузить карту.');
      setStatus('error');
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Обработчик для жеста в шторке. `silent` обязателен — см. комментарий
  // у load выше: обычный путь размонтировал бы колесо и сбросил зум.
  const refresh = useCallback(() => load({ silent: true }), [load]);

  if (status === 'loading') return <ChartLoading />;

  if (status === 'error') {
    return (
      <CenteredNotice
        title="Не удалось загрузить карту"
        text={error}
        action="Повторить"
        onAction={load}
        secondary="Войти заново"
        onSecondary={logout}
      />
    );
  }

  if (status === 'no-chart') {
    return (
      <CenteredNotice
        title="Пока нет ни одной карты"
        text="Карта строится по дате, времени и месту рождения. Постройте её на сайте — здесь она появится сразу."
      />
    );
  }

  const timeLabel = chart.time_unknown ? 'время неизвестно' : chart.birth_time;

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
      <header style={{ padding: '12px 16px 4px', flexShrink: 0 }}>
        {/* name сегодня приходит null на обеих картах служебного аккаунта
            (CHART_API_RECON.md §2), но поле в ответе есть — если карту
            назвали, показываем имя, иначе запасной заголовок. */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <h1 style={{ margin: 0, flex: 1, minWidth: 0, fontFamily: 'var(--font-display)', fontSize: 20, fontWeight: 600, color: 'var(--text-primary)' }}>
            {chart.name || 'Натальная карта'}
          </h1>
          {/* Кнопка «?» есть только в готовом состоянии: на loading/error/
              no-chart объяснять нечего (SPEC_ONBOARDING.md §9). Здесь это
              выходит само — ветки выше возвращаются раньше. */}
          <HintButton onClick={hints.show} />
        </div>
        <p style={{ margin: '2px 0 0', fontSize: 13, color: 'var(--text-secondary)' }}>
          {birthDateWords(chart.birth_date)} · {timeLabel} · {shortPlace(chart.birth_place)}
        </p>
        {chart.time_unknown && (
          <p style={{ margin: '6px 0 0', fontSize: 12, lineHeight: 1.5, color: 'var(--color-warning)' }}>
            Время рождения неизвестно — дома и углы посчитаны на полдень и показаны условно.
          </p>
        )}
      </header>

      <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', padding: '0 8px' }}>
        {/* Колесо квадратное, и сторону квадрата задаёт ШИРИНА: внутри
            NatalChart.jsx стоит <svg width="100%" height="100%"> с квадратным
            viewBox, а все три его собственных div-предка имеют высоту по
            содержимому — значит height:"100%" разрешать не во что, и SVG
            откатывается на пропорцию viewBox, то есть на квадрат по ширине.

            Поэтому обёртка ниже связывает ВЫСОТУ, а ширину выводит из неё
            (height:'100%' + aspectRatio:'1'), а не наоборот. На телефоне
            ограничивающая сторона — именно высота: ширину колесу отдаёт весь
            экран, а по высоте у него остаётся то, что не забрали шапка,
            подсказка, шторка (ChartSheet, жёсткий minHeight:220) и таб-бар.

            Прежний вариант (width:'100%' + maxHeight:'100%') не работал, и
            это подтверждено замером на устройстве 08.09.2026: обёртка честно
            ужималась до 258px, а SVG внутри оставался 344px — квадратом по
            ширине — и вылезал за неё на 86px, ровно на низ круга (IC и знаки
            нижнего сектора), который перекрывала шторка. maxHeight клэмпит
            КОРОБКУ, а не колесо: до SVG это ограничение не доходит.

            ⚠️ Почему не пошли очевидным путём — не пробросили высоту вниз
            через height:'100%' на трёх div-предках внутри NatalChart.jsx (+
            minHeight:0 на среднем, он flex-элемент с min-height:auto).
            NatalChart.jsx общий с вебом, вызывается из девяти мест, и риск
            там не проверяется сборкой — только глазами по каждому месту. А
            правка здесь, в mobile/, доказуемо не задевает веб: content-hash
            в именах dist/assets обязаны совпасть до символа (так и вышло).

            maxWidth:'100%' — для обратного случая (высоты больше, чем
            ширины: длинные экраны, планшет): тогда связывает ширина, а
            колесо просто не дорастает до высоты. Верхний предел размера у
            колеса свой и от этой правки не зависит: у самого SVG стоит
            maxWidth = VSIZE = 600px (NatalChart.jsx), поэтому на планшете
            оно упирается в 600 и не разрастается на всю ширину.

            display:flex + justifyContent:'center' на самой обёртке — ровно
            для того случая: коробка выше колеса, и колесо в ней центрируется
            по вертикали, а не липнет к верхнему краю. По горизонтали его
            центрирует свой же margin:'0 auto' у SVG. Направление column
            обязательно: поперечная ось тогда горизонтальная, и ребёнок
            растягивается по ширине коробки — как при обычном блочном потоке
            до этой правки. С flexDirection:'row' ширина считалась бы по
            содержимому SVG, а это его собственные 600px.

            Подсказка про зум вынесена вторым сиблингом с гарантированным
            местом (flexShrink:0), не общим overflow с колесом. */}
        <div style={{ flex: 1, minHeight: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div
            ref={wheelRef}
            style={{
              height: '100%',
              maxWidth: '100%',
              aspectRatio: '1',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'center',
            }}
          >
            <NatalChart
              planets={chart.planets}
              houses={chart.houses}
              aspects={chart.aspects}
              ascendant={chart.ascendant}
              midheaven={chart.midheaven}
              timeUnknown={chart.time_unknown}
              dark={dark}
              // Оба выключателя — со стороны колеса, разбор причин в шапке
              // NatalChart.jsx: тултипы спорят со шторкой, анимация крутится в
              // фоне на невидимой вкладке и оставляет пустой круг, если rAF
              // придержан.
              onboarding={false}
              animated={false}
            />
          </div>
        </div>
        {/* Про тап по планете здесь не пишем: пока он ничего не открывает
            (§9 спецификации), обещать нечего. flexShrink:0 — эта строка
            больше не делит место с колесом через overflow, у неё всегда
            гарантированная высота. */}
        <p ref={zoomHintRef} style={{ margin: '6px 0 0', textAlign: 'center', fontSize: 11, color: 'var(--text-secondary)', flexShrink: 0 }}>
          Сведите пальцы для зума · двойной тап — сброс
        </p>
      </div>

      {/* Обновление жестом тянут за список шторки — единственное, что на
          этом экране прокручивается (разбор — в ChartSheet.jsx). */}
      <ChartSheet chart={chart} onRefresh={refresh} />

      {hints.open && (
        <HintOverlay steps={CHART_HINTS} anchors={hintAnchors} onClose={hints.close} />
      )}
    </div>
  );
}
