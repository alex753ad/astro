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
import { useLocation } from 'react-router-dom';
import FeedScreen from '../screens/FeedScreen';
import ChartScreen from '../screens/ChartScreen';
import MoreScreen from '../screens/MoreScreen';
import TabBar from './TabBar';
import AristeaFab from './AristeaFab';

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
  const handleHints = useCallback((key, open) => {
    setHintsOwner((prev) => (open ? key : (prev === key ? null : prev)));
  }, []);

  // Высота таб-бара — измеряется, а не захардкожена: она уже включает его
  // собственный `padding-bottom: env(safe-area-inset-bottom)`
  // (класс mobile-tabbar), и FAB (position: fixed) встаёт ровно над ним
  // без гадания числом, которое разошлось бы на устройстве с другим
  // safe-area или другим масштабом шрифта.
  const tabBarRef = useRef(null);
  const [tabBarHeight, setTabBarHeight] = useState(56);

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
          <FeedScreen active={active === 'feed'} onHintsToggle={handleHints} scrollRef={scrollRef} />
        </div>
        <div style={{ display: active === 'chart' ? 'flex' : 'none', flex: 1, minHeight: 0, flexDirection: 'column' }}>
          <ChartScreen active={active === 'chart'} onHintsToggle={handleHints} />
        </div>
        <div style={{ display: active === 'more' ? 'flex' : 'none', flex: 1, minHeight: 0, flexDirection: 'column' }}>
          <MoreScreen />
        </div>
      </div>

      {/* На время подсказок кнопку чата прячем, а не просто перекрываем
          затемнением: она уводит в чат посреди объяснения
          (SPEC_ONBOARDING.md §8). */}
      <AristeaFab visible={showFab && hintsOwner === null} bottomOffset={tabBarHeight + 16} />

      <TabBar ref={tabBarRef} active={active} />
    </div>
  );
}
