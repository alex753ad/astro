/**
 * Закрытая карточка периода в ПРИЛОЖЕНИИ — замочек, без размытия.
 *
 * Находка с телефона 01.10.2026: на бесплатном «Меркурий в 11 доме» стоял
 * под блюром (витрина BlurredHint с 05.09.2026, как на сайте), а замочка не
 * было — в отличие от закрытых карточек ниже. Решение владельца: в
 * приложении — замочек, на сайте размытие остаётся (веб этот компонент не
 * рендерит). Рендер в строку — DOM-окружения в проекте нет.
 */
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import FeedEventCard from './FeedEventCard';

const period = {
  key: 'p1', kind: 'planner_period', title: 'Меркурий в 11 доме', locked: true,
  at: '2026-10-01T10:00:00+03:00', ends_at: '2026-10-20T10:00:00+03:00', duration_days: 19,
  meta: { planet: 'Mercury', house: 11, groups: [] },
};

describe('закрытый период в ленте приложения', () => {
  it.each([false, true])('замочек есть, размытия нет (свёрнут: %s)', (collapsed) => {
    const html = renderToStaticMarkup(<FeedEventCard event={period} collapsed={collapsed} />);
    expect(html).toContain('Расшифровка закрыта');
    expect(html).not.toContain('blur(');
  });
});
