/**
 * MoreCardsList.jsx — «Мои карты» на экране «Ещё» (SPEC_MORE_SCREEN.md §5).
 *
 * ⚠️ Имени карты не существует ни у кого — не пропуск в конкретном ответе:
 * `NatalChart.name`/`.label` не пишет ни одно место в бэкенде
 * (MORE_API_RECON.md §3). Строка карты собирается из даты рождения и
 * места — заменить имя нечем, это не дефект отображения.
 */

import React from 'react';
import { birthDateWords, shortPlace } from '../lib/chartFormat';

function CardRow({ chart }) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        padding: '13px 15px',
        background: 'var(--bg-card)',
        border: '1px solid var(--border)',
        borderRadius: 14,
      }}
    >
      <span
        style={{
          width: 34,
          height: 34,
          borderRadius: '50%',
          border: '1.5px solid var(--accent-muted)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: 16,
          color: 'var(--accent)',
          flexShrink: 0,
        }}
        aria-hidden="true"
      >
        ☉
      </span>
      <span style={{ minWidth: 0, fontFamily: 'var(--font-body)', fontSize: 13.5, color: 'var(--text-primary)' }}>
        {birthDateWords(chart.birth_date)} · {shortPlace(chart.birth_place)}
      </span>
      {chart.is_primary && (
        <span style={{ marginLeft: 'auto', color: 'var(--color-warning)', fontSize: 15, flexShrink: 0 }} aria-label="Основная карта">
          ★
        </span>
      )}
    </div>
  );
}

export default function MoreCardsList({ charts }) {
  return (
    <section style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <p style={{ margin: '0 0 2px', fontFamily: 'var(--font-display)', fontSize: 12.5, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>
        Мои карты
      </p>
      {charts.length === 0 ? (
        // Ведём на вкладку «Карта», а не на сайт: с 08.09.2026 форма есть в
        // самом приложении (SPEC_CHART_CREATE.md). Ссылки-кнопки здесь нет —
        // этот список не умеет переключать вкладки, а заводить ради подписи
        // проброс навигации через весь экран дороже, чем сказать словами.
        <p style={{ margin: 0, fontSize: 13, color: 'var(--text-secondary)' }}>
          Пока нет ни одной карты. Постройте её на вкладке «Карта» — она появится здесь сразу.
        </p>
      ) : (
        charts.map((c) => <CardRow key={c.id} chart={c} />)
      )}
    </section>
  );
}
