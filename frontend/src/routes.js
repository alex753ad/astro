/**
 * routes.js — ЕДИНСТВЕННЫЙ список маршрутов приложения.
 *
 * До 14.09.2026 список существовал в двух местах и уже разошёлся: в App.jsx
 * было 25 маршрутов, в generate-sitemap.js — свой перечень из шести путей,
 * без /zodiac/* вовсе. Расхождение ничем не ловилось и стоило индексации:
 * двенадцать зодиакальных страниц не попадали в карту сайта, а ссылок на них
 * нет ни с одной страницы (в LandingPage.jsx нет ни одного href/to), то есть
 * найти их Google было физически неоткуда.
 *
 * Отсюда список читают ЧЕТЫРЕ потребителя, и ни один не держит свою копию:
 *
 *   App.jsx (useOGMeta)            — метаданные через seoForPath()
 *   generate-sitemap.js            — sitemap.xml, только kind === 'public'
 *   scripts/prerender.mjs          — что пререндерить, только kind === 'public'
 *   scripts/generate-nginx-routes.mjs — map для nginx, ВСЕ записи
 *
 * ⚠️ Один кусок App.jsx этот файл всё ещё НЕ читает — сам список <Route>.
 * Правка роутера на 14.09.2026 не согласована с владельцем, и до неё пути
 * объявлены в двух местах. Совпадение держит тест `routes.test.js`: он парсит
 * <Route path= из App.jsx и требует ровного совпадения множеств. Тест —
 * временная мера вместо настоящего единственного источника, снимать его надо
 * вместе с переводом <Route> на этот файл, а не раньше.
 *
 * ⚠️ Цена расхождения здесь выше, чем кажется: маршрут, добавленный в App.jsx
 * и забытый тут, получит от nginx не «страницу без индексации», а жёсткий 404
 * — его нет в сгенерированном map. Обратное направление (есть тут, нет в
 * App.jsx) ловит пререндер: страница отрисуется экраном «не найдено», и он
 * уронит сборку по сверке с эталоном.
 *
 * ─── Поле kind ───────────────────────────────────────────────────────────────
 *
 *   'public' — страница для всех: пререндерится, попадает в sitemap,
 *              отдаётся статическим файлом со статусом 200.
 *   'app'    — страница приложения: не пререндерится, в sitemap не попадает,
 *              отдаётся шеллом index.html со статусом 200.
 *
 * Всё, чего в этом файле нет, nginx отдаёт честным 404. Поэтому добавление
 * маршрута в App.jsx без добавления сюда даёт не «страницу без индексации», а
 * жёсткий 404 на живой странице — ради этого и стоит тест выше.
 *
 * ─── Поле seo ────────────────────────────────────────────────────────────────
 *
 * title/description для публичных страниц. Их подставляет в готовый HTML
 * scripts/prerender.mjs — вместе с canonical и og:*. До правки 14.09.2026
 * /pricing, /orion, /terms, /privacy и /requisites не имели своих метаданных
 * вовсе и отдавали общий заголовок из index.html, то есть в выдаче были бы
 * неотличимы друг от друга.
 *
 * ⚠️ **Это единственное место, и с 14.09.2026 так и есть — до правки было
 * не так.** useOGMeta в App.jsx держала свои литералы на три группы маршрутов
 * и ПЕРЕЗАПИСЫВАЛА ими пререндеренные значения, как только выполнялся JS.
 * Измерено сравнением документа без JS и после: на «/» и «/zodiac/*»
 * расходились title и og:*, на /pricing и /terms не расходилось ничего —
 * веток для них там просто не было. Содержимое страниц при этом совпадало
 * везде, расходились только метаданные, поэтому обычной проверкой глазами это
 * не ловилось вовсе.
 *
 * Теперь useOGMeta зовёт seoForPath() отсюда же. Замер после правки: на всех
 * 18 страницах title, description, og:* и canonical переживают выполнение JS
 * без изменений. Закреплено тестом, который запрещает литералы метаданных в
 * App.jsx (routes.test.js) — обратный прогон подтверждает, что он падает при
 * их возврате.
 */

export const CANONICAL_ORIGIN = 'https://aristeatime.ru';

/**
 * Знаки зодиака — ключи URL. Порядок соответствует ZodiacPage.jsx (SIGNS).
 *
 * ⚠️ Перечислены поимённо, а не как параметр «любая строка», и это важно для
 * nginx: при [^/]+ адрес /zodiac/абракадабра вернул бы 200 со страницей
 * «Знак не найден» — тот же софт-404, ради устранения которого всё затевалось.
 */
export const ZODIAC_SLUGS = [
  'aries', 'taurus', 'gemini', 'cancer', 'leo', 'virgo',
  'libra', 'scorpio', 'sagittarius', 'capricorn', 'aquarius', 'pisces',
];

const ZODIAC_RU = {
  aries: 'Овен', taurus: 'Телец', gemini: 'Близнецы', cancer: 'Рак',
  leo: 'Лев', virgo: 'Дева', libra: 'Весы', scorpio: 'Скорпион',
  sagittarius: 'Стрелец', capricorn: 'Козерог', aquarius: 'Водолей', pisces: 'Рыбы',
};

export const ROUTES = [
  // ── Публичные ──────────────────────────────────────────────────────────────
  {
    id: 'landing',
    path: '/',
    kind: 'public',
    seo: {
      title: 'Aristea Timeline — натальные карты и разбор транзитов',
      description:
        'Постройте натальную карту по дате и месту рождения, получите интерпретацию ' +
        'транзитов и персональный астрологический планер.',
    },
  },
  {
    id: 'zodiac',
    path: '/zodiac/:sign',
    kind: 'public',
    params: { sign: ZODIAC_SLUGS },
    seo: ({ sign }) => ({
      title: `${ZODIAC_RU[sign]} — характеристика знака зодиака | Aristea Timeline`,
      description:
        `Знак зодиака ${ZODIAC_RU[sign]}: характер, совместимость, стихия и планета-управитель. ` +
        'Ответы на частые вопросы и построение натальной карты.',
    }),
  },
  {
    id: 'pricing',
    path: '/pricing',
    kind: 'public',
    seo: {
      title: 'Тарифы — Aristea Timeline',
      description:
        'Бесплатный доступ, Вега, Лира и Орион: натальные карты, транзиты, лунный ' +
        'календарь и интерпретации. Сравнение возможностей и цены.',
    },
  },
  {
    id: 'orion',
    path: '/orion',
    kind: 'public',
    seo: {
      title: 'Орион — тариф для астрологов | Aristea Timeline',
      description:
        'Безлимитные карты и интерпретации, кабинет астролога с клиентской базой, ' +
        'клиентские порталы и PDF-отчёты.',
    },
  },
  {
    id: 'terms',
    path: '/terms',
    kind: 'public',
    seo: {
      title: 'Публичная оферта — Aristea Timeline',
      description:
        'Условия оказания услуг сервиса Aristea Timeline: предмет договора, тарифы, ' +
        'порядок оплаты и возврата, права и обязанности сторон.',
    },
  },
  {
    id: 'privacy',
    path: '/privacy',
    kind: 'public',
    seo: {
      title: 'Политика конфиденциальности — Aristea Timeline',
      description:
        'Какие персональные данные обрабатывает Aristea Timeline, зачем, сколько они ' +
        'хранятся и как их удалить.',
    },
  },
  {
    id: 'requisites',
    path: '/requisites',
    kind: 'public',
    seo: {
      title: 'Реквизиты — Aristea Timeline',
      description:
        'Реквизиты исполнителя услуг Aristea Timeline, контакты для связи и порядок '  +
        'обращения по вопросам оплаты и возврата.',
    },
  },

  // ── Приложение ─────────────────────────────────────────────────────────────
  // Шелл с кодом 200, без пререндера и без sitemap.
  //
  // ⚠️ /lunar и /home сюда попали по решению владельца 14.09.2026, хотя обе
  // технически публичны: /home стоит за входом, /lunar тянет данные из
  // /calendar/lunar при открытии — пререндер запёк бы состояние загрузки, то
  // есть заморозил бы в индексе страницу без единого числа.
  { id: 'home',          path: '/home',                   kind: 'app' },
  {
    // ⚠️ `seo` у маршрута `app` — не противоречие. Поле `kind` решает, что
    // пререндерить и что класть в sitemap; `seo` — что показать в <head> при
    // переходе внутри приложения. Лунный календарь публичен и им делятся
    // ссылкой, поэтому заголовок ему нужен, а пререндер — нет: страница тянет
    // данные из /calendar/lunar при открытии, и снимок заморозил бы состояние
    // загрузки.
    //
    // Тексты перенесены сюда из useOGMeta (App.jsx) без изменений — там они
    // были до 14.09.2026.
    id: 'lunar',
    path: '/lunar',
    kind: 'app',
    seo: {
      title: 'Лунный календарь 2026 | Aristea Timeline',
      description: 'Фазы Луны, знак Луны на каждый день, благоприятные дни. Персональный лунный календарь.',
    },
  },
  { id: 'profile',       path: '/profile',                kind: 'app' },
  { id: 'admin',         path: '/admin',                  kind: 'app' },
  { id: 'crm',           path: '/dashboard/clients',      kind: 'app' },
  { id: 'reset',         path: '/reset-password',         kind: 'app' },
  { id: 'pilotClaim',    path: '/pilot/claim',            kind: 'app' },
  { id: 'exitSurvey',    path: '/exit-survey',            kind: 'app' },
  { id: 'chartShare',    path: '/chart/share/:token',     kind: 'app' },
  { id: 'chart',         path: '/chart/:chartId',         kind: 'app' },
  { id: 'planner',       path: '/planner/:id',            kind: 'app' },
  { id: 'solarReturn',   path: '/solar-return/:chartId',  kind: 'app' },
  { id: 'synastry',      path: '/synastry/:chartId',      kind: 'app' },
  { id: 'relocation',    path: '/relocation/:chartId',    kind: 'app' },
  { id: 'intake',        path: '/intake/:token',          kind: 'app' },
  { id: 'portal',        path: '/portal/:token',          kind: 'app' },
];

/**
 * Разворачивает маршрут с параметрами в конкретные адреса.
 *
 * Маршрут без `params` даёт сам себя; маршрут с `params` — декартово
 * произведение перечисленных значений. Сегодня параметр ровно один (:sign),
 * но произведение написано сразу: второй такой маршрут не должен требовать
 * правки всех трёх потребителей.
 */
export function expandRoute(route) {
  if (!route.params) return [{ path: route.path, values: {} }];

  const names = Object.keys(route.params);
  let combos = [{}];
  for (const name of names) {
    combos = combos.flatMap(base =>
      route.params[name].map(value => ({ ...base, [name]: value })),
    );
  }

  return combos.map(values => ({
    path: names.reduce((p, name) => p.replace(`:${name}`, values[name]), route.path),
    values,
  }));
}

/**
 * Метаданные для конкретного адреса — или null, если у маршрута их нет.
 *
 * Зовётся из useOGMeta (App.jsx) на каждую смену маршрута. До 14.09.2026 там
 * лежали собственные литералы на три группы маршрутов, и они перезаписывали
 * значения, проставленные пререндером: замер сравнением документа без JS и
 * после показал расхождение title и og:* на «/» и «/zodiac/*». Теперь источник
 * один, и расходиться нечему.
 *
 * ⚠️ Возвращает null для маршрутов `kind: 'app'` — это НЕ недосмотр. У страниц
 * приложения (профиль, карта, CRM) метаданных нет намеренно: они закрыты в
 * robots.txt, а подставлять им заголовок значило бы описывать в разметке
 * страницу, которую поисковик всё равно не увидит. useOGMeta на null не
 * трогает <head> вовсе, оставляя то, что там уже стоит.
 */
export function seoForPath(pathname) {
  const clean = pathname.replace(/\/+$/, '') || '/';

  for (const route of ROUTES) {
    if (!route.seo) continue;
    for (const { path, values } of expandRoute(route)) {
      if (path !== clean) continue;
      const seo = typeof route.seo === 'function' ? route.seo(values) : route.seo;
      return { ...seo, canonical: `${CANONICAL_ORIGIN}${path}` };
    }
  }
  return null;
}

/** Все публичные адреса, уже развёрнутые: то, что пререндерится и идёт в sitemap. */
export function publicUrls() {
  return ROUTES
    .filter(r => r.kind === 'public')
    .flatMap(route =>
      expandRoute(route).map(({ path, values }) => ({
        id: route.id,
        path,
        seo: typeof route.seo === 'function' ? route.seo(values) : route.seo,
      })),
    );
}
