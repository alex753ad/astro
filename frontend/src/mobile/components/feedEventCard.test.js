import { describe, expect, it } from 'vitest';

import { isLocked, isOpenable } from './FeedEventCard';

/**
 * feedEventCard.test.js — какая карточка ленты открывается тапом.
 *
 * ⚠️ Дефект 09.09.2026, найденный приёмкой на устройстве: «тапаю на транзиты,
 * ничего не открывается». Условием открытия было одно `locked`, и до
 * появления разбора транзита это было верно — в панели показывался только
 * тизер, а у открытого события тизера нет. С разбором условие устарело и
 * стало дефектом: сервер не отдаёт тизеры тарифам выше бесплатного
 * (`transit_teaser`, feed/builder.py), поэтому на pro не открывался НИ ОДИН
 * транзит, а на free не открывались ровно те два, ради которых разбор и
 * делался.
 *
 * ⚠️ Почему это не поймали раньше: заметно только на устройстве и только на
 * платном тарифе. Тесты проверяли разбор и правила показа — то есть
 * содержимое панели, — но не то, открывается ли она вообще.
 */

const transit = (extra = {}) => ({ kind: 'transit', ...extra });

describe('транзит открывается всегда — у него есть что показать', () => {
  it('открытый транзит (без тизера) — нажимается', () => {
    // Ровно тот случай, который был сломан: на pro тизеров нет ни у чего.
    expect(isOpenable(transit())).toBe(true);
  });

  it('закрытый транзит (с тизером) — тоже нажимается', () => {
    expect(isOpenable(transit({ teaser: { intro: 'текст' } }))).toBe(true);
  });

  it('на pro ни один транзит не закрыт — и все обязаны открываться', () => {
    // Модель ответа сервера для платного тарифа: teaser отсутствует,
    // locked всегда false (feed/builder.py).
    const feed = [transit({ locked: false }), transit({ locked: false })];
    expect(feed.every(isOpenable)).toBe(true);
    expect(feed.some(isLocked)).toBe(false);
  });
});

describe('у чего разбора нет — открывается только когда закрыто', () => {
  it('лунная фаза без тизера не нажимается: показывать нечего', () => {
    expect(isOpenable({ kind: 'moon_phase' })).toBe(false);
  });

  it('затмение без тизера не нажимается', () => {
    expect(isOpenable({ kind: 'eclipse' })).toBe(false);
  });

  it('период планера закрыт флагом locked — нажимается', () => {
    // У периодов тизера нет вовсе, их закрывает locked.
    expect(isOpenable({ kind: 'planner_period', locked: true })).toBe(true);
  });

  it('открытый период планера не нажимается', () => {
    expect(isOpenable({ kind: 'planner_period', locked: false })).toBe(false);
  });
});

describe('isLocked — признак закрытости не выводится из тарифа', () => {
  it('тизер закрывает', () => {
    expect(isLocked({ kind: 'transit', teaser: { intro: 'т' } })).toBe(true);
  });

  it('locked закрывает', () => {
    expect(isLocked({ kind: 'planner_period', locked: true })).toBe(true);
  });

  it('без обоих — открыто', () => {
    // Тариф здесь не участвует намеренно: копия тарифного правила на клиенте
    // разошлась бы с серверной.
    expect(isLocked({ kind: 'transit' })).toBe(false);
  });
});
