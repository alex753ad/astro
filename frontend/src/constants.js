// Отображаемые названия тарифов. Внутренние идентификаторы ('free'/'lite'/'pro'/'premium')
// используются в API, Stripe, проверках доступа (minTier, TIER_ORDER) и не меняются —
// этот словарь только для текста, который видит пользователь.
export const TIER_NAMES = {
  free: 'Бесплатный',
  lite: 'Вега',
  pro: 'Лира',
  premium: 'Орион',
};

// Горизонт транзитов, который видит бесплатный пользователь.
//
// Это ВИТРИНА, а не тарифный лимит: TIER_FLAGS["free"]["transits_months"] == 0,
// и ноль там означает «AI-разбор транзитов не входит в тариф», а не «список
// транзитов не показывать». Бэкенд отдаёт free эти месяцы через отдельную
// константу FREE_TRANSITS_TEASER_MONTHS (backend/auth/rate_limits.py) —
// решение: список виден всем, монетизируется AI-разбор аспектов, а не сам
// факт просмотра.
//
// ⚠️ Число продублировано с бэкендом: вывести его из флагов нельзя, во флагах
// ноль. Синхронность держит `api/transitsHorizon.test.js` — он читает обе
// половины из исходников и падает при расхождении; менять надо В ДВУХ местах,
// но молча разъехаться они не смогут. Совсем убрать копию можно, только начав
// отдавать витринную константу в /profile/subscription рядом с limits.
export const FREE_TRANSITS_TEASER_MONTHS = 3;

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

// Сколько PDF в месяц даёт тариф. null = безлимит.
//
// Обязаны совпадать с pdf_per_month в TIER_FLAGS
// (backend/auth/rate_limits.py) — по нему check_pdf_limit реально отбивает
// скачивание. Совпадение проверяется тестом
// backend/tests/test_pdf_limit_sync.py, устроенным как test_price_sync.py.
//
// Раньше эти числа были набраны прозой прямо в features ('PDF-экспорт
// (5 карт)') и с сеткой не связаны ничем. Это та же конструкция, что уже
// дважды разошлась в этом проекте — charts_per_month и сам pdf_per_month,
// см. CLAUDE.md.
export const TIER_PDF_PER_MONTH = {
  free: 1,
  lite: 5,
  pro: 15,
  premium: null,
};

// «карта / карты / карт» — склонение по числу, как в русском счёте.
function chartsWord(n) {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return 'карта';
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return 'карты';
  return 'карт';
}

// "PDF-экспорт (5 карт)" — пункт витрины, выведенный из сетки, а не набранный.
export function pdfFeatureLabel(tierId) {
  const n = TIER_PDF_PER_MONTH[tierId];
  if (n === null || n === undefined) return 'PDF-экспорт без лимита';
  return `PDF-экспорт (${n} ${chartsWord(n)})`;
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
      `Транзиты: горизонт ${FREE_TRANSITS_TEASER_MONTHS} месяца, без AI-разбора`,
      'Лунный календарь текущего месяца',
      pdfFeatureLabel('free'),
    ],
  },
  {
    id: 'lite', label: TIER_NAMES.lite, price: `${tierPriceLabel('lite')}/мес`,
    upsellFrom: `Всё из ${TIER_NAMES_GENITIVE.free}, плюс:`,
    features: [
      'До 5 сохранённых карт одновременно',
      '5 AI-интерпретаций в месяц',
      'Планер: рекомендации на месяц',
      'Транзиты: горизонт 6 месяцев + AI-разбор аспектов (3 в месяц)',
      'Лунный календарь на год',
      'Google Calendar',
      pdfFeatureLabel('lite'),
    ],
  },
  {
    id: 'pro', label: TIER_NAMES.pro, price: `${tierPriceLabel('pro')}/мес`, recommended: true,
    upsellFrom: `Всё из ${TIER_NAMES_GENITIVE.lite}, плюс:`,
    features: [
      'До 15 сохранённых карт одновременно',
      '15 AI-интерпретаций в месяц',
      'Планер: + долгосрочные периоды',
      'Транзиты: горизонт 12 месяцев + AI-разбор без лимита',
      'Чат с Аристеей',
      pdfFeatureLabel('pro'),
    ],
  },
  {
    id: 'premium', label: TIER_NAMES.premium, price: `${tierPriceLabel('premium')}/мес`,
    upsellFrom: `Всё из ${TIER_NAMES_GENITIVE.pro}, плюс:`,
    features: [
      'Безлимит карт',
      'Безлимит AI-интерпретаций',
      'Транзиты: горизонт 24 месяца',
      pdfFeatureLabel('premium'),
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
