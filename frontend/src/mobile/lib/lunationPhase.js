/**
 * lunationPhase.js — к какой фазе Луны относится событие ленты.
 *
 * Отдельно от forecastApi.js, потому что это правило читает карточка события
 * (isOpenable в FeedEventCard.jsx), и ей незачем тянуть за собой сетевой код.
 *
 * ⚠️ Затмение — тоже фаза, и это не натяжка: лента ЗАМЕНЯЕТ фазу затмением
 * того же рода (backend/feed/builder.py — солнечное бывает только в
 * новолуние, лунное — только в полнолуние). Без этой ветки новолуние с
 * затмением осталось бы единственной фазой месяца без прогноза.
 */

export function lunationPhase(event) {
  if (event?.kind === 'moon_phase') {
    const t = event?.meta?.type;
    return t === 'new_moon' || t === 'full_moon' ? t : null;
  }
  if (event?.kind === 'eclipse') {
    return { solar: 'new_moon', lunar: 'full_moon' }[event?.meta?.type] || null;
  }
  return null;
}

/** Есть ли у события ленты прогноз на фазу. */
export function hasLunationForecast(event) {
  return lunationPhase(event) !== null;
}
