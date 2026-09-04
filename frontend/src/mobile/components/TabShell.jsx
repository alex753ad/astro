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
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100%' }}>
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
          overflowY: 'auto',
          paddingTop: 'env(safe-area-inset-top)',
          paddingLeft: 'env(safe-area-inset-left)',
          paddingRight: 'env(safe-area-inset-right)',
        }}
      >
        <div style={{ display: active === 'feed' ? 'block' : 'none', minHeight: '100%' }}>
          <FeedScreen />
        </div>
        <div style={{ display: active === 'chart' ? 'block' : 'none', minHeight: '100%' }}>
          <ChartScreen />
        </div>
        <div style={{ display: active === 'more' ? 'block' : 'none', minHeight: '100%' }}>
          <MoreScreen />
        </div>
      </div>
      <TabBar active={active} />
    </div>
  );
}
