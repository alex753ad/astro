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
import { TIER_NAMES } from '../../constants';
import { APP_TIER_FEATURES, APP_TIER_SITE } from '../lib/appTiers';
import { APP_SELLABLE, TIER_ORDER } from '../../lib/offerRule';
import { tierInRu } from '../lib/ruDeclension';
import { openPaySheet } from '../lib/paySheetBus';

/**
 * Следующий тариф, который можно купить ЗДЕСЬ. Орион в приложении не
 * продаётся (lib/offerRule.js, APP_SELLABLE) — до 27.09.2026 карточка на Лире
 * звала «На Орион дополнительно», а лист оплаты отвечал «у тебя уже старший из
 * доступных». Одно противоречило другому.
 */
function nextTierId(currentTier) {
  const idx = TIER_ORDER.indexOf(currentTier);
  if (idx === -1) return null;
  return TIER_ORDER.slice(idx + 1).find((t) => APP_SELLABLE.includes(t)) ?? null;
}

/** «до 24.10.2026» из ISO; пусто — срока нет (free) или прочитать нельзя. */
function untilLabel(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  // Выданное админкой «навсегда» (10 лет) датой не показываем — оно не срок.
  if (d.getFullYear() - new Date().getFullYear() > 5) return '';
  const pad = (n) => String(n).padStart(2, '0');
  return `до ${pad(d.getDate())}.${pad(d.getMonth() + 1)}.${d.getFullYear()}`;
}

export default function MoreTierCard({ tier, highlight, activeUntil, onPayments }) {
  const until = tier !== 'free' ? untilLabel(activeUntil) : '';
  const currentName = TIER_NAMES[tier] || tier;
  const nextId = nextTierId(tier);
  const nextName = nextId ? TIER_NAMES[nextId] : null;
  // Что даст следующий тариф В ПРИЛОЖЕНИИ (lib/appTiers.js), сайт — строкой.
  const features = nextId ? APP_TIER_FEATURES[nextId] || [] : [];
  const site = nextId ? APP_TIER_SITE[nextId] : null;

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
          Твой тариф
        </p>
        <p style={{ margin: '2px 0 0', fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 700, color: 'var(--text-primary)' }}>
          {currentName}
        </p>
        {until && (
          <p style={{ margin: '2px 0 0', fontSize: 13, color: 'var(--text-secondary)' }}>
            Оплачен {until}. Без автопродления — продлишь, когда захочешь.
          </p>
        )}
      </div>

      {nextId && (
        <div>
          <p style={{ margin: '0 0 6px', fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
            {/* Предложный падеж: «На Веге», «На Лире» (ruDeclension.js). */}
            На {tierInRu(nextName)} дополнительно:
          </p>
          <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 4 }}>
            {features.map((f) => (
              <li key={f} style={{ display: 'flex', gap: 6, fontSize: 13, lineHeight: 1.4, color: 'var(--text-secondary)' }}>
                <span aria-hidden="true">·</span>
                <span>{f}</span>
              </li>
            ))}
          </ul>
          {site && <p style={{ margin: '6px 0 0', fontSize: 12, lineHeight: 1.4, color: 'var(--text-secondary)' }}>{site}</p>}
        </div>
      )}

      <button
        type="button"
        className="mobile-btn-primary"
        style={{ height: 44, fontSize: 14, marginTop: 4 }}
        onClick={() => openPaySheet()}
      >
        {nextId ? 'Тарифы' : 'Продлить'}
      </button>
      {onPayments && (
        <button type="button" className="mobile-link" style={{ alignSelf: 'center' }} onClick={onPayments}>
          Оплата и поддержка
        </button>
      )}
    </section>
  );
}
