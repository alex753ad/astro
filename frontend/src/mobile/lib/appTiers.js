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
  // free: 1 разбор карты, 2 разбора транзитов и 3 сообщения чата — на пробу,
  // за всё время аккаунта (решение владельца 28.09.2026).
  free: { charts: 2, interpretations: 1, transits: 2, chat: 3 },
  lite: { charts: 5, interpretations: 5, transits: 3, chat: 30 },
  pro: { charts: 15, interpretations: 15, transits: null, chat: null },
};

/** Полный список — что есть на тарифе (карточка текущего тарифа). */
export const APP_TIER_FEATURES = {
  free: [
    'Прогноз на день и на фазы Луны',
    'Луна по домам — прошедшие периоды и текущая неделя',
    'Текущий период Солнца с расшифровкой',
    `${APP_LIMITS.free.transits} разбора транзитов на пробу`,
    `${APP_LIMITS.free.chat} сообщения в чате с Аристеей на пробу`,
    `${APP_LIMITS.free.interpretations} разбор карты`,
    `${APP_LIMITS.free.charts} карты`,
  ],
  lite: [
    'Луна по домам и периоды Солнца–Марса на всё окно ленты',
    `Разбор транзитов — ${APP_LIMITS.lite.transits} в месяц`,
    `Чат с Аристеей — ${APP_LIMITS.lite.chat} сообщений в месяц`,
    `${APP_LIMITS.lite.interpretations} разборов карты в месяц, подробнее`,
    `До ${APP_LIMITS.lite.charts} карт`,
  ],
  pro: [
    'Долгосрочные периоды — Юпитер, Сатурн, Уран, Нептун, Плутон',
    'Разбор транзитов без лимита',
    'Чат с Аристеей без лимита',
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
