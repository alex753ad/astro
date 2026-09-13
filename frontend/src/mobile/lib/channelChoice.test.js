/**
 * channelChoice.test.js — замок на дедуп между каналами уведомлений.
 *
 * Проверяется СВОЙСТВО, а не перечень случаев: при любом сочетании входов
 * активен не больше одного канала. Именно это, а не текст и не время, не даёт
 * одному и тому же событию прийти дважды — пушем и локальным уведомлением о
 * том же самом.
 *
 * ⚠️ Проверка вида «ни одно сочетание не включает оба» разряжается молча: на
 * выборке, где ни один канал вообще не включается, она зелёная, потому что
 * проверять нечего. Поэтому рядом стоят assert'ы, что в переборе встретились
 * ОБА вида включённого канала — иначе тест доказывал бы только то, что
 * `decideChannel` умеет возвращать `null`.
 */
import { describe, expect, it } from 'vitest';
import {
  CHANNEL_DEVICE,
  CHANNEL_SERVER,
  channelState,
  decideChannel,
} from './channelChoice';

const TOKENS = [null, '', 'fcm-token-abc'];
const PERMISSIONS = ['granted', 'denied', 'prompt', 'unavailable'];

/** Все сочетания входов, какие вообще бывают на устройстве. */
const ALL = TOKENS.flatMap((t) => PERMISSIONS.map((p) => ({ token: t, permission: p })));

describe('активен не больше одного канала', () => {
  it('ни одно сочетание не включает оба канала сразу', () => {
    const states = ALL.map(({ token, permission }) =>
      channelState(decideChannel(token, permission)));

    // ⚠️ Без этих двух строк проверка ниже разряжается: на выборке, где ничего
    // не включается, «не включены оба» верно бессодержательно.
    expect(states.some((s) => s.serverPush), 'в переборе нет ни одного серверного канала').toBe(true);
    expect(states.some((s) => s.localNotifications), 'в переборе нет ни одного локального канала').toBe(true);

    for (const s of states) {
      expect(s.serverPush && s.localNotifications, 'включены оба канала разом').toBe(false);
    }
  });

  it('канал определён однозначно для каждого сочетания', () => {
    for (const { token, permission } of ALL) {
      const chosen = decideChannel(token, permission);
      expect([CHANNEL_SERVER, CHANNEL_DEVICE, null]).toContain(chosen);
    }
  });
});

describe('правило выбора', () => {
  it('есть токен — серверный канал, каким бы ни было разрешение', () => {
    for (const permission of PERMISSIONS) {
      expect(decideChannel('fcm-token-abc', permission)).toBe(CHANNEL_SERVER);
    }
  });

  it('нет токена, но разрешение выдано — локальные запасным каналом', () => {
    expect(decideChannel(null, 'granted')).toBe(CHANNEL_DEVICE);
  });

  it('нет ни токена, ни разрешения — не включается ничего', () => {
    for (const permission of ['denied', 'prompt', 'unavailable']) {
      expect(decideChannel(null, permission)).toBeNull();
    }
  });

  it('пустой токен считается отсутствующим, а не валидным', () => {
    // Мост может вернуть пустую строку вместо null — по значению это «нет
    // токена», и трактовать её как успех значило бы выключить локальные там,
    // где серверный канал не работает.
    expect(decideChannel('', 'granted')).toBe(CHANNEL_DEVICE);
  });

  it('токен важнее разрешения: худший канал не выбирается там, где есть лучший', () => {
    // Серверный будит устройство, локальный нет. Обратный порядок проверок
    // молча отдавал бы человеку худший канал.
    expect(decideChannel('fcm-token-abc', 'granted')).toBe(CHANNEL_SERVER);
  });
});

describe('состояние по каналу', () => {
  it('ни один канал не включён, когда выбора нет', () => {
    expect(channelState(null)).toEqual({ serverPush: false, localNotifications: false });
  });

  it('незнакомый канал не включает ничего', () => {
    expect(channelState('carrier-pigeon')).toEqual({ serverPush: false, localNotifications: false });
  });
});
