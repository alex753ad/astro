/**
 * shareRules.test.js — инвариант приватности листа «Поделиться».
 *
 * Главный кейс здесь — не перечисление шагов, а свойство: множество шагов,
 * из которых РАЗРЕШЕНО действие, обязано быть подмножеством множества
 * шагов, в которых предупреждение ВИДНО. Именно этим «предупреждение до
 * действия» отличается от «предупреждение после действия»: второе
 * проходило бы любую поштучную проверку.
 *
 * ⚠️ Честно про «падает на коде до правки»: модуля до этой правки не было
 * вовсе, поэтому первый прогон падает на импорте — сигнал слабый. Ценность
 * теста вперёд: он падёт, когда кто-нибудь добавит шаг, из которого можно
 * действовать без предупреждения, или размоет сам текст.
 */
import { describe, expect, it } from 'vitest';
import {
  SHARE_DISCLOSURE,
  SHARE_STEPS,
  SHARE_TTL_DAYS,
  disclosureVisible,
  mayRunShareAction,
} from './shareRules';

const ALL_STEPS = Object.values(SHARE_STEPS);

describe('предупреждение показывается ДО действия', () => {
  it('из закрытого листа действовать нельзя — предупреждения ещё не видели', () => {
    expect(mayRunShareAction(SHARE_STEPS.CLOSED)).toBe(false);
    expect(disclosureVisible(SHARE_STEPS.CLOSED)).toBe(false);
  });

  it('нет ни одного шага, где действие разрешено, а предупреждения нет', () => {
    for (const step of ALL_STEPS) {
      if (mayRunShareAction(step)) {
        expect(disclosureVisible(step), `шаг ${step}`).toBe(true);
      }
    }
  });

  it('незнакомый шаг действовать не разрешает', () => {
    expect(mayRunShareAction('done')).toBe(false);
    expect(mayRunShareAction(undefined)).toBe(false);
  });

  it('во время работы повторный тап не запускает второй запрос', () => {
    expect(mayRunShareAction(SHARE_STEPS.WORKING)).toBe(false);
    // При этом предупреждение с экрана не исчезает.
    expect(disclosureVisible(SHARE_STEPS.WORKING)).toBe(true);
  });

  it('после отказа повторить можно, лист остаётся с предупреждением', () => {
    expect(mayRunShareAction(SHARE_STEPS.ERROR)).toBe(true);
    expect(disclosureVisible(SHARE_STEPS.ERROR)).toBe(true);
  });
});

describe('текст предупреждения называет то, что действительно уходит', () => {
  const text = SHARE_DISCLOSURE.join(' ');

  it('дата и место рождения названы', () => {
    expect(text).toMatch(/дата/i);
    expect(text).toMatch(/место рождения/i);
  });

  it('срок назван и совпадает с числом из константы', () => {
    expect(SHARE_TTL_DAYS).toBe(90); // = SHARE_TTL_SECONDS, share_router.py:41
    expect(text).toContain(String(SHARE_TTL_DAYS));
  });

  it('сказано, что отозвать ссылку нельзя — этого на бэкенде нет', () => {
    expect(text).toMatch(/отозвать/i);
  });
});
