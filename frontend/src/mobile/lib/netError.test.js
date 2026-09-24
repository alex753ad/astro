/**
 * netError.test.js — что считается «нет сети», что показать и что не слать в Sentry.
 */
import { describe, expect, it } from 'vitest';
import { NET_TEXT, NetError, errorText, isConnectivity, isNetworkNoise, netKind } from './netError';

describe('netKind', () => {
  it('fetch без связи в WebView — offline', () => {
    expect(netKind(new TypeError('Failed to fetch'))).toBe('offline');
  });

  it('обычный TypeError — не сеть', () => {
    expect(netKind(new TypeError("Cannot read properties of undefined (reading 'id')"))).toBeNull();
  });

  it('NetError несёт свой вид', () => {
    expect(netKind(new NetError('timeout'))).toBe('timeout');
    expect(netKind(new NetError('server', 502))).toBe('server');
  });

  it('5xx — не «нет связи»', () => {
    expect(isConnectivity(new NetError('server', 500))).toBe(false);
    expect(isConnectivity(new NetError('timeout'))).toBe(true);
  });
});

describe('errorText', () => {
  it('вместо «Failed to fetch» — что случилось и что делать', () => {
    expect(errorText(new TypeError('Failed to fetch'), 'x')).toBe(NET_TEXT.offline);
  });

  it('текст сервера остаётся как есть', () => {
    expect(errorText(new Error('Карта не найдена.'), 'x')).toBe('Карта не найдена.');
  });

  it('без текста — запасной', () => {
    expect(errorText(null, 'Не удалось.')).toBe('Не удалось.');
  });

  it('каждый сетевой текст говорит, что делать', () => {
    expect(NET_TEXT.offline).toMatch(/покажем/i);
    expect(NET_TEXT.timeout).toMatch(/повтор/i);
    expect(NET_TEXT.server).toMatch(/попробуй/i);
  });
});

describe('isNetworkNoise — фильтр Sentry', () => {
  it('нет сети и таймаут — шум', () => {
    expect(isNetworkNoise({}, { originalException: new TypeError('Failed to fetch') })).toBe(true);
    expect(isNetworkNoise({}, { originalException: new NetError('timeout') })).toBe(true);
  });

  it('по событию без исходного исключения — тоже', () => {
    const ev = { exception: { values: [{ type: 'TypeError', value: 'Failed to fetch' }] } };
    expect(isNetworkNoise(ev, {})).toBe(true);
  });

  it('5xx и настоящая поломка — уходят', () => {
    expect(isNetworkNoise({}, { originalException: new NetError('server', 500) })).toBe(false);
    const bug = new TypeError("Cannot read properties of null (reading 'at')");
    expect(isNetworkNoise({ exception: { values: [{ type: 'TypeError', value: bug.message }] } }, { originalException: bug })).toBe(false);
  });
});

describe('действия — свой текст', () => {
  it('без сети запись не обещает «покажем», а просит повторить', () => {
    expect(new NetError('offline', undefined, { write: true }).message).toMatch(/попробуй ещё раз/);
    expect(new NetError('offline', undefined, { write: true }).message).not.toMatch(/покажем/i);
  });

  it('humanizeErrorText: «Failed to fetch» из useAuth — по-человечески', async () => {
    const { humanizeErrorText, NET_WRITE_TEXT } = await import('./netError');
    expect(humanizeErrorText('Failed to fetch')).toBe(NET_WRITE_TEXT.offline);
    expect(humanizeErrorText('Неверный email или пароль')).toBe('Неверный email или пароль');
  });

  it('регистрация без сети — не «Failed to fetch»', async () => {
    const { describeSendCodeError, describeVerifyError } = await import('./registerRules');
    const err = new TypeError('Failed to fetch');
    expect(describeSendCodeError(err).text).toMatch(/Нет сети/);
    expect(describeVerifyError(err).text).toMatch(/Нет сети/);
  });
});
