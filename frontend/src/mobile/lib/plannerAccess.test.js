import { describe, it, expect } from 'vitest';
import { lockedPlannerText, upgradeOpensIt } from './plannerAccess';

/**
 * Закреплено то, ради чего файл и заведён: `locked` больше не равно «купи
 * тариф». Перебираются ВСЕ сочетания (тариф × вид события), потому что ошибка
 * здесь молчаливая — человек просто видит не ту фразу, а заметно это только по
 * жалобе «мне предлагают купить то, что я уже купил».
 */

const TIERS = ['free', 'lite', 'pro', 'premium'];
const KINDS = ['planner_moon_house', 'planner_period', 'planner_longterm'];
const ev = (kind, locked = true) => ({ kind, locked });

describe('upgradeOpensIt — открывает ли апгрейд это событие', () => {
  it('открытое событие не продаётся никому', () => {
    for (const tier of TIERS) {
      for (const kind of KINDS) {
        expect(upgradeOpensIt(ev(kind, false), tier)).toBe(false);
      }
    }
  });

  it('на free закрытым может быть что угодно, и апгрейд помогает всегда', () => {
    for (const kind of KINDS) {
      expect(upgradeOpensIt(ev(kind), 'free')).toBe(true);
    }
  });

  it('у платного закрытых проходов Луны не бывает — продавать нечего', () => {
    // ⚠️ Это НЕ «горизонт вместо витрины», как было до 16.09.2026: у платных
    // `planner_weeks_ahead: None`, то есть событие с locked сюда вообще не
    // доходит. Ветка оставлена на случай расхождения сетки между сервером и
    // клиентом, и она обязана молчать, а не продавать наугад.
    for (const tier of ['lite', 'pro', 'premium']) {
      expect(upgradeOpensIt(ev('planner_moon_house'), tier)).toBe(false);
      expect(upgradeOpensIt(ev('planner_period'), tier)).toBe(false);
    }
  });

  it('долгосрочный период на Веге ещё продаётся, на Лире уже нет', () => {
    expect(upgradeOpensIt(ev('planner_longterm'), 'lite')).toBe(true);
    expect(upgradeOpensIt(ev('planner_longterm'), 'pro')).toBe(false);
    expect(upgradeOpensIt(ev('planner_longterm'), 'premium')).toBe(false);
  });

  it('неизвестный тариф не продаёт ничего', () => {
    // Показать заплатившему предложение купить хуже, чем не показать его
    // бесплатному: второй увидит витрину и без нас.
    for (const kind of KINDS) {
      expect(upgradeOpensIt(ev(kind), 'free', false)).toBe(false);
      expect(upgradeOpensIt(ev(kind), undefined, false)).toBe(false);
    }
  });

  it('пустое событие не роняет правило', () => {
    expect(upgradeOpensIt(null, 'free')).toBe(false);
    expect(upgradeOpensIt(undefined, 'pro')).toBe(false);
  });
});

describe('lockedPlannerText — текст соответствует тому, что реально откроется', () => {
  it('платному не говорят ничего — такого состояния у него нет', () => {
    // Прежняя строка «Рекомендации появятся ближе к сроку» удалена вместе с
    // состоянием, которое её порождало (решение владельца 16.09.2026).
    for (const tier of ['lite', 'pro', 'premium']) {
      expect(lockedPlannerText(ev('planner_moon_house'), tier)).toBe('');
    }
  });

  it('бесплатному называют обе открытые половины: прошлое и текущую неделю', () => {
    const text = lockedPlannerText(ev('planner_moon_house'), 'free');
    expect(text).toMatch(/Прошедшие периоды и текущая неделя/);
  });

  it('у долгосрочного периода своя строка — он про старший тариф, а не про неделю', () => {
    const text = lockedPlannerText(ev('planner_longterm'), 'lite');
    expect(text).toMatch(/старшем тарифе/);
    expect(text).not.toMatch(/недел/);
  });

  it('ни в одной ветке не обещано время, которого мы не знаем', () => {
    // «Откроется через N дней» посчитать нечем: горизонт едет вместе с
    // календарём, а не с событием. Та же причина, по которой в ленте
    // запрещены даты границ транзита (CLAUDE.md).
    for (const tier of TIERS) {
      for (const kind of KINDS) {
        expect(lockedPlannerText(ev(kind), tier)).not.toMatch(/\d+\s*(дн|час|недел)/);
      }
    }
  });
});
