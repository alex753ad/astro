/**
 * MoreNotificationsView.jsx — «Уведомления» (SPEC_MORE_SCREEN.md §7).
 *
 * Экран сводит ДВА разных механизма, и их не надо путать:
 *
 * 1. **Тумблер «Уведомления на этом устройстве»** — локальные уведомления
 *    Android (`@capacitor/local-notifications`). Их планирует само приложение
 *    из выдачи `GET /push/upcoming`, поэтому они работают и без сети в момент
 *    показа. Только в приложении; в вебе этого тумблера нет вовсе.
 * 2. **Тумблеры видов событий, время и тихие часы** — НАСТРОЙКИ НА СЕРВЕРЕ
 *    (`/push/settings`), общие с сайтом. Они определяют, что попадёт в выдачу,
 *    то есть управляют обоими механизмами сразу — и веб-пушами, и локальными
 *    уведомлениями.
 *
 * ⚠️ Поэтому серверные настройки БОЛЬШЕ НЕ СПРЯТАНЫ за проверкой Web Push.
 * До 13.09.2026 весь экран закрывался условием «есть serviceWorker +
 * PushManager + Notification», и в Android WebView, где PushManager может
 * отсутствовать, человек видел бы «недоступно» — включая настройки, от Web
 * Push никак не зависящие. Проверка осталась ровно там, где она про дело: в
 * подписи о том, куда приходят уведомления в вебе.
 */

import React, { useCallback, useEffect, useState } from 'react';
import MoreCenteredNotice from './MoreCenteredNotice';
import MoreDeviceChannel from './MoreDeviceChannel';
import { DEVICE_PUSH_SUPPORTED } from '../lib/devicePush';
import MoreSwitch from './MoreSwitch';
import { fetchPushSettings, updatePushSettings } from '../lib/moreApi';
import { syncLocalNotifications } from '../lib/localNotificationsSync';

const PUSH_SUPPORTED =
  typeof navigator !== 'undefined' &&
  'serviceWorker' in navigator &&
  typeof window !== 'undefined' &&
  'PushManager' in window &&
  'Notification' in window;

const TOGGLES = [
  { key: 'daily_forecast', label: 'Прогноз дня' },
  { key: 'planner', label: 'Планер' },
  { key: 'key_transits', label: 'Важные транзиты' },
  { key: 'moon_phases', label: 'Фазы Луны' },
];

function ToggleRow({ label, hint, on, onToggle }) {
  return (
    <button
      type="button"
      onClick={onToggle}
      style={{
        width: '100%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 12,
        padding: '13px 15px',
        background: 'var(--bg-card)',
        border: '1px solid var(--border)',
        borderRadius: 14,
        color: 'var(--text-primary)',
        fontFamily: 'var(--font-body)',
        fontSize: 14.5,
        textAlign: 'left',
      }}
    >
      <span>
        {label}
        {hint ? (
          <span style={{ display: 'block', fontSize: 12, color: 'var(--text-secondary)', marginTop: 2 }}>
            {hint}
          </span>
        ) : null}
      </span>
      <MoreSwitch on={on} />
    </button>
  );
}

/**
 * ⚠️ Тумблер устройства и экран-предисловие ЖИЛИ ЗДЕСЬ до слияния с FCM.
 *
 * Обе ветки добавляли на этот экран тумблер одного смысла: `local-notifications`
 * — «планировать локальные уведомления», `fcm-push` — «зарегистрировать
 * устройство для серверных пушей». Два тумблера про одно и то же на одном
 * экране — дефект независимо от того, как они устроены внутри, поэтому остался
 * ОДИН, в `MoreDeviceChannel.jsx`, и он же решает, каким каналом пользоваться.
 *
 * Здесь не осталось ничего про устройство намеренно: этот файл — про серверные
 * настройки, общие с сайтом.
 */

export default function MoreNotificationsView() {
  const [status, setStatus] = useState('loading');
  const [settings, setSettings] = useState(null);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setStatus('loading');
    setError('');
    try {
      setSettings(await fetchPushSettings());
      setStatus('ready');
    } catch (err) {
      setError(err?.message || 'Не удалось загрузить настройки уведомлений.');
      setStatus('error');
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // ⚠️ Серверные настройки больше НЕ спрятаны за проверкой Web Push.
  // Виды событий, время и тихие часы живут на сервере и от `PushManager`
  // не зависят вовсе — больше того, именно они определяют, что уйдёт в
  // мобильный пуш. В Android WebView, где `PushManager` может отсутствовать,
  // прежнее условие показывало «недоступно» на экране, который работает,
  // и заодно прятало тумблер канала доставки.
  if (!PUSH_SUPPORTED && !DEVICE_PUSH_SUPPORTED) {
    return <MoreCenteredNotice title="Push-уведомления недоступны на этом устройстве" />;
  }

  if (status === 'loading') {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, paddingTop: 8 }}>
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="mobile-skeleton" style={{ height: 48, borderRadius: 14, background: 'var(--bg-deeper)' }} />
        ))}
      </div>
    );
  }

  if (status === 'error') {
    return <MoreCenteredNotice title="Не удалось загрузить" text={error} action="Повторить" onAction={load} />;
  }

  const toggle = async (key) => {
    const next = { ...settings, [key]: !settings[key] };
    setSettings(next); // оптимистично — своя ошибка не должна откатывать весь экран в скелет
    try {
      await updatePushSettings({ [key]: next[key] });
      // Состав уведомлений изменился — план на устройстве обязан пересобраться
      // сразу, а не при следующем заходе: иначе выключенный вид событий ещё
      // неделю приходил бы по уже поставленному плану.
      syncLocalNotifications();
    } catch {
      setSettings(settings); // откат конкретного тумблера при неудаче
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, paddingTop: 8 }}>
      <MoreDeviceChannel />
      {TOGGLES.map(({ key, label }) => (
        <ToggleRow key={key} label={label} on={settings[key]} onToggle={() => toggle(key)} />
      ))}
      <p style={{ margin: '4px 0 0', fontSize: 12, color: 'var(--text-secondary)' }}>
        Уведомления приходят с {settings.daily_time} до {settings.quiet_from || '22:00'}
      </p>
      {/* Строка «Настройки общие с сайтом — уведомления приходят туда» стояла
          здесь с 10.09.2026 как честная подпись к тумблерам, которые на
          устройстве ничего не включали. Теперь включают: тумблер выше
          регистрирует устройство, и уведомления приходят сюда. Строка стала бы
          неправдой, поэтому убрана вместе с появлением канала. */}
    </div>
  );
}
