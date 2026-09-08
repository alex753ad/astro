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

  const load = useCallback(async () => {
    setStatus('loading');
    setError('');
    try {
      const chartId = await resolvePrimaryChartId();
      if (!chartId) {
        setStatus('no-chart');
        return;
      }
      setChart(await fetchChart(chartId));
      setStatus('ready');
    } catch (err) {
      // Текст уже человеческий: chartApi подменяет и «Chart not found»,
      // и сетевой сбой. Сюда попадает то, что можно показать как есть.
      setError(err?.message || 'Не удалось загрузить карту.');
      setStatus('error');
    }
  }, []);

  useEffect(() => { load(); }, [load]);

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
        {/* Колесо квадратное и своей шириной не оглядывается на доступную
            высоту — SVG внутри NatalChart.jsx растёт по ширине экрана, а
            высоту берёт из viewBox (квадрат). Раньше это раскладывалось
            через justifyContent:'center' на весь блок сразу с подсказкой:
            при недостатке высоты (короткая шапка+шторка съедают больше, чем
            в среднем) колесо+подсказка суммарно оказывались выше отведённого
            места, лишнее уходило за нижний край без скролла — и подсказку,
            как самый маленький и последний элемент, перекрывала шторка,
            которая рисуется по DOM-порядку позже поверх переполнения соседа.
            Обёртка ниже — отдельный flex-блок, кадр с aspectRatio:'1' и
            maxHeight:'100%' — клэмпит сторону квадрата по МЕНЬШЕЙ из
            доступных величин (ширина/высота), а подсказка вынесена вторым
            сиблингом с гарантированным местом, не общим overflow с колесом.
            NatalChart.jsx не трогаем — эффект достигается снаружи. */}
        <div style={{ flex: 1, minHeight: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div ref={wheelRef} style={{ width: '100%', maxHeight: '100%', aspectRatio: '1' }}>
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

      <ChartSheet chart={chart} />

      {hints.open && (
        <HintOverlay steps={CHART_HINTS} anchors={hintAnchors} onClose={hints.close} />
      )}
    </div>
  );
}
