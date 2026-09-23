import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { pickAnchorDate, withToday } from './feedAnchor';

const day = (date) => ({ date });

describe('withToday — у сегодняшнего дня всегда есть прогноз', () => {
  const d = (date) => ({ date, events: [{ key: date }] });

  it('пустой сегодняшний день встаёт на своё место по дате', () => {
    const out = withToday([d('2026-09-14'), d('2026-09-18')], '2026-09-16');
    expect(out.map((x) => x.date)).toEqual(['2026-09-14', '2026-09-16', '2026-09-18']);
    expect(out[1].events).toEqual([]);
    // Следствие: якорь теперь — сегодня, а не ближайший следующий день.
    expect(pickAnchorDate(out, '2026-09-16')).toBe('2026-09-16');
  });

  it('если сегодня уже есть события — список не меняется', () => {
    const days = [d('2026-09-16')];
    expect(withToday(days, '2026-09-16')).toBe(days);
  });

  it('пустое окно не получает искусственного дня', () => {
    expect(withToday([], '2026-09-16')).toEqual([]);
  });

  it('сегодня вне окна — не вставляется', () => {
    const days = [d('2026-10-01')];
    expect(withToday(days, '2026-09-16', { from: '2026-09-20', to: '2026-12-01' })).toBe(days);
  });

  it('сегодня позже всех дней — встаёт в конец', () => {
    const out = withToday([d('2026-09-10')], '2026-09-16');
    expect(out.map((x) => x.date)).toEqual(['2026-09-10', '2026-09-16']);
  });
});

describe('pickAnchorDate — день, на котором открывается лента', () => {
  it('сегодняшний день, если он в списке есть', () => {
    const days = ['2026-09-14', '2026-09-16', '2026-09-18'].map(day);
    expect(pickAnchorDate(days, '2026-09-16')).toBe('2026-09-16');
  });

  it('ближайший следующий, если сегодня пусто', () => {
    // 68 дней из 148 в боевой выдаче не содержат ни одной карточки — это не
    // редкий случай, а половина ленты.
    const days = ['2026-09-14', '2026-09-18'].map(day);
    expect(pickAnchorDate(days, '2026-09-16')).toBe('2026-09-18');
  });

  it('последний день, если всё окно в прошлом', () => {
    const days = ['2026-08-14', '2026-08-18'].map(day);
    expect(pickAnchorDate(days, '2026-09-16')).toBe('2026-08-18');
  });

  it('первый день окна, если всё окно в будущем', () => {
    const days = ['2026-10-01', '2026-10-05'].map(day);
    expect(pickAnchorDate(days, '2026-09-16')).toBe('2026-10-01');
  });

  it('⚠️ НИКОГДА не первый день списка, когда впереди есть дни', () => {
    // Ровно то, что видели на приёмке 16.09.2026: лента стояла на начале
    // окна, то есть на месяце назад. Причина была в прокрутке, не здесь, —
    // но без этой проверки правило и прокрутка неразличимы при разборе.
    const days = ['2026-08-12', '2026-08-13', '2026-09-16', '2026-09-17'].map(day);
    expect(pickAnchorDate(days, '2026-09-16')).not.toBe('2026-08-12');
    expect(pickAnchorDate(days, '2026-09-16')).toBe('2026-09-16');
  });

  it('день, начавшийся ДО левого края окна, якорем не становится', () => {
    // Проход Луны, идущий на момент начала окна, приходит с настоящим началом
    // за краем (started_before) и даёт лишний день в самом верху списка.
    const days = ['2026-08-15', '2026-08-16', '2026-09-16'].map(day);
    expect(pickAnchorDate(days, '2026-09-16')).toBe('2026-09-16');
  });

  it('пустой список не роняет правило', () => {
    expect(pickAnchorDate([], '2026-09-16')).toBeNull();
    expect(pickAnchorDate(null, '2026-09-16')).toBeNull();
  });
});

const repoRoot = fileURLToPath(new URL('../../../../', import.meta.url));
const read = (p) => readFileSync(repoRoot + p, 'utf-8');

describe('полоска дней не двигает вертикальный скроллер', () => {
  it('прокрутка к сегодня идёт своим scrollLeft, а не scrollIntoView', () => {
    // ⚠️ `scrollIntoView` прокручивает ВСЕ прокручиваемые предки. У полоски
    // предок — общий вертикальный скроллер ленты (TabShell.jsx), и `block`
    // поднимал его в начало окна поверх прокрутки к сегодняшнему дню.
    // Возврат `scrollIntoView` сюда вернёт и дефект — заметный только на
    // устройстве и выглядящий как «лента открывается на месяц назад».
    const src = read('frontend/src/mobile/components/FeedDayStrip.jsx');
    const effect = src.slice(src.indexOf('useEffect('), src.indexOf('if (!from || !to)'));
    expect(effect).toContain('scrollLeft');
    expect(effect).not.toContain('scrollIntoView');
  });

  it('FeedScreen по-прежнему прокручивает к якорю сам', () => {
    const src = read('frontend/src/mobile/screens/FeedScreen.jsx');
    expect(src).toContain('anchorRef.current.scrollIntoView');
  });
});
