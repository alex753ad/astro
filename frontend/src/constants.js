// Отображаемые названия тарифов. Внутренние идентификаторы ('free'/'lite'/'pro'/'premium')
// используются в API, Stripe, проверках доступа (minTier, TIER_ORDER) и не меняются —
// этот словарь только для текста, который видит пользователь.
export const TIER_NAMES = {
  free: 'Бесплатный',
  lite: 'Вега',
  pro: 'Лира',
  premium: 'Орион',
};

// Родительный падеж названий тарифов — для фраз вида «Всё из X, плюс:».
// Отдельное поле, не шаблонится из TIER_NAMES (склонение непредсказуемо).
export const TIER_NAMES_GENITIVE = {
  free: 'Бесплатного',
  lite: 'Веги',
  pro: 'Лиры',
  premium: 'Ориона',
};

// Цены за месяц, ₽. Разовая оплата, без автопродления — годовых/квартальных
// периодов нет.
//
// Обязаны совпадать с TIER_PRICES_RUB в backend/payments/common.py — по нему
// checkout считает сумму платежа и по нему же вебхук сверяет реально
// списанное. Расхождение = витрина обещает одну цену, а списывается другая.
// Совпадение проверяется тестом backend/tests/test_price_sync.py.
//
// Прежний комментарий тут ссылался на robokassa_service.TIER_PRICES и
// stripe_service.TIER_PRICE_MAP — оба модуля удалены 19.08.2026 вместе с
// провайдерами. Ссылка на несуществующий источник истины хуже её отсутствия:
// по ней идут проверять и не находят ничего.
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
      '2 сохранённые карты',
      '1 бесплатная интерпретация карты навсегда',
      'Лунный календарь текущего месяца',
    ],
  },
  {
    id: 'lite', label: TIER_NAMES.lite, price: `${tierPriceLabel('lite')}/мес`,
    upsellFrom: `Всё из ${TIER_NAMES_GENITIVE.free}, плюс:`,
    features: [
      'До 5 сохранённых карт одновременно',
      '5 AI-интерпретаций в месяц',
      'Планер: рекомендации на месяц',
      'Транзиты: горизонт 1 месяц + AI-разбор аспектов (3 в месяц)',
      'Лунный календарь на год',
      'Google Calendar (1 карта)',
      'PDF-экспорт (5 карт)',
    ],
  },
  {
    id: 'pro', label: TIER_NAMES.pro, price: `${tierPriceLabel('pro')}/мес`, recommended: true,
    upsellFrom: `Всё из ${TIER_NAMES_GENITIVE.lite}, плюс:`,
    features: [
      'До 15 сохранённых карт одновременно',
      '15 AI-интерпретаций в месяц',
      'Планер: + долгосрочные периоды',
      'Транзиты: горизонт 3 месяца + AI-разбор без лимита',
      'Чат с Астреей',
      'PDF-экспорт (15 карт)',
    ],
  },
  {
    id: 'premium', label: TIER_NAMES.premium, price: `${tierPriceLabel('premium')}/мес`,
    upsellFrom: `Всё из ${TIER_NAMES_GENITIVE.pro}, плюс:`,
    features: [
      'Безлимит карт',
      'Безлимит AI-интерпретаций',
      'Транзиты: горизонт 24 месяца',
      'PDF-экспорт без лимита',
      'Рабочий кабинет астролога',
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
