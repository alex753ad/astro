/**
 * MoreTierCard.jsx — блок тарифа на экране «Ещё» (SPEC_MORE_SCREEN.md §4).
 *
 * Название следующего тарифа и его 4 пункта — статический `TIERS` из
 * `constants.js`, НЕ `horizon.next_tier` с сервера: то поле приходит из
 * ленты и требует chart_id, а у аккаунта без карт (реальное состояние,
 * §8) этот блок обязан работать и без него (§4.1).
 *
 * ⚠️ Текущие лимиты тарифа здесь НЕ показываются числом — ни разу. Число
 * из живых `features`/`limits` в этот блок не подставлять: только
 * статический текст `tierFeatures()` (SPEC_MORE_SCREEN.md §4.2).
 *
 * ⚠️ Пункт «Транзиты: горизонт N месяцев…» из списка «На … дополнительно»
 * ИСКЛЮЧЁН намеренно, не по ошибке. Копий горизонта транзитов стало две
 * вместо трёх — 08.09.2026 серверное исключение для free
 * (FREE_TRANSITS_TEASER_MONTHS в rate_limits.py) убрано, флаг поднят до 3,
 * и `features.transits_months` для free больше не врёт. Осталась пара
 * «флаг на бэкенде ↔ константа во фронте», её сверяет
 * `api/transitsHorizon.test.js`. Пункт всё равно не показываем: решение
 * владельца 06.09.2026 было про апселл этого экрана, а не про расхождение
 * чисел, и отдельно не пересматривалось.
 *
 * `highlight` — временная подсветка рамки: сюда переключает FAB чата
 * (AristeaFab.jsx) на free/Веге вместо своей кнопки апгрейда — одна
 * дверь к оплате на весь апп, а не две. Гасится сама через MoreScreen.jsx.
 */

import React from 'react';
import { TIERS, TIER_NAMES, tierFeatures } from '../../constants';
import { tierAccusative } from '../lib/ruDeclension';
import { openInBrowser } from '../lib/openInBrowser';
import { PRICING_URL } from '../lib/onboardingCopy';

function nextTierId(currentTier) {
  const idx = TIERS.findIndex((t) => t.id === currentTier);
  if (idx === -1) return null;
  return TIERS[idx + 1]?.id ?? null;
}

export default function MoreTierCard({ tier, highlight }) {
  const currentName = TIER_NAMES[tier] || tier;
  const nextId = nextTierId(tier);
  const nextName = nextId ? TIER_NAMES[nextId] : null;
  const features = nextId
    ? tierFeatures(nextId).filter((f) => !f.startsWith('Транзиты')).slice(0, 4)
    : [];

  return (
    <section
      style={{
        background: 'var(--bg-card)',
        border: `1px solid ${highlight ? 'var(--accent)' : 'var(--border)'}`,
        boxShadow: highlight ? '0 0 0 3px var(--accent-muted)' : 'none',
        borderRadius: 'var(--radius-lg)',
        padding: '14px 16px',
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
        transition: 'border-color 0.3s ease, box-shadow 0.3s ease',
      }}
    >
      <div>
        <p style={{ margin: 0, fontSize: 11.5, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>
          Ваш тариф
        </p>
        <p style={{ margin: '2px 0 0', fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 700, color: 'var(--text-primary)' }}>
          {currentName}
        </p>
      </div>

      {nextId && (
        <div>
          <p style={{ margin: '0 0 6px', fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
            На {tierAccusative(nextName)} дополнительно:
          </p>
          <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 4 }}>
            {features.map((f) => (
              <li key={f} style={{ display: 'flex', gap: 6, fontSize: 13, lineHeight: 1.4, color: 'var(--text-secondary)' }}>
                <span aria-hidden="true">·</span>
                <span>{f}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <button
        type="button"
        className="mobile-btn-primary"
        style={{ height: 44, fontSize: 14, marginTop: 4 }}
        onClick={() => openInBrowser(PRICING_URL)}
      >
        Тарифы
      </button>
    </section>
  );
}
