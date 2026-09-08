/**
 * dateMask.test.js — маска даты рождения.
 *
 * Проверяется то, что в компоненте проверить нечем (DOM-окружения в проекте
 * нет): расстановка точек по мере набора, обратное преобразование и — самое
 * важное — что НЕДОСОБРАННАЯ дата не превращается в дату.
 */
import { describe, expect, it } from 'vitest';
import { displayToIso, hasDigits, isoToDisplay, maskDateInput } from './dateMask';

describe('maskDateInput — точки расставляются сами', () => {
  it('ставит точки по мере набора', () => {
    expect(maskDateInput('2')).toBe('2');
    expect(maskDateInput('28')).toBe('28');
    expect(maskDateInput('280')).toBe('28.0');
    expect(maskDateInput('2805')).toBe('28.05');
    expect(maskDateInput('28051')).toBe('28.05.1');
    expect(maskDateInput('28051996')).toBe('28.05.1996');
  });

  it('переживает повторный проход по уже размеченной строке', () => {
    // Поле контролируемое: значение возвращается в маску на каждом нажатии.
    expect(maskDateInput('28.05.1996')).toBe('28.05.1996');
  });

  it('выбрасывает всё, кроме цифр, — включая вставленное из буфера', () => {
    // Маска цифры только переставляет и НЕ угадывает пропущенное: «28 мая
    // 1996» даёт цифры 281996, то есть 28.19.96 — и это правильно. Форма
    // такую дату отобьёт как неполную, а не построит карту не по той дате.
    expect(maskDateInput('28 мая 1996')).toBe('28.19.96');
    expect(maskDateInput('28.05.1996 г.')).toBe('28.05.1996');
    expect(maskDateInput('1996-05-28')).toBe('19.96.0528');
  });

  it('лишние цифры отбрасывает, а не сдвигает год', () => {
    expect(maskDateInput('280519966')).toBe('28.05.1996');
  });

  it('удаление символов работает в обратную сторону', () => {
    expect(maskDateInput('28.05.19')).toBe('28.05.19');
    expect(maskDateInput('28.0')).toBe('28.0');
    expect(maskDateInput('')).toBe('');
  });
});

describe('displayToIso — недособранная дата не становится датой', () => {
  it('переводит полную дату', () => {
    expect(displayToIso('28.05.1996')).toBe('1996-05-28');
  });

  it('на неполном вводе отдаёт пустую строку, а не половину', () => {
    // Иначе «28.05.19» уехало бы в запрос как 0019 год.
    expect(displayToIso('28.05.19')).toBe('');
    expect(displayToIso('28.05')).toBe('');
    expect(displayToIso('2')).toBe('');
    expect(displayToIso('')).toBe('');
  });
});

describe('isoToDisplay — обратный перевод', () => {
  it('переводит ISO в вид для поля', () => {
    expect(isoToDisplay('1996-05-28')).toBe('28.05.1996');
  });

  it('пустое и неполное не показывает мусором', () => {
    expect(isoToDisplay('')).toBe('');
    expect(isoToDisplay(null)).toBe('');
    expect(isoToDisplay('1996-05')).toBe('');
  });
});

describe('hasDigits — отличает «не трогали» от «набрали половину»', () => {
  it('различает пустое поле и неполный ввод', () => {
    expect(hasDigits('')).toBe(false);
    expect(hasDigits('.')).toBe(false);
    expect(hasDigits('28.05')).toBe(true);
  });
});
