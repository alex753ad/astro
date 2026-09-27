/**
 * appTiers.js — что даёт тариф В ПРИЛОЖЕНИИ (решение владельца 27.09.2026).
 *
 * Витрина веба (`TIERS` в constants.js) перечисляла то, чего в приложении не
 * видно (лунный календарь на год, Google Calendar, PDF), — человек платил бы
 * за невидимое. Здесь — только то, что он увидит на своих экранах; что есть
 * лишь на сайте, отдельной строкой `site`.
 *
 * Числа — копия `TIER_FLAGS` (backend/auth/rate_limits.py): profiles_limit,
 * interpretations_per_month, transits_ai_per_month. Сверяет appTiers.test.js.
 */

export const APP_LIMITS = {
  free: { charts: 2, interpretations: 1, transits: 2 },   // 1 разбор навсегда, 2 самых значимых транзита
  lite: { charts: 5, interpretations: 5, transits: 3 },
  pro: { charts: 15, interpretations: 15, transits: null },
};

/** Полный список — что есть на тарифе (карточка текущего тарифа). */
export const APP_TIER_FEATURES = {
  free: [
    'Прогноз на день и на фазы Луны',
    'Луна по домам — прошедшие периоды и текущая неделя',
    'Текущий период Солнца с расшифровкой',
    `Разбор ${APP_LIMITS.free.transits} самых значимых транзитов`,
    `${APP_LIMITS.free.interpretations} разбор карты`,
    `${APP_LIMITS.free.charts} карты`,
  ],
  lite: [
    'Луна по домам и периоды Солнца–Марса на всё окно ленты',
    `Разбор транзитов — ${APP_LIMITS.lite.transits} в месяц`,
    `${APP_LIMITS.lite.interpretations} разборов карты в месяц, подробнее`,
    `До ${APP_LIMITS.lite.charts} карт`,
  ],
  pro: [
    'Долгосрочные периоды — Юпитер, Сатурн, Уран, Нептун, Плутон',
    'Разбор транзитов без лимита',
    'Чат с Аристеей',
    `${APP_LIMITS.pro.interpretations} разборов карты в месяц, самые подробные`,
    `До ${APP_LIMITS.pro.charts} карт`,
  ],
};

/** Только на сайте — отдельной строкой, чтобы не обещать это в приложении. */
export const APP_TIER_SITE = {
  free: 'На сайте: PDF-отчёт (1 в месяц), лунный календарь текущего месяца',
  lite: 'На сайте: PDF-отчёт, лунный календарь на год, Google Calendar',
  pro: 'На сайте: PDF-отчёт, лунный календарь на год, Google Calendar',
};
