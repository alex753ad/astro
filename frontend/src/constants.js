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

// Недели планера «Луна по домам» с расшифровкой вперёд, СЧИТАЯ текущую.
// Зеркало `TIER_FLAGS[*]["planner_weeks_ahead"]` (backend/auth/rate_limits.py).
//
// ⚠️ Числом регулируется только БУДУЩЕЕ. Завершившиеся проходы открыты всем
// тарифам без ограничений (решение владельца 16.09.2026, правило целиком — в
// докстринге `is_moon_week_locked`), поэтому строка витрины у free обязана
// называть обе половины: текущую неделю И прошедшие периоды. Назвать одну —
// значит недодать того, что человек реально получает.
//
// ⚠️ `null` у платных — «всё окно ленты», то же значение и тот же смысл, что
// `None` в TIER_FLAGS. Замков на проходах Луны у них нет вовсе.
//
// ⚠️ Копия числа, как и у FREE_TRANSITS_TEASER_MONTHS выше: вывести его из
// ответа сервера нельзя, /profile/subscription этого флага не отдаёт.
// Синхронность держит `api/plannerWeeks.test.js` — он читает обе половины из
// исходников и падает при расхождении.
export const PLANNER_WEEKS_AHEAD = { free: 1, lite: null, pro: null, premium: null };

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
//
// С 24.09.2026 — расписание, зеркало common.PRICE_SCHEDULE: строка с будущей
// датой объявляет смену цены (оферта п. 10.1 — за 14 дней), и витрина
// переключается в ту же дату по Москве, что и чекаут, без деплоя в этот день.
// test_price_sync.py сверяет расписания целиком.
export const TIER_PRICE_SCHEDULE = [
  { from: '2026-08-19', prices: { free: 0, lite: 790, pro: 2490, premium: 7990 } },
];

/** Цены на дату «YYYY-MM-DD» по Москве (граница суток — как у бэкенда). */
export function tierPricesOn(day) {
  let current = TIER_PRICE_SCHEDULE[0].prices;
  for (const row of TIER_PRICE_SCHEDULE) if (row.from <= day) current = row.prices;
  return current;
}

function moscowToday() {
  return new Date(Date.now() + 3 * 3600 * 1000).toISOString().slice(0, 10);
}

// Цены на сегодня. Считаются при загрузке страницы — перезагрузка в день
// смены цены покажет новые.
export const TIER_PRICES = tierPricesOn(moscowToday());

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

// Тарифы по порядку: название, цена, «Рекомендуем». ЧТО тариф даёт — не
// здесь, а в lib/tierCatalog.js (решение владельца 28.09.2026): список пунктов
// здесь и второй в mobile/lib/appTiers.js разошлись словами и числами.
export const TIERS = [
  { id: 'free', label: TIER_NAMES.free, price: `${tierPriceLabel('free')}/мес` },
  { id: 'lite', label: TIER_NAMES.lite, price: `${tierPriceLabel('lite')}/мес` },
  { id: 'pro', label: TIER_NAMES.pro, price: `${tierPriceLabel('pro')}/мес`, recommended: true },
  { id: 'premium', label: TIER_NAMES.premium, price: `${tierPriceLabel('premium')}/мес` },
];
