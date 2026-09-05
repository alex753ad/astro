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
 */

import React from 'react';
import { useLocation } from 'react-router-dom';
import FeedScreen from '../screens/FeedScreen';
import ChartScreen from '../screens/ChartScreen';
import MoreScreen from '../screens/MoreScreen';
import TabBar from './TabBar';

const TAB_KEYS = ['feed', 'chart', 'more'];

export default function TabShell() {
  const location = useLocation();
  const active = TAB_KEYS.includes(location.pathname.split('/')[2])
    ? location.pathname.split('/')[2]
    : 'feed';

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
        style={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          overflowY: 'auto',
          paddingTop: 'env(safe-area-inset-top)',
          paddingLeft: 'env(safe-area-inset-left)',
          paddingRight: 'env(safe-area-inset-right)',
        }}
      >
        <div style={{ display: active === 'feed' ? 'flex' : 'none', flex: 1, flexDirection: 'column' }}>
          <FeedScreen />
        </div>
        <div style={{ display: active === 'chart' ? 'flex' : 'none', flex: 1, flexDirection: 'column' }}>
          <ChartScreen />
        </div>
        <div style={{ display: active === 'more' ? 'flex' : 'none', flex: 1, flexDirection: 'column' }}>
          <MoreScreen />
        </div>
      </div>
      <TabBar active={active} />
    </div>
  );
}
