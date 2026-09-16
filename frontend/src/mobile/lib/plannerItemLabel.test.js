import { describe, it, expect } from 'vitest';
import { splitItemLabel } from './plannerItemLabel';

describe('splitItemLabel — метка в начале пункта рекомендаций', () => {
  it('метка Луны выделяется', () => {
    // Так методичка хранит подписи у Луны: heading пустой, метка внутри пункта.
    const { label, rest } = splitItemLabel('Работа: наведи порядок в документах, разбери почту');
    expect(label).toBe('Работа:');
    expect(rest).toBe('наведи порядок в документах, разбери почту');
  });

  it('пункт без двоеточия остаётся целым', () => {
    const { label, rest } = splitItemLabel('Ставьте цели на будущее и корректируйте курс');
    expect(label).toBe('');
    expect(rest).toBe('Ставьте цели на будущее и корректируйте курс');
  });

  it('двоеточие в середине фразы меткой не считается', () => {
    // ⚠️ Без ограничения длины жирным стала бы половина предложения — а
    // двоеточия в методичке встречаются и в перечислениях.
    const long = 'Следите за модой, политикой и экономикой, а также новостями: это важно';
    expect(splitItemLabel(long).label).toBe('');
  });

  it('метка со знаками препинания внутри не метка', () => {
    expect(splitItemLabel('Утром, днём: что-то').label).toBe('');
    expect(splitItemLabel('Сделай. Потом: ещё').label).toBe('');
  });

  it('двоеточие первым символом ничего не ломает', () => {
    expect(splitItemLabel(': странный пункт').label).toBe('');
  });

  it('пустое и не-строка не роняют правило', () => {
    expect(splitItemLabel('')).toEqual({ label: '', rest: '' });
    expect(splitItemLabel(null)).toEqual({ label: '', rest: '' });
    expect(splitItemLabel(undefined)).toEqual({ label: '', rest: '' });
  });

  it('граница длины: ровно 28 символов — ещё метка, 29 — уже нет', () => {
    const l28 = 'а'.repeat(27);
    expect(splitItemLabel(`${l28}: текст`).label).toBe(`${l28}:`);
    const l29 = 'а'.repeat(29);
    expect(splitItemLabel(`${l29}: текст`).label).toBe('');
  });
});
