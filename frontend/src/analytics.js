// Яндекс.Метрика — только счётчик посещаемости.
//
// Стандартный сниппет из кабинета Метрики сюда не годится: это инлайновый
// <script>, а CSP отдаётся с script-src 'self' без 'unsafe-inline'
// (deploy/opt-astro/nginx/snippets/csp.conf). Инлайн просто не выполнится —
// ровно по той же причине из index.html когда-то вынесли регистрацию service
// worker. Поэтому тег грузится отсюда, из бандла.
//
// В CSP при этом всё равно нужны три источника mc.yandex.ru: script-src (сам
// tag.js), img-src (Метрика досылает статистику пикселем, если недоступен
// XHR) и connect-src (основной канал). Без любого из трёх счётчик молча
// недосчитывается.
//
// Что ОТКЛЮЧЕНО и почему (решение владельца 22.08.2026, зафиксировано в
// политике конфиденциальности, п. 11.3):
//   webvisor          — запись действий на странице
//   trackHash         — не нужен, у нас обычные маршруты
//   ecommerce         — магазина нет
//   childIframe       — своих iframe нет
// Ключевое — вебвизор и запись форм. На /chart и /intake в поля вводят дату,
// время и место рождения; по методичкам РКН это персональные данные, и
// отправлять их содержимое в чужой сервис нельзя. Включение вебвизора сделает
// п. 11.3 политики ложным — это не «настройка», а правка документа.

const COUNTER_ID = import.meta.env.VITE_YANDEX_METRIKA_ID;
const TAG_URL = 'https://mc.yandex.ru/metrika/tag.js';

export function initMetrika() {
  // Пусто — не грузим вообще. Локальная разработка и CI остаются чистыми
  // без каких-либо действий: переменная задаётся только в
  // /opt/astro/frontend.env на сервере.
  if (!COUNTER_ID) return;

  // Очередь вызовов на время загрузки tag.js — тот же механизм, что в
  // официальном сниппете: ym() можно звать сразу, вызовы применятся после.
  window.ym = window.ym || function (...args) {
    (window.ym.a = window.ym.a || []).push(args);
  };
  window.ym.l = Date.now();

  const script = document.createElement('script');
  script.src = TAG_URL;
  script.async = true;
  // Метрика не должна ронять страницу, если её заблокировал аплинк,
  // расширение браузера или CSP.
  script.onerror = () => {};
  document.head.appendChild(script);

  window.ym(COUNTER_ID, 'init', {
    webvisor: false,
    clickmap: false,        // карта кликов — часть записи поведения
    trackLinks: true,       // внешние переходы, содержимого не пишет
    accurateTrackBounce: true,
    trackHash: false,
    ecommerce: false,
    childIframe: false,
  });
}
