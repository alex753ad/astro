/**
 * MoreCardsList.jsx — «Мои карты» на экране «Ещё» (SPEC_MORE_SCREEN.md §5,
 * действия — SPEC_CHART_CREATE.md §3 плана от 08.09.2026).
 *
 * ⚠️ Здесь до 08.09.2026 стояло «имени карты не существует ни у кого». Это
 * больше не так: `POST /chart/calculate` пишет `name` с 07.09.2026
 * (`main.py:690`), а форма построения в приложении его спрашивает. Поэтому
 * строка показывает имя, если оно есть, и дату с местом — если нет. У карт,
 * созданных до тех правок, имени по-прежнему не будет, и это не дефект.
 *
 * Список перестал быть только читающим: отсюда можно удалить карту и
 * сделать её основной. Оба действия меняют состав карт для ДРУГИХ вкладок —
 * подтверждение, запросы и толчок соседям живут в `MoreScreen.jsx`, здесь
 * только вёрстка и вызовы наверх.
 */

import React from 'react';
import { birthDateWords, shortPlace } from '../lib/chartFormat';

function RowAction({ children, onClick, disabled, danger }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      style={{
        background: 'transparent',
        border: 'none',
        padding: '6px 0',
        fontSize: 12.5,
        fontWeight: 600,
        color: danger ? 'var(--color-danger)' : 'var(--accent)',
        opacity: disabled ? 0.45 : 1,
      }}
    >
      {children}
    </button>
  );
}

function CardRow({ chart, busy, onSetPrimary, onDelete }) {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
        padding: '13px 15px',
        background: 'var(--bg-card)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-lg)',
        opacity: busy ? 0.5 : 1,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
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
          {chart.name || `${birthDateWords(chart.birth_date)} · ${shortPlace(chart.birth_place)}`}
        </span>
        {chart.is_primary && (
          <span style={{ marginLeft: 'auto', color: 'var(--color-warning)', fontSize: 15, flexShrink: 0 }} aria-label="Основная карта">
            ★
          </span>
        )}
      </div>

      {/* Вторая строка под именем: дата и место, если имя занято первой
          строкой, — иначе они пропали бы совсем и карты стало бы не
          различить между собой. */}
      {chart.name && (
        <p style={{ margin: 0, paddingLeft: 46, fontSize: 11.5, color: 'var(--text-secondary)' }}>
          {birthDateWords(chart.birth_date)} · {shortPlace(chart.birth_place)}
        </p>
      )}

      <div style={{ display: 'flex', gap: 16, paddingLeft: 46 }}>
        {/* У основной карты действия «сделать основной» нет — вместо него
            звезда выше. Кнопка, которая ничего не меняет, хуже её отсутствия. */}
        {!chart.is_primary && (
          <RowAction onClick={() => onSetPrimary(chart)} disabled={busy}>
            Сделать основной
          </RowAction>
        )}
        <RowAction onClick={() => onDelete(chart)} disabled={busy} danger>
          Удалить
        </RowAction>
      </div>
    </div>
  );
}

export default function MoreCardsList({ charts, busyId, onSetPrimary, onDelete }) {
  return (
    <section style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <p style={{ margin: '0 0 2px', fontFamily: 'var(--font-body)', fontSize: 12.5, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>
        Мои карты
      </p>
      {charts.length === 0 ? (
        // Ведём на вкладку «Карта», а не на сайт: с 08.09.2026 форма есть в
        // самом приложении (SPEC_CHART_CREATE.md). Ссылки-кнопки здесь нет —
        // этот список не умеет переключать вкладки, а заводить ради подписи
        // проброс навигации через весь экран дороже, чем сказать словами.
        <p style={{ margin: 0, fontSize: 13, color: 'var(--text-secondary)' }}>
          Пока нет ни одной карты. Построй её на вкладке «Карта» — она появится здесь сразу.
        </p>
      ) : (
        charts.map((c) => (
          <CardRow
            key={c.id}
            chart={c}
            busy={busyId === c.id}
            onSetPrimary={onSetPrimary}
            onDelete={onDelete}
          />
        ))
      )}
    </section>
  );
}
