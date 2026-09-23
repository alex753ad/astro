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
  // ⚠️ До 23.09.2026 здесь стояло «лунная фаза не нажимается: показывать
  // нечего». Теперь в панели фазы — личный прогноз на новолуние/полнолуние
  // (решение владельца), и ненажимаемая фаза прятала бы его целиком.
  it('новолуние и полнолуние нажимаются — в панели прогноз на фазу', () => {
    expect(isOpenable({ kind: 'moon_phase', meta: { type: 'new_moon' } })).toBe(true);
    expect(isOpenable({ kind: 'moon_phase', meta: { type: 'full_moon' } })).toBe(true);
  });

  it('затмение нажимается — оно заменяет в ленте фазу того же рода', () => {
    expect(isOpenable({ kind: 'eclipse', meta: { type: 'solar' } })).toBe(true);
    expect(isOpenable({ kind: 'eclipse', meta: { type: 'lunar' } })).toBe(true);
  });

  it('фаза без типа не нажимается: прогноз не к чему привязать', () => {
    expect(isOpenable({ kind: 'moon_phase' })).toBe(false);
    expect(isOpenable({ kind: 'eclipse' })).toBe(false);
  });

  it('период планера закрыт флагом locked — нажимается', () => {
    // У периодов тизера нет вовсе, их закрывает locked.
    expect(isOpenable({ kind: 'planner_period', locked: true })).toBe(true);
  });

  // ⚠️ До 16.09.2026 здесь стояло обратное: «открытый период планера не
  // нажимается». Правило отменено решением владельца — панель события научилась
  // показывать срок, тему и рекомендации, то есть у ОТКРЫТОГО периода наконец
  // есть что открывать. Прежнее условие давало тот же дефект, что уже ловили на
  // транзитах 09.09.2026: у платного тарифа не открывалось НИЧЕГО именно
  // потому, что у него всё открыто.
  it('открытый период планера тоже нажимается — в панели его разбор', () => {
    expect(isOpenable({ kind: 'planner_period', locked: false })).toBe(true);
  });

  it('проход Луны по дому нажимается на любом тарифе', () => {
    expect(isOpenable({ kind: 'planner_moon_house', locked: true })).toBe(true);
    expect(isOpenable({ kind: 'planner_moon_house', locked: false })).toBe(true);
  });

  it('долгосрочный период нажимается — чип в полосе «сейчас» ведёт в ту же панель', () => {
    expect(isOpenable({ kind: 'planner_longterm', locked: false })).toBe(true);
  });

  it('не-планерное событие от этого правила не меняется', () => {
    // Проверка, что признак — именно префикс `planner_`, а не «есть ends_at»:
    // у фазы Луны его нет, но у затмения в принципе может появиться.
    // Фаза без типа — чтобы не мешало правило прогноза на фазу выше.
    expect(isOpenable({ kind: 'moon_phase', locked: false })).toBe(false);
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
