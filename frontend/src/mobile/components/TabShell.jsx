/**
 * TabShell.jsx — контейнер трёх вкладок.
 *
 * «Состояние вкладки сохраняется при переключении» реализовано структурно:
 * все три экрана смонтированы одновременно всегда, переключение вкладки
 * только меняет CSS display у обёрток. React Router здесь используется по
 * прямому назначению (путь в MemoryRouter — источник истины о текущей
 * вкладке, TabBar меняет его через navigate), но не как <Routes>/<Route> —
 * это размонтировало бы неактивный экран и обнулило бы его состояние при
 * каждом переключении, что прямо противоречит требованию.
 *
 * Сегодня у экранов-заглушек нет состояния, которое было бы видно на
 * скриншоте, — но при первом же реальном состоянии (скролл, черновик формы)
 * эта развязка перестанет быть незаметной случайностью и станет тем, ради
 * чего она сделана.
 *
 * Раскладка — height + flex:1 сверху донизу, не minHeight:'100%'. Прежняя
 * версия строила высоту вложенных панелей через проценты (minHeight:'100%'
 * у каждой), а проценты резолвятся только относительно родителя с
 * ОПРЕДЕЛЁННОЙ высотой — через несколько уровней вложенности такая цепочка
 * ненадёжна и на конкретном движке рендеринга может сложиться не так, как на
 * бумаге: заголовок вкладки прижимался к статус-бару, хотя верхний
 * safe-area отступ в этом файле стоял правильно с самого начала. flex:1 эту
 * зависимость от процентов убирает целиком — высоту считает сам флекс-
 * алгоритм. height:'100%' на корне тоже резолвится надёжно: html/body/#root
 * уже держат height:100% в mobile.css, это всего один уровень, не цепочка.
 *
 * ⚠️ 06.09.2026 здесь стояла обёртка скроллера в лишний position:relative
 * div (для позиционирования FAB) — регресс: ChartSheet.jsx считает свою
 * высоту в `%` (45%, §5 SPEC_CHART_SCREEN.md), а лишний уровень вложенности
 * — ровно то, от чего предупреждает абзац выше. Подсказка «Сведите пальцы
 * для зума» уезжала под шторку. Кнопка вынесена на `position: fixed`
 * (AristeaFab.jsx) — она не участвует в раскладке скроллера вообще, и
 * структура вернулась к изначальной, без лишнего уровня.
 */

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { listenForTaps } from '../lib/notificationTap';
import FeedScreen from '../screens/FeedScreen';
import ChartScreen from '../screens/ChartScreen';
import MoreScreen from '../screens/MoreScreen';
import TabBar from './TabBar';
import AristeaFab from './AristeaFab';
import HintOverlay from './HintOverlay';
import useChatAccess from '../lib/useChatAccess';
import { chatHint } from '../lib/onboardingCopy';
import { chatHintKey, isSeen, markSeen } from '../lib/onboardingFlags';
import { TIER_NAMES } from '../../constants';
import useTier from '../lib/useTier';
import { syncLocalNotifications } from '../lib/localNotificationsSync';

const TAB_KEYS = ['feed', 'chart', 'more'];

export default function TabShell() {
  const location = useLocation();
  const active = TAB_KEYS.includes(location.pathname.split('/')[2])
    ? location.pathname.split('/')[2]
    : 'feed';

  // Кнопка чата — на «Ленте» и «Карте», не на «Ещё» (там ей нечего делать
  // рядом со своим собственным блоком тарифа).
  const showFab = active === 'feed' || active === 'chart';

  // Какой экран сейчас показывает подсказки (SPEC_ONBOARDING.md §8). Хранится
  // ключ экрана, а не булев флаг: все три экрана смонтированы одновременно и
  // шлют своё состояние независимо, а порядок их эффектов при переключении
  // вкладки не гарантирован — булев сеттер давал бы гонку, в которой
  // «закрылось на одном» затирало бы «открылось на другом».
  const [hintsOwner, setHintsOwner] = useState(null);
  const fabRef = useRef(null);
  const hasChatAccess = useChatAccess();
  const { tier, known } = useTier();
  const [chatHintOpen, setChatHintOpen] = useState(false);

  /**
   * Подсказка у кнопки чата — при первом запуске и по разу на каждый тариф.
   *
   * ⚠️ Ждём `known`: до того как тариф приехал, неизвестно ни какой ключ
   * проверять, ни какой из двух текстов показывать. Показать раньше — значит
   * с равной вероятностью соврать про доступ.
   *
   * ⚠️ Ждём и `showFab`: подсказка подсвечивает кнопку, а её на вкладке «Ещё»
   * нет вовсе. Рамка ушла бы в пустоту.
   */
  useEffect(() => {
    if (!known || !showFab || hintsOwner !== null) return;
    if (!isSeen(chatHintKey(tier))) setChatHintOpen(true);
  }, [known, tier, showFab, hintsOwner]);

  const closeChatHint = useCallback(() => {
    setChatHintOpen(false);
    markSeen(chatHintKey(tier));
  }, [tier]);
  const handleHints = useCallback((key, open) => {
    setHintsOwner((prev) => (open ? key : (prev === key ? null : prev)));
  }, []);

  // Локальные уведомления перепланируются при каждом заходе в приложение и
  // при каждом возврате из фона — здесь, потому что TabShell монтируется
  // только вошедшему (RequireAuth), а ручка /push/upcoming требует токен.
  //
  // ⚠️ Момент выбран не «на всякий случай». План лежит в системе Android, а
  // не в приложении, и расходится с реальностью сам собой: транзиты
  // пересчитаны, основная карта сменилась, окно выдачи в 7 дней просто
  // кончилось. Заход в приложение — единственный момент, когда приложение
  // вообще выполняется и может это исправить.
  //
  // Условия («тумблер включён», «разрешение есть») проверяет сама
  // syncLocalNotifications; разрешение она не спрашивает никогда — его
  // спрашивают только по тапу на тумблер в «Ещё → Уведомления».
  useEffect(() => {
    syncLocalNotifications();
    function onVisible() {
      if (document.visibilityState === 'visible') syncLocalNotifications();
    }
    document.addEventListener('visibilitychange', onVisible);
    return () => document.removeEventListener('visibilitychange', onVisible);
  }, []);

  // Нажатие на уведомление (оба канала — notificationTap.js): "feed_today" и
  // "feed_tomorrow" — открыть ленту и развернуть прогноз своего дня. `n` —
  // счётчик, а не флаг: второе нажатие должно сработать снова.
  const navigate = useNavigate();
  const [openForecast, setOpenForecast] = useState(null);
  useEffect(() => {
    let unsubscribe = () => {};
    let alive = true;
    listenForTaps((target) => {
      navigate('/app/feed', { replace: true });
      setOpenForecast((prev) => ({ target, n: (prev?.n || 0) + 1 }));
    }).then((off) => { if (alive) unsubscribe = off; else off(); });
    return () => { alive = false; unsubscribe(); };
  }, [navigate]);

  // Высота таб-бара — измеряется, а не захардкожена: она уже включает его
  // собственный `padding-bottom: env(safe-area-inset-bottom)`
  // (класс mobile-tabbar), и FAB (position: fixed) встаёт ровно над ним
  // без гадания числом, которое разошлось бы на устройстве с другим
  // safe-area или другим масштабом шрифта.
  const tabBarRef = useRef(null);
  const [tabBarHeight, setTabBarHeight] = useState(56);

  // Счётчик изменений состава карт. Поднимают «Карта» (построила новую) и
  // «Ещё» (удалила карту или сменила основную); слушают «Лента» и «Карта»
  // (SPEC_CHART_CREATE.md §6).
  //
  // ⚠️ Он живёт здесь, а не внутри экранов, потому что экраны друг о друге
  // не знают и знать не должны, а размонтированием их не связать: все три
  // смонтированы одновременно, и `load()` у каждого зовётся только на
  // монтировании (§14 SPEC_FEED_SCREEN.md). Без этого человек, построив
  // первую карту, вернулся бы на ленту и увидел «Постройте её на вкладке
  // «Карта»» — при уже построенной карте.
  //
  // ⚠️ «Ещё» по нему НЕ перезагружается намеренно, хотя теперь и поднимает
  // его сам: список карт там правит на месте тот же обработчик, что послал
  // запрос, — он состав знает точно, и перезапрос ничего не уточнил бы. А
  // после построения карты на другой вкладке список отстаёт на один заход,
  // и ради этого поднимать третий экран не стоит: у него есть жест.
  const [chartsVersion, setChartsVersion] = useState(0);
  const handleChartsChanged = useCallback(() => setChartsVersion((v) => v + 1), []);

  // Какую карту показывает каждая вкладка — для чата: он открывается по той
  // карте, которую человек видит, а не по основной (решение владельца
  // 09.09.2026).
  //
  // ⚠️ Хранится ПО ВКЛАДКАМ, а не одним значением, и это не перестраховка:
  // «Лента» и «Карта» смонтированы одновременно и сообщают свою карту каждая
  // в своё время. Общее поле последний ответ затирал бы первым — человек на
  // «Ленте» открыл бы чат по карте, которую показывает соседняя вкладка.
  // Разойтись они реально могут: после построения новой карты «Карта» держит
  // локальное переопределение, а «Лента» остаётся на закреплённой
  // (SPEC_CHART_CREATE.md §11).
  const [tabCharts, setTabCharts] = useState({ feed: null, chart: null });
  const handleFeedChart = useCallback(
    (c) => setTabCharts((prev) => (prev.feed?.id === c?.id ? prev : { ...prev, feed: c })),
    [],
  );
  const handleChartChart = useCallback(
    (c) => setTabCharts((prev) => (prev.chart?.id === c?.id ? prev : { ...prev, chart: c })),
    [],
  );

  // ⚠️ Ref на скроллер отдаётся ВНИЗ, только «Ленте», и это не каприз:
  // прокрутка ленты живёт здесь, а не в ней самой — собственный `overflow`
  // у ленты сломал бы `position: sticky` заголовков дней (FeedDayHeader.jsx).
  // Жест «потянуть, чтобы обновить» обязан слушать тот узел, который
  // действительно прокручивается, поэтому FeedScreen получает его отсюда.
  // «Карте» и «Ещё» ref не нужен: у них свои скроллеры (список в
  // ChartSheet.jsx и корневой div MoreScreen.jsx соответственно).
  const scrollRef = useRef(null);
  useEffect(() => {
    if (tabBarRef.current) setTabBarHeight(tabBarRef.current.offsetHeight);
  }, []);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/*
        Только верхний безопасный отступ, инлайном, не классом mobile-page:
        тот задаёт padding и снизу тоже, а нижний уже даёт сам TabBar
        (класс mobile-tabbar) — если бы оба применили padding-bottom
        одновременно, отступ снизу задвоился бы и таб-бар оторвался от
        нижнего края экрана видимой пустой полосой.
      */}
      <div
        ref={scrollRef}
        style={{
          flex: 1,
          minHeight: 0,
          display: 'flex',
          flexDirection: 'column',
          overflowY: 'auto',
          paddingTop: 'env(safe-area-inset-top)',
          paddingLeft: 'env(safe-area-inset-left)',
          paddingRight: 'env(safe-area-inset-right)',
          // Запас снизу — только на «Ленте». Без него последняя карточка
          // легла бы под кнопку насовсем. На «Карте» тот же запас живёт
          // внутри списка шторки (ChartSheet.jsx) — этот скроллер сжимать
          // нельзя: у шторки жёсткий minHeight:220, и общий отступ здесь
          // душит всю композицию «колесо + шторка» разом, топя подсказку
          // под колесом (регресс 06.09.2026, найдено при приёмке).
          paddingBottom: active === 'feed' && showFab ? 84 : 0,
        }}
      >
        {/* minHeight:0 обязателен на каждом уровне: без него flex-элемент
            по умолчанию не сжимается уже своего контента (min-height:auto),
            и высота в процентах внутри (ChartSheet — 45%) резолвится в auto
            вместо доли экрана — шторка раздувается по контенту и уезжает
            за нижний край, а не встаёт куда рассчитана. Нашлось на экране
            «Карта» (вкладка «Аспекты», самый длинный список). */}
        {/* `active` экраны получают не ради оформления: все три смонтированы
            одновременно, и без этого признака подсказки «Карты» открылись бы
            сами в момент загрузки карты — поверх «Ленты», на которой человек
            в этот момент находится. */}
        <div style={{ display: active === 'feed' ? 'flex' : 'none', flex: 1, minHeight: 0, flexDirection: 'column' }}>
          <FeedScreen
            active={active === 'feed'}
            onHintsToggle={handleHints}
            scrollRef={scrollRef}
            chartsVersion={chartsVersion}
            onChartResolved={handleFeedChart}
            openForecast={openForecast}
          />
        </div>
        <div style={{ display: active === 'chart' ? 'flex' : 'none', flex: 1, minHeight: 0, flexDirection: 'column' }}>
          <ChartScreen
            active={active === 'chart'}
            onHintsToggle={handleHints}
            onChartCreated={handleChartsChanged}
            chartsVersion={chartsVersion}
            onChartResolved={handleChartChart}
          />
        </div>
        <div style={{ display: active === 'more' ? 'flex' : 'none', flex: 1, minHeight: 0, flexDirection: 'column' }}>
          <MoreScreen onChartsChanged={handleChartsChanged} />
        </div>
      </div>

      {/* На время подсказок кнопку чата прячем, а не просто перекрываем
          затемнением: она уводит в чат посреди объяснения
          (SPEC_ONBOARDING.md §8). */}
      <AristeaFab
        visible={showFab && hintsOwner === null}
        bottomOffset={tabBarHeight + 16}
        chart={active === 'chart' ? tabCharts.chart : tabCharts.feed}
        innerRef={fabRef}
      />

      {/*
        Подсказка у кнопки чата: первый запуск и по разу после каждого
        апгрейда (решение владельца 16.09.2026). Механизм тот же, что у
        подсказок экранов, — HintOverlay плюс флаг в localStorage; нового не
        заводится. Разница одна: ключ флага несёт тариф (`chatHintKey`),
        поэтому смена тарифа сама по себе делает подсказку непоказанной.

        ⚠️ Стоит ЗДЕСЬ, а не в экране: кнопка живёт в оболочке и видна и на
        «Ленте», и на «Карте». В экране она показывалась бы дважды.

        ⚠️ Гейт `hintsOwner === null` обязателен: подсказки экрана прячут саму
        кнопку (см. `visible` выше), и без гейта рамка искала бы элемент,
        которого в этот момент нет.
      */}
      {chatHintOpen && (
        <HintOverlay
          steps={[chatHint(hasChatAccess, TIER_NAMES.pro)]}
          anchors={{ chat: fabRef }}
          onClose={closeChatHint}
        />
      )}

      <TabBar ref={tabBarRef} active={active} />
    </div>
  );
}
