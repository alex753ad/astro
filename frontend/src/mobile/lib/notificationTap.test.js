/**
 * notificationTap.test.js — разбор target из нажатия на уведомление.
 * Сами слушатели Capacitor проверяются только на устройстве.
 */
import { describe, expect, it } from 'vitest';
import { targetOfAction } from './notificationTap';

describe('targetOfAction', () => {
  it('FCM: target лежит в data', () => {
    expect(targetOfAction({ notification: { data: { target: 'feed_today', url: '/chart/1' } } }))
      .toBe('feed_today');
  });

  it('вечернее «прогноз на завтра» — свой target', () => {
    expect(targetOfAction({ notification: { data: { target: 'feed_tomorrow' } } })).toBe('feed_tomorrow');
    expect(targetOfAction({ notification: { extra: { target: 'feed_tomorrow' } } })).toBe('feed_tomorrow');
  });

  it('локальное: target лежит в extra', () => {
    expect(targetOfAction({ notification: { extra: { target: 'feed_today' } } })).toBe('feed_today');
  });

  it('без target — никуда не ведём (просто открыть приложение)', () => {
    expect(targetOfAction({ notification: { data: { target: '', url: '/planner' } } })).toBeNull();
    expect(targetOfAction({ notification: { extra: {} } })).toBeNull();
    expect(targetOfAction(undefined)).toBeNull();
  });

  it('url веба за target не принимается', () => {
    expect(targetOfAction({ notification: { data: { url: '/chart/1?topic=daily' } } })).toBeNull();
  });

  it('незнакомый target не исполняется', () => {
    expect(targetOfAction({ notification: { data: { target: 'something_else' } } })).toBeNull();
  });
});
