// Отображаемые названия тарифов. Внутренние идентификаторы ('free'/'lite'/'pro'/'premium')
// используются в API, Stripe, проверках доступа (minTier, TIER_ORDER) и не меняются —
// этот словарь только для текста, который видит пользователь.
export const TIER_NAMES = {
  free: 'Бесплатный',
  lite: 'Вега',
  pro: 'Лира',
  premium: 'Орион',
};

// Цены за месяц, ₽. Разовая оплата, без автопродления — годовых/квартальных
// периодов нет. Единственный источник цены: бэкенд (robokassa_service.TIER_PRICES,
// stripe_service.TIER_PRICE_MAP) должен совпадать с этими числами.
export const TIER_PRICES = {
  free: 0,
  lite: 790,
  pro: 2490,
  premium: 7990,
};

// "2 490 ₽" — без суффикса "/мес", каждый компонент обрамляет сам.
export function tierPriceLabel(tierId) {
  const n = TIER_PRICES[tierId];
  if (n === 0) return '0 ₽';
  return `${String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ' ')} ₽`;
}

// Состав тарифов — единый источник для страницы /pricing, вкладки «Подписка»
// в личном кабинете (ProfilePage) и модалок сравнения тарифов. Подача
// накопительная: каждый следующий тариф — «всё из предыдущего плюс…».
export const TIERS = [
  {
    id: 'free', label: TIER_NAMES.free, price: `${tierPriceLabel('free')}/мес`,
    features: [
      '4 карты в месяц',
      '1 бесплатная интерпретация карты навсегда, дальше — по шаблону',
      'AI-разбор 2 самых значимых транзитов месяца',
      'Лунный календарь текущего месяца',
      'Базовый PDF натальной карты',
      '1 карта (профиль)',
    ],
  },
  {
    id: 'lite', label: TIER_NAMES.lite, price: `${tierPriceLabel('lite')}/мес`,
    features: [
      'Планер: все планеты, индивидуальные рекомендации на месяц + луна на неделю',
      'Транзиты: все события + AI-разбор (3 в месяц)',
      'Лунный календарь',
      'Google Calendar (1 карта)',
      '1 карта (профиль)',
    ],
  },
  {
    id: 'pro', label: TIER_NAMES.pro, price: `${tierPriceLabel('pro')}/мес`, recommended: true,
    upsellFrom: `Всё из ${TIER_NAMES.lite}, плюс:`,
    features: [
      'Планер: + долгосрочные периоды',
      'Транзиты: AI-разбор без лимита',
      'Чат с Астреей',
      'PDF-экспорт',
      'До 5 карт (семья, партнёр, дети)',
    ],
  },
  {
    id: 'premium', label: TIER_NAMES.premium, price: `${tierPriceLabel('premium')}/мес`,
    upsellFrom: `Всё из ${TIER_NAMES.pro}, плюс:`,
    features: [
      'Транзиты: горизонт 24 месяца',
      'Рабочий кабинет астролога',
      'Безлимит карт',
    ],
  },
];

// Сокращённый список фич тарифа — для модалок, которым нужен только
// заголовок из общего массива, а не отдельный текст (первые n пунктов).
export function tierFeatures(tierId, n) {
  const tier = TIERS.find((t) => t.id === tierId);
  if (!tier) return [];
  return n ? tier.features.slice(0, n) : tier.features;
}
