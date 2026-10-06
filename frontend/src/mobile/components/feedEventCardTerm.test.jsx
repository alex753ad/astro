// Период влияния транзита на карточке ленты (4.13, флаг sky_event): строка
// с сервера выводится как есть; без поля (старый сервер) — строки нет.
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import FeedEventCard from './FeedEventCard';

const LINE = 'Период влияния: 17 октября — 1 декабря 2026, с перерывом с 30 октября по 28 ноября';
const transit = (meta) => ({
  key: 't1', kind: 'transit', title: 'Меркурий соединение Плутон', at: '2026-10-21T13:35:00+03:00',
  meta: { transit_planet: 'Mercury', natal_planet: 'Pluto', aspect_type: 'conjunction', ...meta },
});

describe('период влияния на карточке транзита', () => {
  it('раскрытая — строка периода, без строки касаний', () => {
    const html = renderToStaticMarkup(<FeedEventCard event={transit({ period_line: LINE,
      touches_line: 'Точные касания: 21 октября, 27 октября и 29 ноября 2026' })} collapsed={false} />);
    expect(html).toContain(LINE);
    expect(html).not.toContain('Точные касания');
  });

  it('свёрнутая — строки нет', () => {
    const html = renderToStaticMarkup(<FeedEventCard event={transit({ period_line: LINE })} collapsed />);
    expect(html).not.toContain('Период влияния');
  });

  it('старый сервер без поля — строки нет', () => {
    const html = renderToStaticMarkup(<FeedEventCard event={transit({})} collapsed={false} />);
    expect(html).not.toContain('Период влияния');
  });
});
