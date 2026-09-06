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

import React, { useCallback, useEffect, useState } from 'react';
import NatalChart from '../../components/NatalChart';
import ChartSheet from '../components/ChartSheet';
import useTheme from '../useTheme.jsx';
import { fetchChart, resolvePrimaryChartId } from '../lib/chartApi';
import { birthDateWords, shortPlace } from '../lib/chartFormat';

function CenteredNotice({ title, text, action, onAction }) {
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

export default function ChartScreen() {
  // 'loading' | 'ready' | 'error' | 'no-chart'
  const [status, setStatus] = useState('loading');
  const [chart, setChart] = useState(null);
  const [error, setError] = useState('');
  const { dark } = useTheme();

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
    return <CenteredNotice title="Не удалось загрузить карту" text={error} action="Повторить" onAction={load} />;
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
        <h1 style={{ margin: 0, fontFamily: 'var(--font-display)', fontSize: 20, fontWeight: 600, color: 'var(--text-primary)' }}>
          {chart.name || 'Натальная карта'}
        </h1>
        <p style={{ margin: '2px 0 0', fontSize: 13, color: 'var(--text-secondary)' }}>
          {birthDateWords(chart.birth_date)} · {timeLabel} · {shortPlace(chart.birth_place)}
        </p>
        {chart.time_unknown && (
          <p style={{ margin: '6px 0 0', fontSize: 12, lineHeight: 1.5, color: 'var(--color-warning)' }}>
            Время рождения неизвестно — дома и углы посчитаны на полдень и показаны условно.
          </p>
        )}
      </header>

      <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', justifyContent: 'center', padding: '0 8px' }}>
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
        {/* Про тап по планете здесь не пишем: пока он ничего не открывает
            (§9 спецификации), обещать нечего. */}
        <p style={{ margin: '6px 0 0', textAlign: 'center', fontSize: 11, color: 'var(--text-secondary)' }}>
          Сведите пальцы для зума · двойной тап — сброс
        </p>
      </div>

      <ChartSheet chart={chart} />
    </div>
  );
}
