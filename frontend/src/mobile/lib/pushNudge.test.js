import { describe, expect, it } from 'vitest';
import {
  CARD_DELAY_MS, NUDGE_CARD, NUDGE_CARD_SETTINGS, NUDGE_NONE, NUDGE_SCREEN, NUDGE_SILENT, NUDGE_WAIT,
  decideNudge, diagLine,
} from './pushNudge';

const NOW = 1_800_000_000_000;
const base = {
  registered: true, forecastSeen: true, choice: null, permission: 'prompt',
  askedAt: null, cardClosed: false, now: NOW,
};
const d = (patch) => decideNudge({ ...base, ...patch });

describe('decideNudge', () => {
  it('новый человек после первого прогноза — экран', () => {
    expect(d({})).toBe(NUDGE_SCREEN);
  });

  it('гостю и до первого прогноза — ничего', () => {
    expect(d({ registered: false })).toBe(NUDGE_NONE);
    expect(d({ forecastSeen: false })).toBe(NUDGE_NONE);
  });

  it('тумблер уже трогали (вкл или сам выключил) — ничего', () => {
    expect(d({ choice: '1' })).toBe(NUDGE_NONE);
    expect(d({ choice: '0' })).toBe(NUDGE_NONE);
    expect(d({ choice: '0', permission: 'granted' })).toBe(NUDGE_NONE);
  });

  it('Android до 13: разрешение есть — канал молча, без экрана', () => {
    expect(d({ permission: 'granted' })).toBe(NUDGE_SILENT);
  });

  it('Android до 13, уведомления выключены в системе — экрана нет, через 3 дня карточка с настройками', () => {
    expect(d({ permission: 'denied' })).toBe(NUDGE_WAIT);
    expect(d({ permission: 'denied', askedAt: NOW - CARD_DELAY_MS + 1 })).toBe(NUDGE_NONE);
    expect(d({ permission: 'denied', askedAt: NOW - CARD_DELAY_MS })).toBe(NUDGE_CARD_SETTINGS);
  });

  it('«Не сейчас» или отказ — карточка через 3 дня', () => {
    expect(d({ askedAt: NOW - 1000 })).toBe(NUDGE_NONE);
    expect(d({ askedAt: NOW - CARD_DELAY_MS })).toBe(NUDGE_CARD);
    expect(d({ permission: 'prompt-with-rationale', askedAt: NOW - CARD_DELAY_MS })).toBe(NUDGE_CARD);
  });

  it('повторный отказ — карточка с «Открыть настройки»', () => {
    expect(d({ permission: 'denied', askedAt: NOW - CARD_DELAY_MS })).toBe(NUDGE_CARD_SETTINGS);
  });

  it('карточку закрыли — больше не показываем', () => {
    expect(d({ askedAt: NOW - CARD_DELAY_MS, cardClosed: true })).toBe(NUDGE_NONE);
    expect(d({ permission: 'denied', askedAt: NOW - CARD_DELAY_MS, cardClosed: true })).toBe(NUDGE_NONE);
  });

  it('разрешили в настройках после карточки — канал молча', () => {
    expect(d({ permission: 'granted', askedAt: NOW - CARD_DELAY_MS })).toBe(NUDGE_SILENT);
  });

  it('веб или отказавший мост — ничего', () => {
    expect(d({ permission: 'unavailable' })).toBe(NUDGE_NONE);
  });

  it('Android 12, свежая установка: молча; не вышло — следующая проверка снова молча', () => {
    // Неудача ничего не записывает: choice остаётся null, askedAt — тоже.
    expect(d({ permission: 'granted' })).toBe(NUDGE_SILENT);
    expect(d({ permission: 'granted' })).toBe(NUDGE_SILENT);
  });

  it('Android 13+, свежая установка: до прогноза ничего, после — экран', () => {
    expect(d({ forecastSeen: false })).toBe(NUDGE_NONE);
    expect(d({ forecastSeen: true })).toBe(NUDGE_SCREEN);
  });
});

describe('diagLine', () => {
  it('значения по-русски', () => {
    const line = diagLine({
      forecastSeen: true, askedAt: null, cardClosed: false,
      last: { at: NOW, trigger: 'tab', result: 'silent', permission: 'granted', enable: 'fail' },
    }, null, NOW);
    expect(line).toContain('прогноз показан: да');
    expect(line).toContain('тумблер: не трогали');
    expect(line).toContain('возврат на ленту → молча');
    expect(line).toContain('включение: не вышло');
    expect(diagLine({ forecastSeen: false, last: { enable: 'server', result: 'screen' } }, '1')).toContain('включение: сервер');
    expect(diagLine({ last: { enable: 'device', result: 'wait' } }, '0')).toMatch(/ждать.*устройство/);
  });
});
